"""Optional git egress proxy with in-process health fallback.

Only git subprocesses receive the proxy environment. The controller keeps a
process-local circuit breaker: ``closed`` uses the local proxy, consecutive
proxy-layer failures move it to ``open`` (direct access), a background probe
after the cooldown enters ``half_open``, and consecutive successes close it
again. The proxy URL is a credential-free local address (for example
``http://127.0.0.1:10808``); VLESS and its UUID never reach the API.
"""

from __future__ import annotations

import asyncio
import http.client
import logging
import os
import signal
import ssl
import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import SplitResult, urlsplit

from app.third_party_api.git.observability import (
    GitOperationRecord,
    classify_git_operation,
    current_git_operation_collector,
    emit_git_operation,
    emit_proxy_probe,
    fallback_reason_for,
    is_proxy_traffic,
    target_host_for,
)

logger = logging.getLogger(__name__)

type ProxyState = Literal["disabled", "closed", "open", "half_open"]
type ProxyProbe = Callable[[], Awaitable[bool]]
type Clock = Callable[[], float]
type SpawnGit = Callable[
    [tuple[str, ...], Path | None, dict[str, str]],
    Awaitable["GitProcessResult"],
]

_PROXY_ENVIRONMENT_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)
_SSH_REWRITES = (
    ("git@github.com:", "https://github.com/"),
    ("ssh://git@github.com/", "https://github.com/"),
)
_DEFAULT_PROBE_HOST = "github.com"
_DEFAULT_PROBE_PORT = 443


@dataclass(frozen=True, slots=True)
class GitProcessResult:
    """Captured output from one argument-array git process."""

    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class ProxyStatus:
    """Sanitized proxy state for logging and tests."""

    enabled: bool
    state: ProxyState
    failures: int
    successes: int


def _split_proxy_url(proxy_url: str) -> SplitResult | None:
    """Parse one credential-free HTTP proxy URL or return ``None``."""
    try:
        parsed = urlsplit(proxy_url)
    except ValueError:
        return None
    if parsed.scheme != "http" or not parsed.hostname or parsed.username is not None:
        return None
    if parsed.password is not None or parsed.query or parsed.fragment:
        return None
    if parsed.path not in {"", "/"}:
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None or not 1 <= port <= 65_535:
        return None
    return parsed


