"""Object-revision attribution: pure rule engine, cache, and runner.

The engine is a pure function of the bad case, its trigger coordinates, and the
knowledge evidence gathered in the same Session; its case-level confidence is a
deterministic evidence-completeness score, never a model call. ``AttributionRunner``
owns the cache reads, dialect upserts, reuse accounting, and run-candidate
pointers.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any, Literal, Protocol

from app.db.crud.attributions import (
    BadCaseEvidenceRecord,
    KnowledgeEvidenceRecord,
    ProbeCacheRecord,
    ProbeWrite,
    attribution_cache_key,
)
from app.db.models.evolution import EvolutionRunRecord
from app.service.evolution.attribution_confidence import (
    EvidenceSignals,
    attribution_confidence,
    extract_signals,
)
from app.service.evolution.attribution_context import (
    AttributionCaseContext,
    AttributionContextProvider,
)
from app.service.evolution.attribution_contracts import (
    REPORT_SCHEMA_VERSION,
    AttributionAnalysis,
    AttributionConclusion,
    AttributionEvidence,
    AttributionExecutionManifest,
    AttributionPoint,
    AttributionReportV2,
    AttributionTargetRef,
    canonical_json_hash,
    default_execution_manifest,
)
from app.service.evolution.attribution_executor import (
    AGENT_SKILL_STUB_ENGINE,
    AttributionExecutorBadCase,
    AttributionExecutorContext,
    AttributionExecutorRequest,
    AttributionExecutorSkill,
    AttributionExecutorTarget,
    resolve_attribution_executor,
)
from app.service.evolution.candidate_policy import CandidatePolicy, policy_version
from app.service.evolution.control import PauseAtCheckpoint
from app.service.evolution.engine.contracts import ConfigError, RunBlocked
from app.service.evolution.potential import (
    HitReason,
    OrderState,
    PotentialCase,
)
from app.service.evolution.target_content import GitDefinitionRef, resolve_legacy_target_version
from app.utils.ids import new_id
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)

AttributionCategory = Literal["model", "prompt", "error", "flow", "context"]
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
    attribution_skill_executor_type: str | None = None
    attribution_skill_content: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)
    object_trigger_at: datetime | None = None
    case_trigger_at: datetime | None = None
    knowledge_evidence: tuple[KnowledgeEvidence, ...] = ()
    context: AttributionCaseContext | None = None
    run_id: str = ""
    repo_url: str = ""
    sub_dir: str = ""
    selected_version: str = ""
    source_commit: str | None = None
    report_source: str = ""
    local_input: Mapping[str, str] = field(default_factory=dict)
    definition: GitDefinitionRef | None = None
    local_input_hash: str | None = None
    batch_trigger: Literal["target_binding", "evolution_run"] = "evolution_run"
    candidate_policy: CandidatePolicy | None = None
    source_matches: tuple[dict[str, object], ...] = ()
    legacy_rule: bool = False
    case_object_name: str | None = None
    case_object_version: str | None = None

    def evidence_signals(self) -> EvidenceSignals:
        """Return the three deterministic evidence checks for this input."""
        return extract_signals(
            order_state=self.order_state,
            case_object_name=self.case_object_name,
            case_object_version=self.case_object_version,
            probe_object=self.probe_object,
            target_revision=self.object_version,
        )

    @property
    def definition_key(self) -> str:
        """Address a bound definition or the immutable Git selection of this Run."""
        if self.definition is not None:
            return self.definition.key
        parts = [self.probe_type, self.probe_object, self.object_version]
        if self.source_commit:
            parts.extend((self.repo_url, self.sub_dir, self.source_commit))
        return canonical_json_hash(parts)

    @property
    def cache_key(self) -> str:
        """Return the cache identity frozen for the selected attribution mode."""
        if self.legacy_rule:
            return attribution_cache_key(
                self.workspace_id,
                self.bad_case_id,
                self.probe_type,
                self.probe_object,
                self.object_version,
                self.policy_version,
                self.attribution_engine,
            )
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
            candidate_policy=self.candidate_policy,
            source_matches=self.source_matches,
            session_id=self.session_id,
            hit_reason=self.hit_reason,
            order_state=self.order_state,
            object_trigger_at=self.object_trigger_at,
            case_trigger_at=self.case_trigger_at,
            skill_key=self.attribution_skill_key,
            skill_revision=self.attribution_skill_revision,
            skill_content_hash=self.attribution_skill_content_hash,
            prepared_context_snapshot_hash=self.local_input_hash
            or (self.context.snapshot_hash if self.context is not None else None),
            model_fingerprint=(
                canonical_json_hash(
                    {
                        k: self.attribution_skill_content.get(k)
                        for k in ("agent", "llm", "model", "modelIdentity")
                    }
                )
                if self.attribution_skill_executor_type == "local_agent"
                else "none"
            ),
        )


@dataclass(frozen=True, slots=True)
class AttributionResult:
    """One pure conclusion ready for the runner to persist."""

    conclusion: AttributionConclusion
    category: AttributionCategory | None
    confidence: float
    reason: str
    reasoning: str
    evidence_references: tuple[str, ...] = ()
    suggestion_clues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    token_count: int = 0
    canonical_report: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Reject conclusions that cannot satisfy the table's closed sets."""
        if self.conclusion not in {"attributed", "non_target", "inconclusive"}:
            raise ValueError(f"unknown attribution conclusion: {self.conclusion}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be within [0, 1]: {self.confidence}")
        if self.token_count < 0:
            raise ValueError("token_count must be non-negative")
        if self.conclusion in {"non_target", "inconclusive"}:
            if self.category is not None:
                raise ValueError(f"{self.conclusion} attributions must not carry a category")
            return
        if self.category not in {"model", "prompt", "error", "flow", "context"}:
            raise ValueError("attributed conclusions require category model, prompt, or error")


