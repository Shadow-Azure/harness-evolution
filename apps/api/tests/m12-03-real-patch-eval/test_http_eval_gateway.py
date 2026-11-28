"""ai-eval-platform gateway contract: launch, status, results and errors."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

import httpx
import pytest

from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    EvalGatewayConfigError,
    EvalRequest,
)
from app.third_party_api.eval_gateway.ai_eval_platform import (
    AiEvalPlatformGateway,
)
from app.third_party_api.eval_gateway.base import EvalGatewayError

_COMMIT = "c" * 40
_CONFIG: dict[str, Any] = {
    "mode": "ai-eval-platform",
    "baseUrl": "http://platform.invalid",
    "validationProjectId": "tpl-validation",
    "testProjectId": "tpl-test",
    "primaryMetricKey": "resolved_rate",
    "subDir": "skills/deep-research",
}


def _request(**overrides: Any) -> EvalRequest:
    """Build one candidate evaluation request with the target snapshot."""
    values: dict[str, Any] = {
        "run_id": "run-620",
        "evolution_round_id": "round-620",
        "repo_url": "https://example.invalid/repo.git",
        "ref": "evo/20261125-run-620/candidate/r1",
        "commit": _COMMIT,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "cluster_id": "C1",
        "idempotency_key": f"run-620:1:{_COMMIT}:1",
        "purpose": "candidate",
        "project_id": "tpl-validation",
        "sub_dir": "skills/deep-research",
        "attempt": 1,
        "round_seq": 1,
        "parent_commit": "b" * 40,
    }
    values.update(overrides)
    return EvalRequest(**values)


def _gateway(
    handler: Callable[[httpx.Request], httpx.Response],
    config: Mapping[str, Any] | None = None,
) -> AiEvalPlatformGateway:
    """Build the adapter over a mock transport so no socket is opened."""
    return AiEvalPlatformGateway(
        EvalGatewayConfig.from_mapping(dict(config or _CONFIG)),
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        auth_header={"Authorization": "Bearer stub-token"},
    )


async def test_submit_sends_the_real_launch_contract() -> None:
    """The launch request pins the commit, scopes the asset and sends lineage."""
    received: list[httpx.Request] = []
    body: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        body.update(json.loads(request.content))
        return httpx.Response(
            202,
            json={
                "run_id": "run-platform-1",
                "created": True,
                "asset": {"resolved_commit": _COMMIT},
                "warnings": ["该模板已开启自进化 bad case 上报"],
            },
        )

    gateway = _gateway(handler)
    submission = await gateway.submit(_request())

    assert submission.eval_id == "run-platform-1"
    assert submission.warnings == ("该模板已开启自进化 bad case 上报",)
    assert received[0].url.path == "/api/v1/eval-templates/tpl-validation/launch"
    assert received[0].headers["Authorization"] == "Bearer stub-token"
    assert received[0].headers["Idempotency-Key"] == f"run-620:1:{_COMMIT}:1"
    assert body["asset_override"] == {
        "ref": "evo/20261125-run-620/candidate/r1",
        "commit": _COMMIT,
        "asset_paths": [".claude/skills/deep-research"],
        "asset_types": {".claude/skills/deep-research": "skill"},
    }
    assert body["lineage"] == {
        "evolutionRunId": "run-620",
        "evolutionRoundId": "round-620",
        "roundSeq": 1,
        "parentCommit": "b" * 40,
    }


async def test_submit_uses_the_test_template_for_the_held_out_final() -> None:
    """Test baselines and the test final target the test template."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/eval-templates/tpl-test/launch"
        return httpx.Response(
            202,
            json={"run_id": "run-test", "asset": {"resolved_commit": _COMMIT}},
        )

    gateway = _gateway(handler)
    submission = await gateway.submit(
        _request(
            purpose="test_final",
            evolution_round_id="",
            project_id="tpl-test",
            round_seq=0,
            sub_dir="skills/deep-research",
        ),
    )

    assert submission.eval_id == "run-test"


async def test_submit_declares_an_agent_asset_as_subagent() -> None:
    """Agent targets declare the asset type instead of inheriting the template."""
    body: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body.update(json.loads(request.content))
        return httpx.Response(
            202,
            json={"run_id": "run-agent", "asset": {"resolved_commit": _COMMIT}},
        )

    gateway = _gateway(handler)
    await gateway.submit(
        _request(target_type="agent", sub_dir="agents/reviewer"),
    )

    assert body["asset_override"]["asset_paths"] == [".claude/agents/reviewer.md"]
    assert body["asset_override"]["asset_types"] == {".claude/agents/reviewer.md": "subagent"}


