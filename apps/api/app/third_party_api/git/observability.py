"""Sanitized observability for git subprocesses and proxy decisions.

Each git invocation emits one structured ``git.proxy.operation`` log line and,
inside a run scope, contributes one bounded record to the run's
``workspace_prepared`` event. Records carry only an operation name, proxy
booleans/state, a fallback reason, timing, an exit code, and a host name; full
remote URLs, credentials, stderr, and proxy configuration never appear.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

MAX_EVENT_OPERATIONS = 20
"""Upper bound on the per-run ``gitOperations`` list attached to events."""

PUBLIC_PROXY_STATES = frozenset({"disabled", "closed", "open"})
"""Event-facing proxy states; ``half_open`` routes through the proxy as closed."""

EVENT_OPERATIONS = frozenset({"ls-remote", "clone", "fetch", "push"})
"""Operations kept in the bounded run-event list; every subprocess is still logged."""

_URL_WITH_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)
_SCP_LIKE = re.compile(r"^[^@\s/]+@([^:/\s]+):[^\s]+$")


@dataclass(frozen=True, slots=True)
class GitOperationRecord:
    """One sanitized git process or proxy probe observation."""

    operation: str
    via_proxy: bool
    proxy_state_before: str
    proxy_state_after: str
    fallback_reason: str | None
    duration_ms: int
    exit_code: int | None
    target_host: str | None

    def as_payload(self) -> dict[str, object]:
        """Return the camelCase event/log fields without any raw process output."""
        return {
            "operation": self.operation,
            "viaProxy": self.via_proxy,
            "proxyStateBefore": _public_proxy_state(self.proxy_state_before),
            "proxyStateAfter": _public_proxy_state(self.proxy_state_after),
            "fallbackReason": self.fallback_reason,
            "durationMs": self.duration_ms,
            "exitCode": self.exit_code,
            "targetHost": self.target_host,
        }


@dataclass(slots=True)
class GitOperationCollector:
    """Collect the operations of one run scope for event payloads."""

    run_id: str | None = None
    job_id: str | None = None
    stage: str | None = None
    target_host: str | None = None
    _records: list[GitOperationRecord] = field(default_factory=list)

    @property
    def records(self) -> tuple[GitOperationRecord, ...]:
        """Return every observed operation in chronological order."""
        return tuple(self._records)

    @property
    def proxy_state(self) -> str:
        """Return the last observed public proxy state, or ``disabled``."""
        if not self._records:
            return "disabled"
        return _public_proxy_state(self._records[-1].proxy_state_after)

    def add(self, record: GitOperationRecord) -> None:
        """Append one operation record."""
        self._records.append(record)

    def bounded(self, limit: int = MAX_EVENT_OPERATIONS) -> tuple[list[dict[str, object]], bool]:
        """Return at most ``limit`` payloads plus a truncation flag."""
        if limit < 1:
            raise ValueError("operation limit must be positive")
        selected = self._records[:limit]
        return [record.as_payload() for record in selected], len(self._records) > limit


_current_collector: ContextVar[GitOperationCollector | None] = ContextVar(
    "git_operation_collector",
    default=None,
)


@contextmanager
def git_operation_scope(
    *,
    run_id: str | None,
    job_id: str | None = None,
    stage: str | None = None,
    target_host: str | None = None,
) -> Iterator[GitOperationCollector]:
    """Bind one collector to the current task for the duration of a run stage."""
    collector = GitOperationCollector(
        run_id=run_id,
        job_id=job_id,
        stage=stage,
        target_host=target_host,
    )
    token = _current_collector.set(collector)
    try:
        yield collector
    finally:
        _current_collector.reset(token)


def current_git_operation_collector() -> GitOperationCollector | None:
    """Return the collector bound to the current task, if any."""
    return _current_collector.get()


def emit_git_operation(record: GitOperationRecord) -> None:
    """Collect network operations (when in a run scope) and log every operation."""
    collector = current_git_operation_collector()
    if collector is not None and record.operation in EVENT_OPERATIONS:
        collector.add(record)
    _log_operation(record, collector)


def emit_proxy_probe(record: GitOperationRecord) -> None:
    """Log a health probe separately from run traffic with no run id."""
    _log_operation(record, None)


def classify_git_operation(argv: tuple[str, ...]) -> str:
    """Return the git subcommand used by an argv array, skipping global options."""
    index = 1
    while index < len(argv):
        argument = argv[index]
        if argument in {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}:
            index += 2
            continue
        if argument.startswith("-"):
            index += 1
            continue
        return argument
    return "other"


def is_proxy_traffic(argv: tuple[str, ...]) -> bool:
    """Return whether one operation can actually reach a remote over the proxy.

    A workspace clone from a local ref cache never touches the network, even
    though it inherits the proxy environment; recording it as proxy traffic
    would misreport whether the run used the proxy.
    """
    operation = classify_git_operation(argv)
    if operation in {"fetch", "push", "pull", "ls-remote"}:
        return True
    if operation == "remote" and len(argv) >= 3 and argv[2] in {"update", "prune"}:
        return True
    if operation == "clone":
        for argument in argv[2:]:
            if argument.startswith("-"):
                continue
            if "://" in argument or _SCP_LIKE.fullmatch(argument) is not None:
                return True
        return False
    return False


def target_host_for(argv: tuple[str, ...], fallback: str | None = None) -> str | None:
    """Derive one host name from argv without ever retaining the full URL."""
    for argument in argv:
        host = _host_from_remote(argument)
        if host is not None:
            return host
    return fallback


def fallback_reason_for(stderr: str) -> str:
    """Classify a proxy-layer failure into one stable, credential-free reason."""
    diagnostic = stderr.lower()
    if "407" in diagnostic:
        return "407"
    if "connect tunnel failed" in diagnostic or "proxy connect aborted" in diagnostic:
        return "tunnel"
    if "timed out" in diagnostic or "timeout" in diagnostic:
        return "timeout"
    if "could not resolve proxy" in diagnostic or "proxy error" in diagnostic:
        return "proxy_connect"
    if "failed to connect" in diagnostic:
        return "proxy_connect"
    return "proxy_error"


def _host_from_remote(value: str) -> str | None:
    """Extract a host from an http(s)/ssh URL or an scp-like git remote."""
    if "://" in value and _URL_WITH_SCHEME.match(value):
        try:
            parsed = urlsplit(value)
        except ValueError:
            return None
        return parsed.hostname or None
    if " " in value or "\n" in value:
        return None
    match = _SCP_LIKE.fullmatch(value)
    if match is not None:
        return match.group(1)
    return None


def _public_proxy_state(state: str) -> str:
    """Map internal states to the documented disabled/closed/open vocabulary."""
    if state in PUBLIC_PROXY_STATES:
        return state
    return "closed" if state == "half_open" else "disabled"


def _log_operation(
    record: GitOperationRecord,
    collector: GitOperationCollector | None,
) -> None:
    """Emit one structured log line with run and sanitized operation fields."""
    fields: dict[str, object] = {
        "event": "git.proxy.operation",
        "runId": collector.run_id if collector is not None else None,
        "jobId": collector.job_id if collector is not None else None,
        "stage": collector.stage if collector is not None else None,
        **record.as_payload(),
    }
    level = logging.INFO if record.exit_code in {None, 0} else logging.WARNING
    logger.log(level, "git operation", extra=fields)
