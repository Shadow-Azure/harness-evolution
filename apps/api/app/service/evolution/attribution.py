"""Object-revision attribution: pure rule engine, cache, and runner.

The engine is a pure function of the bad case, its trigger coordinates, and the
knowledge evidence gathered in the same Session. ``AttributionRunner`` owns the
cache reads, dialect upserts, reuse accounting, and run-candidate pointers.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from app.db.crud.attributions import (
    BadCaseEvidenceRecord,
    KnowledgeEvidenceRecord,
    ProbeCacheRecord,
    ProbeWrite,
)
from app.db.models.evolution import EvolutionRunRecord
from app.service.evolution.attribution_contracts import (
    REPORT_SCHEMA_VERSION,
    AttributionAnalysis,
    AttributionConclusion,
    AttributionEvidence,
    AttributionExecutionManifest,
    AttributionPoint,
    AttributionReportV2,
    AttributionTargetRef,
    default_execution_manifest,
)
from app.service.evolution.engine.contracts import ConfigError, RunBlocked
from app.service.evolution.potential import (
    POLICY_VERSION,
    HitReason,
    OrderState,
    PotentialCase,
    resolve_target_revision,
)
from app.utils.ids import new_id
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)

AttributionCategory = Literal["model", "prompt", "error"]
AttributionEngineKey = str

DEFAULT_ATTRIBUTION_ENGINE = "rule-v1"


class AttributionEngine(Protocol):
    """Pure attribution engine; it never reads or writes the database."""

    key: AttributionEngineKey

    async def attribute(self, item: AttributionInput) -> AttributionResult:
        """Return one revision-scoped conclusion for the supplied evidence."""


@dataclass(frozen=True, slots=True)
class KnowledgeEvidence:
    """One knowledge document trigger visible to the attribution engine."""

    document_id: str | None = None
    document_revision: str | None = None
    source_path: str | None = None
    retrieval_kind: str | None = None


@dataclass(frozen=True, slots=True)
class AttributionInput:
    """Everything one engine may use; constructed by the runner, never by the engine."""

    bad_case_id: str
    workspace_id: str
    session_id: str
    probe_type: str
    probe_object: str
    object_version: str | None
    policy_version: str
    attribution_engine: str
    bad_case_type: str
    title: str
    description: str
    hit_reason: HitReason
    order_state: OrderState
    attribution_skill_key: str | None = None
    attribution_skill_revision: str | None = None
    attribution_skill_content_hash: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    object_trigger_at: datetime | None = None
    case_trigger_at: datetime | None = None
    knowledge_evidence: tuple[KnowledgeEvidence, ...] = ()

    @property
    def cache_key(self) -> str:
        """Return the canonical execution-manifest hash for this input."""
        return self.execution_manifest.content_hash

    @property
    def execution_manifest(self) -> AttributionExecutionManifest:
        """Resolve the current built-in engine into an immutable V2 manifest."""
        return default_execution_manifest(
            workspace_id=self.workspace_id,
            bad_case_id=self.bad_case_id,
            target_type=self.probe_type,  # type: ignore[arg-type]
            target_name=self.probe_object,
            target_version=self.object_version,
            policy_version=self.policy_version,
            engine=self.attribution_engine,
            session_id=self.session_id,
            hit_reason=self.hit_reason,
            order_state=self.order_state,
            object_trigger_at=self.object_trigger_at,
            case_trigger_at=self.case_trigger_at,
            skill_key=self.attribution_skill_key,
            skill_revision=self.attribution_skill_revision,
            skill_content_hash=self.attribution_skill_content_hash,
        )


@dataclass(frozen=True, slots=True)
class AttributionResult:
    """One pure conclusion ready for the runner to persist."""

    conclusion: AttributionConclusion
    category: AttributionCategory | None
    confidence: float
    reason: str
    reasoning: str

    def __post_init__(self) -> None:
        """Reject conclusions that cannot satisfy the table's closed sets."""
        if self.conclusion not in {"attributed", "non_target", "inconclusive"}:
            raise ValueError(f"unknown attribution conclusion: {self.conclusion}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within [0, 1]: {self.confidence}")
        if self.conclusion in {"non_target", "inconclusive"}:
            if self.category is not None:
                raise ValueError(f"{self.conclusion} attributions must not carry a category")
            return
        if self.category not in {"model", "prompt", "error"}:
            raise ValueError("attributed conclusions require category model, prompt, or error")


