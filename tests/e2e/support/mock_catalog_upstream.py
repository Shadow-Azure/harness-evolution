#!/usr/bin/env python3
"""Mock upstream for the m6-16 catalog-sync E2E and smoke runs.

Serves three endpoints on one port:
- GET /bad-cases?bad_case_id=&offset=&limit= -> paginated catalog.
- GET /sessions/{id}/children -> direct child session ids.
- GET /sessions/{id}/trajectory -> NDJSON trajectory.
GET /__stats returns call counts and the max observed trajectory concurrency.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from mock_session_query import ROOT, TREE, _trajectory

TIMESTAMP = "2026-10-30T10:00:00+08:00"
CASES = tuple(
    {
        "bad_case_id": index,
        "bad_case_session_id": ROOT,
        "bad_case_type": "self",
        "object_name": "deep-research",
        "object_type": "skill",
        "object_version": "v1",
        "bad_case_agent_id": None,
        "bad_case_title": f"Mock problem {index}",
        "bad_case_description": f"Mock problem description {index}",
        "meta_data": {"index": index},
        "source": "mock",
        "created_at": TIMESTAMP,
        "updated_at": TIMESTAMP,
    }
    for index in (1, 2, 3)
)
_STATS_LOCK = threading.Lock()
_STATS = {"catalogCalls": 0, "trajectoryCalls": 0, "active": 0, "maxActive": 0}


class Handler(BaseHTTPRequestHandler):
    """Serve the deterministic catalog and session-query contracts."""

    protocol_version = "HTTP/1.1"
    delay_seconds = 0.05

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/__stats":
            with _STATS_LOCK:
                body = json.dumps(dict(_STATS)).encode("utf-8")
            self._send(200, "application/json", body)
            return
        if parsed.path == "/bad-cases":
            self._catalog(parse_qs(parsed.query))
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
                _STATS["trajectoryCalls"] += 1
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

    def _catalog(self, query: dict[str, list[str]]) -> None:
        with _STATS_LOCK:
            _STATS["catalogCalls"] += 1
        after = int(query.get("bad_case_id", ["0"])[0])
        offset = max(int(query.get("offset", ["0"])[0]), 0)
        limit = min(max(int(query.get("limit", ["20"])[0]), 1), 200)
        remaining = [case for case in CASES if case["bad_case_id"] > after]
        body = json.dumps(
            {
                "total": len(remaining),
                "offset": offset,
                "limit": limit,
                "items": remaining[offset : offset + limit],
            },
            ensure_ascii=False,
        ).encode("utf-8")
        self._send(200, "application/json", body)

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
    print(f"mock_catalog_upstream: listening on 127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
