"""HttpEvalGateway and EvalMapper contracts against a real local HTTP stub."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from eval_stub import StubEvalPlatform

from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    EvalRequest,
    EvalStatus,
    EvalSubmission,
)
from app.third_party_api.eval_gateway.http import HttpEvalError, HttpEvalGateway
from app.third_party_api.eval_gateway.mapper import EvalMapper

NOW = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)


def _request() -> EvalRequest:
    """Build one fully populated internal evaluation request."""
    return EvalRequest(
        run_id="run-m12-03",
        evolution_round_id="round-m12-03",
        repo_url="https://example.invalid/repo.git",
        ref="evo/20261117-run-m12-03/candidate/r1",
        commit="c" * 40,
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        cluster_id="C1",
        idempotency_key="run-m12-03:1:" + "c" * 40,
    )


async def test_mapper_round_trips_submit_status_and_result() -> None:
    """The mapper is the only place allowed to know the external field names."""
    payload = EvalMapper.submit_payload(_request())
    assert payload == {
        "runId": "run-m12-03",
        "evolutionRoundId": "round-m12-03",
        "repoUrl": "https://example.invalid/repo.git",
        "ref": "evo/20261117-run-m12-03/candidate/r1",
        "commit": "c" * 40,
        "targetType": "skill",
        "targetName": "deep-research",
        "targetVersion": "v2.0.0",
        "clusterId": "C1",
        "idempotencyKey": "run-m12-03:1:" + "c" * 40,
    }
    submission = EvalMapper.parse_submission({"evalId": "eval-9"})
    assert submission == EvalSubmission(eval_id="eval-9")
    status = EvalMapper.parse_status({"status": "running", "message": "wego"})
    assert status == EvalStatus(status="running", message="wego")
    result = EvalMapper.parse_result(
        {
            "currentScore": 80,
            "candidateScore": 91.5,
            "verdict": "reject",
            "metrics": [],
        },
    )
    assert result.external_verdict == "reject"
    assert result.candidate_score == 91.5


async def test_http_gateway_submits_polls_and_fetches_results() -> None:
    """The HTTP gateway performs real calls end to end against a local stub."""
    platform = StubEvalPlatform()
    server, base_url = platform.build()
    try:
        async with httpx.AsyncClient(base_url=base_url) as client:
            gateway = HttpEvalGateway(
                EvalGatewayConfig.from_mapping(
                    {"mode": "http", "baseUrl": base_url},
                ),
                client=client,
                auth_header={"Authorization": "Bearer stub-secret"},
            )
            submission = await gateway.submit(_request())
            assert submission == EvalSubmission(eval_id="eval-e2e-1")
            queued = await gateway.get_status(submission.eval_id)
            assert queued.status == "queued"
            completed = await gateway.get_status(submission.eval_id)
            assert completed.status == "completed"
            result = await gateway.get_result(submission.eval_id)
    finally:
        server.shutdown()

    assert platform.received_auth == ["Bearer stub-secret"]
    assert platform.received_bodies == [EvalMapper.submit_payload(_request())]
    assert result.current_score == 82.0
    assert result.candidate_score == 88.5
    assert result.external_verdict == "accept"
    assert result.metrics[0]["name"] == "pass_rate"


async def test_http_gateway_reports_external_failure_status() -> None:
    """External failed/timeout statuses surface with their safe message."""
    platform = StubEvalPlatform(status_sequence=["failed"], status_message="runner lost")
    server, base_url = platform.build()
    try:
        async with httpx.AsyncClient(base_url=base_url) as client:
            gateway = HttpEvalGateway(
                EvalGatewayConfig.from_mapping({"mode": "http", "baseUrl": base_url}),
                client=client,
            )
            submission = await gateway.submit(_request())
            status = await gateway.get_status(submission.eval_id)
    finally:
        server.shutdown()

    assert status == EvalStatus(status="failed", message="runner lost")
    assert platform.received_auth == [None]


async def test_http_gateway_rejects_invalid_status_and_result_payloads() -> None:
    """Malformed external payloads raise gateway errors instead of silent defaults."""
    platform = StubEvalPlatform(
        status_sequence=["mysterious"],
        result_payload={"currentScore": "high", "candidateScore": 90.0},
    )
    server, base_url = platform.build()
    try:
        async with httpx.AsyncClient(base_url=base_url) as client:
            gateway = HttpEvalGateway(
                EvalGatewayConfig.from_mapping({"mode": "http", "baseUrl": base_url}),
                client=client,
            )
            submission = await gateway.submit(_request())
            with pytest.raises(HttpEvalError, match="status"):
                await gateway.get_status(submission.eval_id)
            with pytest.raises(HttpEvalError, match="result"):
                await gateway.get_result(submission.eval_id)
    finally:
        server.shutdown()


async def test_http_gateway_wraps_transport_and_http_failures() -> None:
    """Connection failures and HTTP error codes become one gateway error type."""
    platform = StubEvalPlatform(result_status_code=500)
    server, base_url = platform.build()
    try:
        async with httpx.AsyncClient(base_url=base_url) as client:
            gateway = HttpEvalGateway(
                EvalGatewayConfig.from_mapping(
                    {"mode": "http", "baseUrl": base_url},
                ),
                client=client,
            )
            submission = await gateway.submit(_request())
            await gateway.get_status(submission.eval_id)
            with pytest.raises(HttpEvalError, match="evaluation platform"):
                await gateway.get_result(submission.eval_id)
    finally:
        server.shutdown()

    dead = HttpEvalGateway(
        EvalGatewayConfig.from_mapping(
            {"mode": "http", "baseUrl": "http://127.0.0.1:1"},
        ),
    )
    with pytest.raises(HttpEvalError):
        await dead.submit(_request())


@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [(500, True), (502, True), (429, True), (404, False), (400, False)],
)
async def test_http_gateway_classifies_http_status_retryability(
    status_code: int,
    retryable: bool,
) -> None:
    """Only 429/5xx are transient; other 4xx rejections are final answers."""
    platform = StubEvalPlatform(status_status_code=status_code)
    server, base_url = platform.build()
    try:
        async with httpx.AsyncClient(base_url=base_url) as client:
            gateway = HttpEvalGateway(
                EvalGatewayConfig.from_mapping({"mode": "http", "baseUrl": base_url}),
                client=client,
            )
            submission = await gateway.submit(_request())
            with pytest.raises(HttpEvalError) as excinfo:
                await gateway.get_status(submission.eval_id)
    finally:
        server.shutdown()

    assert excinfo.value.retryable is retryable


async def test_http_gateway_marks_transport_failures_retryable() -> None:
    """Connection failures and timeouts are transient observation problems."""
    dead = HttpEvalGateway(
        EvalGatewayConfig.from_mapping(
            {"mode": "http", "baseUrl": "http://127.0.0.1:1"},
        ),
    )
    with pytest.raises(HttpEvalError) as excinfo:
        await dead.submit(_request())

    assert excinfo.value.retryable is True


async def test_http_gateway_marks_payload_failures_non_retryable() -> None:
    """Non-JSON and malformed payloads are contract errors, never transient."""
    platform = StubEvalPlatform(status_sequence=["mysterious"])
    server, base_url = platform.build()
    try:
        async with httpx.AsyncClient(base_url=base_url) as client:
            gateway = HttpEvalGateway(
                EvalGatewayConfig.from_mapping({"mode": "http", "baseUrl": base_url}),
                client=client,
            )
            submission = await gateway.submit(_request())
            with pytest.raises(HttpEvalError) as excinfo:
                await gateway.get_status(submission.eval_id)
    finally:
        server.shutdown()

    assert excinfo.value.retryable is False


@pytest.mark.parametrize("body", [b"not-json", b"[1,2,3]"])
async def test_http_gateway_rejects_non_json_and_non_object_bodies(body: bytes) -> None:
    """Non-JSON and non-object responses become one sanitized gateway error."""
    received: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            received.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            """Keep the test output quiet."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{server.server_port}",
        ) as client:
            gateway = HttpEvalGateway(
                EvalGatewayConfig.from_mapping(
                    {"mode": "http", "baseUrl": f"http://127.0.0.1:{server.server_port}"},
                ),
                client=client,
            )
            with pytest.raises(HttpEvalError):
                await gateway.submit(_request())
    finally:
        server.shutdown()
    # Distinguishing assertion: the request really round-tripped once and the
    # bad body was folded by the gateway, not silently passed through.
    assert received == ["/evals"]
