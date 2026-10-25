"""Strict outbound trajectory contract and payload conversion tests."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.config import DatabaseDialect, Settings
from app.main import create_app
from app.service.acquisition.upstream import package_to_payloads
from app.third_party_api.trajectory.models import (
    TrajectoryMetadata,
    TrajectoryPackage,
)
from app.utils.time import now_shanghai

ROOT = "00000000-0000-4000-8000-000000000001"
CHILD = "agent-111111111111"


def package(**overrides: object) -> TrajectoryPackage:
    """Build one valid package while allowing focused contract mutations."""
    values: dict[str, object] = {
        "sessionId": ROOT,
        "metadata": {
            "project": "fixture-project",
            "model": "model-a",
            "startedAt": "2026-10-20T01:00:00+08:00",
            "endedAt": "2026-10-20T01:05:00+08:00",
            "problemFlag": True,
            "problemTags": ["tool-error"],
        },
        "transcripts": [
            {
                "kind": "main",
                "agentId": None,
                "lines": [
                    '{"type":"user","sessionId":"00000000-0000-4000-8000-000000000001"}',
                    '{"type":"assistant","sessionId":"00000000-0000-4000-8000-000000000001"}',
                ],
            },
            {
                "kind": "subagent",
                "agentId": CHILD,
                "agentType": "general-purpose",
                "parentToolUseId": "tool-1",
                "lines": [
                    '{"type":"assistant","sessionId":"00000000-0000-4000-8000-000000000001","agentId":"agent-111111111111"}',
                ],
            },
        ],
    }
    values.update(overrides)
    return TrajectoryPackage.model_validate(values)


def test_contract_models_round_trip_with_camel_case_aliases() -> None:
    """Accept the exact 05 §10 package and window shapes."""
    parsed = package()
    assert parsed.session_id == ROOT
    assert parsed.metadata is not None
    assert parsed.metadata.problem_flag is True
    assert parsed.transcripts[0].agent_id is None
    assert parsed.transcripts[1].parent_tool_use_id == "tool-1"


@pytest.mark.parametrize(
    ("transcripts", "message"),
    [
        ([], "at least 1 item"),
        (
            [
                {"kind": "subagent", "agentId": CHILD, "lines": ["{}"]},
            ],
            "main",
        ),
        (
            [
                {"kind": "main", "agentId": None, "lines": ["{}"]},
                {"kind": "main", "agentId": None, "lines": ["{}"]},
            ],
            "main",
        ),
        (
            [
                {"kind": "main", "agentId": ROOT, "lines": ["{}"]},
            ],
            "agentId",
        ),
        (
            [
                {"kind": "main", "agentId": None, "lines": ["{}"]},
                {"kind": "subagent", "agentId": "", "lines": ["{}"]},
            ],
            "agentId",
        ),
        (
            [
                {"kind": "main", "agentId": None, "lines": ["{}"]},
                {"kind": "subagent", "agentId": CHILD, "lines": ["{}"]},
                {"kind": "subagent", "agentId": CHILD, "lines": ["{}"]},
            ],
            "duplicate",
        ),
    ],
)
def test_package_rejects_invalid_transcript_identity(
    transcripts: list[dict[str, object]],
    message: str,
) -> None:
    """Require one main transcript and unique non-empty child identities."""
    with pytest.raises(ValidationError, match=message):
        package(transcripts=transcripts)


def test_package_rejects_child_that_reuses_root_session_identity() -> None:
    """Keep main and child payload keys distinct."""
    with pytest.raises(ValidationError, match="must differ from sessionId"):
        package(
            transcripts=[
                {"kind": "main", "agentId": None, "lines": ["{}"]},
                {"kind": "subagent", "agentId": ROOT, "lines": ["{}"]},
            ],
        )


def test_package_rejects_extra_and_malformed_timestamp() -> None:
    """Reject unknown fields and non-timezone dates before persistence."""
    with pytest.raises(ValidationError):
        TrajectoryPackage.model_validate(
            {**package().model_dump(by_alias=True), "unexpected": True},
        )
    with pytest.raises(ValidationError):
        TrajectoryMetadata.model_validate(
            {
                "project": "fixture-project",
                "model": "model-a",
                "startedAt": "not-a-date",
                "endedAt": "2026-10-20T01:05:00+08:00",
            },
        )


def test_wire_models_are_alias_only_and_do_not_coerce_booleans() -> None:
    """Keep runtime validation as strict as the canonical JSON wire schema."""
    with pytest.raises(ValidationError):
        TrajectoryPackage.model_validate(package().model_dump(by_alias=False))

    payload = package().model_dump(by_alias=True)
    payload["metadata"]["problemFlag"] = "false"
    with pytest.raises(ValidationError):
        TrajectoryPackage.model_validate(payload)


@pytest.mark.parametrize(
    "started_at",
    ["not-a-date", "2026-10-20T01:00:00", "2026-10-20T01:00:00+08:00"],
)
def test_metadata_requires_ordered_timezone_timestamps(started_at: str) -> None:
    """Reject malformed, timezone-free, and reversed metadata intervals."""
    ended_at = (
        "2026-10-20T00:59:59+08:00"
        if started_at == "2026-10-20T01:00:00+08:00"
        else "2026-10-20T01:05:00+08:00"
    )
    with pytest.raises(ValidationError):
        TrajectoryMetadata.model_validate(
            {
                "project": "fixture-project",
                "model": "model-a",
                "startedAt": started_at,
                "endedAt": ended_at,
            },
        )


def test_package_mapping_preserves_raw_lines_and_derives_payload_metadata() -> None:
    """Map root identity to the session id and child identity to agentId."""
    parsed = package()
    discovered_at = now_shanghai().replace(microsecond=0)
    mapped = package_to_payloads(parsed, discovered_at=discovered_at)

    assert [item.agent_id for item in mapped] == [ROOT, CHILD]
    assert mapped[0].agent_kind == "main"
    assert mapped[1].agent_kind == "subagent"
    assert mapped[0].content == "\n".join(parsed.transcripts[0].lines)
    assert mapped[0].line_count == 2
    assert mapped[0].content_hash == hashlib.sha256(mapped[0].content.encode()).hexdigest()
    assert mapped[1].agent_meta == {
        "agentType": "general-purpose",
        "parentToolUseId": "tool-1",
    }
    assert parsed.metadata is not None
    assert mapped[0].discovered_at == discovered_at
    assert mapped[0].source_updated_at == parsed.metadata.ended_at
    assert mapped[0].source_updated_at.utcoffset() == timedelta(hours=8)


def test_package_mapping_rejects_duplicate_lines_that_are_not_raw_jsonl() -> None:
    """Raw lines are strings and may be malformed for the later normalizer."""
    parsed = package(
        transcripts=[
            {"kind": "main", "agentId": None, "lines": ["not-json"]},
        ],
    )
    mapped = package_to_payloads(parsed, discovered_at=now_shanghai())
    assert mapped[0].content == "not-json"


def test_canonical_schema_encodes_identity_constraints() -> None:
    """Keep the checked-in schema as strict as the runtime model."""
    schema_path = (
        Path(__file__).resolve().parents[4]
        / "packages"
        / "contracts"
        / "upstream"
        / "trajectory.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    package_schema = schema["$defs"]["TrajectoryPackage"]
    transcript_schema = schema["$defs"]["TrajectoryTranscript"]

    transcript_items = package_schema["properties"]["transcripts"]
    assert transcript_items["minItems"] == 1
    assert any(
        rule.get("contains", {}).get("properties", {}).get("kind", {}).get("const") == "main"
        for rule in transcript_items["allOf"]
    )
    assert any("minContains" in rule for rule in transcript_items["allOf"])
    assert any("maxContains" in rule for rule in transcript_items["allOf"])
    assert transcript_schema["allOf"]


def test_upstream_configuration_requires_endpoint_and_secret_together() -> None:
    """Treat a partial upstream configuration as unavailable, never half-live."""
    absent = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        jwt_secret=SecretStr("test-secret"),
    )
    partial = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        jwt_secret=SecretStr("test-secret"),
        upstream_base_url="https://upstream.test",
    )
    assert absent.upstream_configured is False
    assert partial.upstream_configured is False


def test_upstream_configuration_rejects_credentials_in_url() -> None:
    """Keep bearer credentials out of URLs and error messages."""
    with pytest.raises(ValidationError, match="must not contain credentials"):
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            jwt_secret=SecretStr("test-secret"),
            upstream_base_url="https://user:password@upstream.test",
        )


def test_upstream_configuration_rejects_incompatible_major_version() -> None:
    """Reject an unsupported upstream protocol before application startup."""
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "db_dialect": DatabaseDialect.SQLITE,
                "jwt_secret": SecretStr("test-secret"),
                "upstream_api_major": 2,
            },
        )


async def test_application_starts_with_string_upstream_major_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Parse the environment-backed major version before starting the application."""
    monkeypatch.setenv("HE_DB_DIALECT", "sqlite")
    monkeypatch.setenv("HE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HE_JWT_SECRET", "upstream-contract-test-signing-secret")
    monkeypatch.setenv("HE_SYNC_INTERVAL_SECONDS", "0")
    monkeypatch.setenv("HE_UPSTREAM_BASE_URL", "https://upstream.test")
    monkeypatch.setenv("HE_UPSTREAM_TOKEN", "upstream-contract-token")
    monkeypatch.setenv("HE_UPSTREAM_API_MAJOR", "1")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        assert settings.upstream_api_major == 1


@pytest.mark.parametrize("major", ["2", "not-a-major"])
def test_environment_upstream_major_rejects_unsupported_values(
    monkeypatch: pytest.MonkeyPatch,
    major: str,
) -> None:
    """Keep environment parsing strict after converting decimal strings."""
    monkeypatch.setenv("HE_UPSTREAM_API_MAJOR", major)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "base_url",
    ["upstream.test", "http://", "https://upstream.test?token=secret"],
)
def test_upstream_configuration_rejects_invalid_endpoint(base_url: str) -> None:
    """Require a credential-free HTTP endpoint without query leakage."""
    with pytest.raises(ValidationError):
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            jwt_secret=SecretStr("test-secret"),
            upstream_base_url=base_url,
        )