class RuleBasedEngine:
    """First V2 attribution engine; deterministic, template-based, and cacheable."""

    key: AttributionEngineKey = DEFAULT_ATTRIBUTION_ENGINE

    async def attribute(self, item: AttributionInput) -> AttributionResult:
        """Classify one case using the policy hit reason and persisted evidence."""
        signals = item.evidence_signals()
        self_match = item.hit_reason in {"self_report", "both"}
        if self_match:
            if not (item.title.strip() or item.description.strip()):
                return self._insufficient(item, "证据不足", signals)
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
                signals=signals,
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
                signals=signals,
                reason=f"对象进入点之后发现：{_headline(item)}；按 error 归类",  # noqa: RUF001
                lead="bad case 触发点严格晚于对象进入点",
            )
        return self._insufficient(item, "顺序不可比或证据不足", signals)

    def _attributed(
        self,
        item: AttributionInput,
        *,
        category: AttributionCategory,
        signals: EvidenceSignals,
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
            confidence=attribution_confidence("attributed", signals),
            reason=reason,
            reasoning="\n".join(lines),
        )

    def _non_target(
        self,
        item: AttributionInput,
        why: str,
        signals: EvidenceSignals,
    ) -> AttributionResult:
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
            confidence=attribution_confidence("non_target", signals),
            reason=f"非该对象问题：{_headline(item)}；{why}",  # noqa: RUF001
            reasoning="\n".join(lines),
        )

    def _insufficient(
        self, item: AttributionInput, why: str, signals: EvidenceSignals
    ) -> AttributionResult:
        """Retain historical rule outcomes for unbound production targets."""
        if item.legacy_rule:
            return self._non_target(item, why, signals)
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


