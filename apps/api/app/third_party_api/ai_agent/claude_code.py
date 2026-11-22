"""Real Claude Code provider: headless CLI calls, process groups, and usage.

The provider invokes the deployment's ``claude`` binary in headless mode and
collects structured conclusions through the shared submission channel
(:mod:`app.third_party_api.ai_agent.submission`) rather than through any
CLI-internal schema mechanism. The transport is a small injectable protocol so
unit tests script CLI results without spawning a process; only the opt-in e2e
smoke touches a real binary.

Process lifecycle mirrors the Git workspace runner: the child starts in its own
session, a timeout sends ``SIGINT`` to the process group, a short grace period
lets it exit, and a still-running group receives ``SIGKILL``. A cancelled call
is classified as ``detail="cancelled"`` with ``retryable=False``, and exit code
143 (128+SIGTERM) is treated the same way instead of as a generic failure.

Credentials and model endpoints stay in ``~/.claude``; this module never reads
them, never passes a key on the command line, and never logs stdout/stderr
verbatim. Diagnostics are bounded and redacted before they become a
``AgentProviderError`` detail or a health string.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import signal
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol

from app.third_party_api.ai_agent.base import (
    ANALYZE_TIMEOUT_SECONDS,
    EDIT_TIMEOUT_SECONDS,
    PERMISSION_MODE,
    AIAgentProvider,
)
from app.third_party_api.ai_agent.contracts import (
    AgentProviderError,
    AgentUsage,
    AnalysisRequest,
    AnalysisResult,
    EditRequest,
    EditResult,
    ProviderHealth,
)
from app.third_party_api.ai_agent.edits import EditPlan
from app.third_party_api.ai_agent.submission import (
    StructuredSubmission,
    SubmissionOutcome,
    SubmissionPrep,
)
from app.utils.redaction import sanitize_detail, sanitize_message

if TYPE_CHECKING:
    from app.config import Settings

DEFAULT_CLAUDE_BIN: Final = "~/.local/bin/claude"
"""Deployment default used when no Settings instance was bound."""

CLAUDE_SETTINGS_FILENAME: Final = "settings.json"
"""File under ``~/.claude`` that carries model/endpoint configuration."""

EDIT_PLAN_FILENAME: Final = ".harness-evolution/edits.json5"
"""The one file the edit phase may write; the deterministic applier owns it later."""

READ_ONLY_TOOLS: Final = ("Read", "Grep", "Glob")
"""Tools the edit phase may use to explore before it submits one plan (07 §5.5.4)."""

HEALTH_TIMEOUT_SECONDS: Final = 10.0
"""Upper bound for the ``--version`` health probe."""

CANCELLED_EXIT_CODE: Final = 143
"""128+SIGTERM; a CLI killed by a supervisor rather than a real analysis failure."""

_GRACE_SECONDS: Final = 5.0
"""Seconds between the process-group SIGINT and the SIGKILL escalation."""

_MAX_DETAIL_CHARS: Final = 1_000
"""Upper bound for a redacted diagnostic carried by a provider error."""

_MAX_VERSION_CHARS: Final = 120
"""Upper bound for the sanitized version text kept in a health detail."""


@dataclass(frozen=True, slots=True)
class ClaudeCliResult:
    """Captured output from one Claude CLI process.

    ``cancelled`` is set by the default runner when the call was stopped by the
    provider (timeout, cancellation, or escalation). It is separate from
    ``returncode`` because a killed process may report a negative signal code
    or a shell-style ``143``.
    """

    returncode: int
    stdout: str
    stderr: str
    cancelled: bool = False


class ClaudeCliRunner(Protocol):
    """Injectable transport for one Claude CLI invocation."""

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> ClaudeCliResult:
        """Run ``argv`` in ``cwd`` and return its captured output."""
        ...


class _ManagedProcess(Protocol):
    """Structural view of the subprocess fields process management needs."""

    @property
    def pid(self) -> int:
        """Return the child process id."""
        ...

    @property
    def returncode(self) -> int | None:
        """Return the exit code, or ``None`` while still running."""
        ...

    async def wait(self) -> int:
        """Wait for the process to exit and return its code."""
        ...

    async def communicate(self) -> tuple[bytes, bytes]:
        """Collect stdout/stderr until EOF."""
        ...

    def terminate(self) -> None:
        """Ask the process to stop (non-POSIX fallback)."""
        ...

    def kill(self) -> None:
        """Force the process to stop (non-POSIX fallback)."""
        ...


class AsyncioClaudeCliRunner:
    """Default runner: one process group with SIGINT→SIGKILL escalation."""

    def __init__(self, *, grace_seconds: float = _GRACE_SECONDS) -> None:
        """Bind the grace period used between SIGINT and SIGKILL."""
        if grace_seconds < 0:
            raise ValueError("grace_seconds must not be negative")
        self._grace_seconds = grace_seconds

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> ClaudeCliResult:
        """Run the CLI and stop its whole process group on timeout/cancellation."""
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(cwd),
            env=dict(env),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return await self._terminate(process)
        except asyncio.CancelledError:
            await self._terminate(process)
            raise
        return ClaudeCliResult(
            returncode=process.returncode if process.returncode is not None else -1,
            stdout=stdout.decode(errors="replace"),
            stderr=stderr.decode(errors="replace"),
        )

    async def _terminate(self, process: _ManagedProcess) -> ClaudeCliResult:
        """Send SIGINT to the group, then SIGKILL after the grace period."""
        _signal_process_group(process, signal.SIGINT)
        try:
            await asyncio.wait_for(process.wait(), timeout=self._grace_seconds)
        except TimeoutError:
            _signal_process_group(process, signal.SIGKILL)
            if process.returncode is None:
                await process.wait()
        returncode = process.returncode if process.returncode is not None else -1
        return ClaudeCliResult(
            returncode=returncode,
            stdout="",
            stderr="",
            cancelled=True,
        )


def _signal_process_group(process: _ManagedProcess, sig: signal.Signals) -> None:
    """Signal the whole child group, treating an already-gone process as done."""
    if process.returncode is not None:
        return
    if sys.platform == "win32":
        if sig == signal.SIGKILL:
            process.kill()
        else:
            process.terminate()
        return
    try:
        os.killpg(os.getpgid(process.pid), sig)
    except OSError:
        return


@dataclass(frozen=True, slots=True)
class _ParsedCliResult:
    """Normalized view of one CLI stdout document."""

    result: Mapping[str, Any] | None
    capabilities: tuple[str, ...]
    session_id: str | None
    usage: AgentUsage

    @property
    def is_error(self) -> bool:
        """Return whether the CLI marked its result as an application error."""
        return self.result is not None and self.result.get("is_error") is True


class ClaudeCodeProvider(AIAgentProvider):
    """Claude Code backend selected by ``AI_AGENT_PROVIDER=claude-code``."""

    provider_id = "claude-code"

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        runner: ClaudeCliRunner | None = None,
        settings_path: Path | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Bind an optional injected runner, settings path, and latency clock.

        ``runner`` is the test seam: when supplied, the provider never probes
        the host for the real binary and every invocation goes through it.
        ``settings_path`` overrides the resolved ``~/.claude/settings.json``
        path. ``clock`` keeps latency deterministic in tests.
        """
        super().__init__(settings)
        self._runner = runner if runner is not None else AsyncioClaudeCliRunner()
        self._runner_injected = runner is not None
        self._settings_path_override = settings_path
        self._clock = clock
        self._submission = StructuredSubmission()
        self._capabilities: tuple[str, ...] = ()

    @property
    def detected_capabilities(self) -> tuple[str, ...]:
        """Return capability names reported by the last ``system/init`` document.

        This is the only feature-detection source; the provider never compares
        version strings, and the list is recorded for observability only.
        """
        return self._capabilities

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Run one headless analysis and collect it through the submission channel."""
        started = self._clock()
        prep = self._submission.prepare(request.task, request.output_model)
        prompt = _compose_prompt(request.prompt, prep.prompt_addendum)
        settings_file = self._settings_file()
        argv = self._analyze_argv(prompt, prep, settings_file=settings_file)
        _, parsed = await self._call(
            "analysis",
            argv,
            cwd=prep.directory,
            timeout_seconds=ANALYZE_TIMEOUT_SECONDS,
        )

        outcome = self._submission.collect(prep, request.output_model.model_validate)
        if not outcome.is_ok and parsed.session_id is not None:
            feedback = self._submission.feedback_prompt(outcome)
            resume_prompt = _compose_prompt(prompt, feedback)
            resume_argv = self._analyze_argv(
                resume_prompt,
                prep,
                settings_file=settings_file,
                resume_session_id=parsed.session_id,
            )
            _, parsed = await self._call(
                "analysis",
                resume_argv,
                cwd=prep.directory,
                timeout_seconds=ANALYZE_TIMEOUT_SECONDS,
            )
            outcome = self._submission.collect(prep, request.output_model.model_validate)

        validated = outcome.validated
        if not outcome.is_ok or validated is None:
            raise AgentProviderError(
                "claude-code analysis submission failed validation",
                retryable=False,
                provider_id=self.provider_id,
                detail=_submission_detail(outcome),
            )
        return AnalysisResult(
            output=validated.model_dump(mode="json"),
            provider_id=self.provider_id,
            usage=parsed.usage,
            session_id=parsed.session_id,
            latency_ms=_elapsed_ms(started, self._clock),
            retryable=False,
        )

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Collect one EditPlan for the workspace without applying it."""
        started = self._clock()
        prep = self._submission.prepare(
            "agent.edit",
            EditPlan,
            directory=request.workspace,
            filename=EDIT_PLAN_FILENAME,
        )
        prompt = _compose_prompt(request.prompt, prep.prompt_addendum)
        argv = self._edit_argv(prompt, prep, settings_file=self._settings_file())
        _, parsed = await self._call(
            "edit",
            argv,
            cwd=request.workspace,
            timeout_seconds=EDIT_TIMEOUT_SECONDS,
        )
        outcome = self._submission.collect(prep, EditPlan.model_validate)
        validated = outcome.validated
        if not outcome.is_ok or not isinstance(validated, EditPlan):
            raise AgentProviderError(
                "claude-code edit submission failed validation",
                retryable=False,
                provider_id=self.provider_id,
                detail=_submission_detail(outcome),
            )
        return EditResult(
            summary=validated.summary,
            provider_id=self.provider_id,
            changed_files=(),
            unified_diff="",
            usage=parsed.usage,
            session_id=parsed.session_id,
            latency_ms=_elapsed_ms(started, self._clock),
            retryable=False,
        )

    async def health_check(self) -> ProviderHealth:
        """Probe ``--version`` with a short timeout and never raise."""
        started = self._clock()
        binary = self._binary()
        if not self._runner_injected and not _binary_available(binary):
            return ProviderHealth(
                provider_id=self.provider_id,
                healthy=False,
                detail=_bounded_detail(f"claude CLI not found: {binary}"),
                latency_ms=_elapsed_ms(started, self._clock),
            )
        try:
            result = await self._runner.run(
                (binary, "--version"),
                cwd=Path.cwd(),
                env=self._environment(),
                timeout_seconds=HEALTH_TIMEOUT_SECONDS,
            )
        except Exception as exc:  # a probe must never crash startup
            return ProviderHealth(
                provider_id=self.provider_id,
                healthy=False,
                detail=_bounded_detail(f"claude CLI probe failed: {type(exc).__name__}"),
                latency_ms=_elapsed_ms(started, self._clock),
            )
        latency_ms = _elapsed_ms(started, self._clock)
        if _is_cancelled(result) or result.returncode != 0:
            return ProviderHealth(
                provider_id=self.provider_id,
                healthy=False,
                detail=_bounded_detail(
                    f"claude CLI probe exited with code {result.returncode}",
                ),
                latency_ms=latency_ms,
            )
        version = _version_line(result.stdout)
        detail = f"claude CLI available: {version}" if version else "claude CLI available"
        if self._capabilities:
            detail = f"{detail}; capabilities={','.join(self._capabilities)}"
        return ProviderHealth(
            provider_id=self.provider_id,
            healthy=True,
            detail=_bounded_detail(detail),
            latency_ms=latency_ms,
        )

    async def _call(
        self,
        phase: str,
        argv: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float,
    ) -> tuple[ClaudeCliResult, _ParsedCliResult]:
        """Invoke the transport and normalize cancellation, exit, and output errors."""
        try:
            result = await self._runner.run(
                argv,
                cwd=cwd,
                env=self._environment(),
                timeout_seconds=timeout_seconds,
            )
        except TimeoutError:
            raise self._cancelled_error(phase) from None
        except OSError as exc:
            raise AgentProviderError(
                f"claude-code {phase} call could not start",
                retryable=False,
                provider_id=self.provider_id,
                detail=_bounded_detail(f"{type(exc).__name__}: {exc}"),
            ) from None

        if _is_cancelled(result):
            raise self._cancelled_error(phase)
        parsed = _parse_cli_stdout(result.stdout, fallback_model=self.provider_id)
        if parsed.capabilities:
            self._capabilities = parsed.capabilities
        if result.returncode != 0:
            raise AgentProviderError(
                f"claude-code {phase} call exited unsuccessfully",
                retryable=True,
                provider_id=self.provider_id,
                detail=_bounded_detail(_diagnostics(result)),
            )
        if parsed.result is None:
            raise AgentProviderError(
                f"claude-code {phase} output did not contain a JSON result",
                retryable=False,
                provider_id=self.provider_id,
                detail=_bounded_detail(
                    f"stdout_bytes={len(result.stdout.encode('utf-8'))}",
                ),
            )
        if parsed.is_error:
            raise AgentProviderError(
                f"claude-code {phase} reported an error result",
                retryable=False,
                provider_id=self.provider_id,
                detail=_bounded_detail(_error_result_detail(parsed.result, result)),
            )
        return result, parsed

    def _cancelled_error(self, phase: str) -> AgentProviderError:
        """Build the normalized cancellation error for one phase."""
        return AgentProviderError(
            f"claude-code {phase} call was cancelled",
            retryable=False,
            provider_id=self.provider_id,
            detail="cancelled",
        )

    def _analyze_argv(
        self,
        prompt: str,
        prep: SubmissionPrep,
        *,
        settings_file: Path,
        resume_session_id: str | None = None,
    ) -> tuple[str, ...]:
        """Build one analyze argv; only analyze carries ``--no-session-persistence``."""
        argv = [
            self._binary(),
            "--bare",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            PERMISSION_MODE,
            "--allowed-tools",
            prep.allowed_tools[0],
            "--no-session-persistence",
        ]
        if resume_session_id is not None:
            argv.extend(("--resume", resume_session_id))
        if settings_file.is_file():
            argv.extend(("--settings", str(settings_file)))
        return tuple(argv)

    def _edit_argv(
        self,
        prompt: str,
        prep: SubmissionPrep,
        *,
        settings_file: Path,
    ) -> tuple[str, ...]:
        """Build one edit argv; exploration is read-only and the session is kept."""
        argv = [
            self._binary(),
            "--bare",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            PERMISSION_MODE,
            "--allowed-tools",
            ",".join((*READ_ONLY_TOOLS, *prep.allowed_tools)),
        ]
        if settings_file.is_file():
            argv.extend(("--settings", str(settings_file)))
        return tuple(argv)

    def _binary(self) -> str:
        """Resolve the configured CLI path with ``~`` expansion."""
        settings = self.settings
        configured = settings.ai_agent_claude_bin if settings is not None else DEFAULT_CLAUDE_BIN
        return str(Path(configured).expanduser())

    def _settings_file(self) -> Path:
        """Return the deployment settings file path (override or ``~/.claude``)."""
        if self._settings_path_override is not None:
            return self._settings_path_override
        return Path.home() / ".claude" / CLAUDE_SETTINGS_FILENAME

    @staticmethod
    def _environment() -> Mapping[str, str]:
        """Pass the deployment environment through without reading any value."""
        return dict(os.environ)