async def test_submit_rejects_a_drifting_resolved_commit() -> None:
    """A resolved commit different from the candidate must fail closed."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            202,
            json={"run_id": "run-drift", "asset": {"resolved_commit": "d" * 40}},
        )

    gateway = _gateway(handler)
    with pytest.raises(EvalGatewayError, match="different candidate commit"):
        await gateway.submit(_request())


async def test_submit_rejects_knowledge_targets_explicitly() -> None:
    """Knowledge targets are outside this phase and fail before any request."""

    def handler(_request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("knowledge targets must not call the platform")

    gateway = _gateway(handler)
    with pytest.raises(EvalGatewayConfigError, match="knowledge"):
        await gateway.submit(_request(target_type="knowledge"))


@pytest.mark.parametrize(
    ("platform_status", "expected"),
    [
        ("preparing", "queued"),
        ("queued", "queued"),
        ("running", "running"),
        ("finalizing", "running"),
        ("cancelling", "running"),
        ("completed", "completed"),
        ("failed", "failed"),
        ("cancelled", "failed"),
    ],
)
async def test_status_maps_the_platform_lifecycle(
    platform_status: str,
    expected: str,
) -> None:
    """The 11-state platform table folds onto HE's five states."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": platform_status})

    gateway = _gateway(handler)
    status = await gateway.get_status("run-platform-1")

    assert status.status == expected


async def test_partial_status_uses_the_minimum_completion_guard() -> None:
    """A partial run below 50% is a failure; at or above it is completed."""

    def below(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "partial", "progress": {"percent": 40}},
        )

    def above(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "partial", "progress": {"percent": 70}},
        )

    assert (await _gateway(below).get_status("run-1")).status == "failed"
    assert (await _gateway(above).get_status("run-1")).status == "completed"


async def test_budget_pause_is_terminal_with_actionable_copy() -> None:
    """The platform never self-heals a budget pause, so HE fails it."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "paused_budget"})

    gateway = _gateway(handler)
    status = await gateway.get_status("run-1")

    assert status.status == "failed"
    assert "预算" in (status.message or "")


async def test_unknown_status_fails_explicitly() -> None:
    """An unknown platform state cannot silently look queued or running."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "teleporting"})

    gateway = _gateway(handler)
    with pytest.raises(EvalGatewayError, match="unknown status"):
        await gateway.get_status("run-1")


async def test_result_reads_the_primary_metric_and_direction() -> None:
    """Results keep raw items but expose the configured primary measurement."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "is_final": True,
                "items": [
                    {
                        "metric_key": "resolved_count",
                        "value": 4,
                        "direction": "higher_is_better",
                    },
                    {
                        "metric_key": "resolved_rate",
                        "value": 66.7,
                        "direction": "higher_is_better",
                    },
                ],
            },
        )

    gateway = _gateway(handler)
    measurement = await gateway.get_result("run-1")

    assert measurement.candidate_score == 66.7
    assert measurement.primary_metric_key == "resolved_rate"
    assert measurement.direction == "higher_is_better"
    assert measurement.metrics[1]["metric_key"] == "resolved_rate"


async def test_result_without_the_primary_metric_fails_closed() -> None:
    """A results payload missing the configured metric is not a score of zero."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": [{"metric_key": "resolved_count", "value": 4}]},
        )

    gateway = _gateway(handler)
    with pytest.raises(EvalGatewayError, match="no primary metric"):
        await gateway.get_result("run-1")


async def test_4xx_error_envelope_is_final_with_the_platform_code() -> None:
    """A configuration rejection is not retried and keeps the platform code."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "error": {
                    "code": "asset_ref_unresolved",
                    "message": "资产 Ref 解析失败",
                },
            },
        )

    gateway = _gateway(handler)
    with pytest.raises(EvalGatewayError) as excinfo:
        await gateway.submit(_request())

    assert excinfo.value.retryable is False
    assert excinfo.value.platform_code == "asset_ref_unresolved"


async def test_5xx_and_transport_errors_are_retryable() -> None:
    """Platform-side transience is deferred by the poller, not judged final."""

    def unavailable(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="upstream down")

    def broken(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(EvalGatewayError) as unavailable_exc:
        await _gateway(unavailable).get_status("run-1")
    with pytest.raises(EvalGatewayError) as transport_exc:
        await _gateway(broken).get_status("run-1")

    assert unavailable_exc.value.retryable is True
    assert transport_exc.value.retryable is True


async def test_status_exposes_started_at_and_progress() -> None:
    """The status seam keeps the platform's execution start and percentage."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "running",
                "started_at": "2026-11-27T04:52:12Z",
                "progress": {"percent": 37.5},
            },
        )

    status = await _gateway(handler).get_status("run-platform-1")

    assert status.status == "running"
    assert status.started_at == datetime.fromisoformat("2026-11-27T04:52:12+00:00")
    assert status.progress_percent == 37.5


@pytest.mark.parametrize(
    "started_at",
    [None, "not-a-timestamp", "2026-11-27T04:52:12"],
)
async def test_status_tolerates_an_absent_or_invalid_started_at(
    started_at: str | None,
) -> None:
    """A missing, malformed or naive start time falls back to None."""

    def handler(_request: httpx.Request) -> httpx.Response:
        payload: dict[str, Any] = {"status": "running"}
        if started_at is not None:
            payload["started_at"] = started_at
        return httpx.Response(200, json=payload)

    status = await _gateway(handler).get_status("run-platform-1")

    assert status.started_at is None
    assert status.progress_percent is None