class AgentSkillStubEngine:
    """Adapt the versioned executor contract to the existing pure engine boundary."""

    key: AttributionEngineKey = AGENT_SKILL_STUB_ENGINE

    async def attribute(self, item: AttributionInput) -> AttributionResult:
        """Execute the offline Agent Skill stub and validate its structured output."""
        if item.attribution_skill_executor_type != "agent_stub":
            raise ValueError(
                "agent-skill-stub-v1 requires an agent_stub Skill revision",
            )
        if not (
            item.attribution_skill_key
            and item.attribution_skill_revision
            and item.attribution_skill_content_hash
        ):
            raise ValueError("agent attribution requires a frozen Skill revision")
        context = item.context
        bundle_payload = dict(context.bundle.to_payload()) if context is not None else None
        evidence_refs = [
            *(
                [context.report_ref]
                if context is not None and context.report_ref is not None
                else []
            ),
            *(context.path_agent_refs if context is not None else ()),
        ]
        introduction_ref = None
        if context is not None and context.bundle.object_occurrences:
            introduction_ref = context.bundle.object_occurrences[0].ref
            evidence_refs.insert(0, introduction_ref)
        output = await resolve_attribution_executor(self.key).execute(
            AttributionExecutorRequest(
                workspace_id=item.workspace_id,
                run_id=item.run_id,
                target=AttributionExecutorTarget(
                    object_type=item.probe_type,  # type: ignore[arg-type]
                    object_name=item.probe_object,
                    object_version=item.object_version,
                    introduction_ref=introduction_ref,
                    introduction_at=_instant_or_none(item.object_trigger_at),
                ),
                bad_case=AttributionExecutorBadCase(
                    bad_case_id=item.bad_case_id,
                    bad_case_type=item.bad_case_type,
                    title=item.title,
                    description=item.description,
                    report_ref=context.report_ref if context is not None else None,
                    detection_at=_instant_or_none(item.case_trigger_at),
                    hit_reason=item.hit_reason,
                    order_state=item.order_state,
                    error_signal=_error_evidence(item.metadata),
                ),
                skill=AttributionExecutorSkill(
                    key=item.attribution_skill_key,
                    revision=item.attribution_skill_revision,
                    content_hash=item.attribution_skill_content_hash,
                    content=dict(item.attribution_skill_content),
                ),
                context=AttributionExecutorContext(
                    session_id=item.session_id,
                    snapshot_hash=item.execution_manifest.context_snapshot_hash,
                    payload=bundle_payload,
                    evidence_refs=evidence_refs,
                    warnings=(list(context.bundle.warnings) if context is not None else []),
                ),
            ),
        )
        return AttributionResult(
            conclusion=output.conclusion,
            category=output.category,
            confidence=output.confidence,
            reason=output.summary,
            reasoning=output.reasoning,
            evidence_references=tuple(output.evidence_references),
            suggestion_clues=tuple(output.suggestion_clues),
            warnings=tuple(output.warnings),
            token_count=output.token_count,
        )


def _headline(item: AttributionInput) -> str:
    """Pick a bounded one-line human summary from the reported evidence."""
    headline = item.title.strip() or item.description.strip()
    return headline[:200] if headline else "(无标题)"


def _instant(value: datetime | None) -> str:
    """Render one optional trigger instant deterministically."""
    return value.isoformat() if value is not None else "未知"


def _instant_or_none(value: datetime | None) -> str | None:
    """Render one optional coordinate for the executor JSON contract."""
    return value.isoformat() if value is not None else None


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


def build_attribution_report(
    item: AttributionInput,
    result: AttributionResult,
) -> AttributionReportV2:
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
    evidence.extend(
        AttributionEvidence(
            kind="trace",
            summary="Executor-referenced Session trace coordinate",
            reference=reference,
        )
        for reference in result.evidence_references
    )
    warnings = list(result.warnings)
    if result.conclusion == "inconclusive" and "ATTRIBUTION_EVIDENCE_INSUFFICIENT" not in warnings:
        warnings.append("ATTRIBUTION_EVIDENCE_INSUFFICIENT")
    return AttributionReportV2(
        source_report=result.canonical_report,
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
        suggestion_clues=list(result.suggestion_clues),
        warnings=warnings,
    )


