"""Controlled localhost upstream and app helpers for the m12-01 tests."""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.service.acquisition.local_sessions import LocalAgentPayload
from app.utils.time import now_shanghai

ROOT = "00000000-0000-4000-8000-000000000201"
ROOT_2 = "00000000-0000-4000-8000-000000000202"
CHILD_AGENT = "agent-m12-01-child"
UPSTREAM_TOKEN = "controlled-upstream-token"  # noqa: S105 - test-only bearer value


def payload_lines(session_id: str) -> tuple[str, ...]:
    """Build the two raw JSONL lines the Claude parser needs for one session."""
    return (
        json.dumps(
            {
                "type": "user",
                "sessionId": session_id,
                "timestamp": "2026-11-10T01:00:00+08:00",
                "message": {"content": "upstream prompt"},
            },
        ),
        json.dumps(
            {
                "type": "assistant",
                "sessionId": session_id,
                "timestamp": "2026-11-10T01:01:00+08:00",
                "message": {
                    "id": "upstream-message",
                    "model": "fixture-model",
                    "content": [{"type": "text", "text": "upstream reply"}],
                    "usage": {"input_tokens": 2, "output_tokens": 1},
                },
            },
        ),
    )


def main_payload(session_id: str) -> LocalAgentPayload:
    """Build one stored raw payload for the manual-replay path."""
    content = "\n".join(payload_lines(session_id))
    timestamp = now_shanghai()
    return LocalAgentPayload(
        root_session_id=session_id,
        agent_id=session_id,
        agent_kind="main",
        content=content,
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        line_count=len(payload_lines(session_id)),
        agent_meta=None,
        source_updated_at=timestamp,
        discovered_at=timestamp,
    )


def package_payload(session_id: str) -> dict[str, Any]:
    """Build one valid 05 §10 trajectory package with a main transcript."""
    return {
        "sessionId": session_id,
        "metadata": {
            "project": "m12-01-project",
            "model": "fixture-model",
            "startedAt": "2026-11-10T01:00:00+08:00",
            "endedAt": "2026-11-10T01:01:00+08:00",
            "problemFlag": True,
            "problemTags": ["tool-error"],
        },
        "transcripts": [
            {"kind": "main", "agentId": None, "lines": list(payload_lines(session_id))},
        ],
    }


def window_item(session_id: str) -> dict[str, Any]:
    """Build one valid cursor-window item."""
    return {
        "sessionId": session_id,
        "startedAt": "2026-11-10T01:00:00+08:00",
        "model": "fixture-model",
        "problemFlag": True,
    }


@dataclass(frozen=True, slots=True)
class RecordedRequest:
    """One request observed by the controlled upstream."""

    path: str
    query: dict[str, list[str]]
    authorization: str | None


@dataclass
class LocalUpstream:
    """A real HTTP server implementing 05 §10 on loopback."""

    session_ids: Sequence[str] = (ROOT, ROOT_2)
    token: str = UPSTREAM_TOKEN
    api_version: str | None = "1.0"
    package_api_version: str | None = None
    page_size: int = 1
    fail_window: bool = False
    fail_sessions: set[str] = field(default_factory=set)
    requests: list[RecordedRequest] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = field(default=None, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)

    @property
    def base_url(self) -> str:
        """Return the exact loopback origin including the ephemeral port."""
        if self._server is None:
            raise RuntimeError("local upstream is not running")
        port = self._server.server_address[1]
        return f"http://127.0.0.1:{port}"

    def window_requests(self) -> list[RecordedRequest]:
        """Return every enumeration call in arrival order."""
        return [request for request in self.requests if request.path == "/trajectories"]

    def package_requests(self) -> list[RecordedRequest]:
        """Return every package call in arrival order."""
        return [request for request in self.requests if request.path.startswith("/trajectories/")]

    def __enter__(self) -> LocalUpstream:
        """Start the loopback server on an ephemeral port."""
        server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        server.daemon_threads = True
        server.owner = self  # type: ignore[attr-defined]
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        """Stop the server and join its serving thread."""
        server = self._server
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None

    def handle(self, request: BaseHTTPRequestHandler) -> None:
        """Route one GET through the configured contract behavior."""
        split = urlsplit(request.path)
        self.requests.append(
            RecordedRequest(
                path=split.path,
                query=parse_qs(split.query),
                authorization=request.headers.get("Authorization"),
            ),
        )
        if request.headers.get("Authorization") != f"Bearer {self.token}":
            self._write(request, 401, {"error": "unauthorized"}, versioned=False)
            return
        if split.path == "/trajectories":
            if self.fail_window:
                self._write(request, 503, {"error": "busy"}, versioned=False)
                return
            self._write(request, 200, self._window_page(split.query))
            return
        prefix = "/trajectories/"
        if not split.path.startswith(prefix):
            self._write(request, 404, {"error": "missing"}, versioned=False)
            return
        session_id = split.path[len(prefix) :]
        if session_id in self.fail_sessions:
            self._write(request, 503, {"error": "busy"}, versioned=False)
            return
        if session_id not in self.session_ids:
            self._write(request, 404, {"error": "missing"}, versioned=False)
            return
        self._write(
            request,
            200,
            package_payload(session_id),
            version=self.package_api_version,
        )

    def _window_page(self, query: str) -> dict[str, Any]:
        start = int(parse_qs(query).get("cursor", ["0"])[0])
        selected = list(self.session_ids)[start : start + self.page_size]
        consumed = start + len(selected)
        return {
            "items": [window_item(session_id) for session_id in selected],
            "nextCursor": str(consumed) if consumed < len(self.session_ids) else None,
        }

    def _write(
        self,
        request: BaseHTTPRequestHandler,
        status: int,
        body: object,
        *,
        versioned: bool = True,
        version: str | None = None,
    ) -> None:
        encoded = json.dumps(body).encode()
        request.send_response(status)
        request.send_header("Content-Type", "application/json")
        request.send_header("Content-Length", str(len(encoded)))
        header = version if version is not None else self.api_version
        if versioned and header is not None:
            request.send_header("X-Trajectory-Api-Version", header)
        request.end_headers()
        request.wfile.write(encoded)


class _Handler(BaseHTTPRequestHandler):
    """Delegate each request to the owning local upstream without logging."""

    def do_GET(self) -> None:
        owner = getattr(self.server, "owner", None)
        if not isinstance(owner, LocalUpstream):
            self.send_error(500)
            return
        owner.handle(self)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep test output free of stdlib access logs."""
        return


def assert_logs_do_not_contain(caplog: Any, *needles: str) -> None:
    """Check serialized record fields, not only the formatted message."""
    rendered = repr([record.__dict__ for record in caplog.records])
    for needle in needles:
        assert needle not in rendered


def upstream_settings(
    tmp_path: Path,
    *,
    base_url: str,
    token: str = UPSTREAM_TOKEN,
    **overrides: object,
) -> Settings:
    """Build an app configuration with the controlled upstream enabled."""
    values: dict[str, object] = {
        "db_dialect": DatabaseDialect.SQLITE,
        "data_dir": tmp_path,
        "jwt_secret": "m12-01-signing-secret-with-enough-length",
        "admin_username": "admin",
        "admin_password": SecretStr("initial-password"),
        "sync_interval_seconds": 0,
        "upstream_base_url": base_url,
        "upstream_token": SecretStr(token),
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


async def admin_headers(client: httpx.AsyncClient) -> dict[str, str]:
    """Complete the seeded admin's forced password change and log in."""
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "initial-password"},
    )
    initial = login.json()["accessToken"]
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {initial}"},
        json={
            "oldPassword": "initial-password",
            "newPassword": "replacement-password",
        },
    )
    assert changed.status_code == 204
    authenticated = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "replacement-password"},
    )
    return {"Authorization": f"Bearer {authenticated.json()['accessToken']}"}
