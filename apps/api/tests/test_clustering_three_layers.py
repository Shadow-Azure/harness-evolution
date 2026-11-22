"""Three-layer clustering: review partition gate, isolated scoring, degradation.

The unit tests pin the task contracts, the prompt bounds, and the three
independent degradation paths. The prepare tests pin the wiring: the hybrid
algorithm identity in ``run.stats`` and the ``clusters_created`` payload, the
``ai_agent_call``/``degraded`` events, and the untouched legacy lexical path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import update

from app.db.crud.attributions import AttributionRepository, EvolutionRunCandidateRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.models.domain import bad_cases
from app.db.models.jobs import JobRunRecord
from app.service.evolution.attribution import AttributionRunner, RuleBasedEngine
from app.service.evolution.cluster import (
    HYBRID_ALGORITHM,
    LEXICAL_ALGORITHM,
    TYPE_CONFIDENCE,
    ClusterDraft,
    ClusterType,
    cluster_severity,
)
from app.service.evolution.cluster_llm import (
    CLUSTER_KEY_PREFIX,
    CLUSTER_SCORE_TASK,
    REVIEW_TASK,
    SEVERITY_SCORE_TASK,
    CallRecord,
    ClusterCaseEvidence,
    ClusterContractError,
    ClusterDraftStats,
    ClusterPlan,
    ClusterReviewOutput,
    ClusterSummary,
    DegradedCall,
    EnhancedClusters,
    build_cluster_score_request,
    build_review_request,
    build_severity_request,
    enhance_clusters,
    select_samples,
    validate_review_partition,
)
from app.service.evolution.events import EvolutionRunEventStage, EvolutionRunEventType
from app.service.evolution.prepare import EvolutionPrepareService
from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.ai_agent.contracts import (
    AgentProviderError,
    AgentUsage,
    AnalysisRequest,
    AnalysisResult,
    EditRequest,
    EditResult,
    ProviderHealth,
)
from app.third_party_api.ai_agent.fake import FakeAIAgentProvider
from app.third_party_api.git.workspace import PreparedWorkspace
from app.utils.time import SHANGHAI
from tests.m10_02_potential_support import (
    NOW,
    TARGET_NAME,
    TARGET_VERSION,
    WORKSPACE_A,
    Harness,
    harness,
    seed_case,
    seed_event,
    seed_session,
)

__all__ = ["harness"]


RUN_ID = "run-three-layers"
SESSION_ID = "session-three-layers"

_REVIEW_MERGED = {
    "clusters": [
        {
            "from": ["D1", "D2"],
            "title": "检索索引问题",
            "description": "同一失败点",
        },
    ],
}
_REVIEW_IDENTITY = {
    "clusters": [
        {"from": ["D1"], "title": "检索索引问题"},
        {"from": ["D2"], "title": "工具调用超时"},
    ],
}
_CLUSTER_SCORE_MERGED = {
    "scores": [
        {"cluster": "C1", "confidence": 0.9, "evidence_refs": ["c-1", "c-2"]},
    ],
}
_CLUSTER_SCORE_TWO = {
    "scores": [
        {"cluster": "C1", "confidence": 0.8, "evidence_refs": []},
        {"cluster": "C2", "confidence": 0.6, "evidence_refs": []},
    ],
}
_SEVERITY_ITEM = {
    "overall": 8.6,
    "dimensions": {
        "impact": 9.0,
        "scope": 7.0,
        "reproducibility": 8.0,
        "evidence_directness": 9.0,
        "blast_radius": 6.0,
    },
    "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
}
_SEVERITY_OK = {"severities": [{"cluster": "C1", **_SEVERITY_ITEM}]}
_SEVERITY_TWO = {
    "severities": [
        {"cluster": "C1", **_SEVERITY_ITEM},
        {
            "cluster": "C2",
            "overall": 4.2,
            "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L",
        },
    ],
}


class _RawProvider(AIAgentProvider):
    """Return caller-supplied mappings without schema validation.

    The fake validates against the caller model, so it cannot exercise the
    service's own boundary validation; this stub returns raw output and lets a
    task raise a chosen exception.
    """

    provider_id = "raw"

    def __init__(
        self,
        outputs: Mapping[str, Mapping[str, Any]],
        *,
        failures: Mapping[str, BaseException] | None = None,
    ) -> None:
        """Bind fixed outputs and optional per-task exceptions."""
        super().__init__(None)
        self._outputs = {task: dict(output) for task, output in outputs.items()}
        self._failures = dict(failures or {})
        self.requests: list[AnalysisRequest] = []

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Return the bound mapping or raise the bound failure."""
        self.requests.append(request)
        failure = self._failures.get(request.task)
        if failure is not None:
            raise failure
        return AnalysisResult(
            output=self._outputs[request.task],
            provider_id=self.provider_id,
            usage=AgentUsage(
                model="raw-model",
                input_tokens=11,
                output_tokens=7,
                cost_usd=0.002,
            ),
            session_id="raw-session",
            latency_ms=13,
        )

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Reject unexpected edit work in these tests."""
        raise NotImplementedError("edit_workspace is not part of the clustering path")

    async def health_check(self) -> ProviderHealth:
        """Report a healthy deterministic stub."""
        return ProviderHealth(provider_id=self.provider_id, healthy=True, latency_ms=0)


def _draft(
    description: str,
    probes: tuple[str, ...],
    cluster_type: ClusterType = "prompt",
) -> ClusterDraft:
    """Build one lexical draft for the orchestration tests."""
    return ClusterDraft(type=cluster_type, description=description, probes=probes)


def _drafts_pair() -> tuple[ClusterDraft, ...]:
    """Return two same-type drafts whose review may merge them."""
    return (
        _draft("prompt 类问题 · 检索索引读取失败", ("p-1", "p-2")),
        _draft("prompt 类问题 · 工具调用超时", ("p-3",)),
    )


def _evidence_map() -> dict[str, ClusterCaseEvidence]:
    """Return deterministic case evidence for the two drafts."""
    return {
        "c-1": ClusterCaseEvidence(
            case_id="c-1",
            title="检索索引读取失败",
            text="失败详情",
            reported_at=NOW,
        ),
        "c-2": ClusterCaseEvidence(
            case_id="c-2",
            title="检索索引读取超时",
            text="超时详情",
            reported_at=NOW + timedelta(days=2),
        ),
        "c-3": ClusterCaseEvidence(
            case_id="c-3",
            title="工具调用超时",
            text="工具超时",
            reported_at=NOW + timedelta(days=4),
        ),
    }


def _stats() -> dict[int, ClusterDraftStats]:
    """Return the per-draft statistics the prepare layer would gather."""
    return {
        0: ClusterDraftStats(case_ids=("c-1", "c-2"), signature_overlap=0.5, time_span_days=2),
        1: ClusterDraftStats(case_ids=("c-3",)),
    }


def _fake_with(
    outputs: Mapping[str, Mapping[str, Any]] | None = None,
) -> FakeAIAgentProvider:
    """Build the fake with explicit per-task outputs."""
    return FakeAIAgentProvider(outputs=outputs)


async def _enhance(
    provider: AIAgentProvider,
) -> tuple[EnhancedClusters, list[CallRecord], list[DegradedCall]]:
    """Run the orchestrator while capturing the observability callbacks."""
    calls: list[CallRecord] = []
    degraded: list[DegradedCall] = []

    async def record_call(call: CallRecord) -> None:
        calls.append(call)

    async def record_degraded(item: DegradedCall) -> None:
        degraded.append(item)

    result = await enhance_clusters(
        provider,
        _drafts_pair(),
        _evidence_map(),
        stats_by_draft=_stats(),
        record_call=record_call,
        record_degraded=record_degraded,
    )
    return result, calls, degraded


def _scale_fixture(
    total: int,
) -> tuple[tuple[ClusterDraft, ...], dict[str, ClusterCaseEvidence], dict[int, ClusterDraftStats]]:
    """Build N members over the same three drafts with fixed-width rendering."""
    per_draft = total // 3
    sizes = (total - 2 * per_draft, per_draft, per_draft)
    case_ids = [f"case-{index:04d}" for index in range(1, total + 1)]
    drafts: list[ClusterDraft] = []
    evidence: dict[str, ClusterCaseEvidence] = {}
    stats: dict[int, ClusterDraftStats] = {}
    offset = 0
    for index, size in enumerate(sizes):
        members = case_ids[offset : offset + size]
        offset += size
        drafts.append(
            _draft(f"prompt 类问题 · 组{index}", tuple(f"p-{member}" for member in members)),
        )
        for case_id in members:
            evidence[case_id] = ClusterCaseEvidence(
                case_id=case_id,
                title="标题占位",
                text="描述占位",
                reported_at=NOW,
            )
        stats[index] = ClusterDraftStats(
            case_ids=tuple(members),
            signature_overlap=0.42,
            time_span_days=21,
        )
    return tuple(drafts), evidence, stats


def _plans_from_fixture(total: int) -> tuple[ClusterPlan, ...]:
    """Build the final-cluster plans the batch scoring prompts receive."""
    drafts, evidence, stats = _scale_fixture(total)
    return tuple(
        ClusterPlan(
            key=f"{CLUSTER_KEY_PREFIX}{index + 1}",
            summary=ClusterSummary(
                type=draft.type,
                title=draft.description,
                description="",
                member_count=stats[index].member_count,
            ),
            members=select_samples(stats[index].case_ids, evidence),
            stats=stats[index],
        )
        for index, draft in enumerate(drafts)
    )


def test_review_prompt_uses_draft_keys_and_bounded_samples() -> None:
    """The review prompt carries keys, statistics, one summary, and 3-5 samples."""
    drafts, evidence, stats = _scale_fixture(50)

    request = build_review_request(drafts, evidence, stats_by_draft=stats)

    assert request.task == REVIEW_TASK
    assert request.output_model is ClusterReviewOutput
    for index in range(1, len(drafts) + 1):
        assert f"[D{index}]" in request.prompt
    assert "members=18" in request.prompt
    assert "signatureOverlap=0.42" in request.prompt
    assert "timeSpanDays=21" in request.prompt
    assert "summary: prompt 类问题 · 组0" in request.prompt
    assert request.prompt.count("- case-") == 3 * 5
    assert "case-0001" in request.prompt


def test_score_prompts_are_bounded_and_decoupled_from_case_volume() -> None:
    """Both batch scoring prompts keep 3x5 samples and equal length at N=50/200."""
    small = _plans_from_fixture(50)
    large = _plans_from_fixture(200)

    for builder in (build_cluster_score_request, build_severity_request):
        small_request = builder(small)
        large_request = builder(large)
        assert large_request.prompt.count("Samples (") == 3
        assert large_request.prompt.count("- case-") == 3 * 5
        assert len(large_request.prompt) == len(small_request.prompt)
        for index in range(1, len(large) + 1):
            assert f"[C{index}]" in large_request.prompt


def test_review_prompt_length_is_decoupled_from_the_case_volume() -> None:
    """N=200 and N=50 with the same three drafts produce the same prompt size."""
    small_drafts, small_evidence, small_stats = _scale_fixture(50)
    large_drafts, large_evidence, large_stats = _scale_fixture(200)

    small = build_review_request(small_drafts, small_evidence, stats_by_draft=small_stats)
    large = build_review_request(large_drafts, large_evidence, stats_by_draft=large_stats)

    assert len(large.prompt) == len(small.prompt)
    assert large.prompt.count("- case-") == 15
    assert large.prompt.count("title:") == 15
    assert large.prompt.count("case-") == 15


def test_select_samples_is_deterministic_by_case_id() -> None:
    """Shuffled input ids select the same sorted, evenly-spaced sample."""
    evidence = {
        f"c-{index}": ClusterCaseEvidence(case_id=f"c-{index}", title=f"t{index}")
        for index in range(10)
    }

    first = select_samples([f"c-{index}" for index in range(10)], evidence)
    second = select_samples([f"c-{index}" for index in range(9, -1, -1)], evidence)

    assert first == second
    assert len(first) == 5
    assert [sample.case_id for sample in first] == ["c-0", "c-2", "c-4", "c-7", "c-9"]


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ({"clusters": [{"from": ["D1"], "title": "仅一个"}]}, "dropped draft keys D2"),
        (
            {
                "clusters": [
                    {"from": ["D1", "D2"], "title": "合并"},
                    {"from": ["D1"], "title": "重复"},
                ],
            },
            "merge-only",
        ),
        ({"clusters": [{"from": ["D1", "D9"], "title": "未知键"}]}, "unknown draft key"),
    ],
)
def test_review_partition_violations_are_rejected(
    payload: Mapping[str, Any],
    fragment: str,
) -> None:
    """Every draft key must appear exactly once and no unknown key may appear."""
    output = ClusterReviewOutput.model_validate(payload)

    with pytest.raises(ClusterContractError) as caught:
        validate_review_partition(output, _drafts_pair())

    assert fragment in caught.value.reason


def test_review_rejects_empty_titles_and_cross_type_merges() -> None:
    """Naming is required and a cluster always keeps exactly one type."""
    masked = ClusterReviewOutput.model_validate(
        {"clusters": [{"from": ["D1", "D2"], "title": "   "}]},
    )
    with pytest.raises(ClusterContractError, match="empty title"):
        validate_review_partition(masked, _drafts_pair())

    cross_type = (
        _draft("prompt 类问题 · A", ("p-1",)),
        _draft("error 类问题 · B", ("p-2",), cluster_type="error"),
    )
    merged = ClusterReviewOutput.model_validate(
        {"clusters": [{"from": ["D1", "D2"], "title": "混类"}]},
    )
    with pytest.raises(ClusterContractError, match="different types"):
        validate_review_partition(merged, cross_type)


def test_review_output_rejects_an_empty_partition() -> None:
    """An empty cluster list can never be a partition of the input drafts."""
    with pytest.raises(ValidationError):
        ClusterReviewOutput.model_validate({"clusters": []})


async def test_review_merge_names_expands_members_and_scores() -> None:
    """A valid merge is named by the LLM and expanded by code, then batch scored."""
    provider = _fake_with(
        {
            REVIEW_TASK: _REVIEW_MERGED,
            CLUSTER_SCORE_TASK: _CLUSTER_SCORE_MERGED,
            SEVERITY_SCORE_TASK: _SEVERITY_OK,
        },
    )

    result, calls, degraded = await _enhance(provider)

    assert degraded == []
    assert result.algorithm == HYBRID_ALGORITHM
    assert len(result.clusters) == 1
    cluster = result.clusters[0]
    assert cluster.type == "prompt"
    assert cluster.description == "prompt 类问题 · 检索索引问题 · 同一失败点"
    assert cluster.probes == ("p-1", "p-2", "p-3")
    assert cluster.impact == 7.0
    assert cluster.confidence == 0.9
    assert cluster.severity == 8.6
    assert cluster.formula_severity == cluster_severity("prompt", 3)
    assert cluster.evidence_refs == ("c-1", "c-2")
    assert cluster.vector == _SEVERITY_ITEM["vector"]
    assert dict(cluster.dimensions)["impact"] == 9.0
    assert [call.task for call in result.calls] == [
        REVIEW_TASK,
        CLUSTER_SCORE_TASK,
        SEVERITY_SCORE_TASK,
    ]
    assert [call.outcome for call in result.calls] == ["ok", "ok", "ok"]
    assert result.calls == tuple(calls)
    assert calls[0].provider_id == "fake"
    assert calls[0].model == "fake"
    assert calls[0].session_id == "fake-session"


async def test_two_final_clusters_still_cost_exactly_three_calls() -> None:
    """Batch scoring keeps one call per task regardless of the cluster count."""
    provider = _fake_with(
        {
            REVIEW_TASK: _REVIEW_IDENTITY,
            CLUSTER_SCORE_TASK: _CLUSTER_SCORE_TWO,
            SEVERITY_SCORE_TASK: _SEVERITY_TWO,
        },
    )

    result, calls, degraded = await _enhance(provider)

    assert degraded == []
    assert [call.task for call in calls] == [
        REVIEW_TASK,
        CLUSTER_SCORE_TASK,
        SEVERITY_SCORE_TASK,
    ]
    assert [call.outcome for call in calls] == ["ok", "ok", "ok"]
    assert [cluster.confidence for cluster in result.clusters] == [0.8, 0.6]
    assert [cluster.severity for cluster in result.clusters] == [8.6, 4.2]


async def test_review_provider_failure_degrades_the_whole_batch() -> None:
    """A raising review call falls back to the drafts and still batch scores them."""
    provider = _RawProvider(
        {
            CLUSTER_SCORE_TASK: _CLUSTER_SCORE_TWO,
            SEVERITY_SCORE_TASK: _SEVERITY_TWO,
        },
        failures={
            REVIEW_TASK: AgentProviderError(
                "review backend unavailable",
                retryable=True,
                provider_id="raw",
            ),
        },
    )

    result, calls, degraded = await _enhance(provider)

    assert [cluster.description for cluster in result.clusters] == [
        "prompt 类问题 · 检索索引读取失败",
        "prompt 类问题 · 工具调用超时",
    ]
    assert [call.outcome for call in result.calls] == ["error", "ok", "ok"]
    assert calls[0].task == REVIEW_TASK
    assert calls[0].model == "unknown"
    assert degraded[0].task == REVIEW_TASK
    assert "AgentProviderError" in degraded[0].reason
    assert result.calls == tuple(calls)


@pytest.mark.parametrize(
    ("review_output", "fragment"),
    [
        ({"clusters": [{"from": ["D1"], "title": "只留一个"}]}, "dropped draft keys D2"),
        (
            {
                "clusters": [
                    {"from": ["D1", "D2"], "title": "合并"},
                    {"from": ["D1"], "title": "重复"},
                ],
            },
            "merge-only",
        ),
        ({"clusters": [{"from": ["D1", "D9"], "title": "未知键"}]}, "unknown draft key"),
    ],
)
async def test_review_partition_violation_degrades_and_records_events(
    review_output: Mapping[str, Any],
    fragment: str,
) -> None:
    """A partition violation degrades the batch instead of partially accepting it."""
    provider = _fake_with(
        {
            REVIEW_TASK: review_output,
            CLUSTER_SCORE_TASK: _CLUSTER_SCORE_TWO,
            SEVERITY_SCORE_TASK: _SEVERITY_TWO,
        },
    )

    result, calls, degraded = await _enhance(provider)

    assert len(result.clusters) == 2
    assert result.clusters[0].probes == ("p-1", "p-2")
    assert result.clusters[1].probes == ("p-3",)
    assert result.clusters[0].description == "prompt 类问题 · 检索索引读取失败"
    assert calls[0].outcome == "degraded"
    assert degraded[0].task == REVIEW_TASK
    assert fragment in degraded[0].reason
    assert len(calls) == 3


async def test_cluster_score_failure_keeps_the_formula_confidence_only() -> None:
    """A failed confidence call falls back to the category constant."""
    provider = _RawProvider(
        {
            REVIEW_TASK: _REVIEW_MERGED,
            SEVERITY_SCORE_TASK: _SEVERITY_OK,
        },
        failures={
            CLUSTER_SCORE_TASK: AgentProviderError(
                "score backend unavailable",
                retryable=True,
                provider_id="raw",
            ),
        },
    )

    result, _, degraded = await _enhance(provider)

    cluster = result.clusters[0]
    assert cluster.confidence == TYPE_CONFIDENCE["prompt"]
    assert cluster.severity == 8.6
    assert cluster.evidence_refs == ()
    assert [item.task for item in degraded] == [CLUSTER_SCORE_TASK]


async def test_cluster_score_invalid_payload_degrades_that_score_only() -> None:
    """An out-of-range confidence degrades only the confidence value."""
    provider = _RawProvider(
        {
            REVIEW_TASK: _REVIEW_MERGED,
            CLUSTER_SCORE_TASK: {
                "scores": [{"cluster": "C1", "confidence": 1.5, "evidence_refs": []}],
            },
            SEVERITY_SCORE_TASK: _SEVERITY_OK,
        },
    )

    result, calls, degraded = await _enhance(provider)

    cluster = result.clusters[0]
    assert cluster.confidence == TYPE_CONFIDENCE["prompt"]
    assert cluster.severity == 8.6
    assert calls[1].outcome == "degraded"
    assert degraded[0].task == CLUSTER_SCORE_TASK
    assert "output failed schema" in degraded[0].reason


async def test_cluster_score_batch_coverage_violation_degrades_every_confidence() -> None:
    """A batch missing one cluster key falls back for every cluster, not one."""
    provider = _fake_with(
        {
            REVIEW_TASK: _REVIEW_IDENTITY,
            CLUSTER_SCORE_TASK: {
                "scores": [{"cluster": "C1", "confidence": 0.9, "evidence_refs": []}],
            },
            SEVERITY_SCORE_TASK: _SEVERITY_TWO,
        },
    )

    result, calls, degraded = await _enhance(provider)

    assert [cluster.confidence for cluster in result.clusters] == [
        TYPE_CONFIDENCE["prompt"],
        TYPE_CONFIDENCE["prompt"],
    ]
    assert [cluster.severity for cluster in result.clusters] == [8.6, 4.2]
    assert calls[1].outcome == "degraded"
    assert [item.task for item in degraded] == [CLUSTER_SCORE_TASK]
    assert "dropped final-cluster keys C2" in degraded[0].reason


async def test_severity_batch_coverage_violation_degrades_every_severity() -> None:
    """A severity batch missing one key falls back for every cluster, not one."""
    provider = _fake_with(
        {
            REVIEW_TASK: _REVIEW_IDENTITY,
            CLUSTER_SCORE_TASK: _CLUSTER_SCORE_TWO,
            SEVERITY_SCORE_TASK: {
                "severities": [{"cluster": "C1", **_SEVERITY_ITEM}],
            },
        },
    )

    result, calls, degraded = await _enhance(provider)

    assert [cluster.confidence for cluster in result.clusters] == [0.8, 0.6]
    assert [cluster.severity for cluster in result.clusters] == [
        cluster_severity("prompt", 2),
        cluster_severity("prompt", 1),
    ]
    assert calls[2].outcome == "degraded"
    assert [item.task for item in degraded] == [SEVERITY_SCORE_TASK]
    assert "dropped final-cluster keys C2" in degraded[0].reason


async def test_evidence_refs_must_belong_to_the_same_cluster_batch() -> None:
    """A cluster may only cite its own prompt samples; the batch degrades otherwise."""
    provider = _fake_with(
        {
            REVIEW_TASK: _REVIEW_IDENTITY,
            CLUSTER_SCORE_TASK: {
                "scores": [
                    {"cluster": "C1", "confidence": 0.9, "evidence_refs": ["c-3"]},
                    {"cluster": "C2", "confidence": 0.7, "evidence_refs": []},
                ],
            },
            SEVERITY_SCORE_TASK: _SEVERITY_TWO,
        },
    )

    result, _, degraded = await _enhance(provider)

    assert [cluster.confidence for cluster in result.clusters] == [
        TYPE_CONFIDENCE["prompt"],
        TYPE_CONFIDENCE["prompt"],
    ]
    assert "cluster.score [C1]" in degraded[0].reason
    assert "outside the prompt samples" in degraded[0].reason


async def test_severity_failure_keeps_the_llm_confidence_and_formula_severity() -> None:
    """The two batch score calls are isolated; severity alone may fall back."""
    provider = _fake_with(
        {
            REVIEW_TASK: _REVIEW_MERGED,
            CLUSTER_SCORE_TASK: {
                "scores": [
                    {"cluster": "C1", "confidence": 0.88, "evidence_refs": ["c-1"]},
                ],
            },
            SEVERITY_SCORE_TASK: {
                "severities": [
                    {"cluster": "C1", "overall": 11.0, "vector": "CVSS:3.1/AV:N"},
                ],
            },
        },
    )

    result, calls, degraded = await _enhance(provider)

    cluster = result.clusters[0]
    assert cluster.confidence == 0.88
    assert cluster.severity == cluster_severity("prompt", 3)
    assert cluster.formula_severity == cluster.severity
    assert cluster.vector is None
    assert dict(cluster.dimensions) == {}
    assert [item.task for item in degraded] == [SEVERITY_SCORE_TASK]
    assert calls[2].outcome == "error"


async def test_evidence_refs_outside_the_prompt_samples_degrade_that_score() -> None:
    """Citing a case id that was not in the prompt is a contract violation."""
    provider = _RawProvider(
        {
            REVIEW_TASK: _REVIEW_MERGED,
            CLUSTER_SCORE_TASK: {
                "scores": [{"cluster": "C1", "confidence": 0.9, "evidence_refs": ["c-999"]}],
            },
            SEVERITY_SCORE_TASK: _SEVERITY_OK,
        },
    )

    result, calls, degraded = await _enhance(provider)

    cluster = result.clusters[0]
    assert cluster.confidence == TYPE_CONFIDENCE["prompt"]
    assert cluster.severity == 8.6
    assert calls[1].outcome == "degraded"
    assert "outside the prompt samples" in degraded[0].reason
    assert [item.task for item in degraded] == [CLUSTER_SCORE_TASK]


async def test_empty_drafts_short_circuit_without_a_call() -> None:
    """No drafts means no prompt and no provider call."""
    calls: list[CallRecord] = []

    async def record_call(call: CallRecord) -> None:
        calls.append(call)

    result = await enhance_clusters(
        _fake_with(),
        (),
        {},
        stats_by_draft={},
        record_call=record_call,
    )

    assert result.clusters == ()
    assert result.algorithm == HYBRID_ALGORITHM
    assert result.calls == ()
    assert calls == []


@dataclass(frozen=True, slots=True)
class _RecordedEvent:
    """One prepare event captured for payload assertions."""

    event_type: str
    stage: str
    payload: Mapping[str, Any] | None


class RecordingEvents:
    """Capture prepare events without touching the event table."""

    def __init__(self) -> None:
        """Start with no recorded events."""
        self.records: list[_RecordedEvent] = []

    async def record(
        self,
        run_id: str,
        event_type: EvolutionRunEventType,
        *,
        level: str,
        stage: EvolutionRunEventStage,
        message: str,
        step_index: int | None = None,
        cluster_id: str | None = None,
        round_id: str | None = None,
        job_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        error: BaseException | None = None,
    ) -> object:
        """Keep the event fields the clustering contract needs."""
        del run_id, level, message, step_index, cluster_id, round_id, job_id, error
        self.records.append(
            _RecordedEvent(event_type=str(event_type), stage=str(stage), payload=payload),
        )
        return object()


class UnusedWorkspacePreparer:
    """Fail if a cluster-only run tries to prepare a git workspace."""

    async def prepare(self, run: object) -> PreparedWorkspace:
        """Reject unexpected workspace work."""
        del run
        raise AssertionError("cluster-only prepare must not touch git")


class _FailingProvider(AIAgentProvider):
    """Stand in for the claude-code placeholder: every analysis call fails."""

    provider_id = "claude-code"

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Fail exactly like the unimplemented real backend."""
        raise NotImplementedError(f"{request.task} is not implemented")

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Fail exactly like the unimplemented real backend."""
        raise NotImplementedError("edit is not implemented")

    async def health_check(self) -> ProviderHealth:
        """Report the reserved backend as unhealthy."""
        return ProviderHealth(provider_id=self.provider_id, healthy=False, latency_ms=0)


def _job() -> JobRunRecord:
    """Build one evolution_prepare job row for the service under test."""
    now = datetime(2026, 11, 22, 9, 0, tzinfo=SHANGHAI)
    return JobRunRecord(
        id="job-three-layers",
        kind="evolution_prepare",
        ref_id=RUN_ID,
        status="running",
        progress=0.0,
        executor="test",
        external_job_id=None,
        attempt=1,
        payload={"runId": RUN_ID},
        result=None,
        error=None,
        created_by=None,
        created_at=now,
        started_at=now,
        finished_at=None,
        updated_at=now,
    )


async def _create_cluster_only_run(harness: Harness) -> None:
    """Insert one cluster-only run snapshot over the shared workspace fixture."""
    await EvolutionRepository(harness.database).create_run(
        {
            "id": RUN_ID,
            "title": f"{TARGET_NAME} {TARGET_VERSION} 聚类预览",
            "workspace_id": WORKSPACE_A,
            "mode": "cluster_only",
            "engine_key": "cluster_only",
            "eval_config": {},
            "potential_policy": {"preset": "default"},
            "cache_enabled": True,
            "attribution_engine": "rule-v1",
            "target_config_id": None,
            "target_type": "skill",
            "target_name": TARGET_NAME,
            "target_version": TARGET_VERSION,
            "repo_url": "https://example.invalid/deep-research.git",
            "sub_dir": "skills/deep-research",
            "window_from": date(2026, 11, 1),
            "window_to": date(2026, 11, 30),
            "models": ["glm-5.3"],
            "status": "preparing",
        },
    )


async def _seed_titled_cases(harness: Harness) -> None:
    """Seed three self-reported cases whose titles form two lexical drafts."""
    main = await seed_session(
        harness.database,
        session_id=SESSION_ID,
        started_at=NOW,
        title="three layers 聚类",
    )
    await seed_event(
        harness.database,
        agent_id=main,
        event_index=1,
        kind="skill",
        name=TARGET_NAME,
        object_version=TARGET_VERSION,
        triggered_at=NOW,
    )
    titles = {
        "case-three-layers-a": "检索索引读取失败",
        "case-three-layers-b": "检索索引读取超时",
        "case-three-layers-c": "工具调用超时",
    }
    for case_id in titles:
        await seed_case(
            harness.database,
            case_id=case_id,
            session_id=SESSION_ID,
            case_type="self",
            agent_id=main,
        )
    async with harness.database.transaction() as session:
        for case_id, title in titles.items():
            await session.execute(
                update(bad_cases)
                .where(bad_cases.c.bad_case_id == case_id)
                .values(title=title, bad_case_description=title),
            )


def _service(
    harness: Harness,
    events: RecordingEvents,
    agent: AIAgentProvider | None = None,
) -> EvolutionPrepareService:
    """Compose the prepare service with an optional agent over the test database."""
    attributions = AttributionRepository(harness.database)
    return EvolutionPrepareService(
        EvolutionRepository(harness.database),
        EvolutionRunCandidateRepository(harness.database),
        attributions,
        harness.matcher,
        AttributionRunner(attributions, engine_factory=lambda _key: RuleBasedEngine()),
        UnusedWorkspacePreparer(),
        events,
        agent=agent,
    )


async def test_prepare_hybrid_persists_llm_values_and_records_calls(
    harness: Harness,
) -> None:
    """A fake provider produces the hybrid identity, LLM values, and both events."""
    await _seed_titled_cases(harness)
    await _create_cluster_only_run(harness)
    events = RecordingEvents()
    provider = _fake_with(
        {
            REVIEW_TASK: _REVIEW_MERGED,
            CLUSTER_SCORE_TASK: {
                "scores": [
                    {
                        "cluster": "C1",
                        "confidence": 0.91,
                        "evidence_refs": ["case-three-layers-a"],
                    },
                ],
            },
            SEVERITY_SCORE_TASK: _SEVERITY_OK,
        },
    )

    await _service(harness, events, provider).handle(_job())

    runs = EvolutionRepository(harness.database)
    run = await runs.get_run(RUN_ID)
    assert run is not None
    assert run.progress_unit == 5
    assert run.status == "completed"
    assert (run.stats or {}).get("clusterAlgorithm") == HYBRID_ALGORITHM

    clusters = await runs.list_clusters(RUN_ID)
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.probe_cluster_type == "prompt"
    assert cluster.probe_cluster_description == "prompt 类问题 · 检索索引问题 · 同一失败点"
    assert cluster.confidence == pytest.approx(0.91)
    assert cluster.severity == pytest.approx(8.6)
    assert cluster.impact == pytest.approx(7.0)
    assert cluster.rank == 1

    created = next(event for event in events.records if event.event_type == "clusters_created")
    assert created.payload is not None
    assert created.payload["algorithm"] == HYBRID_ALGORITHM
    comparison = created.payload["severityFormula"]
    assert isinstance(comparison, list)
    assert len(comparison) == 1
    assert comparison[0]["severityFormula"] == cluster_severity("prompt", 3)
    assert comparison[0]["severity"] == pytest.approx(8.6)
    assert len(str(comparison[0]["clusterHash"])) == 64
    assert comparison[0]["vector"] == _SEVERITY_ITEM["vector"]
    assert comparison[0]["dimensions"] == _SEVERITY_ITEM["dimensions"]

    calls = [event for event in events.records if event.event_type == "ai_agent_call"]
    assert [event.payload["task"] for event in calls if event.payload] == [
        REVIEW_TASK,
        CLUSTER_SCORE_TASK,
        SEVERITY_SCORE_TASK,
    ]
    assert all(event.stage == "cluster" for event in calls)
    payload = calls[0].payload
    assert payload is not None
    assert payload["provider"] == "fake"
    assert payload["model"] == "fake"
    assert payload["outcome"] == "ok"
    assert payload["sessionId"] == "fake-session"
    assert {"inputTokens", "outputTokens", "costUsd", "latencyMs"} <= set(payload)
    assert [event for event in events.records if event.event_type == "degraded"] == []


async def test_prepare_without_agent_keeps_the_lexical_path(harness: Harness) -> None:
    """No agent means lexical identity, formula values, and no AI events."""
    await _seed_titled_cases(harness)
    await _create_cluster_only_run(harness)
    events = RecordingEvents()

    await _service(harness, events).handle(_job())

    runs = EvolutionRepository(harness.database)
    run = await runs.get_run(RUN_ID)
    assert run is not None
    assert (run.stats or {}).get("clusterAlgorithm") == LEXICAL_ALGORITHM
    clusters = await runs.list_clusters(RUN_ID)
    assert len(clusters) == 2
    assert all(cluster.confidence == pytest.approx(0.74) for cluster in clusters)
    created = next(event for event in events.records if event.event_type == "clusters_created")
    assert created.payload is not None
    assert created.payload["algorithm"] == LEXICAL_ALGORITHM
    assert "severityFormula" not in created.payload
    assert [event for event in events.records if event.event_type == "ai_agent_call"] == []
    assert [event for event in events.records if event.event_type == "degraded"] == []


async def test_prepare_degrades_gracefully_when_every_call_fails(
    harness: Harness,
) -> None:
    """A backend that raises (like the claude-code placeholder) never blocks a run."""
    await _seed_titled_cases(harness)
    await _create_cluster_only_run(harness)
    events = RecordingEvents()

    await _service(harness, events, _FailingProvider()).handle(_job())

    runs = EvolutionRepository(harness.database)
    run = await runs.get_run(RUN_ID)
    assert run is not None
    assert run.progress_unit == 5
    assert run.status == "completed"
    assert (run.stats or {}).get("clusterAlgorithm") == HYBRID_ALGORITHM
    clusters = await runs.list_clusters(RUN_ID)
    assert len(clusters) == 2
    assert all(
        cluster.confidence == pytest.approx(TYPE_CONFIDENCE["prompt"]) for cluster in clusters
    )
    assert all(
        cluster.severity == pytest.approx(cluster_severity("prompt", count))
        for cluster, count in zip(clusters, (2, 1), strict=True)
    )
    assert [cluster.probe_cluster_description for cluster in clusters] == [
        "prompt 类问题 · 检索索引读取失败",
        "prompt 类问题 · 工具调用超时",
    ]
    assert [cluster.rank for cluster in clusters] == [1, 2]
    created = next(event for event in events.records if event.event_type == "clusters_created")
    assert created.payload is not None
    comparison = created.payload["severityFormula"]
    assert [row["severityFormula"] for row in comparison] == [
        cluster.severity for cluster in clusters
    ]
    assert [row["severity"] for row in comparison] == [cluster.severity for cluster in clusters]
    calls = [event for event in events.records if event.event_type == "ai_agent_call"]
    degraded = [event for event in events.records if event.event_type == "degraded"]
    assert len(calls) == 3
    assert all(event.payload["outcome"] == "error" for event in calls if event.payload)
    assert [event.payload["task"] for event in degraded if event.payload] == [
        REVIEW_TASK,
        CLUSTER_SCORE_TASK,
        SEVERITY_SCORE_TASK,
    ]