class RuleBasedEngine:
    """First V2 attribution engine; deterministic, template-based, and cacheable."""

    key: AttributionEngineKey = DEFAULT_ATTRIBUTION_ENGINE

    async def attribute(self, item: AttributionInput) -> AttributionResult:
        """Classify one case using the policy hit reason and persisted evidence."""
        self_match = item.hit_reason in {"self_report", "both"}
        if self_match:
            if not (item.title.strip() or item.description.strip()):
                return self._inconclusive(item, "证据不足")
            error = _error_evidence(item.metadata)
            category: AttributionCategory = "error" if error is not None else "prompt"
            evidence = (
                f"错误证据：{error}"  # noqa: RUF001
                if error is not None
                else "未发现错误证据，按 prompt 归类"  # noqa: RUF001
            )
            return self._attributed(
                item,
                category=category,
                confidence=0.8,
                reason=f"对象自身上报：{_headline(item)}；{evidence}",  # noqa: RUF001
                lead="对象自身上报",
            )
        if (
            item.hit_reason == "after_object"
            and item.bad_case_type == "discovery"
            and item.order_state == "comparable"
        ):
            return self._attributed(
                item,
                category="error",
                confidence=0.6,
                reason=f"对象进入点之后发现：{_headline(item)}；按 error 归类",  # noqa: RUF001
                lead="bad case 触发点严格晚于对象进入点",
            )
        return self._inconclusive(
            item,
            "顺序不可比或证据不足",
        )

    def _attributed(
        self,
        item: AttributionInput,
        *,
        category: AttributionCategory,
        confidence: float,
        reason: str,
        lead: str,
    ) -> AttributionResult:
        """Build one attributed conclusion with a stable template."""
        lines = [
            f"1. 命中原因：{lead}（hitReason={item.hit_reason}，badCaseType={item.bad_case_type}）。",  # noqa: E501, RUF001
            (
                "2. 触发顺序："  # noqa: RUF001
                f"orderState={item.order_state}，"  # noqa: RUF001
                f"bad case 触发点={_instant(item.case_trigger_at)}，"  # noqa: RUF001
                f"对象进入点={_instant(item.object_trigger_at)}。"
            ),
            f"3. 分类依据：{reason}",  # noqa: RUF001
        ]
        lines.extend(_knowledge_lines(item.knowledge_evidence))
        lines.append(
            "4. 结论只作用于 "
            f"{item.probe_object}@{item.object_version}（{item.policy_version}/{item.attribution_engine}）。",  # noqa: RUF001
        )
        return AttributionResult(
            conclusion="attributed",
            category=category,
            confidence=confidence,
            reason=reason,
            reasoning="\n".join(lines),
        )

    def _non_target(self, item: AttributionInput, why: str) -> AttributionResult:
        """Build one visible non-target conclusion that never enters a cluster."""
        lines = [
            f"1. 命中原因：{item.hit_reason}；orderState={item.order_state}。",  # noqa: RUF001
            f"2. 未归到 {item.probe_object}@{item.object_version}：{why}。",  # noqa: RUF001
            "3. non_target 保留明细与 case 关联，但 attribute_type 为空，不进簇。",  # noqa: RUF001
        ]
        lines.extend(_knowledge_lines(item.knowledge_evidence))
        return AttributionResult(
            conclusion="non_target",
            category=None,
            confidence=0.7,
            reason=f"非该对象问题：{_headline(item)}；{why}",  # noqa: RUF001
            reasoning="\n".join(lines),
        )

    def _inconclusive(self, item: AttributionInput, why: str) -> AttributionResult:
        """Keep insufficient evidence distinct from a confident non-target result."""
        return AttributionResult(
            conclusion="inconclusive",
            category=None,
            confidence=0.0,
            reason=f"归因证据不足：{_headline(item)}；{why}",  # noqa: RUF001
            reasoning=(
                f"1. 命中原因：{item.hit_reason}；orderState={item.order_state}。\n"  # noqa: RUF001
                f"2. 当前证据不足以判断是否归属于 {item.probe_object}@{item.object_version}。\n"
                "3. inconclusive 保留明细但不进入聚类。"
            ),
        )


