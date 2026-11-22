"""Mock-runner matrix for the real Claude Code provider (#492).

Every test here scripts the CLI transport; none spawns a process or touches the
network. The default asyncio runner is exercised against a fake process object,
and the single real-CLI smoke is opt-in through ``HE_AI_AGENT_CLAUDE_E2E=1`` and
must be run in the serial lane.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, Field

from app.config import Settings
from app.third_party_api.ai_agent import (
    AgentProviderError,
    AnalysisRequest,
    ClaudeCliResult,
    ClaudeCodeProvider,
    EditRequest,
)
from app.third_party_api.ai_agent.base import (
    ANALYZE_TIMEOUT_SECONDS,
    EDIT_TIMEOUT_SECONDS,
    PERMISSION_MODE,
)
from app.third_party_api.ai_agent.claude_code import (
    EDIT_PLAN_FILENAME,
    HEALTH_TIMEOUT_SECONDS,
    READ_ONLY_TOOLS,
    AsyncioClaudeCliRunner,
)


class ScoreOutput(BaseModel):
    """Minimal caller schema for the confidence-scoring task."""

    confidence: float = Field(ge=0, le=1, description="between zero and one")
    summary: str


@dataclass(frozen=True, slots=True)
class RunnerCall:
    """One scripted invocation captured by the mock transport."""

    argv: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str]
    timeout_seconds: float


type _RunnerStep = ClaudeCliResult | Callable[[Path], ClaudeCliResult]


class MockRunner:
    """Scripted transport; each call consumes one result or one callback."""

    def __init__(self, *steps: _RunnerStep) -> None:
        """Bind the ordered steps this runner will serve."""
        self._steps = list(steps)
        self.calls: list[RunnerCall] = []

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> ClaudeCliResult:
        """Record the call and return (or produce) the next scripted step."""
        self.calls.append(
            RunnerCall(
                argv=tuple(argv),
                cwd=cwd,
                env=dict(env),
                timeout_seconds=timeout_seconds,
            ),
        )
        if not self._steps:
            raise AssertionError("unexpected CLI invocation")
        step = self._steps.pop(0)
        if isinstance(step, ClaudeCliResult):
            return step
        return step(cwd)


class FailingRunner:
    """Transport that raises before any process exists."""

    def __init__(self, error: Exception) -> None:
        """Bind the exception raised on every invocation."""
        self._error = error

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> ClaudeCliResult:
        """Raise the bound transport failure."""
        raise self._error


def _binary(tmp_path: Path) -> Path:
    """Create an executable-looking deployment path without running it."""
    binary = tmp_path / "claude"
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    return binary


def _settings(tmp_path: Path, *, binary: Path | None = None) -> Settings:
    """Build settings pinned to one test binary and the real provider."""
    resolved = binary if binary is not None else _binary(tmp_path)
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        ai_agent_provider="claude-code",
        ai_agent_claude_bin=str(resolved),
    )


def _write_result(
    cwd: Path,
    payload: Mapping[str, Any],
    *,
    filename: str = "result.json5",
) -> None:
    """Write one submission literal exactly where the agent would."""
    path = cwd / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _analyze_step(
    payload: Mapping[str, Any],
    *,
    session_id: str | None = "session-1",
    usage: Mapping[str, Any] | None = None,
    total_cost_usd: float | None = None,
    model: str | None = None,
    model_usage: Mapping[str, Any] | None = None,
    is_error: bool = False,
    subtype: str | None = None,
) -> Callable[[Path], ClaudeCliResult]:
    """Build a CLI step that writes a submission and emits one result document."""

    def step(cwd: Path) -> ClaudeCliResult:
        _write_result(cwd, payload)
        document: dict[str, Any] = {"type": "result", "is_error": is_error}
        if session_id is not None:
            document["session_id"] = session_id
        if usage is not None:
            document["usage"] = dict(usage)
        if total_cost_usd is not None:
            document["total_cost_usd"] = total_cost_usd
        if model is not None:
            document["model"] = model
        if model_usage is not None:
            document["model_usage"] = dict(model_usage)
        if subtype is not None:
            document["subtype"] = subtype
        return ClaudeCliResult(
            returncode=0,
            stdout=json.dumps(document),
            stderr="",
        )

    return step


def _edit_step(
    plan: Mapping[str, Any],
    *,
    session_id: str | None = "edit-session",
    usage: Mapping[str, Any] | None = None,
    total_cost_usd: float | None = None,
) -> Callable[[Path], ClaudeCliResult]:
    """Build a CLI step that writes one EditPlan submission."""

    def step(cwd: Path) -> ClaudeCliResult:
        _write_result(cwd, plan, filename=EDIT_PLAN_FILENAME)
        document: dict[str, Any] = {"type": "result", "is_error": False}
        if session_id is not None:
            document["session_id"] = session_id
        if usage is not None:
            document["usage"] = dict(usage)
        if total_cost_usd is not None:
            document["total_cost_usd"] = total_cost_usd
        return ClaudeCliResult(
            returncode=0,
            stdout=json.dumps(document),
            stderr="",
        )

    return step


def _ndjson_step(
    payload: Mapping[str, Any],
    documents: Sequence[Mapping[str, Any]],
) -> Callable[[Path], ClaudeCliResult]:
    """Build a CLI step that writes a submission and emits an NDJSON stream."""

    def step(cwd: Path) -> ClaudeCliResult:
        _write_result(cwd, payload)
        return ClaudeCliResult(
            returncode=0,
            stdout="\n".join(json.dumps(document) for document in documents),
            stderr="",
        )

    return step


def _request(prompt: str = "rate the cluster") -> AnalysisRequest:
    """Build one analysis request with the minimal caller schema."""
    return AnalysisRequest(
        task="cluster.score",
        prompt=prompt,
        output_model=ScoreOutput,
    )


async def test_analyze_success_single_json_result(tmp_path: Path) -> None:
    """A normal result document plus a written literal becomes an AnalysisResult."""
    binary = _binary(tmp_path)
    runner = MockRunner(
        _analyze_step(
            {"confidence": 0.5, "summary": "ok"},
            session_id="session-1",
            usage={"input_tokens": 10, "output_tokens": 4},
            total_cost_usd=0.02,
            model="claude-sonnet-4",
        ),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path, binary=binary),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    result = await provider.analyze(_request())

    assert dict(result.output) == {"confidence": 0.5, "summary": "ok"}
    assert result.provider_id == "claude-code"
    assert result.session_id == "session-1"
    assert result.usage.model == "claude-sonnet-4"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 4
    assert result.usage.cost_usd == pytest.approx(0.02)
    assert result.latency_ms >= 0
    assert result.retryable is False

    call = runner.calls[0]
    argv = call.argv
    assert call.cwd.is_dir()
    assert call.cwd.name.startswith("he-ai-submission-")
    assert call.timeout_seconds == ANALYZE_TIMEOUT_SECONDS
    assert argv[0] == str(binary)
    assert "--bare" in argv
    prompt = argv[argv.index("-p") + 1]
    assert "rate the cluster" in prompt
    assert "./result.json5" in prompt
    assert argv[argv.index("--output-format") + 1] == "json"
    assert argv[argv.index("--permission-mode") + 1] == PERMISSION_MODE
    assert argv[argv.index("--allowed-tools") + 1] == "Write(./result.json5)"
    assert "--no-session-persistence" in argv
    assert "--settings" not in argv
    assert "--resume" not in argv


async def test_analyze_parses_ndjson_last_result_and_capabilities(tmp_path: Path) -> None:
    """NDJSON keeps the last ``type=result`` line and records system/init features."""
    runner = MockRunner(
        _ndjson_step(
            {"confidence": 0.9, "summary": "ndjson"},
            [
                {
                    "type": "system",
                    "subtype": "init",
                    "capabilities": ["session-resume", "json-schema"],
                },
                {
                    "type": "system",
                    "subtype": "status",
                    "capabilities": ["not-an-init-document"],
                },
                {"type": "assistant", "message": {"content": []}},
                {"type": "result", "session_id": "first-result", "is_error": False},
                {
                    "type": "result",
                    "session_id": "last-result",
                    "is_error": False,
                    "total_cost_usd": 0.3,
                    "model_usage": {
                        "claude-haiku": {
                            "input_tokens": 2,
                            "output_tokens": 1,
                            "cost_usd": 0.1,
                        },
                        "claude-sonnet": {
                            "input_tokens": 8,
                            "output_tokens": 3,
                            "cost_usd": 0.2,
                        },
                    },
                },
            ],
        ),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    result = await provider.analyze(_request())

    assert result.session_id == "last-result"
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 4
    assert result.usage.cost_usd == pytest.approx(0.3)
    assert result.usage.model == "claude-haiku+claude-sonnet"
    assert provider.detected_capabilities == ("session-resume", "json-schema")


async def test_analyze_tolerates_a_missing_session_id(tmp_path: Path) -> None:
    """A successful analysis can finish without a resumable session id."""
    runner = MockRunner(
        _analyze_step({"confidence": 0.5, "summary": "ok"}, session_id=None),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    result = await provider.analyze(_request())

    assert result.session_id is None
    assert result.output["summary"] == "ok"


async def test_invalid_submission_resumes_once_with_feedback(tmp_path: Path) -> None:
    """The first invalid literal triggers one ``--resume`` call with feedback."""
    runner = MockRunner(
        _analyze_step({"confidence": 2.0, "summary": "too high"}, session_id="session-1"),
        _analyze_step({"confidence": 0.5, "summary": "fixed"}, session_id="session-2"),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    result = await provider.analyze(_request())

    assert result.output["confidence"] == 0.5
    assert result.session_id == "session-2"
    assert len(runner.calls) == 2
    first_argv = runner.calls[0].argv
    assert "--resume" not in first_argv
    resume_argv = runner.calls[1].argv
    assert resume_argv[resume_argv.index("--resume") + 1] == "session-1"
    resume_prompt = resume_argv[resume_argv.index("-p") + 1]
    assert "rate the cluster" in resume_prompt
    assert "confidence" in resume_prompt
    assert "重新写入" in resume_prompt
    assert "--allowed-tools" in resume_argv
    assert resume_argv[resume_argv.index("--allowed-tools") + 1] == ("Write(./result.json5)")


async def test_second_invalid_submission_fails_with_bounded_detail(tmp_path: Path) -> None:
    """After one failed resume the provider raises instead of retrying forever."""
    runner = MockRunner(
        _analyze_step({"confidence": 2.0, "summary": "still high"}, session_id="session-1"),
        _analyze_step({"confidence": 3.0, "summary": "higher"}, session_id="session-2"),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    with pytest.raises(AgentProviderError) as caught:
        await provider.analyze(_request())

    error = caught.value
    assert error.retryable is False
    assert error.provider_id == "claude-code"
    assert error.detail is not None
    assert "confidence" in error.detail
    assert len(error.detail) <= 1_000
    assert len(runner.calls) == 2


async def test_invalid_submission_without_session_id_does_not_resume(
    tmp_path: Path,
) -> None:
    """No session id means there is nothing to resume; fail after one call."""
    runner = MockRunner(
        _analyze_step({"confidence": 2.0, "summary": "bad"}, session_id=None),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    with pytest.raises(AgentProviderError) as caught:
        await provider.analyze(_request())

    assert caught.value.retryable is False
    assert len(runner.calls) == 1


@pytest.mark.parametrize(
    "cli_result",
    [
        ClaudeCliResult(returncode=-2, stdout="", stderr="", cancelled=True),
        ClaudeCliResult(returncode=143, stdout="", stderr="", cancelled=False),
    ],
    ids=["sigint-cancelled", "exit-143"],
)
async def test_cancelled_cli_result_is_classified_as_cancelled(
    tmp_path: Path,
    cli_result: ClaudeCliResult,
) -> None:
    """A stopped process is a cancellation, not a generic analysis failure."""
    runner = MockRunner(cli_result)
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    with pytest.raises(AgentProviderError) as caught:
        await provider.analyze(_request())

    error = caught.value
    assert error.detail == "cancelled"
    assert error.retryable is False
    assert len(runner.calls) == 1


async def test_nonzero_exit_raises_a_retryable_bounded_error(tmp_path: Path) -> None:
    """A process failure is retryable and its stderr is redacted and bounded."""
    secret = "sk-proj-abcdefghijklmnop"  # noqa: S105 - fake credential for redaction
    runner = MockRunner(
        ClaudeCliResult(returncode=7, stdout="", stderr=f"boom {secret} " + "x" * 2_000),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    with pytest.raises(AgentProviderError) as caught:
        await provider.analyze(_request())

    error = caught.value
    assert error.retryable is True
    assert error.detail is not None
    assert "exit_code=7" in error.detail
    assert secret not in error.detail
    assert len(error.detail.encode("utf-8")) <= 1_000


async def test_is_error_result_raises_without_echoing_model_text(tmp_path: Path) -> None:
    """An ``is_error`` result is terminal and its text never reaches the detail."""
    runner = MockRunner(
        ClaudeCliResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "type": "result",
                    "is_error": True,
                    "subtype": "error_max_turns",
                    "result": "model secret text",
                },
            ),
            stderr="",
        ),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    with pytest.raises(AgentProviderError) as caught:
        await provider.analyze(_request())

    error = caught.value
    assert error.retryable is False
    assert error.detail is not None
    assert "is_error" in error.detail
    assert "error_max_turns" in error.detail
    assert "model secret text" not in error.detail


async def test_unparseable_stdout_fails_with_a_bounded_diagnostic(tmp_path: Path) -> None:
    """A zero-exit process without a JSON result is a format failure, not success."""
    runner = MockRunner(ClaudeCliResult(returncode=0, stdout="not-json", stderr=""))
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    with pytest.raises(AgentProviderError) as caught:
        await provider.analyze(_request())

    assert caught.value.retryable is False
    assert caught.value.detail is not None
    assert "stdout_bytes" in caught.value.detail


async def test_usage_maps_model_usage_without_double_counting(tmp_path: Path) -> None:
    """``model_usage`` is the per-model truth; the aggregate ``usage`` is ignored."""
    runner = MockRunner(
        _analyze_step(
            {"confidence": 0.5, "summary": "ok"},
            session_id="session-1",
            usage={"input_tokens": 999, "output_tokens": 999},
            model_usage={
                "claude-sonnet": {"input_tokens": 8, "output_tokens": 3, "cost_usd": 0.2},
                "claude-haiku": {"input_tokens": 2, "output_tokens": 1, "cost_usd": 0.05},
            },
            total_cost_usd=0.25,
        ),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    result = await provider.analyze(_request())

    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 4
    assert result.usage.cost_usd == pytest.approx(0.25)
    assert result.usage.model == "claude-haiku+claude-sonnet"


async def test_usage_falls_back_to_aggregate_usage_fields(tmp_path: Path) -> None:
    """Without ``model_usage`` the aggregate token counters are used."""
    runner = MockRunner(
        _analyze_step(
            {"confidence": 0.5, "summary": "ok"},
            session_id="session-1",
            usage={"input_tokens": 11, "output_tokens": 7},
            model="claude-opus-4",
        ),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    result = await provider.analyze(_request())

    assert result.usage.input_tokens == 11
    assert result.usage.output_tokens == 7
    assert result.usage.cost_usd == 0.0
    assert result.usage.model == "claude-opus-4"


async def test_usage_defaults_to_zero_and_provider_id(tmp_path: Path) -> None:
    """A result without usage metadata still yields a valid AgentUsage."""
    runner = MockRunner(_analyze_step({"confidence": 0.5, "summary": "ok"}))
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    result = await provider.analyze(_request())

    assert result.usage.input_tokens == 0
    assert result.usage.output_tokens == 0
    assert result.usage.cost_usd == 0.0
    assert result.usage.model == "claude-code"


async def test_analyze_adds_settings_only_when_the_file_exists(tmp_path: Path) -> None:
    """``--settings`` is advertised only for an existing deployment settings file."""
    settings_file = tmp_path / "settings.json"
    runner = MockRunner(
        _analyze_step({"confidence": 0.5, "summary": "first"}),
        _analyze_step({"confidence": 0.5, "summary": "second"}),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=settings_file,
    )

    await provider.analyze(_request())
    assert "--settings" not in runner.calls[0].argv

    settings_file.write_text("{}\n", encoding="utf-8")
    await provider.analyze(_request())
    second_argv = runner.calls[1].argv
    assert second_argv[second_argv.index("--settings") + 1] == str(settings_file)


async def test_edit_workspace_collects_the_plan_without_applying_it(
    tmp_path: Path,
) -> None:
    """The edit phase ships an EditPlan but leaves every workspace file untouched."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    sentinel = workspace / "skill.json"
    sentinel.write_text('{"timeoutSeconds": 30}\n', encoding="utf-8")
    plan = {
        "summary": "raise the fetch timeout",
        "edits": [
            {
                "op": "replace",
                "file": "skill.json",
                "target": '"timeoutSeconds": 30',
                "content": '"timeoutSeconds": 120',
                "rationale": "three cases timed out at 30s",
            },
        ],
    }
    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}\n", encoding="utf-8")
    runner = MockRunner(
        _edit_step(
            plan,
            session_id="edit-session",
            usage={"input_tokens": 20, "output_tokens": 8},
            total_cost_usd=0.04,
        ),
    )
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=settings_file,
    )

    result = await provider.edit_workspace(
        EditRequest(workspace=workspace, prompt="make the skill tolerate slow hosts"),
    )

    assert result.summary == "raise the fetch timeout"
    assert result.provider_id == "claude-code"
    assert result.changed_files == ()
    assert result.unified_diff == ""
    assert result.session_id == "edit-session"
    assert result.usage.input_tokens == 20
    assert result.usage.cost_usd == pytest.approx(0.04)
    assert result.latency_ms >= 0
    assert sentinel.read_text(encoding="utf-8") == '{"timeoutSeconds": 30}\n'
    assert (workspace / EDIT_PLAN_FILENAME).exists()

    call = runner.calls[0]
    argv = call.argv
    assert call.cwd == workspace
    assert call.timeout_seconds == EDIT_TIMEOUT_SECONDS
    expected_tools = ",".join((*READ_ONLY_TOOLS, f"Write(./{EDIT_PLAN_FILENAME})"))
    assert argv[argv.index("--allowed-tools") + 1] == expected_tools
    assert "make the skill tolerate slow hosts" in argv[argv.index("-p") + 1]
    assert argv[argv.index("--settings") + 1] == str(settings_file)
    assert "--no-session-persistence" not in argv
    assert "--resume" not in argv