def _is_cancelled(result: ClaudeCliResult) -> bool:
    """Return whether a CLI result means "stopped", not "failed".

    ``cancelled`` covers the runner's own SIGINT/SIGKILL path (whose
    ``returncode`` is negative on POSIX); the bare ``143`` case covers a child
    that translated SIGTERM into its own exit status.
    """
    return result.cancelled or result.returncode == CANCELLED_EXIT_CODE


def _binary_available(binary: str) -> bool:
    """Return whether the configured binary is present without executing it."""
    if not binary:
        return False
    if os.sep in binary or (os.altsep is not None and os.altsep in binary):
        return Path(binary).is_file()
    return shutil.which(binary) is not None


def _compose_prompt(prompt: str, addendum: str) -> str:
    """Join the caller prompt and the submission instructions deterministically."""
    return f"{prompt.rstrip()}\n\n{addendum.strip()}\n"


def _elapsed_ms(started: float, clock: Callable[[], float]) -> int:
    """Return a non-negative whole-millisecond latency."""
    return max(0, int((clock() - started) * 1_000))


def _parse_cli_stdout(stdout: str, *, fallback_model: str) -> _ParsedCliResult:
    """Parse one JSON object or an NDJSON stream into the last result document.

    A single ``--output-format json`` object is accepted directly; an NDJSON
    stream keeps the last document whose ``type`` is ``result`` and records the
    first ``system/init`` capability list it sees. No version string is
    consulted anywhere in this function.
    """
    capabilities: tuple[str, ...] = ()
    result: Mapping[str, Any] | None = None
    document = stdout.strip()
    single = _single_json_object(document)
    if single is not None:
        document_type = single.get("type")
        capabilities = _capabilities_from(single)
        if document_type in (None, "result"):
            result = single
        elif document_type != "system":
            result = None
    else:
        for line in stdout.splitlines():
            item = _single_json_object(line.strip())
            if item is None:
                continue
            item_type = item.get("type")
            if item_type == "system":
                line_capabilities = _capabilities_from(item)
                if line_capabilities:
                    capabilities = line_capabilities
                continue
            if item_type == "result":
                result = item
    return _ParsedCliResult(
        result=result,
        capabilities=capabilities,
        session_id=_session_id_from(result),
        usage=_usage_from(result, fallback_model=fallback_model),
    )