def _headline(item: AttributionInput) -> str:
    """Pick a bounded one-line human summary from the reported evidence."""
    headline = item.title.strip() or item.description.strip()
    return headline[:200] if headline else "(无标题)"


def _instant(value: datetime | None) -> str:
    """Render one optional trigger instant deterministically."""
    return value.isoformat() if value is not None else "未知"


def _error_evidence(metadata: Mapping[str, object]) -> str | None:
    """Return the first concrete error signal in bad-case metadata, if any."""
    for key in ("error", "stderr", "stack"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:300]
    exit_code = metadata.get("exitCode")
    if isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0:
        return f"exitCode={exit_code}"
    if metadata.get("status") == "failed":
        return "status=failed"
    return None


def _knowledge_lines(evidence: Sequence[KnowledgeEvidence]) -> list[str]:
    """Render knowledge evidence without importing document bodies."""
    if not evidence:
        return ["- 知识库证据：未发现"]  # noqa: RUF001
    lines = ["- 知识库证据："]  # noqa: RUF001
    for item in evidence[:5]:
        parts = [item.source_path or "(无路径)"]
        if item.document_id is not None:
            parts.append(f"doc={item.document_id}")
        if item.document_revision is not None:
            parts.append(item.document_revision)
        if item.retrieval_kind is not None:
            parts.append(item.retrieval_kind)
        lines.append(f"  - {'；'.join(parts)}")  # noqa: RUF001
    return lines


def _report_payload(item: AttributionInput, result: AttributionResult) -> AttributionReportV2:
    """Project one engine result into the stable V2 report payload."""
    evidence = [
        AttributionEvidence(
            kind="bad_case",
            summary=_headline(item),
            reference=item.bad_case_id,
        ),
    ]
    evidence.extend(
        AttributionEvidence(
            kind="knowledge",
            summary=knowledge.source_path or "Knowledge document evidence",
            reference=knowledge.document_id,
        )
        for knowledge in item.knowledge_evidence
    )
    warnings = ["ATTRIBUTION_EVIDENCE_INSUFFICIENT"] if result.conclusion == "inconclusive" else []
    return AttributionReportV2(
        target=AttributionTargetRef(
            object_type=item.probe_type,  # type: ignore[arg-type]
            object_name=item.probe_object,
            object_version=item.object_version,
        ),
        conclusion=result.conclusion,
        category=result.category,
        introduction_point=AttributionPoint(
            occurred_at=item.object_trigger_at,
            label="object_entry",
        ),
        detection_point=AttributionPoint(
            occurred_at=item.case_trigger_at,
            label="bad_case_report",
        ),
        evidence=evidence,
        analysis=AttributionAnalysis(summary=result.reason, reasoning=result.reasoning),
        warnings=warnings,
    )


_ENGINE_FACTORIES: dict[str, Callable[[], AttributionEngine]] = {
    DEFAULT_ATTRIBUTION_ENGINE: RuleBasedEngine,
}


def registered_engine_keys() -> tuple[str, ...]:
    """Return the explicitly registered engine identities."""
    return tuple(_ENGINE_FACTORIES)


def resolve_attribution_engine(key: AttributionEngineKey) -> AttributionEngine:
    """Resolve one registered engine or fail fast before any probe write."""
    factory = _ENGINE_FACTORIES.get(key)
    if factory is None:
        raise ConfigError(f"unknown attribution engine: {key}")
    return factory()


@dataclass(frozen=True, slots=True)
class AttributionRunSummary:
    """Counts the attribution step can publish without replaying its inputs."""

    processed: int
    created: int
    reused: int
    non_target: int
    skipped: int


EngineFactory = Callable[[AttributionEngineKey], AttributionEngine]