async def test_edit_omits_settings_when_the_deployment_file_is_absent(
    tmp_path: Path,
) -> None:
    """Edit advertises ``--settings`` only for an existing deployment settings file."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    plan = {"summary": "no-op plan", "edits": []}
    runner = MockRunner(_edit_step(plan))
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "missing-settings.json",
    )

    await provider.edit_workspace(EditRequest(workspace=workspace, prompt="edit"))

    assert "--settings" not in runner.calls[0].argv


async def test_edit_invalid_plan_raises_without_retry(tmp_path: Path) -> None:
    """An invalid EditPlan is terminal; the edit phase never resumes on its own."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    runner = MockRunner(_edit_step({"summary": "   ", "edits": []}))
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "settings.json",
    )

    with pytest.raises(AgentProviderError) as caught:
        await provider.edit_workspace(EditRequest(workspace=workspace, prompt="edit"))

    error = caught.value
    assert error.retryable is False
    assert error.detail is not None
    assert "summary" in error.detail
    assert len(runner.calls) == 1


async def test_health_check_reports_healthy_and_probes_version(tmp_path: Path) -> None:
    """Exit 0 makes the provider healthy and keeps only a sanitized version line."""
    binary = _binary(tmp_path)
    runner = MockRunner(ClaudeCliResult(returncode=0, stdout="2.1.311 (Claude Code)\n", stderr=""))
    provider = ClaudeCodeProvider(
        _settings(tmp_path, binary=binary),
        runner=runner,
        settings_path=tmp_path / "settings.json",
    )

    health = await provider.health_check()

    assert health.provider_id == "claude-code"
    assert health.healthy is True
    assert health.detail is not None
    assert "2.1.311" in health.detail
    assert health.latency_ms is not None and health.latency_ms >= 0
    call = runner.calls[0]
    assert call.argv == (str(binary), "--version")
    assert call.timeout_seconds == HEALTH_TIMEOUT_SECONDS