def build_git_environment() -> dict[str, str]:
    """Return the sanitized environment every git subprocess starts from."""
    environment = dict(os.environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "Never"
    return environment


def strip_proxy_environment(environment: dict[str, str]) -> None:
    """Remove every proxy variable so a fallback really is direct."""
    for key in _PROXY_ENVIRONMENT_KEYS:
        environment.pop(key, None)


def _merge_no_proxy(environment: dict[str, str]) -> str:
    """Keep operator exclusions and always bypass the local proxy for loopback."""
    ambient = environment.get("NO_PROXY") or environment.get("no_proxy") or ""
    parts = [part.strip() for part in ambient.split(",") if part.strip()]
    for loopback in ("127.0.0.1", "localhost", "::1"):
        if loopback not in parts:
            parts.append(loopback)
    return ",".join(parts)


def apply_proxy_environment(
    environment: dict[str, str],
    proxy_url: str,
    *,
    rewrite_ssh: bool = True,
) -> None:
    """Point git at the local proxy and optionally rewrite GitHub SSH remotes.

    ``GIT_CONFIG_*`` is used instead of touching argv so command construction
    and its assertions stay unchanged. SSH remotes outside GitHub are not
    rewritten and therefore cannot use an HTTP proxy. Callers skip the rewrite
    for ``git remote get-url`` (which would resolve ``insteadOf`` and break the
    stored-URL comparisons) and for ``git push`` (SSH auth must stay intact).
    """
    strip_proxy_environment(environment)
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        environment[key] = proxy_url
    no_proxy = _merge_no_proxy(environment)
    environment["NO_PROXY"] = no_proxy
    environment["no_proxy"] = no_proxy
    if not rewrite_ssh:
        return
    environment["GIT_CONFIG_COUNT"] = str(len(_SSH_REWRITES))
    for index, (instead_of, replacement) in enumerate(_SSH_REWRITES):
        environment[f"GIT_CONFIG_KEY_{index}"] = f"url.{replacement}.insteadOf"
        environment[f"GIT_CONFIG_VALUE_{index}"] = instead_of


def allows_ssh_rewrite(argv: tuple[str, ...]) -> bool:
    """Return whether this git command may safely rewrite SSH remotes to HTTPS.

    ``git remote get-url`` must keep the raw stored URL, and ``git push`` must
    keep SSH authentication; both skip the rewrite.
    """
    if len(argv) < 2:
        return True
    if argv[1] == "push":
        return False
    return not (len(argv) >= 3 and argv[1] == "remote" and argv[2] == "get-url")


def is_network_command(argv: tuple[str, ...]) -> bool:
    """Return whether a successful command proves the proxy link works.

    Local commands (``rev-parse``, ``cat-file``, ``commit``) succeed even when
    the proxy is dead, so they must not reset the breaker or close half-open.
    """
    if len(argv) < 2:
        return False
    if argv[1] in {"clone", "fetch", "pull", "push", "ls-remote"}:
        return True
    return bool(
        argv[1] == "remote" and len(argv) >= 3 and argv[2] in {"update", "prune"},
    )


def is_proxy_failure(stderr: str, proxy_url: str) -> bool:
    """Classify only failures that clearly came from the proxy layer.

    A slow GitHub through a healthy proxy stays a content timeout; mapping it
    to a proxy failure would open the breaker for a link the direct path cannot
    fix either.
    """
    lowered = stderr.lower()
    if not lowered:
        return False
    parsed = _split_proxy_url(proxy_url)
    host = (parsed.hostname or "").lower() if parsed is not None else ""
    port = str(parsed.port or 80) if parsed is not None else ""
    if "proxy connect aborted" in lowered:
        return True
    if "could not resolve proxy" in lowered or "proxy error" in lowered:
        return True
    if "connect tunnel failed" in lowered:
        return True
    if "error: 407" in lowered or ("407" in lowered and "proxy" in lowered):
        return True
    return bool(
        "failed to connect" in lowered and host and host in lowered and port in lowered,
    )


async def probe_http_connect(
    proxy_url: str,
    *,
    target_host: str = _DEFAULT_PROBE_HOST,
    target_port: int = _DEFAULT_PROBE_PORT,
    timeout_seconds: float = 5.0,
) -> bool:
    """Probe the local proxy with one bounded HTTP CONNECT tunnel."""
    parsed = _split_proxy_url(proxy_url)
    if parsed is None or parsed.hostname is None:
        return False
    port = parsed.port or 80
    ssl_context = ssl.create_default_context() if parsed.scheme == "https" else None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                parsed.hostname,
                port,
                ssl=ssl_context,
                server_hostname=parsed.hostname if ssl_context is not None else None,
            ),
            timeout=timeout_seconds,
        )
    except (OSError, TimeoutError, ssl.SSLError):
        return False
    try:
        request = (
            f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
            f"Host: {target_host}:{target_port}\r\n"
            "Proxy-Connection: Keep-Alive\r\n\r\n"
        )
        writer.write(request.encode("ascii"))
        await asyncio.wait_for(writer.drain(), timeout=timeout_seconds)
        status = await asyncio.wait_for(reader.readline(), timeout=timeout_seconds)
    except (OSError, TimeoutError, ssl.SSLError):
        return False
    finally:
        with suppress(OSError, TimeoutError):
            writer.close()
            await writer.wait_closed()
    return status.startswith(b"HTTP/") and b" 200 " in status


def _probe_https_blocking(
    proxy_url: str,
    target_host: str,
    target_port: int,
    timeout_seconds: float,
) -> bool:
    """Fetch one HTTPS HEAD through the proxy (blocking; run in a thread)."""
    parsed = _split_proxy_url(proxy_url)
    if parsed is None or parsed.hostname is None:
        return False
    connection = http.client.HTTPSConnection(
        parsed.hostname,
        parsed.port or 80,
        timeout=timeout_seconds,
    )
    try:
        connection.set_tunnel(target_host, target_port)
        connection.request(
            "HEAD",
            "/",
            headers={"User-Agent": "harness-evolution-probe"},
        )
        response = connection.getresponse()
        response.read(1)
        return response.status < 500 and response.status != 407
    except (OSError, http.client.HTTPException, ValueError):
        return False
    finally:
        with suppress(OSError):
            connection.close()


