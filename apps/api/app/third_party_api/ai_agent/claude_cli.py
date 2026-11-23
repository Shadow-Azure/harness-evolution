"""Shared subprocess transport for analysis, edits and sandboxed Skill calls."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

_GRACE_SECONDS = 5.0


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
    stderr_truncated: bool = False


class ClaudeCliCancelled(asyncio.CancelledError):
    """Caller cancellation with the diagnostics available after process cleanup."""

    def __init__(self, result: ClaudeCliResult) -> None:
        super().__init__()
        self.result = result


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
        # A verbose CLI must not fill service memory with stderr. Keep the tail
        # available after a timeout or cancellation, just like a normal exit.
        with tempfile.TemporaryFile() as errors:
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd),
                env=dict(env),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=errors,
                start_new_session=True,
            )
            io_task = asyncio.create_task(process.communicate())
            interrupted = False
            timed_out = False
            stdout = b""
            try:
                stdout, _ = await asyncio.wait_for(asyncio.shield(io_task), timeout_seconds)
            except (TimeoutError, asyncio.CancelledError) as exc:
                interrupted = isinstance(exc, asyncio.CancelledError)
                timed_out = not interrupted
                _signal_process_group(process, signal.SIGINT)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(process.wait(), self._grace_seconds)
            finally:
                # The leader can exit before a tool it spawned. The session id
                # is the original PID even after the leader has been reaped.
                _signal_process_group(process, signal.SIGKILL)
                if process.returncode is None:
                    await process.wait()
                if not io_task.done():
                    io_task.cancel()
                await asyncio.gather(io_task, return_exceptions=True)
            size = errors.seek(0, os.SEEK_END)
            errors.seek(max(0, size - 16384))
            result = ClaudeCliResult(
                returncode=process.returncode if process.returncode is not None else -1,
                stdout=stdout.decode(errors="replace"),
                stderr=errors.read().decode(errors="replace"),
                cancelled=timed_out or interrupted,
                stderr_truncated=size > 16384,
            )
        if interrupted:
            raise ClaudeCliCancelled(result)
        return result


def _signal_process_group(process: _ManagedProcess, sig: signal.Signals) -> None:
    """Signal the child session, including descendants after the leader exits."""
    if sys.platform == "win32":
        if process.returncode is None:
            if sig == signal.SIGKILL:
                process.kill()
            else:
                process.terminate()
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, sig)