async def test_health_check_reports_unhealthy_on_nonzero_exit(tmp_path: Path) -> None:
    """A failed version probe is unhealthy rather than an exception."""
    runner = MockRunner(ClaudeCliResult(returncode=1, stdout="", stderr="license error"))
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=runner,
        settings_path=tmp_path / "settings.json",
    )

    health = await provider.health_check()

    assert health.healthy is False
    assert health.detail is not None
    assert "code 1" in health.detail


async def test_health_check_never_raises_when_the_transport_fails(
    tmp_path: Path,
) -> None:
    """A transport exception becomes a sanitized unhealthy detail."""
    provider = ClaudeCodeProvider(
        _settings(tmp_path),
        runner=FailingRunner(OSError("no such binary")),
        settings_path=tmp_path / "settings.json",
    )

    health = await provider.health_check()

    assert health.healthy is False
    assert health.detail is not None
    assert "OSError" in health.detail


async def test_health_check_skips_the_probe_when_the_binary_is_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing deployment binary is reported without spawning anything."""

    async def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("health probe must not spawn an absent binary")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    provider = ClaudeCodeProvider(
        _settings(tmp_path, binary=tmp_path / "absent-claude"),
        settings_path=tmp_path / "settings.json",
    )

    health = await provider.health_check()

    assert health.healthy is False
    assert health.detail is not None
    assert "not found" in health.detail


async def test_default_runner_escalates_sigint_to_sigkill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A process that ignores SIGINT receives SIGKILL and is marked cancelled."""
    process = _FakeProcess()
    recorded_signals: list[signal.Signals] = []

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        assert kwargs["start_new_session"] is True
        assert kwargs["stdin"] is asyncio.subprocess.DEVNULL
        return process

    def fake_killpg(pgid: int, sig: signal.Signals) -> None:
        assert pgid == process.pid
        recorded_signals.append(sig)
        if sig == signal.SIGKILL:
            process.returncode = -9
            process.exit_event.set()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr(os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(os, "killpg", fake_killpg)
    runner = AsyncioClaudeCliRunner(grace_seconds=0.01)

    result = await runner.run(
        ("claude", "--version"),
        cwd=tmp_path,
        env={},
        timeout_seconds=0.01,
    )

    assert recorded_signals == [signal.SIGINT, signal.SIGKILL]
    assert result.cancelled is True
    assert result.returncode == -9


async def test_default_runner_cleans_up_and_reraises_cancellation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller cancellation still stops the group before propagating."""
    process = _FakeProcess()
    recorded_signals: list[signal.Signals] = []

    async def fake_create(*args: Any, **kwargs: Any) -> _FakeProcess:
        return process

    def fake_killpg(pgid: int, sig: signal.Signals) -> None:
        recorded_signals.append(sig)
        if sig == signal.SIGKILL:
            process.returncode = -9
            process.exit_event.set()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr(os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(os, "killpg", fake_killpg)
    runner = AsyncioClaudeCliRunner(grace_seconds=0.01)

    task = asyncio.create_task(
        runner.run(
            ("claude", "-p", "analyse"),
            cwd=tmp_path,
            env={},
            timeout_seconds=30.0,
        ),
    )
    await process.communicate_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert recorded_signals == [signal.SIGINT, signal.SIGKILL]
    assert process.returncode == -9


class _FakeProcess:
    """Minimal process double for the default runner's timeout path."""

    def __init__(self) -> None:
        """Start in the running state with a stable pid."""
        self.pid = 4_242
        self.returncode: int | None = None
        self.exit_event = asyncio.Event()
        self.communicate_started = asyncio.Event()

    async def communicate(self) -> tuple[bytes, bytes]:
        """Block until the fake process is killed."""
        self.communicate_started.set()
        await self.exit_event.wait()
        return (b"", b"")

    async def wait(self) -> int:
        """Block until the fake process exits, then return its code."""
        if self.returncode is None:
            await self.exit_event.wait()
        return self.returncode if self.returncode is not None else 0

    def terminate(self) -> None:
        """Record a non-POSIX termination."""
        self.returncode = -signal.SIGTERM
        self.exit_event.set()

    def kill(self) -> None:
        """Record a non-POSIX kill."""
        self.returncode = -signal.SIGKILL
        self.exit_event.set()


def _e2e_enabled() -> bool:
    """Return whether the opt-in real-CLI smoke is requested."""
    return os.environ.get("HE_AI_AGENT_CLAUDE_E2E", "").strip() == "1"


_E2E_BIN = str(
    Path(os.environ.get("HE_AI_AGENT_CLAUDE_BIN", "~/.local/bin/claude")).expanduser(),
)


class E2EOutput(BaseModel):
    """Trivial schema for the real-CLI smoke."""

    ok: bool


@pytest.mark.skipif(
    not _e2e_enabled() or not Path(_E2E_BIN).is_file(),
    reason="set HE_AI_AGENT_CLAUDE_E2E=1 with an installed claude CLI",
)
async def test_e2e_real_cli_analyze_smoke() -> None:
    """Opt-in real CLI smoke; run it serially, never in the unit matrix."""
    provider = ClaudeCodeProvider(
        Settings(
            _env_file=None,  # type: ignore[call-arg]
            ai_agent_provider="claude-code",
            ai_agent_claude_bin=_E2E_BIN,
        ),
    )
    request = AnalysisRequest(
        task="smoke",
        prompt=(
            'Write exactly {"ok": true} to the submission file and stop. '
            "Do not add any other field or explanation."
        ),
        output_model=E2EOutput,
    )

    result = await provider.analyze(request)

    assert dict(result.output) == {"ok": True}
    assert result.provider_id == "claude-code"
    assert result.usage.model
