"""Git egress proxy: circuit state, runner environment, and config validation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.third_party_api.git.proxy import (
    GitProcessResult,
    GitProxyController,
    ProxyAwareGitRunner,
    apply_proxy_environment,
    build_git_environment,
    is_proxy_failure,
    probe_http_connect,
    strip_proxy_environment,
)

PROXY = "http://127.0.0.1:10808"


class Clock:
    """Controllable monotonic clock for cooldown tests."""

    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


def make_controller(
    *,
    probe: Callable[[], Awaitable[bool]] | None = None,
    clock: Clock | None = None,
) -> GitProxyController:
    """Build a controller with explicit probe and clock seams."""
    return GitProxyController(
        PROXY,
        probe=probe,
        interval_seconds=5.0,
        probe_timeout_seconds=0.5,
        failure_threshold=3,
        success_threshold=2,
        open_seconds=30.0,
        clock=clock or Clock(),
    )


@pytest.mark.asyncio
async def test_disabled_controller_never_uses_proxy() -> None:
    controller = GitProxyController(None)

    assert controller.enabled is False
    assert await controller.endpoint() is None
    assert controller.status.state == "disabled"


@pytest.mark.asyncio
async def test_closed_controller_uses_proxy_until_threshold() -> None:
    controller = make_controller()

    assert await controller.endpoint() == PROXY
    await controller.report_failure()
    await controller.report_failure()
    assert await controller.endpoint() == PROXY
    await controller.report_failure()
    assert await controller.endpoint() is None
    assert controller.status.state == "open"


@pytest.mark.asyncio
async def test_half_open_probe_then_two_successes_close_circuit() -> None:
    clock = Clock()
    controller = make_controller(probe=_healthy_probe, clock=clock)
    for _ in range(3):
        await controller.report_failure()
    assert await controller.endpoint() is None

    clock.value += 31
    assert await controller.probe_once() is True
    assert controller.status.state == "half_open"
    assert await controller.endpoint() == PROXY

    assert await controller.probe_once() is True
    assert str(controller.status.state) == "closed"
    assert await controller.endpoint() == PROXY


@pytest.mark.asyncio
async def test_failed_half_open_probe_keeps_circuit_open() -> None:
    clock = Clock()
    controller = make_controller(probe=_unhealthy_probe, clock=clock)
    for _ in range(3):
        await controller.report_failure()
    clock.value += 31

    assert await controller.probe_once() is False
    assert controller.status.state == "open"
    assert await controller.endpoint() is None


@pytest.mark.asyncio
async def test_background_loop_probes_and_stops() -> None:
    calls = 0

    async def probe() -> bool:
        nonlocal calls
        calls += 1
        return False

    controller = GitProxyController(
        PROXY,
        probe=probe,
        interval_seconds=5.0,
        probe_timeout_seconds=0.5,
        open_seconds=1.0,
    )
    controller.start()
    await asyncio.sleep(0.02)
    await controller.stop()

    assert calls >= 1
    assert controller.status.state == "open"


def test_from_settings_reads_proxy_and_thresholds() -> None:
    settings = Settings(
        jwt_secret=SecretStr("test-secret"),
        git_proxy=PROXY,
        git_proxy_probe_interval_seconds=30,
        git_proxy_probe_timeout_seconds=2,
    )
    controller = GitProxyController.from_settings(settings)

    assert controller.enabled is True
    assert controller.status.state == "closed"


@pytest.mark.asyncio
async def test_first_failed_probe_opens_circuit_immediately() -> None:
    controller = make_controller(probe=_unhealthy_probe)

    assert await controller.probe_once() is False
    assert controller.status.state == "open"
    assert await controller.endpoint() is None


@pytest.mark.asyncio
async def test_probe_failure_counts_toward_threshold_when_closed() -> None:
    controller = make_controller(probe=_unhealthy_probe)

    await controller.probe_once()
    assert controller.status.state == "open"


@pytest.mark.asyncio
async def test_runner_sets_proxy_environment_and_ssh_rewrite() -> None:
    calls: list[dict[str, str]] = []

    async def spawn(
        _argv: tuple[str, ...],
        _cwd: Path | None,
        environment: dict[str, str],
    ) -> GitProcessResult:
        calls.append(dict(environment))
        return GitProcessResult(returncode=0, stdout="", stderr="")

    runner = ProxyAwareGitRunner(make_controller(), spawn=spawn)
    await runner.run(("git", "ls-remote", "git@github.com:owner/repo.git"), None)

    environment = calls[0]
    assert environment["HTTPS_PROXY"] == PROXY
    assert environment["HTTP_PROXY"] == PROXY
    assert environment["https_proxy"] == PROXY
    assert environment["GIT_CONFIG_COUNT"] == "2"
    assert environment["GIT_CONFIG_KEY_0"] == "url.https://github.com/.insteadOf"
    assert environment["GIT_CONFIG_VALUE_0"] == "git@github.com:"
    assert environment["GIT_CONFIG_VALUE_1"] == "ssh://git@github.com/"


@pytest.mark.asyncio
async def test_runner_direct_mode_strips_ambient_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "http://ambient:9000")
    monkeypatch.setenv("HTTP_PROXY", "http://ambient:9000")
    monkeypatch.setenv("ALL_PROXY", "socks5://ambient:9001")
    captured: list[dict[str, str]] = []

    async def spawn(
        _argv: tuple[str, ...],
        _cwd: Path | None,
        environment: dict[str, str],
    ) -> GitProcessResult:
        captured.append(dict(environment))
        return GitProcessResult(returncode=0, stdout="", stderr="")

    controller = make_controller()
    for _ in range(3):
        await controller.report_failure()
    runner = ProxyAwareGitRunner(controller, spawn=spawn)
    await runner.run(("git", "rev-parse", "HEAD"), None)

    assert "HTTPS_PROXY" not in captured[0]
    assert "HTTP_PROXY" not in captured[0]
    assert "ALL_PROXY" not in captured[0]


@pytest.mark.asyncio
async def test_runner_retries_direct_after_proxy_layer_failure() -> None:
    responses = [
        GitProcessResult(
            returncode=128,
            stdout="",
            stderr=(
                "fatal: unable to access 'https://github.com/owner/repo.git/': "
                "Failed to connect to 127.0.0.1 port 10808 after 0 ms: "
                "Couldn't connect to server"
            ),
        ),
        GitProcessResult(returncode=0, stdout="ok", stderr=""),
    ]
    environments: list[dict[str, str]] = []

    async def spawn(
        _argv: tuple[str, ...],
        _cwd: Path | None,
        environment: dict[str, str],
    ) -> GitProcessResult:
        environments.append(dict(environment))
        return responses.pop(0)

    controller = make_controller()
    runner = ProxyAwareGitRunner(controller, spawn=spawn)
    result = await runner.run(("git", "ls-remote", "https://github.com/o/r.git"), None)

    assert result.returncode == 0
    assert len(environments) == 2
    assert environments[0]["HTTPS_PROXY"] == PROXY
    assert "HTTPS_PROXY" not in environments[1]
    assert controller.status.failures == 1


@pytest.mark.asyncio
async def test_runner_does_not_retry_or_trip_on_unrelated_failure() -> None:
    calls = 0

    async def spawn(
        _argv: tuple[str, ...],
        _cwd: Path | None,
        environment: dict[str, str],
    ) -> GitProcessResult:
        nonlocal calls
        calls += 1
        return GitProcessResult(
            returncode=128,
            stdout="",
            stderr=(
                "fatal: could not read Username for 'https://github.com': terminal prompts disabled"
            ),
        )

    controller = make_controller()
    runner = ProxyAwareGitRunner(controller, spawn=spawn)
    result = await runner.run(("git", "clone", "https://github.com/o/r.git"), None)

    assert result.returncode == 128
    assert calls == 1
    assert controller.status.failures == 0
    assert controller.status.state == "closed"


def test_proxy_failure_classification() -> None:
    assert is_proxy_failure(
        "fatal: unable to access 'https://github.com/': Failed to connect to 127.0.0.1 port 10808",
        PROXY,
    )
    assert is_proxy_failure(
        "fatal: unable to access 'https://github.com/': Proxy CONNECT aborted", PROXY
    )
    assert is_proxy_failure("The requested URL returned error: 407", PROXY)
    assert not is_proxy_failure("fatal: repository 'https://github.com/o/r.git/' not found", PROXY)
    assert not is_proxy_failure("", PROXY)


def test_proxy_environment_is_removed_completely() -> None:
    environment = build_git_environment()
    environment.update(
        {
            "HTTPS_PROXY": PROXY,
            "HTTP_PROXY": PROXY,
            "ALL_PROXY": "socks5://127.0.0.1:1080",
            "https_proxy": PROXY,
        },
    )
    strip_proxy_environment(environment)
    assert all(
        key not in environment for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy")
    )


def test_apply_proxy_environment_keeps_loopback_direct() -> None:
    environment: dict[str, str] = {}
    apply_proxy_environment(environment, PROXY)
    assert environment["NO_PROXY"] == "127.0.0.1,localhost,::1"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("http://127.0.0.1:10808", "http://127.0.0.1:10808"),
        ("http://127.0.0.1:10808/", "http://127.0.0.1:10808"),
    ],
)
def test_git_proxy_config_accepts_local_http(value: str | None, expected: str | None) -> None:
    settings = Settings(jwt_secret=SecretStr("test-secret"), git_proxy=value)
    assert settings.git_proxy == expected


@pytest.mark.parametrize(
    "value",
    ["https://127.0.0.1:10808", "http://user:pass@127.0.0.1:10808", "socks5://127.0.0.1:1080"],
)
def test_git_proxy_config_rejects_unsupported_values(value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(jwt_secret=SecretStr("test-secret"), git_proxy=value)


@pytest.mark.asyncio
async def test_probe_accepts_connect_200() -> None:
    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    socket = server.sockets[0]
    try:
        port = socket.getsockname()[1]
        assert await probe_http_connect(f"http://127.0.0.1:{port}", timeout_seconds=1) is True
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_probe_rejects_malformed_proxy_without_connecting() -> None:
    assert await probe_http_connect("not-a-url", timeout_seconds=0.1) is False
    assert await probe_http_connect("http://127.0.0.1:1", timeout_seconds=0.1) is False


async def _healthy_probe() -> bool:
    return True


async def _unhealthy_probe() -> bool:
    return False
