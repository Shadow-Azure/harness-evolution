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

A failed analyze submission gets exactly one fresh, stateless retry that repeats
the original prompt plus the concrete validation feedback. Analyze never resumes
a CLI session: the real CLI's ``--no-session-persistence`` explicitly makes a
session unavailable for ``--resume``, so the retry is a new call, not a resumed
conversation.

Analysis and edits use the deployment environment. Skill calls project only
their allowed settings into a private home and sandbox. The shared runner
keeps credentials off argv and bounds stderr for diagnostics.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from app.third_party_api.ai_agent import claude_skill
from app.third_party_api.ai_agent.base import (
    ANALYZE_TIMEOUT_SECONDS,
    EDIT_TIMEOUT_SECONDS,
    PERMISSION_MODE,
    AIAgentProvider,
)
from app.third_party_api.ai_agent.claude_cli import (
    AsyncioClaudeCliRunner,
    ClaudeCliResult,
    ClaudeCliRunner,
)
from app.third_party_api.ai_agent.contracts import (
    AgentCallTrace,
    AgentProviderError,
    AgentUsage,
    AnalysisRequest,
    AnalysisResult,
    EditRequest,
    EditResult,
    ProviderHealth,
    SkillRunRequest,
)
from app.third_party_api.ai_agent.edits import EditPlan
from app.third_party_api.ai_agent.submission import (
    SCHEMA_FILENAME,
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

ANALYZE_TOOLS: Final = ("Read", "Write")
"""The exact built-in tool set one analyze call may use.

``--bare`` narrows the CLI tool set to ``Bash``/``Edit``/``Read`` and therefore
removes ``Write`` entirely, so analyze cannot use ``--bare``. Naming the set
explicitly keeps the surface at the two tools the submission contract needs:
read the schema and write the result literal.
"""

SUBMISSION_TOOL: Final = "Write"
"""Tool that performs the single write the analyze submission channel accepts."""

_MAX_TOOLS_DETAIL_CHARS: Final = 240
"""Upper bound for the tool list and denial summary kept on a failure detail."""

EDIT_MAX_TURNS: Final = 40
"""Turn cap for one edit call; the process timeout is the other spend guard."""

HEALTH_TIMEOUT_SECONDS: Final = 10.0
"""Upper bound for the ``--version`` health probe."""

CANCELLED_EXIT_CODE: Final = 143
"""128+SIGTERM; a CLI killed by a supervisor rather than a real analysis failure."""

_MAX_DETAIL_CHARS: Final = 1_000
"""Upper bound for a redacted diagnostic carried by a provider error."""

_MAX_VERSION_CHARS: Final = 120
"""Upper bound for the sanitized version text kept in a health detail."""

_MAX_SETTINGS_BYTES: Final = 1024 * 1024
"""Settings files larger than this are ignored by the auth-source probe."""


@dataclass(frozen=True, slots=True)
class _ParsedCliResult:
    """Normalized view of one CLI stdout document."""

    result: Mapping[str, Any] | None
    capabilities: tuple[str, ...]
    session_id: str | None
    usage: AgentUsage
    tools: tuple[str, ...] = ()
    permission_denials: tuple[Mapping[str, Any], ...] = ()
    stop_reason: str | None = None
    num_turns: int | None = None

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

    def default_skill_model(self) -> str | None:
        return claude_skill.default_model(self._settings_file())

    def skill_model_identity(self, model: str | None) -> dict[str, str]:
        return claude_skill.model_identity(model, self._settings_file())

    async def run_skill(self, request: SkillRunRequest, *, diagnostics: dict[str, Any]) -> int:
        """Invoke one slash command in its isolated attempt with the shared CLI runner."""
        return await claude_skill.run(
            request,
            diagnostics,
            self._runner,
            self._binary(),
            self._settings_file(),
            allow_path_fallback=not self.settings
            or self.settings.ai_agent_claude_bin == DEFAULT_CLAUDE_BIN,
        )

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Run one headless analysis and collect it through the submission channel."""
        started = self._clock()
        prep = self._submission.prepare(request.task, request.output_model)
        try:
            return await self._analyze_with(prep, request, started)
        finally:
            # The task directory is disposable; without an explicit release it
            # would live as long as the provider singleton and accumulate
            # schema/result files for every analysis.
            self._submission.discard(prep)

    async def _analyze_with(
        self,
        prep: SubmissionPrep,
        request: AnalysisRequest,
        started: float,
    ) -> AnalysisResult:
        """Run the analysis and one feedback retry against one prepared directory."""
        prompt = _compose_prompt(request.prompt, prep.prompt_addendum)
        settings_file = self._settings_file()
        # The task directory is resolved once and used for both ``cwd`` and the
        # permission rules. The CLI compares the requested path with the path
        # the symlinks resolve to; on hosts where the temp root is a symlink
        # (for example ``/tmp`` -> ``/private/tmp`` on macOS) an unresolved
        # ``cwd`` makes the allow rule fail even when the rule names the same
        # physical directory.
        directory = _resolved_directory(prep.directory)
        argv = self._analyze_argv(
            prompt,
            prep,
            directory=directory,
            settings_file=settings_file,
        )
        _, parsed = await self._call(
            "analysis",
            argv,
            cwd=directory,
            timeout_seconds=ANALYZE_TIMEOUT_SECONDS,
        )
        self._ensure_submission_tool(parsed, attempts=1, outcomes=(), started=started)

        outcomes: list[SubmissionOutcome] = [
            self._submission.collect(prep, request.output_model.model_validate),
        ]
        if not outcomes[-1].is_ok:
            # A denied write is terminal: repeating the same prompt would only
            # burn the second 300s budget against the same permission surface.
            # Only a missing file can mean the write never happened; a parsed
            # but invalid literal still deserves the designed feedback retry.
            denial = _submission_denial_detail(parsed) if outcomes[-1].status == "missing" else None
            if denial is not None:
                raise AgentProviderError(
                    "claude-code analysis submission write was denied",
                    retryable=False,
                    provider_id=self.provider_id,
                    detail=_bounded_detail(
                        f"{denial}; submission {outcomes[-1].status}; "
                        f"{_cli_result_diagnostics(parsed)}",
                    ),
                    trace=_call_trace(outcomes),
                    usage=parsed.usage,
                    latency_ms=_elapsed_ms(started, self._clock),
                )
            # Analyze is stateless, so the retry cannot continue the first CLI
            # session; it repeats the original prompt plus the concrete
            # validation feedback as a fresh call. The budget stays exactly one,
            # and a session id is not needed because nothing is resumed.
            feedback = self._submission.feedback_prompt(outcomes[-1])
            retry_prompt = _compose_prompt(prompt, feedback)
            retry_argv = self._analyze_argv(
                retry_prompt,
                prep,
                directory=directory,
                settings_file=settings_file,
            )
            try:
                _, parsed = await self._call(
                    "analysis",
                    retry_argv,
                    cwd=directory,
                    timeout_seconds=ANALYZE_TIMEOUT_SECONDS,
                )
            except AgentProviderError as exc:
                # The retry process failed before it could submit anything, so
                # keep the first attempt's parse provenance and count both calls.
                exc.trace = replace(_call_trace(outcomes), attempts=len(outcomes) + 1)
                raise
            self._ensure_submission_tool(
                parsed,
                attempts=2,
                outcomes=tuple(outcomes),
                started=started,
            )
            outcomes.append(
                self._submission.collect(prep, request.output_model.model_validate),
            )

        outcome = outcomes[-1]
        trace = _call_trace(outcomes)
        validated = outcome.validated
        if not outcome.is_ok or validated is None:
            detail = _submission_detail(outcome)
            diagnostics = _cli_result_diagnostics(parsed)
            if diagnostics:
                detail = _bounded_detail(f"{detail}; {diagnostics}")
            raise AgentProviderError(
                "claude-code analysis submission failed validation",
                retryable=False,
                provider_id=self.provider_id,
                detail=detail,
                trace=trace,
                usage=parsed.usage,
                latency_ms=_elapsed_ms(started, self._clock),
            )
        return AnalysisResult(
            output=validated.model_dump(mode="json"),
            provider_id=self.provider_id,
            usage=parsed.usage,
            session_id=parsed.session_id,
            latency_ms=_elapsed_ms(started, self._clock),
            retryable=False,
            trace=trace,
        )

    def _ensure_submission_tool(
        self,
        parsed: _ParsedCliResult,
        *,
        attempts: int,
        outcomes: Sequence[SubmissionOutcome],
        started: float,
    ) -> None:
        """Fail immediately when the CLI tool set cannot perform the submission.

        The allow rule is not a tool provider: naming ``Write`` in
        ``--allowed-tools`` cannot bring it back after ``--bare`` removed it. A
        ``system/init`` document makes that mismatch visible before the retry.
        """
        if not parsed.tools or SUBMISSION_TOOL in parsed.tools:
            return
        raise AgentProviderError(
            "claude-code analysis tool set does not include Write",
            retryable=False,
            provider_id=self.provider_id,
            detail=_bounded_detail(
                f"submission tool {SUBMISSION_TOOL} is missing; "
                f"tools={_tool_list_detail(parsed.tools)}",
            ),
            trace=AgentCallTrace(attempts=attempts, submission_rounds=len(outcomes)),
            usage=parsed.usage,
            latency_ms=_elapsed_ms(started, self._clock),
        )

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Collect one EditPlan for the workspace.

        The plan is not applied here: the agent-edit patch source applies it
        deterministically against a scratch mirror and turns the result into a
        PatchBundle.
        """
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
        trace = _call_trace((outcome,))
        validated = outcome.validated
        if not outcome.is_ok or not isinstance(validated, EditPlan):
            raise AgentProviderError(
                "claude-code edit submission failed validation",
                retryable=False,
                provider_id=self.provider_id,
                detail=_submission_detail(outcome),
                trace=trace,
                usage=parsed.usage,
                latency_ms=_elapsed_ms(started, self._clock),
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
            plan=validated,
            trace=trace,
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
        detail = f"{detail}; {self._bare_mode_auth_hint()}"
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
            raise self._cancelled_error(phase, result)
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
                    f"stdout_bytes={len(result.stdout.encode('utf-8'))}; {_diagnostics(result)}",
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

    def _cancelled_error(
        self,
        phase: str,
        result: ClaudeCliResult | None = None,
    ) -> AgentProviderError:
        """Build the normalized cancellation error for one phase.

        A timeout or supervisor cancellation still returns the tail the
        transport captured. Report the bounded stderr and the structured CLI
        evidence (tool set and permission denials) instead of the bare
        ``cancelled`` string, so the 300s failure is diagnosable.
        """
        detail = "cancelled"
        if result is not None:
            parsed = _parse_cli_stdout(result.stdout, fallback_model=self.provider_id)
            diagnostics = _cli_result_diagnostics(parsed)
            stderr = sanitize_detail(result.stderr, limit=600)
            parts = ["cancelled"]
            if diagnostics:
                parts.append(diagnostics)
            if stderr is not None and stderr.strip():
                parts.append(f"stderr={stderr.strip()}")
            if result.stderr_truncated:
                parts.append("stderr_truncated=true")
            detail = _bounded_detail("; ".join(parts))
        return AgentProviderError(
            f"claude-code {phase} call was cancelled",
            retryable=False,
            provider_id=self.provider_id,
            detail=detail,
        )

    def _analyze_argv(
        self,
        prompt: str,
        prep: SubmissionPrep,
        *,
        directory: Path,
        settings_file: Path,
    ) -> tuple[str, ...]:
        """Build one analyze argv; analyze is stateless and never resumes a session.

        ``--bare`` is deliberately absent: it removes ``Write`` from the tool
        set, so the submission file could never be produced. The hardened flags
        keep its context minimization (no CLAUDE.md auto-discovery, hooks and
        plugins from user/project settings ignored, MCP closed, no
        command-running tools) while ``--tools`` limits the built-in set to the
        two tools the submission needs. Writes are permission-checked against
        ``Edit`` rules, not ``Write`` rules, so the one write target is granted
        through an absolute ``Edit(//...)`` rule.
        """
        rules = ",".join(
            (
                f"Read({_permission_rule_path(directory / SCHEMA_FILENAME)})",
                f"Edit({_permission_rule_path(prep.result_path)})",
            ),
        )
        argv = [
            self._binary(),
            "--safe-mode",
            "--restricted",
            "--strict-mcp-config",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            PERMISSION_MODE,
            "--tools",
            ",".join(ANALYZE_TOOLS),
            "--allowed-tools",
            rules,
            "--no-session-persistence",
        ]
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
        """Build one edit argv; exploration is read-only and stateless.

        ``--max-turns`` bounds one call's spend; the timeout constant bounds its
        wall clock. ``--no-session-persistence`` matches analyze (#488): an edit
        call is a single request, so the shared settings directory never needs
        to be writable by the service user.
        """
        argv = [
            self._binary(),
            "--bare",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--permission-mode",
            PERMISSION_MODE,
            "--max-turns",
            str(EDIT_MAX_TURNS),
            "--allowed-tools",
            ",".join((*READ_ONLY_TOOLS, *prep.allowed_tools)),
            "--no-session-persistence",
        ]
        if settings_file.is_file():
            argv.extend(("--settings", str(settings_file)))
        return tuple(argv)

    def _binary(self) -> str:
        return claude_binary(self.settings)

    def _settings_file(self) -> Path:
        return self._settings_path_override or claude_settings_file(self.settings)

    def _bare_mode_auth_hint(self) -> str:
        """Name the bare-mode credential *source*, never a credential value.

        ``--bare`` accepts only ``ANTHROPIC_API_KEY`` or an ``apiKeyHelper`` from
        the deployment settings file; OAuth and the keychain are never read. The
        probe still reports healthy when neither is configured because the
        binary itself works, but the detail says so instead of implying that a
        real analysis would authenticate.
        """
        if _env_declares("ANTHROPIC_API_KEY"):
            return "bare-mode auth: ANTHROPIC_API_KEY"
        if _settings_declare_api_key_helper(self._settings_file()):
            return "bare-mode auth: apiKeyHelper"
        return "no bare-mode auth configured (ANTHROPIC_API_KEY / apiKeyHelper)"

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


def claude_binary(settings: Settings | None) -> str:
    """Resolve the shared service binary installed by Deploy."""
    return str(Path(settings.ai_agent_claude_bin if settings else DEFAULT_CLAUDE_BIN).expanduser())


def claude_settings_file(settings: Settings | None) -> Path:
    """Resolve the explicit service settings, CLI config directory, or user default."""
    configured = (settings.ai_agent_claude_settings or "").strip() if settings else ""
    if configured:
        return Path(configured).expanduser()
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR", "").strip()
    directory = Path(config_dir).expanduser() if config_dir else Path.home() / ".claude"
    return directory / CLAUDE_SETTINGS_FILENAME


def _binary_available(binary: str) -> bool:
    """Return whether the configured binary is present without executing it."""
    if not binary:
        return False
    if os.sep in binary or (os.altsep is not None and os.altsep in binary):
        return Path(binary).is_file()
    return shutil.which(binary) is not None


def _env_declares(name: str) -> bool:
    """Return whether an environment variable holds a non-blank value.

    The value is only tested for presence and is never logged or returned, so a
    health detail can name the credential source without echoing a secret.
    """
    return bool(os.environ.get(name, "").strip())


def _settings_declare_api_key_helper(settings_file: Path) -> bool:
    """Return whether the settings file declares a non-empty ``apiKeyHelper``.

    Only the key's presence and non-blank-ness are consulted; the helper command
    itself may embed a token, so its text never reaches a health detail.
    """
    try:
        if settings_file.stat().st_size > _MAX_SETTINGS_BYTES:
            return False
        document = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(document, Mapping):
        return False
    helper = document.get("apiKeyHelper")
    return isinstance(helper, str) and bool(helper.strip())


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
    first ``system/init`` capability and tool lists it sees. The result also
    carries the CLI's own ``permission_denials``/``stop_reason``/``num_turns``
    evidence. No version string is consulted anywhere in this function.
    """
    capabilities: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    result: Mapping[str, Any] | None = None
    document = stdout.strip()
    single = _single_json_object(document)
    if single is not None:
        document_type = single.get("type")
        capabilities = _capabilities_from(single)
        tools = _tools_from(single)
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
                line_tools = _tools_from(item)
                if line_tools:
                    tools = line_tools
                continue
            if item_type == "result":
                result = item
    return _ParsedCliResult(
        result=result,
        capabilities=capabilities,
        session_id=_session_id_from(result),
        usage=_usage_from(result, fallback_model=fallback_model),
        tools=tools,
        permission_denials=_permission_denials_from(result),
        stop_reason=_non_blank_text(result, "stop_reason"),
        num_turns=_optional_count(result, "num_turns"),
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


def _tools_from(payload: Mapping[str, Any]) -> tuple[str, ...]:
    """Extract ``system/init.tools`` from an init document only.

    The tool list is CLI-owned: it says which tools actually exist, unlike the
    allow list, which can only further restrict them.
    """
    if payload.get("type") != "system" or payload.get("subtype") != "init":
        return ()
    raw = payload.get("tools")
    if not isinstance(raw, list):
        return ()
    return tuple(value.strip() for value in raw if isinstance(value, str) and value.strip())


def _permission_denials_from(
    payload: Mapping[str, Any] | None,
) -> tuple[Mapping[str, Any], ...]:
    """Return the result's structured permission denials, keeping non-mapping items out."""
    if payload is None:
        return ()
    raw = payload.get("permission_denials")
    if not isinstance(raw, list):
        return ()
    return tuple(denial for item in raw if (denial := _as_mapping(item)) is not None)


def _non_blank_text(payload: Mapping[str, Any] | None, *keys: str) -> str | None:
    """Return the first non-blank string value, or ``None``."""
    if payload is None:
        return None
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _optional_count(payload: Mapping[str, Any] | None, key: str) -> int | None:
    """Return a non-negative integer counter, or ``None`` when it is absent."""
    if payload is None:
        return None
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    return int(value)


def _session_id_from(payload: Mapping[str, Any] | None) -> str | None:
    """Return a non-blank session id, if the CLI reported one."""
    if payload is None:
        return None
    value = payload.get("session_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _usage_from(payload: Mapping[str, Any] | None, *, fallback_model: str) -> AgentUsage:
    """Map the CLI usage documents into ``AgentUsage``.

    The real CLI mixes spellings: the result document carries snake_case
    ``usage``/``total_cost_usd`` and a camelCase ``modelUsage`` whose entries use
    ``inputTokens``/``outputTokens``/``costUSD``. Both spellings are accepted so
    the per-model branch actually fires against the real shape. The per-model
    breakdown is the token truth when present; the aggregate ``usage`` is never
    added on top of it, which would double-count tokens.
    """
    if payload is None:
        return AgentUsage(model=fallback_model)
    usage = _as_mapping(payload.get("usage"))
    model_usage = _as_mapping(_first_present(payload, "model_usage", "modelUsage"))
    models: list[str] = []
    model_cost = 0.0
    if model_usage:
        input_tokens = 0
        output_tokens = 0
        for name, raw_entry in model_usage.items():
            entry = _as_mapping(raw_entry)
            if entry is None:
                continue
            models.append(name)
            input_tokens += _as_int(_first_present(entry, "input_tokens", "inputTokens"))
            output_tokens += _as_int(_first_present(entry, "output_tokens", "outputTokens"))
            model_cost += _as_float(_first_present(entry, "cost_usd", "costUSD"))
    else:
        input_tokens = _as_int(_first_present(usage, "input_tokens", "inputTokens"))
        output_tokens = _as_int(_first_present(usage, "output_tokens", "outputTokens"))

    raw_total_cost = payload.get("total_cost_usd")
    cost = _as_float(raw_total_cost) if raw_total_cost is not None else model_cost
    # The real CLI has no top-level ``model``; deriving the identity from the
    # ``modelUsage`` keys is what makes the model answerable in call events.
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


def _first_present(payload: Mapping[str, Any] | None, *keys: str) -> Any:
    """Return the first present key's value, or ``None`` when none is present."""
    if payload is None:
        return None
    for key in keys:
        if key in payload:
            return payload[key]
    return None


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


_DENIED_WRITE_TOOLS: Final = frozenset({"Bash", "Edit", "NotebookEdit", "Write"})
"""Tools whose denial means the model tried a path outside the submission rule."""


def _resolved_directory(directory: Path) -> Path:
    """Resolve a task directory once so ``cwd`` and permission rules agree."""
    return directory.resolve()


def _permission_rule_path(path: Path) -> str:
    """Render one absolute Claude permission path (the ``//`` anchor).

    A single leading slash anchors at the settings source; only ``//`` means
    the filesystem root. The service runs on POSIX, where ``as_posix`` produces
    the forward-slash form the CLI matches.
    """
    return f"//{path.resolve().as_posix().lstrip('/')}"


def _tool_list_detail(tools: Sequence[str]) -> str:
    """Render a bounded tool list for one failure detail."""
    text = ",".join(tools)
    return text[:_MAX_TOOLS_DETAIL_CHARS] or "none"


def _denial_target(denial: Mapping[str, Any]) -> str | None:
    """Return the bounded file path or command one denial names."""
    tool_input = _as_mapping(denial.get("tool_input"))
    if tool_input is None:
        return None
    for key in ("file_path", "path", "command"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return sanitize_message(value.strip(), limit=200)
    return None


def _render_denial(denial: Mapping[str, Any]) -> str:
    """Render one permission denial as ``Tool(target)`` without model prose."""
    tool = _non_blank_text(denial, "tool_name") or "unknown"
    target = _denial_target(denial)
    return f"{tool}({target})" if target else tool


def _submission_denial_detail(parsed: _ParsedCliResult) -> str | None:
    """Name the first denied write that made the submission impossible."""
    for denial in parsed.permission_denials:
        tool = _non_blank_text(denial, "tool_name")
        if tool in _DENIED_WRITE_TOOLS:
            return f"permission denied: {_render_denial(denial)}"
    return None


def _cli_result_diagnostics(parsed: _ParsedCliResult) -> str:
    """Summarize the CLI's structured evidence without echoing model prose."""
    parts: list[str] = []
    if parsed.tools:
        parts.append(f"tools={_tool_list_detail(parsed.tools)}")
    stop_reason = parsed.stop_reason
    if stop_reason is not None:
        parts.append(f"stop_reason={sanitize_message(stop_reason, limit=80)}")
    if parsed.num_turns is not None:
        parts.append(f"num_turns={parsed.num_turns}")
    if parsed.permission_denials:
        rendered = "; ".join(_render_denial(denial) for denial in parsed.permission_denials[:3])
        parts.append(f"permission_denials={rendered[:_MAX_TOOLS_DETAIL_CHARS]}")
    return "; ".join(parts)


def _diagnostics(result: ClaudeCliResult) -> str:
    """Render a bounded, redacted stderr diagnostic without echoing stdout."""
    parts = [f"exit_code={result.returncode}"]
    stderr = sanitize_detail(result.stderr, limit=600)
    if stderr is not None and stderr.strip():
        parts.append(f"stderr={stderr.strip()}")
    return "; ".join(parts)


def _error_result_detail(payload: Mapping[str, Any], result: ClaudeCliResult) -> str:
    """Render an ``is_error`` result without including its model text.

    The real CLI may report ``is_error=true`` together with ``subtype=success``
    and a concrete HTTP status, so ``subtype`` alone can describe a failed call
    as a success. The API status (when present) is what makes the detail
    actionable; the model's result text is never echoed.
    """
    parts = ["is_error"]
    subtype = payload.get("subtype")
    if isinstance(subtype, str) and subtype.strip():
        parts.append(f"subtype={subtype.strip()}")
    status = payload.get("api_error_status")
    if isinstance(status, (int, float, str)) and not isinstance(status, bool):
        status_text = str(status).strip()
        if status_text:
            parts.append(f"api_error_status={status_text[:40]}")
    parts.append(f"exit_code={result.returncode}")
    return "; ".join(parts)


def _submission_detail(outcome: SubmissionOutcome) -> str:
    """Bound the concrete validation/parse reason kept on a provider error."""
    if outcome.validation_error is not None:
        return _bounded_detail(f"validation failed: {outcome.validation_error}")
    if outcome.parse_error is not None:
        return _bounded_detail(f"submission {outcome.status}: {outcome.parse_error}")
    return _bounded_detail(f"submission {outcome.status}")


def _call_trace(outcomes: Sequence[SubmissionOutcome]) -> AgentCallTrace:
    """Summarize the collection rounds into bounded layer-5 provenance.

    One round runs per model call, so ``attempts`` equals the number of
    outcomes; a parse failure is a round whose read/parse ladder produced no
    document, and a validation failure is a parsed document the caller's model
    rejected. The last round owns ``parsed_by`` because that is the document the
    caller actually consumed.
    """
    if not outcomes:
        return AgentCallTrace()
    last = outcomes[-1]
    return AgentCallTrace(
        attempts=len(outcomes),
        submission_rounds=len(outcomes),
        submission_parse_failures=sum(1 for outcome in outcomes if outcome.parse_error is not None),
        submission_validation_failures=sum(
            1 for outcome in outcomes if outcome.validation_error is not None
        ),
        parsed_by=last.parsed_by,
        repaired=last.parsed_by == "repair",
    )


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
    "ANALYZE_TOOLS",
    "EDIT_PLAN_FILENAME",
    "READ_ONLY_TOOLS",
    "SUBMISSION_TOOL",
    "AsyncioClaudeCliRunner",
    "ClaudeCliResult",
    "ClaudeCliRunner",
    "ClaudeCodeProvider",
]
