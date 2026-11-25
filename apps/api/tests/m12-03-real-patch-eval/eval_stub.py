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
    """Local stub speaking the ai-eval-platform launch/status/results contract.

    A launch is scored when it is recorded: round candidates use
    ``candidate_score``, the validation baseline uses ``baseline_score``, and
    the test template's first launch is the test baseline while later launches
    are the test final. That mirrors the real platform's separation of
    validation and held-out test templates without inventing a verdict.
    """

    received_auth: list[str | None] = field(default_factory=list)
    received_idempotency: list[str | None] = field(default_factory=list)
    received_bodies: list[dict[str, Any]] = field(default_factory=list)
    status_sequences: dict[str, list[str]] = field(default_factory=dict)
    status_message: str | None = None
    baseline_score: float = 80.0
    candidate_score: float = 88.5
    test_baseline_score: float = 70.0
    test_final_score: float = 90.0
    result_status_code: int = 200
    status_status_code: int = 200
    launches: dict[str, dict[str, Any]] = field(default_factory=dict)
    _next_id: int = 0

    def build(self) -> tuple[ThreadingHTTPServer, str]:
        """Serve on an ephemeral local port and return the base URL."""
        platform = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                platform.received_bodies.append(body)
                platform.received_auth.append(self.headers.get("Authorization"))
                platform.received_idempotency.append(self.headers.get("Idempotency-Key"))
                platform._next_id += 1
                run_id = f"eval-e2e-{platform._next_id}"
                template = self.path.split("/eval-templates/")[-1].split("/")[0]
                lineage = body.get("lineage") or {}
                score = platform._score_for(template, lineage)
                platform.launches[run_id] = {
                    "template": template,
                    "lineage": lineage,
                    "score": score,
                    "body": body,
                }
                commit = (body.get("asset_override") or {}).get("commit")
                response = json.dumps(
                    {
                        "run_id": run_id,
                        "created": True,
                        "asset": {"resolved_commit": commit},
                        "warnings": [],
                    },
                ).encode()
                self.send_response(202)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                self.wfile.write(response)

            def do_GET(self) -> None:
                run_id = self.path.split("/eval-runs/")[-1].split("/")[0]
                if self.path.endswith("/results"):
                    launch = platform.launches.get(
                        run_id,
                        {"score": platform.candidate_score},
                    )
                    response = json.dumps(
                        {
                            "run_id": run_id,
                            "is_final": True,
                            "items": [
                                {
                                    "metric_key": "resolved_rate",
                                    "value": launch.get("score"),
                                    "direction": "higher_is_better",
                                    "is_final": True,
                                },
                            ],
                        },
                    ).encode()
                    code = platform.result_status_code
                else:
                    sequence = platform.status_sequences.get(run_id)
                    status = sequence.pop(0) if sequence else "completed"
                    payload: dict[str, Any] = {"status": status, "terminal": True}
                    if platform.status_message:
                        payload["message"] = platform.status_message
                    response = json.dumps(payload).encode()
                    code = platform.status_status_code
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

    def _score_for(self, template: str, lineage: dict[str, Any]) -> float:
        """Assign the score associated with one launched template/purpose."""
        if lineage.get("evolutionRoundId"):
            return self.candidate_score
        if template == "tpl-validation":
            return self.baseline_score
        launched_tests = sum(
            1 for launch in self.launches.values() if launch["template"] == template
        )
        return self.test_baseline_score if launched_tests == 0 else self.test_final_score
