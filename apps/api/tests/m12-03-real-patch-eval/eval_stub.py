"""Shared fixtures for the m12-03 real patch/eval slice."""

from __future__ import annotations

import json
import subprocess
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def git(cwd: Any, *args: str) -> str:
    """Run one deterministic local git command and return stdout."""
    result = subprocess.run(
        ("git", *args),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@dataclass
class StubEvalPlatform:
    """Minimal opt-in evaluation platform stub speaking the mapper contract."""

    received_auth: list[str | None] = field(default_factory=list)
    received_bodies: list[dict[str, Any]] = field(default_factory=list)
    status_sequence: list[str] = field(default_factory=lambda: ["queued", "completed"])
    status_message: str | None = None
    result_payload: dict[str, Any] = field(
        default_factory=lambda: {
            "currentScore": 82.0,
            "candidateScore": 88.5,
            "externalVerdict": "accept",
            "metrics": [{"name": "pass_rate", "value": 0.9}],
        },
    )
    result_status_code: int = 200

    def build(self) -> tuple[ThreadingHTTPServer, str]:
        """Serve on an ephemeral local port and return the base URL."""
        platform = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                platform.received_bodies.append(body)
                platform.received_auth.append(self.headers.get("Authorization"))
                response = json.dumps({"evalId": "eval-e2e-1"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def do_GET(self) -> None:
                if self.path.endswith("/result"):
                    response = json.dumps(platform.result_payload).encode()
                    code = platform.result_status_code
                else:
                    status = (
                        platform.status_sequence.pop(0) if platform.status_sequence else "completed"
                    )
                    payload: dict[str, Any] = {"status": status}
                    if platform.status_message:
                        payload["message"] = platform.status_message
                    response = json.dumps(payload).encode()
                    code = 200
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def log_message(self, *args: object) -> None:
                """Keep the test output quiet."""

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server, f"http://127.0.0.1:{server.server_port}"