async def probe_https_through_proxy(
    proxy_url: str,
    *,
    target_host: str = _DEFAULT_PROBE_HOST,
    target_port: int = _DEFAULT_PROBE_PORT,
    timeout_seconds: float = 5.0,
) -> bool:
    """Probe a real HTTPS HEAD through the proxy, not just the CONNECT line.

    This catches a local client that accepts CONNECT but blackholes the VLESS
    path; a bare CONNECT check would keep the circuit closed while every git
    operation times out.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _probe_https_blocking,
                proxy_url,
                target_host,
                target_port,
                max(0.5, timeout_seconds - 0.5),
            ),
            timeout=timeout_seconds,
        )
    except (TimeoutError, OSError):
        return False


async def _sleep_briefly(seconds: float) -> None:
    """Sleep in one place so tests can patch a single symbol if needed."""
    await asyncio.sleep(seconds)


class GitProxyController:
    """Track proxy health and decide whether one git subprocess uses it."""

    def __init__(
        self,
        proxy_url: str | None = None,
        *,
        probe: ProxyProbe | None = None,
        interval_seconds: float = 60.0,
        probe_timeout_seconds: float = 5.0,
        failure_threshold: int = 3,
        success_threshold: int = 2,
        open_seconds: float = 30.0,
        clock: Clock = time.monotonic,
    ) -> None:
        """Bind the local proxy URL, probe seam, and circuit thresholds."""
        self._proxy_url = (proxy_url or "").strip() or None
        self._proxy = _split_proxy_url(self._proxy_url) if self._proxy_url else None
        self._probe = probe or self._default_probe
        self._interval_seconds = interval_seconds
        self._probe_timeout_seconds = probe_timeout_seconds
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._open_seconds = open_seconds
        self._clock = clock
        self._state: ProxyState = "disabled" if self._proxy is None else "closed"
        self._failures = 0
        self._successes = 0
        self._opened_at = 0.0
        self._probe_attempts = 0
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    @classmethod
    def from_settings(cls, settings: object) -> GitProxyController:
        """Build a controller from API settings without importing a cycle."""
        return cls(
            getattr(settings, "git_proxy", None),
            interval_seconds=float(getattr(settings, "git_proxy_probe_interval_seconds", 60.0)),
            probe_timeout_seconds=float(getattr(settings, "git_proxy_probe_timeout_seconds", 5.0)),
        )

    @property
    def enabled(self) -> bool:
        """Return whether a proxy URL was configured."""
        return self._state != "disabled"

    @property
    def state(self) -> ProxyState:
        """Return the current circuit state."""
        return self._state

    @property
    def status(self) -> ProxyStatus:
        """Return counters safe to log or assert on."""
        return ProxyStatus(
            enabled=self.enabled,
            state=self._state,
            failures=self._failures,
            successes=self._successes,
        )

    def start(self) -> None:
        """Start the background probe loop when a proxy is configured."""
        if not self.enabled or self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run_forever(), name="git-proxy-probe")

    async def stop(self) -> None:
        """Stop the background probe loop."""
        self._stopping = True
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def endpoint(self) -> str | None:
        """Return the proxy URL when the circuit currently allows it."""
        async with self._lock:
            if self._state in {"disabled", "open"}:
                return None
            return self._proxy_url

    async def report_success(self) -> None:
        """Record a successful git operation through the proxy."""
        async with self._lock:
            self._failures = 0
            if self._state == "half_open":
                self._successes += 1
                if self._successes >= self._success_threshold:
                    self._state = "closed"
                    self._successes = 0
                    self._log_state("closed")
            elif self._state == "closed":
                self._successes = 0

    async def report_failure(self) -> None:
        """Record one proxy-layer failure and open the circuit when needed."""
        async with self._lock:
            self._successes = 0
            self._failures += 1
            if self._state == "half_open" or self._failures >= self._failure_threshold:
                self._open()

    async def probe_once(self) -> bool:
        """Run one bounded probe and move the state machine accordingly."""
        state_before = self._state
        started = time.perf_counter()
        try:
            healthy = await asyncio.wait_for(
                self._probe(),
                timeout=self._probe_timeout_seconds,
            )
        except (TimeoutError, OSError):
            healthy = False
        self._probe_attempts += 1
        async with self._lock:
            if healthy:
                self._failures = 0
                if self._state == "open":
                    self._state = "half_open"
                    self._successes = 1
                    self._log_state("half_open")
                    if self._successes >= self._success_threshold:
                        self._state = "closed"
                        self._successes = 0
                        self._log_state("closed")
                elif self._state == "half_open":
                    self._successes += 1
                    if self._successes >= self._success_threshold:
                        self._state = "closed"
                        self._successes = 0
                        self._log_state("closed")
            else:
                if self._state in {"open", "half_open"} or (
                    self._state == "closed" and self._probe_attempts == 1
                ):
                    self._open()
                elif self._state == "closed":
                    self._failures += 1
                    if self._failures >= self._failure_threshold:
                        self._open()
        emit_proxy_probe(
            GitOperationRecord(
                operation="probe",
                via_proxy=self.enabled,
                proxy_state_before=state_before,
                proxy_state_after=self._state,
                fallback_reason=None,
                duration_ms=int((time.perf_counter() - started) * 1000),
                exit_code=0 if healthy else 1,
                target_host=_DEFAULT_PROBE_HOST,
            ),
        )
        return healthy

    def _open(self) -> None:
        """Open the circuit and start a fresh cooldown."""
        self._state = "open"
        self._opened_at = self._clock()
        self._successes = 0
        self._log_state("open")

    async def _run_forever(self) -> None:
        """Probe periodically; while open, retry no earlier than the cooldown."""
        while not self._stopping:
            try:
                await self.probe_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "git proxy probe failed unexpectedly",
                    extra={"event": "git.proxy.probe_error"},
                )
            await _sleep_briefly(self._next_delay())

    def _next_delay(self) -> float:
        """Return the interval, shortened to the remaining cooldown when open."""
        if self._state != "open":
            return self._interval_seconds
        remaining = self._open_seconds - (self._clock() - self._opened_at)
        return max(1.0, min(self._interval_seconds, remaining))

    def _log_state(self, state: ProxyState) -> None:
        """Log one state transition without exposing the proxy address or config."""
        if state == "open":
            logger.warning(
                "git proxy unavailable; using direct git access",
                extra={
                    "event": "git.proxy.state",
                    "state": state,
                    "failures": self._failures,
                },
            )
            return
        logger.info(
            "git proxy state changed",
            extra={
                "event": "git.proxy.state",
                "state": state,
                "successes": self._successes,
            },
        )

    async def _default_probe(self) -> bool:
        """Probe the configured local proxy with a real HTTPS HEAD."""
        if self._proxy_url is None:
            return False
        return await probe_https_through_proxy(
            self._proxy_url,
            timeout_seconds=self._probe_timeout_seconds,
        )


class ProxyAwareGitRunner:
    """Run git subprocesses through the proxy when healthy, direct otherwise."""

    def __init__(
        self,
        controller: GitProxyController,
        *,
        spawn: SpawnGit | None = None,
        extra_environment: Callable[[], Mapping[str, str]] | None = None,
    ) -> None:
        """Bind the controller, process seam, and credential environment overlay."""
        self._controller = controller
        self._spawn = spawn or _spawn_process
        self._extra_environment = extra_environment

    async def run(
        self,
        argv: tuple[str, ...],
        cwd: Path | None,
    ) -> GitProcessResult:
        """Run one git argv, retrying direct after a proxy-layer failure."""
        operation = classify_git_operation(argv)
        network_operation = is_proxy_traffic(argv)
        collector = current_git_operation_collector()
        operation_host = target_host_for(
            argv,
            collector.target_host if collector is not None else None,
        )
        state_before = self._controller.state
        started = time.perf_counter()
        result: GitProcessResult | None = None
        via_proxy = False
        fallback_reason: str | None = None
        try:
            endpoint = await self._controller.endpoint()
            environment = build_git_environment()
            if self._extra_environment is not None:
                environment.update(self._extra_environment())
            if endpoint is None:
                if self._controller.enabled:
                    strip_proxy_environment(environment)
                result = await self._spawn(argv, cwd, environment)
                return result
            apply_proxy_environment(
                environment,
                endpoint,
                rewrite_ssh=allows_ssh_rewrite(argv),
            )
            result = await self._spawn(argv, cwd, environment)
            if result.returncode == 0:
                via_proxy = network_operation
                if is_network_command(argv):
                    await self._controller.report_success()
                return result
            if not is_proxy_failure(result.stderr, endpoint):
                via_proxy = network_operation
                return result
            await self._controller.report_failure()
            fallback_reason = fallback_reason_for(result.stderr)
            logger.warning(
                "git request failed through proxy; retrying direct",
                extra={
                    "event": "git.proxy.retry_direct",
                    "fallbackReason": fallback_reason,
                },
            )
            direct_environment = build_git_environment()
            if self._extra_environment is not None:
                direct_environment.update(self._extra_environment())
            strip_proxy_environment(direct_environment)
            via_proxy = False
            result = await self._spawn(argv, cwd, direct_environment)
            return result
        finally:
            emit_git_operation(
                GitOperationRecord(
                    operation=operation,
                    via_proxy=via_proxy,
                    proxy_state_before=state_before,
                    proxy_state_after=self._controller.state,
                    fallback_reason=fallback_reason,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    exit_code=result.returncode if result is not None else None,
                    target_host=operation_host,
                ),
            )

    async def run_remote(self, argv: tuple[str, ...]) -> GitProcessResult:
        """Run one git argv without a working directory (ls-remote seam)."""
        return await self.run(argv, None)


async def _spawn_process(
    argv: tuple[str, ...],
    cwd: Path | None,
    environment: dict[str, str],
) -> GitProcessResult:
    """Execute git with prompts disabled and kill the group on cancellation."""
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd is not None else None,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
        start_new_session=sys.platform != "win32",
    )
    try:
        stdout, stderr = await process.communicate()
    except asyncio.CancelledError:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                if sys.platform == "win32":
                    process.kill()
                else:
                    os.killpg(process.pid, signal.SIGKILL)
            await process.wait()
        raise
    return GitProcessResult(
        returncode=process.returncode or 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )
