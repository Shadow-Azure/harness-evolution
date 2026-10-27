"""Probe hit preview and launch request rules for the wizard."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator

from app.db.crud.probe_query import ProbeHitQuery, ProbeHitRow, ProbeQueryRepository
from app.errors import AppError, ErrorCode
from app.service.identity.schemas import IdentityModel


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

    id: str
    object_type: str
    object_name: str
    default_ref: str
    repo_url: str
    sub_dir: str
    enabled: bool


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


def _attribute_of(row: ProbeHitRow) -> Literal["model", "prompt", "error", "non_issue"] | None:
    """Map one hit row to its distribution key, ignoring foreign values."""
    if row.analysis_status == "analyzed_nonissue":
        return "non_issue"
    if row.analysis_status != "analyzed_issue" or row.probe_id is None:
        return None
    if row.attribute_type in ("model", "prompt", "error"):
        return row.attribute_type  # type: ignore[return-value]
    return None


def _item_of(rows: list[ProbeHitRow]) -> ProbePreviewItem | None:
    """Merge one probe's hit rows into a single preview item."""
    probes = [row for row in rows if row.probe_id is not None]
    if not probes:
        return None
    first = probes[0]
    attribute = _attribute_of(first)
    if attribute is None or attribute == "non_issue":
        return None
    return ProbePreviewItem(
        probe_id=first.probe_id or "",
        session_id=first.probe_session_id or first.bad_case_id,
        session_title=first.session_title,
        model=first.case_agent_model or first.session_model,
        probe_type=first.probe_type or "",
        probe_object=first.probe_object or "",
        object_version=first.object_version,
        attribute_type=attribute,
        description=first.probe_description or "",
        source_bad_case_ids=[row.bad_case_id for row in rows if row.probe_id is not None],
    )


class ProbeQueryService:
    """Project the wizard condition into hit statistics and probe rows."""

    def __init__(self, repository: ProbeQueryRepository) -> None:
        """Bind the service to its read-only hit repository."""
        self._repository = repository

    async def preview(
        self,
        body: ProbeQueryRequest,
        *,
        default_version: str | None = None,
    ) -> ProbeQueryResult:
        """Return hit statistics plus one page of analyzed probe rows.

        Args:
            body: Validated wizard condition.
            default_version: Version used when the request carries none.

        Returns:
            Backend-computed summary, paged items, and paging echo.

        Raises:
            AppError: With `NO_PROBES_MATCHED` when no analyzed probe hits.
        """
        query = normalized_query(body, default_version=default_version)
        rows = await self._repository.list_hit_rows(query)

        grouped: OrderedDict[str, list[ProbeHitRow]] = OrderedDict()
        for row in rows:
            grouped.setdefault(row.probe_id or row.bad_case_id, []).append(row)

        items: list[ProbePreviewItem] = []
        distribution = AttributeStats()
        analyzed = 0
        unanalyzed = 0
        for group in grouped.values():
            for row in group:
                if row.analysis_status == "unanalyzed" or row.analysis_status is None:
                    unanalyzed += 1
                elif row.analysis_status.startswith("analyzed"):
                    analyzed += 1
                attribute = _attribute_of(row)
                if attribute is not None:
                    setattr(distribution, attribute, getattr(distribution, attribute) + 1)
            item = _item_of(group)
            if item is not None:
                items.append(item)
        sessions = {
            row.probe_session_id
            for row in rows
            if row.probe_id is not None and row.probe_session_id is not None
        }

        probes = len(items)
        if probes == 0:
            raise AppError(
                status_code=409,
                code=ErrorCode.NO_PROBES_MATCHED,
                message="no analyzed probe matches the wizard condition",
            )
        total = len(items)
        start = (body.page - 1) * body.page_size
        return ProbeQueryResult(
            summary=ProbeHitSummary(
                sessions=len(sessions),
                bad_cases=len({row.bad_case_id for row in rows}),
                analyzed=analyzed,
                unanalyzed=unanalyzed,
                probes=probes,
                used_probes=probes,
                by_attribute_type=distribution,
            ),
            items=items[start : start + body.page_size],
            total=total,
            page=body.page,
            page_size=body.page_size,
        )