def _single_json_object(document: str) -> Mapping[str, Any] | None:
    """Return one JSON object document, or ``None`` for anything else."""
    if not document.startswith("{"):
        return None
    try:
        loaded = json.loads(document)
    except (ValueError, TypeError):
        return None
    if not isinstance(loaded, dict):
        return None
    return {str(key): value for key, value in loaded.items()}


def _capabilities_from(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Extract ``system/init.capabilities`` from an init document only.

    The design names exactly one feature-detection source (07 §5.5.1), so a
    capability list on any other document type or subtype is ignored rather
    than treated as a second, implicit source.
    """
    if payload.get("type") != "system" or payload.get("subtype") != "init":
        return ()
    raw = payload.get("capabilities")
    if not isinstance(raw, list):
        return ()
    return tuple(value.strip() for value in raw if isinstance(value, str) and value.strip())


def _session_id_from(payload: Mapping[str, Any] | None) -> str | None:
    """Return a non-blank session id, if the CLI reported one."""
    if payload is None:
        return None
    value = payload.get("session_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _usage_from(payload: Mapping[str, Any] | None, *, fallback_model: str) -> AgentUsage:
    """Map ``total_cost_usd`` / ``model_usage`` / ``usage`` into ``AgentUsage``."""
    if payload is None:
        return AgentUsage(model=fallback_model)
    usage = _as_mapping(payload.get("usage"))
    model_usage = _as_mapping(payload.get("model_usage"))
    models: list[str] = []
    model_cost = 0.0
    if model_usage:
        # ``model_usage`` is the per-model breakdown and ``usage`` its
        # aggregate; summing both would double-count tokens.
        input_tokens = 0
        output_tokens = 0
        for name, raw_entry in model_usage.items():
            entry = _as_mapping(raw_entry)
            if entry is None:
                continue
            models.append(name)
            input_tokens += _as_int(entry.get("input_tokens"))
            output_tokens += _as_int(entry.get("output_tokens"))
            model_cost += _as_float(entry.get("cost_usd"))
    else:
        input_tokens = _as_int(usage.get("input_tokens")) if usage is not None else 0
        output_tokens = _as_int(usage.get("output_tokens")) if usage is not None else 0

    raw_total_cost = payload.get("total_cost_usd")
    cost = _as_float(raw_total_cost) if raw_total_cost is not None else model_cost
    model_value = payload.get("model")
    if isinstance(model_value, str) and model_value.strip():
        model = model_value.strip()
    elif models:
        model = "+".join(sorted(dict.fromkeys(models)))
    else:
        model = fallback_model
    return AgentUsage(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
    )


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    """Return a string-keyed mapping view or ``None`` for non-mappings."""
    if not isinstance(value, Mapping):
        return None
    return {str(key): item for key, item in value.items()}


def _as_int(value: object) -> int:
    """Coerce a token counter to a non-negative integer."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float) and math.isfinite(value):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value.strip()))
        except ValueError:
            return 0
    return 0


def _as_float(value: object) -> float:
    """Coerce a cost to a non-negative finite float."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        candidate = float(value)
    elif isinstance(value, str):
        try:
            candidate = float(value.strip())
        except ValueError:
            return 0.0
    else:
        return 0.0
    if not math.isfinite(candidate) or candidate < 0:
        return 0.0
    return candidate


def _diagnostics(result: ClaudeCliResult) -> str:
    """Render a bounded, redacted stderr diagnostic without echoing stdout."""
    parts = [f"exit_code={result.returncode}"]
    stderr = sanitize_detail(result.stderr, limit=600)
    if stderr is not None and stderr.strip():
        parts.append(f"stderr={stderr.strip()}")
    return "; ".join(parts)


def _error_result_detail(payload: Mapping[str, Any], result: ClaudeCliResult) -> str:
    """Render an ``is_error`` result without including its model text."""
    subtype = payload.get("subtype")
    subtype_text = subtype.strip() if isinstance(subtype, str) else "unknown"
    return f"is_error; subtype={subtype_text}; exit_code={result.returncode}"


def _submission_detail(outcome: SubmissionOutcome) -> str:
    """Bound the concrete validation/parse reason kept on a provider error."""
    if outcome.validation_error is not None:
        return _bounded_detail(f"validation failed: {outcome.validation_error}")
    if outcome.parse_error is not None:
        return _bounded_detail(f"submission {outcome.status}: {outcome.parse_error}")
    return _bounded_detail(f"submission {outcome.status}")


def _bounded_detail(text: str) -> str:
    """Redact and bound one diagnostic string for a provider error or health."""
    detail = sanitize_detail(text, limit=_MAX_DETAIL_CHARS)
    if detail is None or not detail.strip():
        return "claude-code failure"
    return detail.strip()


def _version_line(stdout: str) -> str:
    """Return the first non-blank version line, redacted and bounded."""
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped:
            return sanitize_message(stripped, limit=_MAX_VERSION_CHARS)
    return ""


__all__ = [
    "EDIT_PLAN_FILENAME",
    "READ_ONLY_TOOLS",
    "AsyncioClaudeCliRunner",
    "ClaudeCliResult",
    "ClaudeCliRunner",
    "ClaudeCodeProvider",
]
