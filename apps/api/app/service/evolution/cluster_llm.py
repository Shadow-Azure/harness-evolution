"""Bounded LLM review and scoring for the three-layer clustering path.

The design (07 §5.5.2) keeps the member lists in code: the lexical grouping
layer owns them, the review layer only merges, names, and summarises drafts by
draft key, and the two scoring calls rate the final cluster from a summary plus
a bounded sample. Every prompt is therefore a function of ``K`` drafts, ``s``
samples, and a handful of deterministic statistics — never of the attribution
volume ``N``.

Three degradation paths are independent (07 §5.5.2, 06 §5.3): a rejected review
falls back to the lexical drafts, a failed ``cluster.score`` falls back to the
category confidence constant, and a failed ``severity.score`` falls back to the
``cluster_severity()`` formula. Degradation never blocks a run and never changes
the ``hybrid-lexical-llm-v1`` algorithm identity; the recorded ``degraded``
events explain which layer fell back.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.service.evolution.cluster import (
    HYBRID_ALGORITHM,
    TYPE_CONFIDENCE,
    TYPE_IMPACT,
    ClusterDraft,
    ClusterType,
    cluster_severity,
)
from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.ai_agent.contracts import (
    AgentProviderError,
    AnalysisRequest,
    AnalysisResult,
)

logger = logging.getLogger(__name__)

REVIEW_TASK = "cluster.review"
"""Review layer task key: merge/name/summarise the lexical drafts."""

CLUSTER_SCORE_TASK = "cluster.score"
"""Cluster confidence task key: direct 0-1 rating with evidence references."""

SEVERITY_SCORE_TASK = "severity.score"
"""Severity task key: five graded dimensions plus one decision score."""

REVIEW_SAMPLES_MIN = 3
"""Target floor for representative samples per draft (07 §5.5.2).

A draft with fewer cases renders every case; a draft at or above the floor
renders between the floor and :data:`REVIEW_SAMPLES_MAX`.
"""

REVIEW_SAMPLES_MAX = 5
"""Hard cap for representative samples per draft and per scoring prompt."""

MAX_PROMPT_SAMPLES = REVIEW_SAMPLES_MAX
"""Shared sample cap: scoring prompts cite at most this many cases."""

DRAFT_SUMMARY_TOKENS = 60
"""Approximate token budget for one draft summary in the review prompt."""

DRAFT_SUMMARY_MAX_CHARS = 240
"""Enforced character bound matching :data:`DRAFT_SUMMARY_TOKENS`."""

SAMPLE_TITLE_MAX_CHARS = 120
"""Character bound for one sampled case title."""

SAMPLE_TEXT_MAX_CHARS = 240
"""Character bound for one sampled case description."""

MAX_REASON_CHARS = 300
"""Character bound for one recorded degradation reason."""

DRAFT_KEY_PREFIX = "D"
"""Prefix of the draft references the review output must use (``D1``..``Dk``)."""

CLUSTER_KEY_PREFIX = "C"
"""Prefix of the final-cluster references the batch scoring output must use (``C1``..``Cm``)."""

EVIDENCE_REF_ALIAS = "evidence_refs"
"""Output field that must cite only the sample ids passed in the prompt."""

REVIEW_FROM_ALIAS = "from"
"""Output field carrying the draft keys one final cluster is merged from."""

SEVERITY_DIMENSION_ANCHORS: Mapping[str, str] = MappingProxyType(
    {
        "impact": (
            "how damaging the wrong behaviour is for the user's task "
            "(0 cosmetic, 10 blocks the task)"
        ),
        "scope": (
            "how many bad cases, sessions, or versions are affected "
            "(0 one edge case, 10 all traffic)"
        ),
        "reproducibility": "how reliably the failure reproduces (0 one-off, 10 deterministic)",
        "evidence_directness": (
            "how directly the samples prove the failure "
            "(0 indirect, 10 the failing interaction is visible)"
        ),
        "blast_radius": (
            "how much downstream behaviour a fix or regression can touch (0 isolated, 10 global)"
        ),
    },
)
"""Human-facing anchors for the stable severity dimension names."""

SEVERITY_DIMENSIONS: tuple[str, ...] = tuple(SEVERITY_DIMENSION_ANCHORS)
"""Stable severity dimension names; the prompt and payload use exactly these."""

CONFIDENCE_ANCHORS: tuple[tuple[str, str], ...] = (
    (
        "0.9",
        "direct evidence in at least 3 cases and the cases share one signature "
        "(same failure point or error text)",
    ),
    (
        "0.7",
        "most cases share one signature, but one case only matches partially",
    ),
    (
        "0.5",
        "plausible grouping, but the evidence is thin (one or two cases)",
    ),
    (
        "0.2",
        "weak grouping; the cases look unrelated or the evidence is indirect",
    ),
    ("0.0", "no usable evidence"),
)
"""Human-facing confidence rubric anchors shared by the scoring prompt."""

SEVERITY_VECTOR_PATTERN = r"^CVSS:3\.1(/[A-Z]{1,3}:[A-Z])+$"
"""Permissive CVSS-3.1-style vector check; the metric set is not enumerated."""


class ClusterContractError(ValueError):
    """One semantic contract violation in a task output or request.

    The caller records a ``degraded`` event with :attr:`reason`; the reason is
    bounded and never echoes raw model output so it is safe to persist.
    """

    def __init__(self, reason: str) -> None:
        """Store the bounded reason alongside the exception message."""
        self.reason = _bounded(reason, MAX_REASON_CHARS)
        super().__init__(self.reason)


class ClusterReviewItem(BaseModel):
    """One final cluster declared by the draft keys it merges.

    The field alias is ``from`` because that is the wire shape of the design
    (07 §5.5.2): members are expanded by code from the draft keys, so the model
    only ever names a subset of ``D1``..``Dk``. Extra keys are rejected: an
    unexpected field means the model did not follow the merge/naming contract,
    so the whole batch degrades instead of guessing what the extra key meant.
    """

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    from_keys: list[str] = Field(alias="from", min_length=1)
    title: str
    description: str | None = None


class ClusterReviewOutput(BaseModel):
    """The complete review partition of the input drafts.

    ``min_length=1`` rejects an empty result before it reaches the partition
    validator: an empty list cannot cover any draft key, so it is never a legal
    partition and must degrade the whole review batch instead of persisting
    zero clusters.
    """

    clusters: list[ClusterReviewItem] = Field(min_length=1)


class ClusterScoreItem(BaseModel):
    """One cluster's confidence inside the single batch ``cluster.score`` output."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    cluster: str
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)


