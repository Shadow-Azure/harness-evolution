"""Probe hit preview and launch request rules for the wizard."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator

from app.db.crud.probe_query import ProbeHitQuery, ProbeHitRow, ProbeQueryRepository
from app.errors import AppError, ErrorCode
from app.service.identity.schemas import IdentityModel

_ATTRIBUTE_TYPES: tuple[Literal["model", "prompt", "error"], ...] = (
    "model",
    "prompt",
    "error",
)


class AttributeStats(IdentityModel):
    """Probe counts by attribution type shown in the wizard distribution bar."""

    model: int = 0
    prompt: int = 0
    error: int = 0
    non_issue: int = 0


class ProbeQueryRequest(IdentityModel):
    """Wizard filter condition shared by preview and launch endpoints."""

    target_type: Literal["skill", "agent"]
    target_name: str = Field(min_length=1, max_length=128)
    target_version: str | None = Field(default=None, max_length=64)
    window_from: date | None = Field(default=None, alias="from")
    window_to: date | None = Field(default=None, alias="to")
    models: list[str] = Field(default_factory=list)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=8, ge=1, le=50)
    mode: Literal["full", "cluster_only"] = "full"
    engine_key: str | None = Field(default=None, max_length=64)
    eval: dict[str, Any] | None = None

    @field_validator("models")
    @classmethod
    def _strip_models(cls, value: list[str]) -> list[str]:
        """Drop empty model chips so the query falls back to every model."""
        return [model for model in value if model.strip()]

    @field_validator("target_version")
    @classmethod
    def _strip_version(cls, value: str | None) -> str | None:
        """Normalize an optional explicit version chip."""
        return value.strip() if isinstance(value, str) and value.strip() else None


class ProbeHitSummary(IdentityModel):
    """Hit statistics shown by wizard step 2 before the probe table."""

    sessions: int
    bad_cases: int
    analyzed: int
    unanalyzed: int
    probes: int
    used_probes: int
    by_attribute_type: AttributeStats


class ProbePreviewItem(IdentityModel):
    """One analyzed probe row rendered by wizard step 2."""

    probe_id: str
    session_id: str
    session_title: str | None
    model: str | None
    probe_type: str
    probe_object: str
    object_version: str | None
    attribute_type: Literal["model", "prompt", "error"]
    description: str
    source_bad_case_ids: list[str]


class ProbeQueryResult(IdentityModel):
    """Complete preview payload for wizard step 2."""

    summary: ProbeHitSummary
    items: list[ProbePreviewItem]
    total: int
    page: int
    page_size: int


class RunAccepted(IdentityModel):
    """Asynchronous acceptance returned by both launch endpoints."""

    run_id: str
    job_id: str
    status: Literal["preparing"]


class TargetConfigRecord(Protocol):
    """Minimal enabled-target facts consumed from configuration storage."""

    @property
    def id(self) -> str:
        """Return the configured target id."""

    @property
    def object_type(self) -> str:
        """Return the configured object type."""

    @property
    def object_name(self) -> str:
        """Return the configured object name."""

    @property
    def default_ref(self) -> str:
        """Return the configured default reference."""

    @property
    def repo_url(self) -> str:
        """Return the configured git remote."""

    @property
    def sub_dir(self) -> str:
        """Return the configured repository sub directory."""

    @property
    def enabled(self) -> bool:
        """Return whether the target accepts launches."""


class TargetConfigStore(Protocol):
    """Persistence operations consumed by the launch service."""

    async def find(self, object_type: str, object_name: str) -> TargetConfigRecord | None:
        """Return one configured object pair."""
        ...


def normalized_query(
    body: ProbeQueryRequest,
    *,
    default_version: str | None = None,
) -> ProbeHitQuery:
    """Resolve the wizard condition into its repository form.

    Args:
        body: Validated wizard condition.
        default_version: Version used when the request carries none.

    Returns:
        Repository query with a non-null resolved version.
    """
    version = body.target_version or default_version
    if not version:
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_INVALID,
            message="target version is required",
        )
    if (
        body.window_from is not None
        and body.window_to is not None
        and body.window_from > body.window_to
    ):
        raise AppError(
            status_code=422,
            code=ErrorCode.VALIDATION_INVALID,
            message="time window is inverted",
        )
    return ProbeHitQuery(
        target_type=body.target_type,
        target_name=body.target_name,
        target_version=version,
        window_from=body.window_from,
        window_to=body.window_to,
        models=tuple(body.models),
    )


def _attribute_of(row: ProbeHitRow) -> Literal["model", "prompt", "error"] | None:
    """Map one probe row to its distribution key, ignoring foreign values."""
    if row.attribute_type in _ATTRIBUTE_TYPES:
        return row.attribute_type
    return None


def _item_of(rows: list[ProbeHitRow]) -> ProbePreviewItem | None:
    """Render one hit probe with its distinct linked bad cases."""
    first = rows[0]
    attribute = _attribute_of(first)
    if attribute is None:
        return None
    source_bad_case_ids = list(dict.fromkeys(row.bad_case_id for row in rows))
    return ProbePreviewItem(
        probe_id=first.probe_id,
        session_id=first.probe_session_id,
        session_title=first.session_title,
        model=first.case_agent_model or first.session_model,
        probe_type=first.probe_type,
        probe_object=first.probe_object,
        object_version=first.object_version,
        attribute_type=attribute,
        description=first.probe_description,
        source_bad_case_ids=source_bad_case_ids,
    )


class ProbeQueryService:
    """Project the wizard condition into hit statistics and probe rows."""

    def __init__(
        self,
        repository: ProbeQueryRepository,
        targets: TargetConfigStore,
    ) -> None:
        """Bind the service to its read repository and target configuration."""
        self._repository = repository
        self._targets = targets

    async def preview(self, body: ProbeQueryRequest) -> ProbeQueryResult:
        """Return hit statistics plus one page of matched probe rows.

        Args:
            body: Validated wizard condition.

        Returns:
            Backend-computed summary, paged items, and paging echo.

        Raises:
            AppError: With `TARGET_NOT_CONFIGURED` when the target is missing or
                disabled, and `NO_PROBES_MATCHED` when the probe count is zero.
        """
        config = await self._targets.find(body.target_type, body.target_name)
        if config is None or not config.enabled:
            raise AppError(
                status_code=409,
                code=ErrorCode.TARGET_NOT_CONFIGURED,
                message="target is not configured or enabled",
            )
        query = normalized_query(body, default_version=config.default_ref)
        rows = await self._repository.list_hit_rows(query)

        grouped: OrderedDict[str, list[ProbeHitRow]] = OrderedDict()
        for row in rows:
            grouped.setdefault(row.probe_id, []).append(row)

        items: list[ProbePreviewItem] = []
        distribution = AttributeStats()
        for group in grouped.values():
            item = _item_of(group)
            if item is None:
                continue
            items.append(item)
            setattr(
                distribution,
                item.attribute_type,
                getattr(distribution, item.attribute_type) + 1,
            )

        probes = len(items)
        if probes == 0:
            raise AppError(
                status_code=409,
                code=ErrorCode.NO_PROBES_MATCHED,
                message="no analyzed probe matches the wizard condition",
            )
        bad_cases = {row.bad_case_id for row in rows}
        analyzed = {row.bad_case_id for row in rows if row.analysis_status == "analyzed_issue"}
        sessions = {row.probe_session_id for row in rows}
        total = probes
        start = (body.page - 1) * body.page_size
        return ProbeQueryResult(
            summary=ProbeHitSummary(
                sessions=len(sessions),
                bad_cases=len(bad_cases),
                analyzed=len(analyzed),
                unanalyzed=0,
                probes=probes,
                used_probes=probes,
                by_attribute_type=distribution,
            ),
            items=items[start : start + body.page_size],
            total=total,
            page=body.page,
            page_size=body.page_size,
        )