class AttributionStore(Protocol):
    """Persistence operations consumed by the runner."""

    async def linked_probe_ids(self, run_id: str) -> dict[str, str]:
        """Return candidates that already have a persisted probe pointer."""

    async def load_bad_case_evidence(
        self,
        case_ids: Sequence[str],
    ) -> dict[str, BadCaseEvidenceRecord]:
        """Batch-load bad-case titles, descriptions, and metadata."""

    async def load_knowledge_evidence(
        self,
        session_ids: Sequence[str],
    ) -> dict[str, tuple[KnowledgeEvidenceRecord, ...]]:
        """Batch-load knowledge document triggers per root session."""

    async def get_probe_by_cache_key(self, cache_key: str) -> ProbeCacheRecord | None:
        """Return the cached probe for one seven-part identity."""

    async def reuse_probe_and_link(
        self,
        probe_id: str,
        run_id: str,
        bad_case_id: str,
        now: datetime,
    ) -> bool:
        """Count one cache hit and link the candidate."""

    async def write_probe_and_link(
        self,
        write: ProbeWrite,
        run_id: str,
        now: datetime,
    ) -> str:
        """Persist a fresh probe, its link, and its candidate pointer."""


class AttributionRunner:
    """Apply the configured engine to included candidates with cache semantics."""

    def __init__(
        self,
        store: AttributionStore,
        *,
        engine_factory: EngineFactory = resolve_attribution_engine,
        now: Callable[[], datetime] = now_shanghai,
    ) -> None:
        """Bind persistence, engine resolution, and the injectable clock."""
        self._store = store
        self._engine_factory = engine_factory
        self._now = now

    async def run(
        self,
        run: EvolutionRunRecord,
        candidates: Sequence[PotentialCase],
        cache_enabled: bool,
    ) -> AttributionRunSummary:
        """Attribute included candidates and return exact reuse/creation counts.

        Already-linked candidates are skipped so a retried step only fills the
        missing tail. A cache hit reuses the existing probe id, advances the
        reuse counter at most once per run, and never calls the engine.

        Args:
            run: Run snapshot providing workspace, target, and engine identity.
            candidates: Matcher output; excluded candidates are ignored.
            cache_enabled: Whether existing cache keys may be reused.

        Returns:
            Created, reused, non-target, and skipped counts for this invocation.

        Raises:
            RunBlocked: With ``stage="attribution"`` when the engine or a write
                fails; rows written before the failure remain durable.
        """
        engine = self._engine_factory(run.attribution_engine)
        if engine.key != run.attribution_engine:
            raise ConfigError(
                f"attribution engine {engine.key} does not match run {run.attribution_engine}",
            )
        included = tuple(candidate for candidate in candidates if candidate.included)
        if not included:
            return AttributionRunSummary(processed=0, created=0, reused=0, non_target=0, skipped=0)

        try:
            linked = await self._store.linked_probe_ids(run.id)
        except Exception as exc:
            raise self._blocked(run.id, None, exc) from exc
        pending = tuple(candidate for candidate in included if candidate.bad_case_id not in linked)
        skipped = len(included) - len(pending)
        if not pending:
            return AttributionRunSummary(
                processed=0,
                created=0,
                reused=0,
                non_target=0,
                skipped=skipped,
            )

        case_ids = tuple(candidate.bad_case_id for candidate in pending)
        session_ids = tuple(dict.fromkeys(candidate.session_id for candidate in pending))
        try:
            bad_cases = await self._store.load_bad_case_evidence(case_ids)
            knowledge = await self._store.load_knowledge_evidence(session_ids)
        except Exception as exc:
            raise self._blocked(run.id, None, exc) from exc

        object_version = resolve_target_revision(run.target_version)[1]
        created = 0
        reused = 0
        non_target = 0
        for candidate in pending:
            try:
                item = self._build_input(
                    run,
                    candidate,
                    bad_cases,
                    knowledge,
                    object_version,
                )
                now = self._now()
                if cache_enabled:
                    cached = await self._store.get_probe_by_cache_key(item.cache_key)
                    if cached is not None:
                        await self._store.reuse_probe_and_link(
                            cached.probe_id,
                            run.id,
                            candidate.bad_case_id,
                            now,
                        )
                        reused += 1
                        if cached.conclusion == "non_target":
                            non_target += 1
                        continue
                result = await engine.attribute(item)
                manifest = item.execution_manifest
                report = _report_payload(item, result)
                await self._store.write_probe_and_link(
                    ProbeWrite(
                        probe_id=new_id(),
                        workspace_id=run.workspace_id,
                        session_id=candidate.session_id,
                        bad_case_id=candidate.bad_case_id,
                        probe_type=run.target_type,
                        probe_object=run.target_name,
                        object_version=object_version,
                        attribute_type=result.category,
                        conclusion=result.conclusion,
                        confidence=result.confidence,
                        probe_description=result.reason,
                        probe_analysis=result.reasoning,
                        policy_version=POLICY_VERSION,
                        attribution_engine=engine.key,
                        report_schema_version=REPORT_SCHEMA_VERSION,
                        report_payload=report.model_dump(mode="json", by_alias=True),
                        execution_manifest=manifest.model_dump(mode="json", by_alias=True),
                        execution_manifest_hash=manifest.content_hash,
                        created_run_id=run.id,
                        created_at=now,
                        updated_at=now,
                    ),
                    run.id,
                    now,
                )
            except RunBlocked:
                raise
            except (ConfigError, ValueError):
                raise
            except Exception as exc:
                raise self._blocked(run.id, candidate.bad_case_id, exc) from exc
            created += 1
            if result.conclusion == "non_target":
                non_target += 1

        return AttributionRunSummary(
            processed=len(pending),
            created=created,
            reused=reused,
            non_target=non_target,
            skipped=skipped,
        )

    def _build_input(
        self,
        run: EvolutionRunRecord,
        candidate: PotentialCase,
        bad_cases: Mapping[str, BadCaseEvidenceRecord],
        knowledge: Mapping[str, tuple[KnowledgeEvidenceRecord, ...]],
        object_version: str,
    ) -> AttributionInput:
        """Join one matcher row with its persisted bad-case and knowledge evidence."""
        evidence = bad_cases.get(candidate.bad_case_id)
        if evidence is None:
            raise LookupError(f"bad case evidence not found: {candidate.bad_case_id}")
        return AttributionInput(
            bad_case_id=candidate.bad_case_id,
            workspace_id=run.workspace_id,
            session_id=candidate.session_id,
            probe_type=run.target_type,
            probe_object=run.target_name,
            object_version=object_version,
            policy_version=POLICY_VERSION,
            attribution_engine=run.attribution_engine,
            attribution_skill_key=run.attribution_skill_key,
            attribution_skill_revision=(
                str(run.attribution_skill_revision)
                if run.attribution_skill_revision is not None
                else None
            ),
            attribution_skill_content_hash=run.attribution_skill_content_hash,
            bad_case_type=candidate.bad_case_type,
            title=evidence.title,
            description=evidence.description,
            metadata=evidence.metadata,
            hit_reason=candidate.hit_reason,
            order_state=candidate.order_state,
            object_trigger_at=candidate.object_trigger.triggered_at,
            case_trigger_at=(
                candidate.case_trigger.triggered_at if candidate.case_trigger is not None else None
            ),
            knowledge_evidence=tuple(
                KnowledgeEvidence(
                    document_id=item.document_id,
                    document_revision=item.document_revision,
                    source_path=item.source_path,
                    retrieval_kind=item.retrieval_kind,
                )
                for item in knowledge.get(candidate.session_id, ())
            ),
        )

    def _blocked(
        self,
        run_id: str,
        bad_case_id: str | None,
        exc: BaseException,
    ) -> RunBlocked:
        """Convert an engine or storage failure into a retryable blocked stage."""
        logger.exception(
            "attribution step failed",
            extra={"run_id": run_id, "bad_case_id": bad_case_id},
        )
        return RunBlocked(
            "attribution failed",
            stage="attribution",
            error_stage="prepare",
            retryable=True,
        )


__all__ = [
    "DEFAULT_ATTRIBUTION_ENGINE",
    "AttributionEngine",
    "AttributionInput",
    "AttributionResult",
    "AttributionRunSummary",
    "AttributionRunner",
    "KnowledgeEvidence",
    "RuleBasedEngine",
    "registered_engine_keys",
    "resolve_attribution_engine",
]