class ClusterScoresOutput(BaseModel):
    """The batch confidence output: exactly one item per final cluster.

    The two scoring tasks run once per run over every final cluster, so the cost
    shape stays at one review call plus two scoring calls regardless of the
    cluster count (07 §5.5.2). Cluster keys keep the values attached to the
    right cluster without asking the model to repeat member lists.
    """

    scores: list[ClusterScoreItem] = Field(min_length=1)


SeverityDimension = Annotated[float, Field(ge=0, le=10)]


class SeverityScoreItem(BaseModel):
    """One cluster's severity grading inside the single batch ``severity.score`` output."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    cluster: str
    overall: float = Field(ge=0, le=10)
    dimensions: dict[str, SeverityDimension] = Field(default_factory=dict)
    vector: str = Field(pattern=SEVERITY_VECTOR_PATTERN)


class SeverityScoresOutput(BaseModel):
    """The batch severity output: one decision score, dimensions, and vector per cluster.

    ``dimensions`` defaults to an empty mapping because the model may keep the
    grading in ``overall`` alone; when dimensions are present every documented
    name keeps its meaning and every value stays on the 0-10 scale. ``vector``
    is a CVSS-3.1-style audit string checked by a permissive regex.
    """

    severities: list[SeverityScoreItem] = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class ClusterCaseEvidence:
    """One bad case as it may appear in a prompt sample.

    Only the identity and the two human-readable fields are rendered; the
    reported timestamp feeds the deterministic time-span statistic and never
    reaches a prompt.
    """

    case_id: str
    title: str
    text: str = ""
    reported_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ClusterDraftStats:
    """Deterministic per-draft statistics computed outside the model.

    ``case_ids`` is the code-held member list: it is sampled for prompts but
    never rendered as a whole. ``signature_overlap`` is the mean pairwise
    lexical similarity of the member titles and ``time_span_days`` the span
    between the earliest and latest reported case.
    """

    case_ids: tuple[str, ...]
    signature_overlap: float = 0.0
    time_span_days: int | None = None

    @property
    def member_count(self) -> int:
        """Return the number of distinct bad cases behind the draft."""
        return len(self.case_ids)


@dataclass(frozen=True, slots=True)
class ClusterSummary:
    """Final cluster identity handed to the two scoring tasks."""

    type: ClusterType
    title: str
    description: str = ""
    member_count: int = 0


@dataclass(frozen=True, slots=True)
class CallRecord:
    """Normalized observability record for exactly one provider analysis call."""

    task: str
    provider_id: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    outcome: Literal["ok", "degraded", "error"]
    session_id: str | None = None


@dataclass(frozen=True, slots=True)
class DegradedCall:
    """One layer that fell back to its deterministic value."""

    task: str
    reason: str


@dataclass(frozen=True, slots=True)
class EnhancedCluster:
    """One final cluster after review and scoring.

    ``severity`` is the decision score actually persisted; ``formula_severity``
    keeps the deterministic formula value so the two can be compared in the
    ``clusters_created`` payload even when the LLM severity succeeded.
    """

    type: ClusterType
    description: str
    probes: tuple[str, ...]
    impact: float
    confidence: float
    severity: float
    formula_severity: float
    evidence_refs: tuple[str, ...]
    dimensions: Mapping[str, float]
    vector: str | None


@dataclass(frozen=True, slots=True)
class EnhancedClusters:
    """The complete hybrid result: final clusters plus every call and fallback."""

    clusters: tuple[EnhancedCluster, ...]
    algorithm: str
    degraded: tuple[DegradedCall, ...]
    calls: tuple[CallRecord, ...]


@dataclass(frozen=True, slots=True)
class ClusterPlan:
    """One final cluster as the two batch scoring prompts see it.

    ``members`` is already sampled to at most five cases, so the prompt size is
    a function of the cluster count and the sample cap rather than of the
    attribution volume.
    """

    key: str
    summary: ClusterSummary
    members: tuple[ClusterCaseEvidence, ...]
    stats: ClusterDraftStats


RecordCall = Callable[[CallRecord], Awaitable[None]]
"""Sink for one observability record; failures never break the run."""

RecordDegraded = Callable[[DegradedCall], Awaitable[None]]
"""Sink for one degradation record; failures never break the run."""


@dataclass(frozen=True, slots=True)
class _Group:
    """One final cluster while it still references input draft indexes."""

    type: ClusterType
    title: str
    description: str
    draft_indexes: tuple[int, ...]
    fallback: bool = False


def build_review_request(
    drafts: Sequence[ClusterDraft],
    evidence: Mapping[str, ClusterCaseEvidence],
    *,
    stats_by_draft: Mapping[int, ClusterDraftStats],
) -> AnalysisRequest:
    """Build the bounded ``cluster.review`` request for the lexical drafts.

    Each draft becomes one block keyed ``D1``..``Dk`` in draft order. A block
    carries the deterministic statistics (type, member count, signature
    overlap, time span), one bounded summary, and 3-5 representative case
    samples selected by sorted case id. The full member list never appears.

    Args:
        drafts: Lexical drafts in ``model``, ``prompt``, ``error`` order.
        evidence: Case evidence by case id; samples are drawn from it.
        stats_by_draft: Deterministic statistics keyed by 0-based draft index.
            Missing entries fall back to the probe count and no samples.

    Returns:
        One ``AnalysisRequest`` whose output model is ``ClusterReviewOutput``.

    Raises:
        ValueError: When there are no drafts to review.
    """
    if not drafts:
        raise ValueError("cluster.review needs at least one draft")
    lines = [
        "Task: cluster.review — merge lexical draft clusters of attributed bad cases.",
        "",
        (
            "You may only merge drafts, name each resulting cluster, and write an "
            "optional one-sentence description."
        ),
        (
            "Member lists are owned by the caller and are never shown here; "
            "reference drafts only by key."
        ),
        "",
        "Rules:",
        (
            '1. Return only JSON: {"clusters": '
            '[{"from": ["D1", "D2"], "title": "...", "description": "..."}]}.'
        ),
        (
            f"2. Use draft keys {DRAFT_KEY_PREFIX}1..{DRAFT_KEY_PREFIX}{len(drafts)} "
            "exactly as listed; never invent keys and never cite case ids as draft keys."
        ),
        (
            f'3. Every draft key must appear in exactly one "{REVIEW_FROM_ALIAS}" list: '
            f"the output is a complete partition of {DRAFT_KEY_PREFIX}1.."
            f"{DRAFT_KEY_PREFIX}{len(drafts)}."
        ),
        (
            "4. The review is merge-only: a draft key may appear exactly once, so "
            "splitting one draft into two clusters is impossible."
        ),
        (
            '5. "title" is a short human label (<= 60 characters) in the language of '
            'the samples; "description" is optional.'
        ),
        "6. Merge only drafts of the same type; never merge across types.",
        "",
        "Draft blocks:",
    ]
    for index, draft in enumerate(drafts):
        key = f"{DRAFT_KEY_PREFIX}{index + 1}"
        stats = stats_by_draft.get(index)
        if stats is None:
            stats = ClusterDraftStats(case_ids=tuple(sorted(draft.probes)))
        samples = select_samples(
            stats.case_ids,
            evidence,
            limit=_sample_target(stats.member_count),
        )
        lines.append(
            f"[{key}] type={draft.type} members={stats.member_count} "
            f"signatureOverlap={stats.signature_overlap:.2f} "
            f"timeSpanDays={_render_span(stats.time_span_days)}",
        )
        lines.append(f"  summary: {_bounded(draft.description, DRAFT_SUMMARY_MAX_CHARS)}")
        lines.append(f"  samples ({len(samples)} of {stats.member_count}):")
        lines.extend(_render_sample(sample) for sample in samples)
        lines.append("")
    return AnalysisRequest(
        task=REVIEW_TASK,
        prompt="\n".join(lines),
        output_model=ClusterReviewOutput,
    )


def build_cluster_score_request(plans: Sequence[ClusterPlan]) -> AnalysisRequest:
    """Build the single batch ``cluster.score`` request for every final cluster.

    One call carries all final-cluster summaries, their sampled cases, and the
    deterministic statistics; the prompt therefore scales with cluster count and
    the sample cap, never with the attribution volume. The confidence rubric
    anchors the value across runs, and ``evidence_refs`` is restricted to the
    sample ids rendered under the same cluster key.

    Args:
        plans: Final clusters in deterministic order, each with sampled members.

    Returns:
        One ``AnalysisRequest`` whose output model is ``ClusterScoresOutput``.

    Raises:
        ValueError: When there is no final cluster to score.
    """
    if not plans:
        raise ValueError("cluster.score needs at least one final cluster")
    lines = [
        "Task: cluster.score — rate how confidently each cluster is one real problem.",
        "",
        "Confidence rubric:",
        *(f"- {anchor}: {description}" for anchor, description in CONFIDENCE_ANCHORS),
        "",
        "Rules:",
        (
            '1. Return only JSON: {"scores": [{"cluster": "C1", "confidence": <0..1>, '
            f'"{EVIDENCE_REF_ALIAS}": [<sample ids>]}}]}}.'
        ),
        (
            f"2. Use the cluster keys {CLUSTER_KEY_PREFIX}1..{CLUSTER_KEY_PREFIX}{len(plans)} "
            "exactly as listed; every key appears exactly once and no other key is legal."
        ),
        (
            f'3. "{EVIDENCE_REF_ALIAS}" entries for one cluster must be sample ids listed '
            "under that same cluster; never cite another cluster's sample or a draft key."
        ),
        ("4. 0.0 means no usable evidence; 1.0 means every sample shares one signature."),
        "",
        "Cluster blocks:",
    ]
    for plan in plans:
        lines.append(f"[{plan.key}] {_render_cluster_header(plan.summary, plan.stats)}")
        lines.append(f"Samples ({len(plan.members)}):")
        lines.extend(_render_sample(sample) for sample in plan.members)
        lines.append("")
    return AnalysisRequest(
        task=CLUSTER_SCORE_TASK,
        prompt="\n".join(lines),
        output_model=ClusterScoresOutput,
    )


def build_severity_request(plans: Sequence[ClusterPlan]) -> AnalysisRequest:
    """Build the single batch ``severity.score`` request for every final cluster.

    The model grades the stable dimensions in a fixed order and then gives one
    decision score per cluster; the deterministic formula score is kept
    separately by the caller for comparison. One call per run keeps the cost
    shape fixed while the prompt stays bounded by cluster count and sample cap.

    Args:
        plans: Final clusters in deterministic order, each with sampled members.

    Returns:
        One ``AnalysisRequest`` whose output model is ``SeverityScoresOutput``.

    Raises:
        ValueError: When there is no final cluster to score.
    """
    if not plans:
        raise ValueError("severity.score needs at least one final cluster")
    lines = [
        "Task: severity.score — grade the severity of each failure cluster.",
        "",
        ("Think in this order, one dimension at a time, then give one overall decision score:"),
        *(f"- {name}: {anchor}" for name, anchor in SEVERITY_DIMENSION_ANCHORS.items()),
        "",
        "Rules:",
        (
            '1. Return only JSON: {"severities": [{"cluster": "C1", "overall": <0..10>, '
            '"dimensions": {<dimension>: <0..10>}, "vector": "<CVSS 3.1 vector>"}]}.'
        ),
        (
            f"2. Use the cluster keys {CLUSTER_KEY_PREFIX}1..{CLUSTER_KEY_PREFIX}{len(plans)} "
            "exactly as listed; every key appears exactly once and no other key is legal."
        ),
        f"3. Use exactly these dimension keys: {', '.join(SEVERITY_DIMENSIONS)}.",
        (
            '4. The "vector" must follow the CVSS 3.1 shape, for example '
            '"CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L".'
        ),
        (
            '5. "overall" is your decision score; a deterministic formula score is kept '
            "separately for comparison."
        ),
        "",
        "Cluster blocks:",
    ]
    for plan in plans:
        lines.append(f"[{plan.key}] {_render_cluster_header(plan.summary, plan.stats)}")
        lines.append(f"Samples ({len(plan.members)}):")
        lines.extend(_render_sample(sample) for sample in plan.members)
        lines.append("")
    return AnalysisRequest(
        task=SEVERITY_SCORE_TASK,
        prompt="\n".join(lines),
        output_model=SeverityScoresOutput,
    )


def validate_review_partition(
    output: ClusterReviewOutput,
    drafts: Sequence[ClusterDraft],
) -> tuple[ClusterReviewItem, ...]:
    """Enforce the review partition gate over the input drafts.

    The output must be a partition of ``D1``..``Dk``: every input draft key
    appears exactly once, no unknown key appears, every title is non-empty, and
    no cluster merges drafts of different types.

    Args:
        output: Validated review output.
        drafts: The exact drafts the prompt listed, in draft order.

    Returns:
        The validated review items in model order.

    Raises:
        ClusterContractError: On any partition or cross-field violation.
    """
    if not output.clusters:
        raise ClusterContractError(
            "cluster.review returned no clusters; an empty result cannot partition the drafts",
        )
    expected = [f"{DRAFT_KEY_PREFIX}{index + 1}" for index in range(len(drafts))]
    seen: dict[str, int] = {}
    for position, item in enumerate(output.clusters):
        if not item.title.strip():
            raise ClusterContractError(f"cluster.review item {position} has an empty title")
        item_types: set[ClusterType] = set()
        for key in item.from_keys:
            index = _draft_index(key, len(drafts))
            if key in seen:
                raise ClusterContractError(
                    "cluster.review is merge-only: every draft key must appear exactly once, "
                    f"so splitting a draft is impossible; {key} appears in items {seen[key]} and "
                    f"{position}",
                )
            seen[key] = position
            item_types.add(drafts[index].type)
        if len(item_types) > 1:
            raise ClusterContractError(
                f"cluster.review item {position} merges drafts of different types "
                f"({', '.join(sorted(item_types))}); a cluster has exactly one type",
            )
    missing = [key for key in expected if key not in seen]
    if missing:
        raise ClusterContractError(
            "cluster.review dropped draft keys "
            f"{', '.join(missing)}; every draft must appear exactly once (complete partition)",
        )
    return tuple(output.clusters)


def validate_evidence_refs(
    refs: Sequence[str],
    members: Sequence[ClusterCaseEvidence],
) -> tuple[str, ...]:
    """Enforce ``evidence_refs`` to be a subset of the prompt sample ids.

    Args:
        refs: Sample ids the model cited.
        members: Samples actually rendered in the same prompt.

    Returns:
        The cited ids in first-seen order without duplicates.

    Raises:
        ClusterContractError: When any cited id was not passed in the prompt.
    """
    allowed = {member.case_id for member in members}
    unknown = [ref for ref in refs if ref not in allowed]
    if unknown:
        raise ClusterContractError(
            f"cluster.score cited {len(unknown)} evidence_ref(s) outside the prompt samples; "
            "evidence_refs must be a subset of the sample ids passed in the prompt",
        )
    return tuple(dict.fromkeys(refs))


def validate_cluster_scores(
    output: ClusterScoresOutput,
    plans: Sequence[ClusterPlan],
) -> dict[str, tuple[float, tuple[str, ...]]]:
    """Enforce the batch ``cluster.score`` coverage and per-cluster citations.

    The single call must return exactly one item per final cluster key; each
    item's ``evidence_refs`` must be a subset of the sample ids rendered under
    that same key. A missing, duplicated, unknown, or mis-cited item rejects the
    whole batch so the caller can degrade every confidence together.

    Args:
        output: Validated batch confidence output.
        plans: The final clusters the prompt listed, in key order.

    Returns:
        Confidence and cited sample ids by cluster key.

    Raises:
        ClusterContractError: On any coverage or citation violation.
    """
    by_key = {plan.key: plan for plan in plans}
    expected = [plan.key for plan in plans]
    scores: dict[str, tuple[float, tuple[str, ...]]] = {}
    for item in output.scores:
        if item.cluster not in by_key:
            raise ClusterContractError(
                f"cluster.score returned unknown cluster key {item.cluster!r}; expected one of "
                f"{CLUSTER_KEY_PREFIX}1..{CLUSTER_KEY_PREFIX}{len(plans)}",
            )
        if item.cluster in scores:
            raise ClusterContractError(
                f"cluster.score returned cluster key {item.cluster} more than once; every final "
                "cluster must appear exactly once",
            )
        try:
            refs = validate_evidence_refs(item.evidence_refs, by_key[item.cluster].members)
        except ClusterContractError as exc:
            raise ClusterContractError(f"cluster.score [{item.cluster}]: {exc.reason}") from None
        scores[item.cluster] = (item.confidence, refs)
    missing = [key for key in expected if key not in scores]
    if missing:
        raise ClusterContractError(
            "cluster.score dropped final-cluster keys "
            f"{', '.join(missing)}; every final cluster must appear exactly once",
        )
    return scores


def validate_severity_scores(
    output: SeverityScoresOutput,
    plans: Sequence[ClusterPlan],
) -> dict[str, tuple[float, Mapping[str, float], str | None]]:
    """Enforce the batch ``severity.score`` coverage of every final cluster.

    Args:
        output: Validated batch severity output.
        plans: The final clusters the prompt listed, in key order.

    Returns:
        Decision score, dimensions, and vector by cluster key.

    Raises:
        ClusterContractError: When a key is missing, duplicated, or unknown.
    """
    by_key = {plan.key: plan for plan in plans}
    expected = [plan.key for plan in plans]
    severities: dict[str, tuple[float, Mapping[str, float], str | None]] = {}
    for item in output.severities:
        if item.cluster not in by_key:
            raise ClusterContractError(
                f"severity.score returned unknown cluster key {item.cluster!r}; expected one of "
                f"{CLUSTER_KEY_PREFIX}1..{CLUSTER_KEY_PREFIX}{len(plans)}",
            )
        if item.cluster in severities:
            raise ClusterContractError(
                f"severity.score returned cluster key {item.cluster} more than once; every final "
                "cluster must appear exactly once",
            )
        severities[item.cluster] = (
            item.overall,
            MappingProxyType(dict(item.dimensions)),
            item.vector,
        )
    missing = [key for key in expected if key not in severities]
    if missing:
        raise ClusterContractError(
            "severity.score dropped final-cluster keys "
            f"{', '.join(missing)}; every final cluster must appear exactly once",
        )
    return severities


def _sample_target(member_count: int) -> int:
    """Return how many representative samples one prompt should render.

    The design asks for three to five representative cases per draft and per
    scoring prompt: below the floor every case is rendered, at or above it the
    hard cap applies.
    """
    if member_count <= REVIEW_SAMPLES_MIN:
        return member_count
    return REVIEW_SAMPLES_MAX


def select_samples(
    case_ids: Sequence[str],
    evidence: Mapping[str, ClusterCaseEvidence],
    *,
    limit: int = MAX_PROMPT_SAMPLES,
) -> tuple[ClusterCaseEvidence, ...]:
    """Select at most ``limit`` representative samples deterministically.

    Case ids are deduplicated and sorted first, then evenly spaced indexes pick
    the sample so the choice depends on the ordered ids only — never on database
    row order or on how many cases the cluster has. Ids without loaded evidence
    are skipped.

    Args:
        case_ids: Code-held member case ids of one draft or final cluster.
        evidence: Case evidence keyed by case id.
        limit: Hard cap on the returned sample count.

    Returns:
        Samples ordered by case id.
    """
    ordered = sorted(dict.fromkeys(str(case_id) for case_id in case_ids))
    present = tuple(evidence[case_id] for case_id in ordered if case_id in evidence)
    count = min(len(present), max(limit, 0))
    if count <= 0:
        return ()
    return tuple(present[index] for index in _evenly_spaced_indexes(len(present), count))


async def enhance_clusters(
    agent: AIAgentProvider,
    drafts: Sequence[ClusterDraft],
    evidence: Mapping[str, ClusterCaseEvidence],
    *,
    stats_by_draft: Mapping[int, ClusterDraftStats],
    record_call: RecordCall | None = None,
    record_degraded: RecordDegraded | None = None,
) -> EnhancedClusters:
    """Run the review and scoring layers over lexical drafts with degradation.

    Order of operations is deterministic and costs exactly three bounded
    ``analyze`` calls for every non-empty run: one ``cluster.review`` call over
    the lexical drafts, then one batch ``cluster.score`` call over every final
    cluster, then one batch ``severity.score`` call. The two scoring calls are
    isolated, so a failed confidence batch changes only confidence and a failed
    severity batch changes only severity; the cluster count never changes the
    call count.

    Args:
        agent: Outbound provider used for the three analysis tasks.
        drafts: Lexical drafts in ``model``, ``prompt``, ``error`` order.
        evidence: Case evidence keyed by case id.
        stats_by_draft: Deterministic statistics keyed by 0-based draft index.
        record_call: Optional sink receiving one record per provider call.
        record_degraded: Optional sink receiving one record per fallback.

    Returns:
        The final clusters, the ``hybrid-lexical-llm-v1`` identity, every
        degradation, and every call record, in evaluation order.
    """
    calls: list[CallRecord] = []
    degraded: list[DegradedCall] = []

    async def note_call(call: CallRecord) -> None:
        calls.append(call)
        await _notify_call(record_call, call)

    async def note_degraded(item: DegradedCall) -> None:
        degraded.append(item)
        await _notify_degraded(record_degraded, item)

    if not drafts:
        return EnhancedClusters(
            clusters=(),
            algorithm=HYBRID_ALGORITHM,
            degraded=(),
            calls=(),
        )

    groups = await _review(agent, drafts, evidence, stats_by_draft, note_call, note_degraded)
    plans = _build_plans(groups, drafts, evidence, stats_by_draft)
    confidence_by_key = await _score_confidences(agent, plans, note_call, note_degraded)
    severity_by_key = await _score_severities(agent, plans, note_call, note_degraded)
    clusters: list[EnhancedCluster] = []
    for group, plan in zip(groups, plans, strict=True):
        confidence, evidence_refs = confidence_by_key[plan.key]
        severity, dimensions, vector = severity_by_key[plan.key]
        formula_severity = cluster_severity(group.type, plan.stats.member_count)
        description = (
            group.title
            if group.fallback
            else _compose_description(group.type, group.title, group.description)
        )
        clusters.append(
            EnhancedCluster(
                type=group.type,
                description=description,
                probes=_merged_probes(group.draft_indexes, drafts),
                impact=float(TYPE_IMPACT[group.type]),
                confidence=confidence,
                severity=severity,
                formula_severity=formula_severity,
                evidence_refs=evidence_refs,
                dimensions=MappingProxyType(dict(dimensions)),
                vector=vector,
            ),
        )
    return EnhancedClusters(
        clusters=tuple(clusters),
        algorithm=HYBRID_ALGORITHM,
        degraded=tuple(degraded),
        calls=tuple(calls),
    )


def _build_plans(
    groups: Sequence[_Group],
    drafts: Sequence[ClusterDraft],
    evidence: Mapping[str, ClusterCaseEvidence],
    stats_by_draft: Mapping[int, ClusterDraftStats],
) -> tuple[ClusterPlan, ...]:
    """Expand validated groups into deterministic final-cluster scoring plans."""
    plans: list[ClusterPlan] = []
    for index, group in enumerate(groups):
        stats = _merged_stats(group.draft_indexes, drafts, stats_by_draft, evidence)
        plans.append(
            ClusterPlan(
                key=f"{CLUSTER_KEY_PREFIX}{index + 1}",
                summary=ClusterSummary(
                    type=group.type,
                    title=group.title,
                    description=group.description,
                    member_count=stats.member_count,
                ),
                members=select_samples(
                    stats.case_ids,
                    evidence,
                    limit=_sample_target(stats.member_count),
                ),
                stats=stats,
            ),
        )
    return tuple(plans)


async def _review(
    agent: AIAgentProvider,
    drafts: Sequence[ClusterDraft],
    evidence: Mapping[str, ClusterCaseEvidence],
    stats_by_draft: Mapping[int, ClusterDraftStats],
    note_call: _CallSink,
    note_degraded: _DegradedSink,
) -> tuple[_Group, ...]:
    """Run one review call and return the final cluster groups.

    Any provider failure or contract violation degrades the whole review batch
    to the original drafts: partial acceptance would break the partition.
    """
    request = build_review_request(drafts, evidence, stats_by_draft=stats_by_draft)
    started = time.perf_counter()
    try:
        result = await agent.analyze(request)
    except Exception as exc:
        await note_call(_failure_record(REVIEW_TASK, agent, _elapsed_ms(started)))
        await note_degraded(DegradedCall(REVIEW_TASK, _provider_reason(exc)))
        return _fallback_groups(drafts)
    elapsed = _elapsed_ms(started)
    try:
        output = ClusterReviewOutput.model_validate(dict(result.output))
        items = validate_review_partition(output, drafts)
    except (ValidationError, ClusterContractError) as exc:
        await note_call(_result_record(REVIEW_TASK, result, "degraded", elapsed))
        await note_degraded(DegradedCall(REVIEW_TASK, _contract_reason(exc)))
        return _fallback_groups(drafts)
    await note_call(_result_record(REVIEW_TASK, result, "ok", elapsed))
    return _groups_from_review(items, drafts)


async def _score_confidences(
    agent: AIAgentProvider,
    plans: Sequence[ClusterPlan],
    note_call: _CallSink,
    note_degraded: _DegradedSink,
) -> dict[str, tuple[float, tuple[str, ...]]]:
    """Run the single batch confidence call, degrading every cluster on failure."""
    fallback: dict[str, tuple[float, tuple[str, ...]]] = {
        plan.key: (TYPE_CONFIDENCE[plan.summary.type], ()) for plan in plans
    }
    if not plans:
        return fallback
    request = build_cluster_score_request(plans)
    started = time.perf_counter()
    try:
        result = await agent.analyze(request)
    except Exception as exc:
        await note_call(_failure_record(CLUSTER_SCORE_TASK, agent, _elapsed_ms(started)))
        await note_degraded(DegradedCall(CLUSTER_SCORE_TASK, _provider_reason(exc)))
        return fallback
    elapsed = _elapsed_ms(started)
    try:
        output = ClusterScoresOutput.model_validate(dict(result.output))
        scores = validate_cluster_scores(output, plans)
    except (ValidationError, ClusterContractError) as exc:
        await note_call(_result_record(CLUSTER_SCORE_TASK, result, "degraded", elapsed))
        await note_degraded(DegradedCall(CLUSTER_SCORE_TASK, _contract_reason(exc)))
        return fallback
    await note_call(_result_record(CLUSTER_SCORE_TASK, result, "ok", elapsed))
    return scores


async def _score_severities(
    agent: AIAgentProvider,
    plans: Sequence[ClusterPlan],
    note_call: _CallSink,
    note_degraded: _DegradedSink,
) -> dict[str, tuple[float, Mapping[str, float], str | None]]:
    """Run the single batch severity call, degrading every cluster on failure."""
    fallback: dict[str, tuple[float, Mapping[str, float], str | None]] = {
        plan.key: (
            cluster_severity(plan.summary.type, plan.stats.member_count),
            MappingProxyType({}),
            None,
        )
        for plan in plans
    }
    if not plans:
        return fallback
    request = build_severity_request(plans)
    started = time.perf_counter()
    try:
        result = await agent.analyze(request)
    except Exception as exc:
        await note_call(_failure_record(SEVERITY_SCORE_TASK, agent, _elapsed_ms(started)))
        await note_degraded(DegradedCall(SEVERITY_SCORE_TASK, _provider_reason(exc)))
        return fallback
    elapsed = _elapsed_ms(started)
    try:
        output = SeverityScoresOutput.model_validate(dict(result.output))
        severities = validate_severity_scores(output, plans)
    except (ValidationError, ClusterContractError) as exc:
        await note_call(_result_record(SEVERITY_SCORE_TASK, result, "degraded", elapsed))
        await note_degraded(DegradedCall(SEVERITY_SCORE_TASK, _contract_reason(exc)))
        return fallback
    await note_call(_result_record(SEVERITY_SCORE_TASK, result, "ok", elapsed))
    return severities


_CallSink = Callable[[CallRecord], Awaitable[None]]
_DegradedSink = Callable[[DegradedCall], Awaitable[None]]


def _groups_from_review(
    items: Sequence[ClusterReviewItem],
    drafts: Sequence[ClusterDraft],
) -> tuple[_Group, ...]:
    """Expand a validated review partition into deterministic final groups.

    Groups are ordered by the smallest input draft index they contain, which is
    the same ``type`` then probe order the lexical layer produced.
    """
    groups: list[_Group] = []
    for item in items:
        indexes = tuple(sorted(_draft_index(key, len(drafts)) for key in item.from_keys))
        groups.append(
            _Group(
                type=drafts[indexes[0]].type,
                title=item.title.strip(),
                description=(item.description or "").strip(),
                draft_indexes=indexes,
            ),
        )
    return tuple(sorted(groups, key=lambda group: group.draft_indexes[0]))


def _fallback_groups(drafts: Sequence[ClusterDraft]) -> tuple[_Group, ...]:
    """Use the lexical drafts unchanged after a rejected review batch."""
    return tuple(
        _Group(
            type=draft.type,
            title=draft.description,
            description="",
            draft_indexes=(index,),
            fallback=True,
        )
        for index, draft in enumerate(drafts)
    )


def _merged_stats(
    indexes: Sequence[int],
    drafts: Sequence[ClusterDraft],
    stats_by_draft: Mapping[int, ClusterDraftStats],
    evidence: Mapping[str, ClusterCaseEvidence],
) -> ClusterDraftStats:
    """Combine the per-draft statistics of one final cluster deterministically."""
    case_ids = tuple(
        sorted(
            {
                case_id
                for index in indexes
                for case_id in stats_by_draft.get(
                    index,
                    ClusterDraftStats(case_ids=tuple(drafts[index].probes)),
                ).case_ids
            },
        ),
    )
    weighted = 0.0
    weight = 0
    draft_spans: list[int] = []
    for index in indexes:
        stats = stats_by_draft.get(index)
        if stats is None:
            continue
        weighted += stats.signature_overlap * max(stats.member_count, 1)
        weight += max(stats.member_count, 1)
        if stats.time_span_days is not None:
            draft_spans.append(stats.time_span_days)
    reported: list[datetime] = []
    for case_id in case_ids:
        sample = evidence.get(case_id)
        if sample is not None and sample.reported_at is not None:
            reported.append(sample.reported_at)
    span: int | None = None
    if len(reported) > 1:
        span = (max(reported) - min(reported)).days
    elif draft_spans:
        span = max(draft_spans)
    return ClusterDraftStats(
        case_ids=case_ids,
        signature_overlap=round(weighted / weight, 4) if weight else 0.0,
        time_span_days=span,
    )


def _merged_probes(indexes: Sequence[int], drafts: Sequence[ClusterDraft]) -> tuple[str, ...]:
    """Expand the merged draft members into one sorted probe tuple."""
    return tuple(
        sorted({probe_id for index in indexes for probe_id in drafts[index].probes}),
    )


def _draft_index(key: str, draft_count: int) -> int:
    """Map one review draft key to its 0-based draft index.

    Raises:
        ClusterContractError: When the key is not one of ``D1``..``Dk``.
    """
    digits = key[len(DRAFT_KEY_PREFIX) :] if key.startswith(DRAFT_KEY_PREFIX) else ""
    canonical = str(int(digits)) if digits.isdigit() else ""
    if digits != canonical or not 1 <= int(canonical or 0) <= draft_count:
        raise ClusterContractError(
            f"cluster.review returned unknown draft key {key!r}; expected one of "
            f"{DRAFT_KEY_PREFIX}1..{DRAFT_KEY_PREFIX}{draft_count}",
        )
    return int(digits) - 1


def _compose_description(cluster_type: ClusterType, title: str, summary: str) -> str:
    """Fold the review title and optional summary into the single stored column.

    06 §5.3 has no title column (zero migration), so the persisted description
    keeps the lexical category prefix and appends the optional LLM summary.
    """
    headline = _bounded(title, 120) or f"{cluster_type} 类问题"
    detail = _bounded(summary, 200)
    text = f"{headline} · {detail}" if detail else headline
    return f"{cluster_type} 类问题 · {text}"


def _render_cluster_header(cluster: ClusterSummary, stats: ClusterDraftStats) -> str:
    """Render the deterministic cluster header shared by both scoring prompts."""
    title = _bounded(cluster.title, SAMPLE_TITLE_MAX_CHARS) or cluster.type
    detail = _bounded(cluster.description, DRAFT_SUMMARY_MAX_CHARS)
    summary = f" | description: {detail}" if detail else ""
    return (
        f"Cluster: type={cluster.type} | title: {title}{summary} | "
        f"members={stats.member_count} | signatureOverlap={stats.signature_overlap:.2f} | "
        f"timeSpanDays={_render_span(stats.time_span_days)}"
    )


def _render_sample(sample: ClusterCaseEvidence) -> str:
    """Render one bounded sample line: id, title, and text only."""
    title = _bounded(sample.title, SAMPLE_TITLE_MAX_CHARS) or "(untitled)"
    text = _bounded(sample.text, SAMPLE_TEXT_MAX_CHARS)
    suffix = f" | text: {text}" if text else ""
    return f"- {sample.case_id} | title: {title}{suffix}"


def _render_span(days: int | None) -> str:
    """Render the time-span statistic without inventing a value."""
    return str(days) if days is not None else "unknown"


def _evenly_spaced_indexes(total: int, count: int) -> tuple[int, ...]:
    """Return ``count`` strictly increasing indexes spread over ``total`` items."""
    if count >= total:
        return tuple(range(total))
    selected: list[int] = []
    for position in range(count):
        index = round(position * (total - 1) / (count - 1))
        if not selected or index > selected[-1]:
            selected.append(index)
    return tuple(selected)


def _elapsed_ms(started: float) -> int:
    """Return the measured wall-clock duration in whole milliseconds."""
    return max(0, round((time.perf_counter() - started) * 1_000))


def _failure_record(task: str, agent: AIAgentProvider, elapsed_ms: int) -> CallRecord:
    """Build the observability record for a call that raised before returning."""
    return CallRecord(
        task=task,
        provider_id=agent.provider_id,
        model="unknown",
        input_tokens=0,
        output_tokens=0,
        cost_usd=0.0,
        latency_ms=elapsed_ms,
        outcome="error",
        session_id=None,
    )


def _result_record(
    task: str,
    result: AnalysisResult,
    outcome: Literal["ok", "degraded"],
    elapsed_ms: int,
) -> CallRecord:
    """Build the observability record for a call that returned a result."""
    return CallRecord(
        task=task,
        provider_id=result.provider_id,
        model=result.usage.model,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        cost_usd=result.usage.cost_usd,
        latency_ms=result.latency_ms or elapsed_ms,
        outcome=outcome,
        session_id=result.session_id,
    )


def _provider_reason(exc: BaseException) -> str:
    """Render one bounded, sanitized provider failure reason."""
    if isinstance(exc, AgentProviderError):
        return _bounded(f"{type(exc).__name__}: {exc.message}", MAX_REASON_CHARS)
    return _bounded(f"{type(exc).__name__} raised during analysis", MAX_REASON_CHARS)


def _contract_reason(exc: ValidationError | ClusterContractError) -> str:
    """Render one bounded contract violation without echoing raw output."""
    if isinstance(exc, ClusterContractError):
        return exc.reason
    parts = [
        ".".join(str(part) for part in error["loc"]) or "<root>"
        for error in exc.errors(include_url=False, include_input=False)
    ]
    return _bounded(f"output failed schema: {', '.join(parts)}", MAX_REASON_CHARS)


async def _notify_call(callback: RecordCall | None, call: CallRecord) -> None:
    """Deliver one call record without letting an observer break the run."""
    if callback is None:
        return
    try:
        await callback(call)
    except Exception:
        logger.exception("failed to record ai_agent_call", extra={"task": call.task})


async def _notify_degraded(callback: RecordDegraded | None, item: DegradedCall) -> None:
    """Deliver one degradation record without letting an observer break the run."""
    if callback is None:
        return
    try:
        await callback(item)
    except Exception:
        logger.exception("failed to record degraded call", extra={"task": item.task})


def _bounded(text: str, limit: int) -> str:
    """Collapse whitespace and truncate one rendered string with an ellipsis."""
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


__all__ = [
    "CLUSTER_KEY_PREFIX",
    "CLUSTER_SCORE_TASK",
    "DRAFT_KEY_PREFIX",
    "DRAFT_SUMMARY_MAX_CHARS",
    "DRAFT_SUMMARY_TOKENS",
    "EVIDENCE_REF_ALIAS",
    "MAX_PROMPT_SAMPLES",
    "REVIEW_SAMPLES_MAX",
    "REVIEW_SAMPLES_MIN",
    "REVIEW_TASK",
    "SEVERITY_DIMENSIONS",
    "SEVERITY_SCORE_TASK",
    "CallRecord",
    "ClusterCaseEvidence",
    "ClusterContractError",
    "ClusterDraftStats",
    "ClusterPlan",
    "ClusterReviewItem",
    "ClusterReviewOutput",
    "ClusterScoreItem",
    "ClusterScoresOutput",
    "ClusterSummary",
    "DegradedCall",
    "EnhancedCluster",
    "EnhancedClusters",
    "SeverityScoreItem",
    "SeverityScoresOutput",
    "build_cluster_score_request",
    "build_review_request",
    "build_severity_request",
    "enhance_clusters",
    "select_samples",
    "validate_cluster_scores",
    "validate_evidence_refs",
    "validate_review_partition",
    "validate_severity_scores",
]
