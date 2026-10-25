"""Export the deterministic outbound trajectory contract and example payloads."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pydantic.json_schema import models_json_schema

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.third_party_api.trajectory.models import (  # noqa: E402
    TrajectoryPackage,
    TrajectoryWindow,
)


def canonicalize(value: Any) -> Any:
    """Recursively order mapping keys for byte-stable artifacts."""
    if isinstance(value, dict):
        return {key: canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def fixture() -> dict[str, Any]:
    """Return one compact package and window accepted by the client contract."""
    session_id = "00000000-0000-4000-8000-000000000000"
    package = TrajectoryPackage.model_validate(
        {
            "sessionId": session_id,
            "metadata": {
                "project": "fixture-project",
                "model": "fixture-model",
                "startedAt": "2026-10-20T01:00:00+08:00",
                "endedAt": "2026-10-20T01:01:00+08:00",
                "problemFlag": True,
                "problemTags": ["tool-error"],
            },
            "transcripts": [
                {
                    "kind": "main",
                    "agentId": None,
                    "lines": [
                        '{"type":"user","sessionId":"00000000-0000-4000-8000-000000000000"}',
                        '{"type":"assistant","sessionId":"00000000-0000-4000-8000-000000000000"}',
                    ],
                },
                {
                    "kind": "subagent",
                    "agentId": "agent-fixture",
                    "agentType": "general-purpose",
                    "parentToolUseId": "tool-fixture",
                    "lines": [
                        '{"type":"assistant","agentId":"agent-fixture"}',
                    ],
                },
            ],
        },
    )
    window = TrajectoryWindow.model_validate(
        {
            "items": [
                {
                    "sessionId": session_id,
                    "startedAt": "2026-10-20T01:00:00+08:00",
                    "model": "fixture-model",
                    "problemFlag": True,
                },
            ],
            "nextCursor": "",
        },
    )
    return {
        "package": package.model_dump(by_alias=True, mode="json"),
        "window": window.model_dump(by_alias=True, mode="json"),
    }


def strict_schema(models_schema: dict[str, Any]) -> dict[str, Any]:
    """Add the identity constraints that Pydantic enforces after parsing."""
    defs = canonicalize(models_schema["$defs"])
    main_transcript = {
        "properties": {"kind": {"const": "main"}},
        "required": ["kind"],
    }
    package_schema = defs["TrajectoryPackage"]
    transcripts_schema = package_schema["properties"]["transcripts"]
    transcripts_schema["allOf"] = [
        {
            "contains": main_transcript,
            "maxContains": 1,
            "minContains": 1,
        }
    ]
    transcript_schema = defs["TrajectoryTranscript"]
    transcript_schema["allOf"] = [
        {
            "if": {
                "properties": {"kind": {"const": "main"}},
                "required": ["kind"],
            },
            "then": {"properties": {"agentId": {"type": "null"}}},
        },
        {
            "if": {
                "properties": {"kind": {"const": "subagent"}},
                "required": ["kind"],
            },
            "then": {
                "properties": {"agentId": {"minLength": 1, "type": "string"}},
                "required": ["agentId"],
            },
        },
        {
            "if": {
                "properties": {"kind": {"const": "subagent"}},
                "required": ["kind"],
            },
            "then": {
                "properties": {
                    "agentId": {
                        "not": {"const": {"$data": "3/sessionId"}},
                    },
                },
            },
        },
    ]
    package_schema["$comment"] = (
        "The child agentId inequality uses the Ajv $data extension. Runtime also "
        "enforces subagent agentId uniqueness."
    )
    return defs


def main() -> None:
    """Print one contract artifact selected by argv."""
    if len(sys.argv) != 2 or sys.argv[1] not in {"schema", "fixture"}:
        raise SystemExit("expected schema or fixture")
    if sys.argv[1] == "schema":
        _, models_schema = models_json_schema(
            [
                (TrajectoryPackage, "validation"),
                (TrajectoryWindow, "validation"),
            ],
            title="TrajectoryContract",
        )
        value: Any = {
            "$comment": "Generated from the upstream trajectory client models. Do not edit.",
            "$defs": strict_schema(models_schema),
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "oneOf": [
                {"$ref": "#/$defs/TrajectoryPackage"},
                {"$ref": "#/$defs/TrajectoryWindow"},
            ],
        }
    else:
        value = fixture()
    json.dump(canonicalize(value), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