_ENGINE_FACTORIES: dict[str, Callable[[], AttributionEngine]] = {
    DEFAULT_ATTRIBUTION_ENGINE: RuleBasedEngine,
    AGENT_SKILL_STUB_ENGINE: AgentSkillStubEngine,
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
    failed: int = 0
    average_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    token_count: int = 0
    warning_count: int = 0
    evidence_coverage_rate: float = 0.0
    context_hash: str | None = None


@dataclass(frozen=True, slots=True)
class AttributionRunProgress:
    """Sanitized observations at batch start and after each case finishes."""

    total: int
    completed: int = 0
    created: int = 0
    reused: int = 0
    failed: int = 0
    non_target: int = 0
    average_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    token_count: int = 0
    warning_count: int = 0
    evidence_coverage_rate: float = 0.0
    context_hash: str | None = None


AttributionProgressCallback = Callable[[AttributionRunProgress], Awaitable[None]]


EngineFactory = Callable[[AttributionEngineKey], AttributionEngine]


@dataclass(frozen=True, slots=True)
class AttributionSkillSnapshot:
    """Exact immutable Skill facts consumed by an executor-backed run."""

    executor_type: str
    content: Mapping[str, Any]


class AttributionSkillSnapshotResolver(Protocol):
    """Load a frozen Skill revision without consulting current bindings."""

    async def resolve_snapshot(
        self,
        workspace_id: str,
        skill_key: str,
        revision: int,
        content_hash: str,
    ) -> AttributionSkillSnapshot:
        """Return the exact revision selected when the run was launched."""


@dataclass(frozen=True)
class AttributionTarget:
    """One member identity available to an attribution run or binding batch."""

    object_type: str
    object_name: str
    target_version: str
    target_revision: str
    sub_dir: str = ""
    definition: GitDefinitionRef | None = None


@dataclass(frozen=True)
class BindingBatch:
    id: str
    owner: str
    workspace_id: str
    target_type: str
    target_name: str
    target_version: str
    target_revision: str
    repo_url: str
    sub_dir: str
    attribution_engine: str
    attribution_skill_key: str
    attribution_skill_revision: int
    attribution_skill_content_hash: str
    definition: GitDefinitionRef | None = None
    targets: tuple[AttributionTarget, ...] = ()
    candidate_policy: CandidatePolicy | None = None


def _batch_targets(run: EvolutionRunRecord | BindingBatch) -> tuple[AttributionTarget, ...]:
    """Return the member identities frozen by a run or binding batch."""
    if isinstance(run, BindingBatch):
        if run.targets:
            return run.targets
        return (
            AttributionTarget(
                run.target_type,
                run.target_name,
                run.target_version,
                run.target_revision,
                run.sub_dir,
                run.definition,
            ),
        )
    if run.targets:
        return tuple(
            AttributionTarget(
                item.object_type,
                item.object_name,
                item.target_version,
                item.target_revision or "",
                item.sub_dir,
            )
            for item in run.targets
        )
    return (
        AttributionTarget(
            run.target_type,
            run.target_name,
            run.target_version,
            run.target_revision or "",
            run.sub_dir,
        ),
    )


def _target_for(
    run: EvolutionRunRecord | BindingBatch,
    candidate: PotentialCase,
) -> AttributionTarget:
    """Return the member owning one case, falling back to the first member."""
    targets = _batch_targets(run)
    for target in targets:
        if (
            target.object_type == candidate.object_type
            and target.object_name == candidate.object_name
        ):
            return target
    return targets[0]


class AttributionStore(Protocol):
    """Persistence operations consumed by the runner."""

    async def linked_probe_ids(self, run_id: str) -> dict[str, str]:
        """Return candidates that already have a persisted probe pointer."""

    async def load_bad_case_evidence(
        self,
        case_ids: Sequence[str],
    ) -> dict[str, BadCaseEvidenceRecord]:
        """Batch-load bad-case identity, titles, descriptions, and metadata."""

    async def load_knowledge_evidence(
        self,
        session_ids: Sequence[str],
    ) -> dict[str, tuple[KnowledgeEvidenceRecord, ...]]:
        """Batch-load knowledge document triggers per root session."""

    async def load_historical_probe_ids(
        self,
        session_ids: Sequence[str],
    ) -> dict[str, tuple[str, ...]]:
        """Batch-load historical report references per root session."""

    async def latest_reports(
        self,
        workspace: str,
        kind: str,
        name: str,
        version: str,
        cases: Sequence[str],
        *,
        generation: str | None = None,
    ) -> dict[str, tuple[str, str, str]]:
        """Find latest completed reports for cache-only runs."""

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
        run_id: str | None,
        now: datetime,
    ) -> str:
        """Persist a fresh probe, its link, and its candidate pointer."""


