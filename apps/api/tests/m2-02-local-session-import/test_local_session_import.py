"""Local session discovery, persistence, and verification contracts."""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.cli import main as cli_main
from app.config import DatabaseDialect, ServicePhase, Settings
from app.service.acquisition.local_sessions import (
    LocalSessionSourceError,
    import_local_sessions,
    scan_local_sessions,
    verify_local_sessions,
)

SESSION_A = "11111111-1111-4111-8111-111111111111"
SESSION_B = "22222222-2222-4222-8222-222222222222"
AGENT_A1 = "a1111111111111111"
AGENT_A2 = "at2-review-2222222222222222"
AGENT_B1 = "b1111111111111111"


def settings_for(tmp_path: Path) -> Settings:
    """Return an isolated SQLite target for local import tests."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}",
        jwt_secret=SecretStr("local-session-import-test-secret"),
        phase=ServicePhase.DEMO,
    )


def write_json(path: Path, value: object) -> None:
    """Write deterministic test JSON without depending on production code."""
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, lines: list[dict[str, object]]) -> None:
    """Write deterministic test JSONL without exposing real transcript data."""
    path.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines),
        encoding="utf-8",
    )


def write_subagent(
    root: Path,
    session_id: str,
    agent_id: str,
    *,
    meta: dict[str, object] | None = None,
    agent_id_in_payload: str | None = None,
    include_meta: bool = True,
) -> tuple[Path, Path]:
    """Create one subagent transcript and its companion metadata."""
    subagents = root / session_id / "subagents"
    subagents.mkdir(parents=True, exist_ok=True)
    payload = subagents / f"agent-{agent_id}.jsonl"
    write_jsonl(
        payload,
        [
            {
                "agentId": agent_id_in_payload or agent_id,
                "sessionId": session_id,
                "type": "assistant",
            },
        ],
    )
    metadata = subagents / f"agent-{agent_id}.meta.json"
    if include_meta:
        write_json(
            metadata,
            meta
            or {
                "agentType": "reviewer",
                "description": "Synthetic reviewer",
                "model": "test-model",
                "spawnDepth": 1,
                "toolUseId": "tool-1",
            },
        )
    return payload, metadata


def make_sample(root: Path) -> None:
    """Create two roots and three subagents for a compact deterministic corpus."""
    root.mkdir(parents=True)
    write_jsonl(
        root / f"{SESSION_A}.jsonl",
        [
            {"sessionId": SESSION_A, "type": "user"},
            {"sessionId": SESSION_A, "type": "assistant"},
        ],
    )
    write_jsonl(
        root / f"{SESSION_B}.jsonl",
        [{"sessionId": SESSION_B, "type": "user"}],
    )
    write_subagent(root, SESSION_A, AGENT_A1)
    write_subagent(
        root,
        SESSION_A,
        AGENT_A2,
        meta={
            "agentType": "reviewer",
            "description": "Synthetic second reviewer",
            "model": "test-model",
            "spawnDepth": 2,
        },
    )
    write_subagent(
        root,
        SESSION_B,
        AGENT_B1,
        meta={
            "agentType": "worker",
            "description": "Synthetic worker",
            "spawnDepth": 1,
        },
    )


def test_scan_discovers_roots_subagents_and_exact_payloads(tmp_path: Path) -> None:
    source = tmp_path / "sessions"
    make_sample(source)

    corpus = scan_local_sessions(source)

    assert corpus.root_sessions == 2
    assert corpus.jsonl_files == 5
    assert corpus.subagents == 3
    assert len(corpus.payloads) == 5
    by_id = {payload.agent_id: payload for payload in corpus.payloads}
    assert by_id[SESSION_A].agent_kind == "main"
    assert by_id[SESSION_A].agent_meta is None
    assert by_id[SESSION_A].line_count == 2
    assert by_id[AGENT_A2].agent_kind == "subagent"
    assert by_id[AGENT_A2].agent_meta == {
        "agentType": "reviewer",
        "description": "Synthetic second reviewer",
        "model": "test-model",
        "spawnDepth": 2,
    }
    assert all(len(payload.content_hash) == 64 for payload in corpus.payloads)


def test_scan_rejects_wrong_subagent_identity_without_leaking_path(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions"
    make_sample(source)
    write_subagent(
        source,
        SESSION_A,
        "a3333333333333333",
        agent_id_in_payload="different-agent",
    )

    with pytest.raises(LocalSessionSourceError) as error:
        scan_local_sessions(source)

    assert "agent id does not match filename" in str(error.value)
    assert str(tmp_path) not in str(error.value)


@pytest.mark.parametrize("case", ["missing_meta", "orphan_meta", "duplicate_key", "bad_root"])
def test_scan_rejects_ambiguous_or_malformed_sources(
    tmp_path: Path,
    case: str,
) -> None:
    source = tmp_path / "sessions"
    source.mkdir()
    write_jsonl(source / f"{SESSION_A}.jsonl", [{"sessionId": SESSION_A, "type": "user"}])

    if case == "missing_meta":
        write_subagent(source, SESSION_A, AGENT_A1, include_meta=False)
    elif case == "orphan_meta":
        meta = source / SESSION_A / "subagents" / f"agent-{AGENT_A1}.meta.json"
        meta.parent.mkdir(parents=True)
        write_json(meta, {"agentType": "worker", "description": "orphan", "spawnDepth": 1})
    elif case == "duplicate_key":
        (source / f"{SESSION_A}.jsonl").write_text(
            f'{{"sessionId":"{SESSION_A}","sessionId":"{SESSION_A}"}}\n',
            encoding="utf-8",
        )
    else:
        write_jsonl(source / f"{SESSION_A}.jsonl", [{"sessionId": SESSION_B}])

    with pytest.raises(LocalSessionSourceError):
        scan_local_sessions(source)


def test_scan_rejects_symlink_entries(tmp_path: Path) -> None:
    source = tmp_path / "sessions"
    source.mkdir()
    target = tmp_path / "outside.jsonl"
    write_jsonl(target, [{"sessionId": SESSION_A}])
    (source / f"{SESSION_A}.jsonl").symlink_to(target)

    with pytest.raises(LocalSessionSourceError, match="symlink"):
        scan_local_sessions(source)


def test_scan_sanitizes_path_bearing_filesystem_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sessions"
    make_sample(source)
    private_path = "/private/source/secret"

    def fail_rglob(_path: Path, _pattern: str) -> None:
        raise PermissionError(13, "Permission denied", private_path)

    monkeypatch.setattr(Path, "rglob", fail_rglob)

    with pytest.raises(LocalSessionSourceError) as error:
        scan_local_sessions(source)

    assert "could not be scanned" in str(error.value)
    assert private_path not in str(error.value)


def test_scan_sanitizes_nested_directory_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "sessions"
    make_sample(source)
    private_path = "/private/source/nested-secret"
    original_iterdir = Path.iterdir

    def guarded_iterdir(path: Path) -> Iterator[Path]:
        if path.name == "subagents":
            raise PermissionError(13, "Permission denied", private_path)
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)

    with pytest.raises(LocalSessionSourceError) as error:
        scan_local_sessions(source)

    assert "subagent directory could not be read" in str(error.value)
    assert private_path not in str(error.value)


def test_scan_accepts_64_character_agent_ids_and_rejects_65(
    tmp_path: Path,
) -> None:
    accepted = tmp_path / "accepted"
    make_sample(accepted)
    accepted_id = "a" * 64
    write_subagent(accepted, SESSION_A, accepted_id)
    assert any(
        payload.agent_id == accepted_id for payload in scan_local_sessions(accepted).payloads
    )

    rejected = tmp_path / "rejected"
    make_sample(rejected)
    rejected_id = "b" * 65
    write_subagent(rejected, SESSION_A, rejected_id)

    with pytest.raises(LocalSessionSourceError, match="agent id exceeds"):
        scan_local_sessions(rejected)


def test_scan_allows_omitted_but_rejects_conflicting_root_session_ids(
    tmp_path: Path,
) -> None:
    source = tmp_path / "omitted"
    source.mkdir()
    write_jsonl(
        source / f"{SESSION_A}.jsonl",
        [
            {"sessionId": SESSION_A, "type": "user"},
            {"type": "assistant"},
        ],
    )
    assert scan_local_sessions(source).root_sessions == 1

    conflicting = tmp_path / "conflicting"
    conflicting.mkdir()
    write_jsonl(
        conflicting / f"{SESSION_A}.jsonl",
        [
            {"sessionId": SESSION_A, "type": "user"},
            {"sessionId": SESSION_B, "type": "assistant"},
        ],
    )

    with pytest.raises(LocalSessionSourceError, match="does not match filename"):
        scan_local_sessions(conflicting)


async def test_import_is_transactional_idempotent_and_preserves_runtime_state(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions"
    make_sample(source)
    settings = settings_for(tmp_path)

    first = await import_local_sessions(settings, source)
    assert first.root_sessions == 2
    assert first.jsonl_files == 5
    assert first.subagents == 3
    assert first.payload_rows == 5
    assert first.inserted_payloads == 5
    assert first.inserted_source_records == 5

    database = tmp_path / "sessions.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            UPDATE source_records
            SET processed_at = '2026-01-01 00:00:00',
                processed_hash = 'processed-hash',
                parser_version = 7
            WHERE root_session_id = ? AND agent_id = ?
            """,
            (SESSION_A, AGENT_A1),
        )
        before = connection.execute(
            """
            SELECT payload, content_hash, line_count, updated_at
            FROM trajectory_payloads
            ORDER BY root_session_id, agent_id
            """,
        ).fetchall()

    second = await import_local_sessions(settings, source)
    assert second.inserted_payloads == 0
    assert second.updated_payloads == 0
    assert second.unchanged_payloads == 5

    changed_path = source / SESSION_A / "subagents" / f"agent-{AGENT_A1}.jsonl"
    write_jsonl(
        changed_path,
        [
            {
                "agentId": AGENT_A1,
                "sessionId": SESSION_A,
                "type": "assistant",
            },
            {
                "agentId": AGENT_A1,
                "sessionId": SESSION_A,
                "type": "tool_use",
            },
        ],
    )
    os.utime(changed_path, (1_800_000_000, 1_800_000_000))

    third = await import_local_sessions(settings, source)
    assert third.inserted_payloads == 0
    assert third.updated_payloads == 1
    assert third.unchanged_payloads == 4

    with sqlite3.connect(database) as connection:
        processing = connection.execute(
            """
            SELECT processed_at, processed_hash, parser_version
            FROM source_records
            WHERE root_session_id = ? AND agent_id = ?
            """,
            (SESSION_A, AGENT_A1),
        ).fetchone()
        after = connection.execute(
            """
            SELECT payload, content_hash, line_count, updated_at
            FROM trajectory_payloads
            ORDER BY root_session_id, agent_id
            """,
        ).fetchall()

    assert processing == ("2026-01-01 00:00:00", "processed-hash", 7)
    assert sum(before[index] != after[index] for index in range(len(before))) == 1

    verified = await verify_local_sessions(settings, source)
    assert verified.status == "verified"
    assert verified.payload_rows == 5
    assert verified.source_record_rows == 5


