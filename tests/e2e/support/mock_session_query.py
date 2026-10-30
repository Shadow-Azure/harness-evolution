#!/usr/bin/env python3
"""Deterministic mock of the two bad-case session-query endpoints.

API 1: GET /sessions/{sessionId}/children -> bare JSON array of direct children.
API 2: GET /sessions/{sessionId}/trajectory -> NDJSON trajectory.
GET /__stats -> call count and max observed concurrency for smoke assertions.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

ROOT = "11111111-1111-4111-8111-111111111111"
CHILD_A = "agent-mock-a"
CHILD_B = "agent-mock-b"
TREE: dict[str, tuple[str, ...]] = {
    ROOT: (CHILD_A,),
    CHILD_A: (CHILD_B,),
    CHILD_B: (),
}
_STATS_LOCK = threading.Lock()
_STATS = {"calls": 0, "active": 0, "maxActive": 0}


def _line(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _trajectory(session_id: str) -> str:
    timestamp = "2026-10-30T10:00:00+08:00"
    if session_id == ROOT:
        records = [
            {
                "type": "user",
                "sessionId": ROOT,
                "timestamp": timestamp,
                "cwd": "/workspace/mock-project",
                "gitBranch": "main",
                "message": {"content": "mock problem prompt"},
            },
            {
                "type": "assistant",
                "sessionId": ROOT,
                "timestamp": "2026-10-30T10:00:01+08:00",
                "message": {
                    "id": "mock-main-message",
                    "model": "mock-model",
                    "content": [{"type": "text", "text": "mock main reply"}],
                    "usage": {"input_tokens": 2, "output_tokens": 1},
                },
            },
        ]
    else:
        records = [
            {
                "type": "assistant",
                "sessionId": ROOT,
                "agentId": session_id,
                "timestamp": "2026-10-30T10:00:02+08:00",
                "message": {
                    "id": f"mock-{session_id}-message",
                    "model": "mock-model",
                    "content": [{"type": "text", "text": f"mock {session_id} reply"}],
                },
            },
        ]
    return "\n".join(_line(record) for record in records)


class Handler(BaseHTTPRequestHandler):
    """Serve the deterministic mock contract."""

    protocol_version = "HTTP/1.1"
    delay_seconds = 0.05

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/__stats":
            with _STATS_LOCK:
                body = json.dumps(dict(_STATS)).encode("utf-8")
            self._send(200, "application/json", body)
            return
        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "children":
            session_id = parts[1]
            if session_id not in TREE:
                self._send(404, "application/json", b'{"error":"unknown session"}')
                return
            body = json.dumps(list(TREE[session_id])).encode("utf-8")
            self._send(200, "application/json", body)
            return
        if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "trajectory":
            session_id = parts[1]
            if session_id not in TREE:
                self._send(404, "application/json", b'{"error":"unknown session"}')
                return
            with _STATS_LOCK:
                _STATS["calls"] += 1
                _STATS["active"] += 1
                _STATS["maxActive"] = max(_STATS["maxActive"], _STATS["active"])
            try:
                time.sleep(self.delay_seconds)
                body = _trajectory(session_id).encode("utf-8")
            finally:
                with _STATS_LOCK:
                    _STATS["active"] -= 1
            self._send(200, "application/x-ndjson", body)
            return
        self._send(404, "application/json", b'{"error":"not found"}')

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--delay", type=float, default=0.05)
    args = parser.parse_args()
    Handler.delay_seconds = max(0.0, args.delay)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"mock_session_query: listening on 127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