InputPreparer = Callable[[AttributionInput], Awaitable[AttributionInput]]


class AttributionRunner:
    """Apply the configured engine to included candidates with cache semantics."""

    def __init__(
        self,
        store: AttributionStore,
        *,
        engine_factory: EngineFactory = resolve_attribution_engine,
        now: Callable[[], datetime] = now_shanghai,
        context_provider: AttributionContextProvider | None = None,
        skill_resolver: AttributionSkillSnapshotResolver | None = None,
        max_concurrency: int = 1,
        prepare_input: InputPreparer | None = None,
        prepare_inputs: Callable[[Sequence[str]], InputPreparer] | None = None,
    ) -> None:
        """Bind persistence, engine resolution, and the injectable clock."""
        self._store = store
        self._prepare_input = prepare_input
        self._prepare_inputs = prepare_inputs
        self._engine_factory = engine_factory
        self._now = now
        self._context_provider = context_provider
        self._skill_resolver = skill_resolver
        self._max_concurrency = max(1, max_concurrency)

    async def run(
        self,
        run: EvolutionRunRecord | BindingBatch,
        candidates: Sequence[PotentialCase],
        cache_enabled: bool,
        *,
        on_progress: AttributionProgressCallback | None = None,
        before_case: Callable[[], Awaitable[None]] | None = None,
        target_revision: str | None = None,
    ) -> AttributionRunSummary:
        """Attribute included candidates and return exact reuse/creation counts.

        Already-linked candidates are skipped so a retried step only fills the
        missing tail. A cache hit reuses the existing probe id, advances the
        reuse counter at most once per run, and never calls the engine.

        Args:
            run: Run snapshot providing workspace, target, and engine identity.
            candidates: Matcher output; excluded candidates are ignored.
            cache_enabled: Whether existing cache keys may be reused.
            target_revision: Revision resolved by prepare for a historical NULL run.

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
            linked = (
                {} if isinstance(run, BindingBatch) else await self._store.linked_probe_ids(run.id)
            )
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

        if on_progress is not None:
            await on_progress(AttributionRunProgress(total=len(pending)))
        case_ids = tuple(candidate.bad_case_id for candidate in pending)
        if (
            cache_enabled
            and isinstance(run, EvolutionRunRecord)
            and (run.potential_policy or {}).get("latestReportsOnly")
        ):
            reports: dict[str, tuple[str, str, str]] = {}
            for batch_target in _batch_targets(run):
                target_cases = tuple(
                    candidate.bad_case_id
                    for candidate in pending
                    if _target_for(run, candidate) == batch_target
                )
                if not target_cases:
                    continue
                reports.update(
                    await self._store.latest_reports(
                        run.workspace_id,
                        batch_target.object_type,
                        batch_target.object_name,
                        batch_target.target_revision
                        or target_revision
                        or batch_target.target_version,
                        target_cases,
                    ),
                )
            for case_id, (probe_id, _, _) in reports.items():
                await self._store.reuse_probe_and_link(probe_id, run.id, case_id, self._now())
            return AttributionRunSummary(
                processed=len(reports),
                created=0,
                reused=len(reports),
                non_target=sum(row[2] == "non_target" for row in reports.values()),
                skipped=len(included) - len(reports),
            )
        session_ids = tuple(dict.fromkeys(candidate.session_id for candidate in pending))
        try:
            bad_cases = await self._store.load_bad_case_evidence(case_ids)
            knowledge = await self._store.load_knowledge_evidence(session_ids)
            historical_probe_ids = (
                await self._store.load_historical_probe_ids(session_ids)
                if self._context_provider is not None
                else {}
            )
            contexts: dict[str, AttributionCaseContext] = {}
            if self._context_provider is not None:
                for batch_target in _batch_targets(run):
                    group = tuple(
                        candidate
                        for candidate in pending
                        if _target_for(run, candidate) == batch_target
                    )
                    if not group:
                        continue
                    contexts.update(
                        await self._context_provider.prepare(
                            target_type=batch_target.object_type,  # type: ignore[arg-type]
                            target_name=batch_target.object_name,
                            target_version=batch_target.target_version,
                            target_revision=(target_revision or batch_target.target_revision),
                            candidates=group,
                            bad_cases=bad_cases,
                            knowledge=knowledge,
                            historical_probe_ids=historical_probe_ids,
                        ),
                    )
        except Exception as exc:
            raise self._blocked(run.id, None, exc) from exc

        skill_snapshot = await self._resolve_skill_snapshot(run, engine)
        semaphore = asyncio.Semaphore(self._max_concurrency)

        prepared = tuple(
            (
                candidate,
                self._build_input(
                    run,
                    candidate,
                    bad_cases,
                    knowledge,
                    target_revision,
                    contexts,
                    skill_snapshot,
                ),
            )
            for candidate in pending
        )
        batch_context_hash = canonical_json_hash(
            [
                {
                    "badCaseId": candidate.bad_case_id,
                    "contextSnapshotHash": item.execution_manifest.context_snapshot_hash,
                }
                for candidate, item in prepared
            ],
        )

        prepare_input = (
            self._prepare_inputs([case.session_id for case in pending])
            if self._prepare_inputs
            else self._prepare_input
        )

        async def attribute_one(
            candidate: PotentialCase,
            item: AttributionInput,
        ) -> tuple[str, bool, float, int, bool, int]:
            async with semaphore:
                if before_case is not None:
                    await before_case()
                started = perf_counter()
                now = self._now()
                if (
                    prepare_input is not None
                    and item.attribution_skill_executor_type == "local_agent"
                ):
                    item = await prepare_input(item)
                if cache_enabled:
                    cached = await self._store.get_probe_by_cache_key(item.cache_key)
                    if cached is not None:
                        await self._store.reuse_probe_and_link(
                            cached.probe_id,
                            run.id,
                            candidate.bad_case_id,
                            now,
                        )
                        return (
                            "reused",
                            cached.conclusion == "non_target",
                            (perf_counter() - started) * 1000,
                            0,
                            True,
                            0,
                        )
                result = await engine.attribute(item)
                now = self._now()
                manifest = item.execution_manifest
                report = build_attribution_report(item, result)
                await self._store.write_probe_and_link(
                    ProbeWrite(
                        probe_id=new_id(),
                        workspace_id=run.workspace_id,
                        session_id=candidate.session_id,
                        bad_case_id=candidate.bad_case_id,
                        probe_type=item.probe_type,
                        probe_object=item.probe_object,
                        object_version=item.object_version,
                        attribute_type=result.category,
                        conclusion=result.conclusion,
                        confidence=result.confidence,
                        probe_description=result.reason,
                        probe_analysis=result.reasoning,
                        policy_version=item.policy_version,
                        attribution_engine=engine.key,
                        report_schema_version=REPORT_SCHEMA_VERSION,
                        report_payload=report.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=False,
                            exclude={"source_report"} if result.canonical_report is None else set(),
                        ),
                        execution_manifest=manifest.snapshot(),
                        execution_manifest_hash=manifest.content_hash,
                        legacy_rule=item.legacy_rule,
                        attribution_skill_name=manifest.skill.key,
                        binding_generation=run.id if isinstance(run, BindingBatch) else None,
                        binding_owner=run.owner if isinstance(run, BindingBatch) else None,
                        analysis_id=run.id
                        if isinstance(run, BindingBatch)
                        or (
                            not cache_enabled
                            and item.attribution_skill_executor_type == "local_agent"
                        )
                        else None,
                        created_run_id=None if isinstance(run, BindingBatch) else run.id,
                        created_at=now,
                        updated_at=now,
                    ),
                    None if isinstance(run, BindingBatch) else run.id,
                    now,
                )
                return (
                    "created",
                    result.conclusion == "non_target",
                    (perf_counter() - started) * 1000,
                    len(result.warnings),
                    bool(result.evidence_references),
                    result.token_count,
                )

        tasks = [
            asyncio.create_task(attribute_one(candidate, item)) for candidate, item in prepared
        ]
        created = 0
        reused = 0
        failed = 0
        non_target = 0
        warning_count = 0
        evidence_covered = 0
        token_count = 0
        latencies: list[float] = []
        errors: list[Exception] = []
        paused = False
        try:
            for future in asyncio.as_completed(tasks):
                try:
                    source, is_non_target, latency_ms, warnings, covered, tokens = await future
                    created += int(source == "created")
                    reused += int(source == "reused")
                    non_target += int(is_non_target)
                    warning_count += warnings
                    evidence_covered += int(covered)
                    token_count += tokens
                    latencies.append(latency_ms)
                except PauseAtCheckpoint:
                    paused = True
                    continue
                except Exception as exc:  # keep sibling cases durable before surfacing failure
                    failed += 1
                    errors.append(exc)
                if on_progress is not None:
                    await on_progress(
                        _progress(
                            total=len(pending),
                            created=created,
                            reused=reused,
                            failed=failed,
                            non_target=non_target,
                            latencies=latencies,
                            token_count=token_count,
                            warning_count=warning_count,
                            evidence_covered=evidence_covered,
                            context_hash=batch_context_hash,
                        ),
                    )
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
        if errors:
            first = errors[0]
            if isinstance(first, (ConfigError, ValueError, RunBlocked)):
                raise first
            raise self._blocked(run.id, None, first) from first

        if paused:
            raise PauseAtCheckpoint

        progress = _progress(
            total=len(pending),
            created=created,
            reused=reused,
            failed=failed,
            non_target=non_target,
            latencies=latencies,
            token_count=token_count,
            warning_count=warning_count,
            evidence_covered=evidence_covered,
            context_hash=batch_context_hash,
        )

        return AttributionRunSummary(
            processed=len(pending),
            created=created,
            reused=reused,
            non_target=non_target,
            skipped=skipped,
            failed=failed,
            average_latency_ms=progress.average_latency_ms,
            p95_latency_ms=progress.p95_latency_ms,
            token_count=progress.token_count,
            warning_count=warning_count,
            evidence_coverage_rate=progress.evidence_coverage_rate,
            context_hash=batch_context_hash,
        )

    def _build_input(
        self,
        run: EvolutionRunRecord | BindingBatch,
        candidate: PotentialCase,
        bad_cases: Mapping[str, BadCaseEvidenceRecord],
        knowledge: Mapping[str, tuple[KnowledgeEvidenceRecord, ...]],
        target_revision_override: str | None,
        contexts: Mapping[str, AttributionCaseContext],
        skill_snapshot: AttributionSkillSnapshot | None,
    ) -> AttributionInput:
        """Join one matcher row with its persisted bad-case and knowledge evidence."""
        evidence = bad_cases.get(candidate.bad_case_id)
        if evidence is None:
            raise LookupError(f"bad case evidence not found: {candidate.bad_case_id}")
        target = _target_for(run, candidate)
        object_version = (
            target.target_revision
            or target_revision_override
            or run.target_revision
            or resolve_legacy_target_version(run.target_version).target_revision
        )
        legacy_rule = False
        if (
            isinstance(run, EvolutionRunRecord)
            and run.attribution_engine == DEFAULT_ATTRIBUTION_ENGINE
        ):
            # Main's queued/interrupted rule runs predate Skill snapshots and the mode marker.
            legacy_rule = bool(
                (run.potential_policy or {}).get("legacyRule", run.attribution_skill_key is None)
            )
        policy = (
            run.candidate_policy
            if isinstance(run, BindingBatch)
            else CandidatePolicy.model_validate(
                (run.potential_policy or {}).get("candidatePolicy", {})
            )
        )
        return AttributionInput(
            source_matches=candidate.matched_sources,
            candidate_policy=policy,
            bad_case_id=candidate.bad_case_id,
            run_id=run.id,
            definition=target.definition if isinstance(run, BindingBatch) else None,
            batch_trigger="target_binding" if isinstance(run, BindingBatch) else "evolution_run",
            workspace_id=run.workspace_id,
            session_id=candidate.session_id,
            probe_type=target.object_type,
            probe_object=target.object_name,
            object_version=object_version,
            policy_version=policy_version(policy),
            attribution_engine=run.attribution_engine,
            attribution_skill_key=run.attribution_skill_key,
            attribution_skill_revision=(
                str(run.attribution_skill_revision)
                if run.attribution_skill_revision is not None
                else None
            ),
            attribution_skill_content_hash=run.attribution_skill_content_hash,
            attribution_skill_executor_type=(
                skill_snapshot.executor_type if skill_snapshot is not None else None
            ),
            attribution_skill_content=(
                skill_snapshot.content if skill_snapshot is not None else {}
            ),
            bad_case_type=candidate.bad_case_type,
            title=evidence.title,
            description=evidence.description,
            metadata=evidence.metadata,
            repo_url=run.repo_url,
            sub_dir=target.sub_dir or run.sub_dir,
            selected_version=target.target_version,
            source_commit=run.base_commit if isinstance(run, EvolutionRunRecord) else None,
            report_source=evidence.source or "",
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
            context=contexts.get(candidate.bad_case_id),
            legacy_rule=legacy_rule,
            case_object_name=evidence.object_name,
            case_object_version=evidence.object_version,
        )

    async def _resolve_skill_snapshot(
        self,
        run: EvolutionRunRecord | BindingBatch,
        engine: AttributionEngine,
    ) -> AttributionSkillSnapshot | None:
        """Load executor content by the immutable identity frozen into the run."""
        if engine.key == DEFAULT_ATTRIBUTION_ENGINE:
            return None
        if self._skill_resolver is None:
            raise ConfigError("attribution Skill snapshot resolver is not configured")
        if not (
            run.attribution_skill_key
            and run.attribution_skill_revision is not None
            and run.attribution_skill_content_hash
        ):
            raise ConfigError("run does not contain a frozen attribution Skill revision")
        try:
            return await self._skill_resolver.resolve_snapshot(
                run.workspace_id,
                run.attribution_skill_key,
                run.attribution_skill_revision,
                run.attribution_skill_content_hash,
            )
        except Exception as exc:
            raise ConfigError("frozen attribution Skill revision cannot be resolved") from exc

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


def _progress(
    *,
    total: int,
    created: int,
    reused: int,
    failed: int,
    non_target: int,
    latencies: Sequence[float],
    token_count: int,
    warning_count: int,
    evidence_covered: int,
    context_hash: str,
) -> AttributionRunProgress:
    """Build one bounded observation without trace or Skill content."""
    ordered = sorted(latencies)
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    completed = created + reused + failed
    return AttributionRunProgress(
        total=total,
        completed=completed,
        created=created,
        reused=reused,
        failed=failed,
        non_target=non_target,
        average_latency_ms=(sum(ordered) / len(ordered) if ordered else 0.0),
        p95_latency_ms=(ordered[p95_index] if ordered else 0.0),
        token_count=token_count,
        warning_count=warning_count,
        evidence_coverage_rate=(evidence_covered / completed if completed else 0.0),
        context_hash=context_hash,
    )


__all__ = [
    "DEFAULT_ATTRIBUTION_ENGINE",
    "AgentSkillStubEngine",
    "AttributionEngine",
    "AttributionInput",
    "AttributionResult",
    "AttributionRunProgress",
    "AttributionRunSummary",
    "AttributionRunner",
    "KnowledgeEvidence",
    "RuleBasedEngine",
    "build_attribution_report",
    "registered_engine_keys",
    "resolve_attribution_engine",
]