async def test_import_separates_source_write_and_discovery_times(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions"
    make_sample(source)
    root_path = source / f"{SESSION_A}.jsonl"
    old_timestamp = 1_600_000_000
    os.utime(root_path, (old_timestamp, old_timestamp))
    settings = settings_for(tmp_path)

    await import_local_sessions(settings, source)
    database = tmp_path / "sessions.db"
    with sqlite3.connect(database) as connection:
        payload_updated_at = connection.execute(
            """
            SELECT updated_at FROM trajectory_payloads
            WHERE root_session_id = ? AND agent_id = ?
            """,
            (SESSION_A, SESSION_A),
        ).fetchone()[0]
        received_at = connection.execute(
            """
            SELECT received_at FROM source_records
            WHERE root_session_id = ? AND agent_id = ?
            """,
            (SESSION_A, SESSION_A),
        ).fetchone()[0]

    assert str(payload_updated_at).startswith("2020-")
    assert not str(received_at).startswith("2020-")

    await import_local_sessions(settings, source)
    with sqlite3.connect(database) as connection:
        repeated_received_at = connection.execute(
            """
            SELECT received_at FROM source_records
            WHERE root_session_id = ? AND agent_id = ?
            """,
            (SESSION_A, SESSION_A),
        ).fetchone()[0]
    assert repeated_received_at == received_at


async def test_import_refuses_production_before_creating_database(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sessions"
    make_sample(source)
    settings = settings_for(tmp_path).model_copy(update={"production": True})

    with pytest.raises(LocalSessionSourceError, match="production"):
        await import_local_sessions(settings, source)

    assert not (tmp_path / "sessions.db").exists()


async def test_verify_reports_database_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "sessions"
    make_sample(source)
    settings = settings_for(tmp_path)
    await import_local_sessions(settings, source)

    with sqlite3.connect(tmp_path / "sessions.db") as connection:
        connection.execute(
            """
            DELETE FROM trajectory_payloads
            WHERE root_session_id = ? AND agent_id = ?
            """,
            (SESSION_B, SESSION_B),
        )

    with pytest.raises(LocalSessionSourceError, match="payload row count mismatch"):
        await verify_local_sessions(settings, source)


def test_cli_import_and_verify_emit_only_aggregates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "sessions"
    make_sample(source)
    database = tmp_path / "sessions.db"
    monkeypatch.setenv("HE_DB_DIALECT", "sqlite")
    monkeypatch.setenv("HE_DB_URL", f"sqlite+aiosqlite:///{database}")
    monkeypatch.setenv("HE_JWT_SECRET", "local-session-import-test-secret")
    monkeypatch.setenv("HE_PHASE", "demo")

    assert cli_main(["import-local", "--sessions-dir", str(source)]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported == {
        "inserted_payloads": 5,
        "inserted_source_records": 5,
        "jsonl_files": 5,
        "payload_rows": 5,
        "root_sessions": 2,
        "status": "imported",
        "subagents": 3,
        "unchanged_payloads": 0,
        "updated_payloads": 0,
        "updated_source_records": 0,
    }
    assert str(tmp_path) not in json.dumps(imported)

    assert cli_main(["verify-local", "--sessions-dir", str(source)]) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["status"] == "verified"
    assert verified["payload_rows"] == 5
    assert str(tmp_path) not in json.dumps(verified)


def test_cli_refuses_production_without_echoing_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "sessions"
    make_sample(source)
    monkeypatch.setenv("HE_DB_DIALECT", "sqlite")
    monkeypatch.setenv("HE_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'production.db'}")
    monkeypatch.setenv("HE_JWT_SECRET", "local-session-import-test-secret")
    monkeypatch.setenv("HE_PRODUCTION", "true")

    assert cli_main(["import-local", "--sessions-dir", str(source)]) == 2
    captured = capsys.readouterr()
    assert "refuses production" in captured.err
    assert str(tmp_path) not in captured.err
    assert not (tmp_path / "production.db").exists()


def test_cli_sanitizes_path_bearing_filesystem_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "sessions"
    make_sample(source)
    private_path = "/private/source/secret"
    monkeypatch.setenv("HE_DB_DIALECT", "sqlite")
    monkeypatch.setenv("HE_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'sessions.db'}")
    monkeypatch.setenv("HE_JWT_SECRET", "local-session-import-test-secret")
    monkeypatch.setenv("HE_PHASE", "demo")

    def fail_rglob(_path: Path, _pattern: str) -> None:
        raise PermissionError(13, "Permission denied", private_path)

    monkeypatch.setattr(Path, "rglob", fail_rglob)

    assert cli_main(["import-local", "--sessions-dir", str(source)]) == 2
    captured = capsys.readouterr()
    assert "could not be scanned" in captured.err
    assert private_path not in captured.out
    assert private_path not in captured.err
    assert str(tmp_path) not in captured.out
    assert str(tmp_path) not in captured.err
