"""Attribution-driven clustering: one draft per conclusion, merged by root cause.

The fixture mirrors the production run from issue #587: 13 ``prompt`` probes
share the same ``[SWE-bench] astropy__astropy-13398 · unresolved`` title template
but describe different mechanisms, 6 are ``flow`` and 1 is ``error``. The tests
pin that grouping reads the attribution conclusion, that a degraded review
falls back to category buckets instead of one cluster per probe, and that an
oversized input is reviewed in category batches.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pytest

from app.service.evolution import cluster_llm
from app.service.evolution.cluster import (
    ATTRIBUTION_DRAFT_MAX_CHARS,
    ATTRIBUTION_HYBRID_ALGORITHM,
    ClusterDraft,
    ProbeForCluster,
    attribution_fallback_description,
    build_attribution_drafts,
)
from app.service.evolution.cluster_llm import (
    CLUSTER_SCORE_TASK,
    REVIEW_TASK,
    SEVERITY_SCORE_TASK,
    CallRecord,
    ClusterCaseEvidence,
    ClusterDraftStats,
    DegradedCall,
    build_review_request,
    enhance_clusters,
)
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

SHARED_TITLE = "[SWE-bench] astropy__astropy-13398 · unresolved"

_PROMPT_CONCLUSIONS = (
    "no-test 场景缺少回归验证门禁;控制者把相关失败判为预期并压制审查。",
    "缺少需求覆盖度核对与既有测试回归检查;折射被逐级固化为非目标。",
    "缺少回归与验收门禁和审查发现闭环;以官方补丁会更新为由接受失败。",
    "缺少行为保持与回归证据门禁;把既有行为回归当作预期行为变化。",
    "需求在计划阶段被静默丢弃;评审范围被收窄;已检出的回归被驳回。",
    "缺少把需求原文落成可执行验收的门禁;F2P 2/2 不通过。",
    "no-test 静默丢弃验证步骤;缺少审查发现与硬约束冲突的处置。",
    "缺少需求原文对照与假设登记;验收面从未被执行。",
    "缺少 429 与传输故障恢复分支、增量持久化检查点与预算门禁。",
    "no-test 语义被扩大为禁止运行测试;缺少导入与公共表面检查。",
    "固定串行多代理流程缺少时间预算、任务粒度合并与降级收尾。",
    "缺少传输层失败状态分支、增量持久化与降级完成出口。",
    "no-test 硬红线与审查闭环缺失;验证期望来自自产 design 的自证 oracle。",
)
_FLOW_CONCLUSIONS = (
    "固定串行多代理流程缺少时间预算。",
    "缺少任务粒度合并与降级收尾。",
    "缺少阶段之间的持久化检查点。",
    "缺少失败状态分支与重试预算。",
    "缺少降级完成出口。",
    "缺少跨阶段进度可观测性。",
)
_ERROR_CONCLUSION = "no-test 硬红线叠加审查闭环缺失, 验证期望是自证 oracle。"


@dataclass(frozen=True, slots=True)
class _Attribution:
    probe_id: str
    attribute_type: str
    description: str
    case_id: str


def _attributions() -> tuple[_Attribution, ...]:
    """Build the 20-attribution production-shaped fixture."""
    items: list[_Attribution] = []
    for index, conclusion in enumerate(_PROMPT_CONCLUSIONS):
        items.append(
            _Attribution(
                probe_id=f"p-prompt-{index:02d}",
                attribute_type="prompt",
                description=conclusion,
                case_id=f"case-{index:02d}",
            ),
        )
    for index, conclusion in enumerate(_FLOW_CONCLUSIONS):
        items.append(
            _Attribution(
                probe_id=f"p-flow-{index:02d}",
                attribute_type="flow",
                description=conclusion,
                case_id=f"case-flow-{index:02d}",
            ),
        )
    items.append(
        _Attribution(
            probe_id="p-error-00",
            attribute_type="error",
            description=_ERROR_CONCLUSION,
            case_id="case-error-00",
        ),
    )
    return tuple(items)


def _drafts() -> tuple[ClusterDraft, ...]:
    """Render the attribution fixture through the production draft builder."""
    return build_attribution_drafts(
        tuple(
            ProbeForCluster(
                probe_id=item.probe_id,
                attribute_type=item.attribute_type,  # type: ignore[arg-type]
                text=item.description,
            )
            for item in _attributions()
        ),
    )


def _evidence() -> dict[str, ClusterCaseEvidence]:
    """Give every draft one bad case whose title is the shared template."""
    return {
        item.case_id: ClusterCaseEvidence(
            case_id=item.case_id,
            title=SHARED_TITLE,
            text="同签名记录",
        )
        for item in _attributions()
    }


def _stats(drafts: tuple[ClusterDraft, ...]) -> dict[int, ClusterDraftStats]:
    """Map one draft to the single case behind it."""
    return {
        index: ClusterDraftStats(case_ids=(f"case-{index:02d}",)) for index in range(len(drafts))
    }


class _ResultProvider(AIAgentProvider):
    """Return caller-supplied outputs and expose every request for assertions."""

    provider_id = "result"

    def __init__(self, outputs: Mapping[str, Mapping[str, Any]]) -> None:
        """Bind one output per task key."""
        super().__init__(None)
        self.outputs = dict(outputs)
        self.requests: list[AnalysisRequest] = []

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Record the request and return the bound mapping."""
        self.requests.append(request)
        return AnalysisResult(
            output=self.outputs[request.task],
            provider_id=self.provider_id,
            usage=AgentUsage(model="result-model"),
            latency_ms=1,
        )

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Reject unexpected edit work."""
        raise NotImplementedError

    async def health_check(self) -> ProviderHealth:
        """Report a healthy deterministic stub."""
        return ProviderHealth(provider_id=self.provider_id, healthy=True, latency_ms=0)


class _FailingProvider(AIAgentProvider):
    """Fail every analysis call to exercise the degrade path."""

    provider_id = "failing"

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Raise the same retryable failure for every task."""
        raise AgentProviderError("review unavailable", retryable=True, provider_id=self.provider_id)

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Reject unexpected edit work."""
        raise NotImplementedError

    async def health_check(self) -> ProviderHealth:
        """Report an unhealthy backend."""
        return ProviderHealth(provider_id=self.provider_id, healthy=False, latency_ms=0)


class _DynamicProvider(AIAgentProvider):
    """Answer review/scoring from the task keys present in the prompt.

    Used by the batching test: a fixed output cannot cover batches of different
    sizes, while this stub derives an identity partition and one score item per
    cited cluster key.
    """

    provider_id = "dynamic"

    def __init__(self) -> None:
        """Start with no recorded requests."""
        super().__init__(None)
        self.review_calls = 0
        self.requests: list[AnalysisRequest] = []

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Return a structurally valid output for the keys in the prompt."""
        self.requests.append(request)
        if request.task == REVIEW_TASK:
            self.review_calls += 1
            keys = re.findall(r"\[(D\d+)\]", request.prompt)
            output: dict[str, Any] = {
                "clusters": [{"from": [key], "title": f"根因 {key}"} for key in keys],
            }
        elif request.task == CLUSTER_SCORE_TASK:
            keys = re.findall(r"\[(C\d+)\]", request.prompt)
            output = {
                "scores": [
                    {"cluster": key, "confidence": 0.5, "evidence_refs": []} for key in keys
                ],
            }
        elif request.task == SEVERITY_SCORE_TASK:
            keys = re.findall(r"\[(C\d+)\]", request.prompt)
            output = {
                "severities": [
                    {
                        "cluster": key,
                        "overall": 5.0,
                        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L",
                    }
                    for key in keys
                ],
            }
        else:  # pragma: no cover - the clustering path has exactly three tasks
            raise AssertionError(f"unexpected task {request.task}")
        return AnalysisResult(
            output=output,
            provider_id=self.provider_id,
            usage=AgentUsage(model="dynamic-model"),
            latency_ms=1,
        )

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Reject unexpected edit work."""
        raise NotImplementedError

    async def health_check(self) -> ProviderHealth:
        """Report a healthy deterministic stub."""
        return ProviderHealth(provider_id=self.provider_id, healthy=True, latency_ms=0)


def _identity_output() -> dict[str, Any]:
    """Merge D1 and D2, and keep D3 apart."""
    return {
        "clusters": [
            {"from": ["D1", "D2"], "title": "共同根因", "description": "同一机制"},
            {"from": ["D3"], "title": "另一个根因"},
        ],
    }


def test_twenty_attributions_become_twenty_singleton_drafts() -> None:
    """The grouping layer never merges probes before the review layer."""
    drafts = _drafts()

    assert len(drafts) == 20
    assert [draft.type for draft in drafts].count("prompt") == 13
    assert [draft.type for draft in drafts].count("flow") == 6
    assert [draft.type for draft in drafts].count("error") == 1
    assert all(len(draft.probes) == 1 for draft in drafts)
    assert len({draft.probes[0] for draft in drafts}) == 20
    assert all(draft.description != SHARED_TITLE for draft in drafts)
    assert all(SHARED_TITLE not in draft.description for draft in drafts)


def test_attribution_draft_summary_is_the_bounded_conclusion() -> None:
    """The review summary comes from the conclusion, bounded to the draft cap."""
    long_conclusion = "缺少回归门禁" * 80
    drafts = build_attribution_drafts(
        (ProbeForCluster(probe_id="p-1", attribute_type="prompt", text=long_conclusion),),
    )

    assert len(drafts[0].description) <= ATTRIBUTION_DRAFT_MAX_CHARS + len("prompt 类问题 · ")
    assert drafts[0].description.startswith("prompt 类问题 · 缺少回归门禁")
    assert drafts[0].description.endswith("…")


def test_missing_conclusion_stays_a_unique_honest_draft() -> None:
    """An empty conclusion must not collapse unrelated probes into one draft."""
    drafts = build_attribution_drafts(
        (
            ProbeForCluster(probe_id="p-1", attribute_type="prompt", text=""),
            ProbeForCluster(probe_id="p-2", attribute_type="prompt", text=""),
        ),
    )

    assert [draft.probes for draft in drafts] == [("p-1",), ("p-2",)]
    assert drafts[0].description != drafts[1].description


def test_attribution_review_prompt_uses_conclusions_and_forbids_template_merges() -> None:
    """The prompt carries the conclusion as summary and names the forbidden signals."""
    drafts = _drafts()
    request = build_review_request(
        drafts,
        _evidence(),
        stats_by_draft=_stats(drafts),
        grouping="attribution",
    )

    assert request.task == REVIEW_TASK
    assert "shared root cause" in request.prompt
    assert "bad-case instance" in request.prompt
    assert "title template" in request.prompt
    assert "summary: prompt 类问题 · no-test 场景缺少回归验证门禁" in request.prompt
    assert "summary: prompt 类问题 · [SWE-bench]" not in request.prompt


async def test_attribution_review_merges_by_root_cause() -> None:
    """A valid review partition persists root-cause titles for the merged groups."""
    drafts = _drafts()[:3]
    stats = {
        0: ClusterDraftStats(case_ids=("case-00",)),
        1: ClusterDraftStats(case_ids=("case-01",)),
        2: ClusterDraftStats(case_ids=("case-02",)),
    }
    evidence = {
        f"case-{index:02d}": ClusterCaseEvidence(
            case_id=f"case-{index:02d}",
            title=SHARED_TITLE,
        )
        for index in range(3)
    }
    provider = _ResultProvider(
        {
            REVIEW_TASK: _identity_output(),
            CLUSTER_SCORE_TASK: {
                "scores": [
                    {"cluster": "C1", "confidence": 0.9, "evidence_refs": []},
                    {"cluster": "C2", "confidence": 0.5, "evidence_refs": []},
                ],
            },
            SEVERITY_SCORE_TASK: {
                "severities": [
                    {
                        "cluster": "C1",
                        "overall": 8.0,
                        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L",
                    },
                    {
                        "cluster": "C2",
                        "overall": 4.0,
                        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L",
                    },
                ],
            },
        },
    )

    result = await enhance_clusters(
        provider,
        drafts,
        evidence,
        stats_by_draft=stats,
        grouping="attribution",
    )

    assert result.algorithm == ATTRIBUTION_HYBRID_ALGORITHM
    assert result.degraded == ()
    assert len(result.clusters) == 2
    assert result.clusters[0].probes == ("p-prompt-00", "p-prompt-01")
    assert result.clusters[1].probes == ("p-prompt-02",)
    assert result.clusters[0].description != SHARED_TITLE
    assert "共同根因" in result.clusters[0].description
    assert all(call.outcome == "ok" for call in result.calls)
    assert [call.task for call in result.calls] == [
        REVIEW_TASK,
        CLUSTER_SCORE_TASK,
        SEVERITY_SCORE_TASK,
    ]


async def test_degraded_attribution_review_buckets_by_category() -> None:
    """A failed review with 20 drafts falls back to 3 category buckets, never 20."""
    drafts = _drafts()
    calls: list[CallRecord] = []
    degraded: list[DegradedCall] = []

    async def record_call(call: CallRecord) -> None:
        calls.append(call)

    async def record_degraded(item: DegradedCall) -> None:
        degraded.append(item)

    result = await enhance_clusters(
        _FailingProvider(),
        drafts,
        _evidence(),
        stats_by_draft=_stats(drafts),
        record_call=record_call,
        record_degraded=record_degraded,
        failure_policy="degrade",
        grouping="attribution",
    )

    assert len(result.clusters) == 3
    assert [cluster.type for cluster in result.clusters] == ["prompt", "error", "flow"]
    assert [len(cluster.probes) for cluster in result.clusters] == [13, 1, 6]
    assert [cluster.description for cluster in result.clusters] == [
        attribution_fallback_description("prompt", 13),
        attribution_fallback_description("error", 1),
        attribution_fallback_description("flow", 6),
    ]
    assert "（聚类降级）" in result.clusters[0].description  # noqa: RUF001
    assert all(call.outcome == "error" for call in calls)
    assert [item.task for item in degraded] == [
        REVIEW_TASK,
        CLUSTER_SCORE_TASK,
        SEVERITY_SCORE_TASK,
    ]


async def test_oversized_attribution_review_batches_by_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Above the cap the review runs in batches, records it, and still partitions."""
    monkeypatch.setattr(cluster_llm, "ATTRIBUTION_REVIEW_MAX_DRAFTS", 2)
    drafts = _drafts()[:5]
    stats = {index: ClusterDraftStats(case_ids=(f"case-{index:02d}",)) for index in range(5)}
    evidence = {
        f"case-{index:02d}": ClusterCaseEvidence(
            case_id=f"case-{index:02d}",
            title=SHARED_TITLE,
        )
        for index in range(5)
    }
    provider = _DynamicProvider()
    degraded: list[DegradedCall] = []

    async def record_degraded(item: DegradedCall) -> None:
        degraded.append(item)

    result = await enhance_clusters(
        provider,
        drafts,
        evidence,
        stats_by_draft=stats,
        record_degraded=record_degraded,
        failure_policy="degrade",
        grouping="attribution",
    )

    assert provider.review_calls == 3
    assert len(result.clusters) == 5
    assert {probe for cluster in result.clusters for probe in cluster.probes} == {
        draft.probes[0] for draft in drafts
    }
    assert [item.task for item in degraded] == [REVIEW_TASK]
    assert "category batches" in degraded[0].reason
