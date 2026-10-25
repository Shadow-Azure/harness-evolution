"""Contracts for the deterministic m2-01 synthetic fixture corpus."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import BigInteger, String, func, inspect, select, text, update

from app.cli import main
from app.config import DatabaseDialect, ServicePhase, Settings
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import (
    agent_events,
    agents,
    bad_case_analysis,
    bad_cases,
    evolution_targets,
    probe_reports,
    session_families,
    source_records,
    sync_runs,
    trajectory_payloads,
    user_turns,
)
from app.db.models.users import users
from app.fixture_corpus import FixtureCorpus, load_fixture_corpus
from app.fixtures_seed import SeedEnvironmentError, run_corpus_seed

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CORPUS_PATH = REPOSITORY_ROOT / "fixtures" / "m2-synthetic" / "corpus.json"
FIXTURE_OWNER_CREDENTIAL_DIGEST = "not-a-real-password-hash"


def sqlite_settings(path: Path, *, phase: ServicePhase = ServicePhase.DEMO) -> Settings:
    """Return isolated SQLite settings for a fixture seed run."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=path,
        phase=phase,
    )


def write_json(path: Path, value: str) -> None:
    """Write a test corpus JSON document without production helpers."""
    path.write_text(value, encoding="utf-8")


def test_canonical_corpus_has_four_bounded_synthetic_roots() -> None:
    """The checked-in corpus is deterministic, four-root, and hash-derived."""
    corpus = load_fixture_corpus(CORPUS_PATH)

    assert isinstance(corpus, FixtureCorpus)
    assert len(corpus.root_sessions) == 4
    assert {session.id for session in corpus.root_sessions} == {
        "10000000-0000-4000-8000-000000000001",
        "10000000-0000-4000-8000-000000000002",
        "10000000-0000-4000-8000-000000000003",
        "10000000-0000-4000-8000-000000000004",
    }
    payloads = [
        agent for session in corpus.root_sessions for agent in session.agents if agent.has_payload
    ]
    assert all(len(payload.content_hash) == 64 for payload in payloads)
    assert all(payload.line_count >= 1 for payload in payloads)
    assert sum(len(payload.content.encode("utf-8")) for payload in payloads) <= 128 * 1024


def test_loader_rejects_unknown_fields_and_real_path_markers(tmp_path: Path) -> None:
    """Fixture schema is closed and cannot leak local session locations."""
    source = CORPUS_PATH.read_text(encoding="utf-8")
    altered = tmp_path / "corpus.json"
    write_json(altered, source.replace('"version": 1', '"version": 1, "unknown": true'))
    with pytest.raises((ValidationError, ValueError), match=r"unknown|extra"):
        load_fixture_corpus(altered)

    unsafe = source.replace("/workspace/example-repo", "/Users/example/real-repo")
    write_json(altered, unsafe)
    with pytest.raises(ValueError, match=r"real-session|path marker"):
        load_fixture_corpus(altered)


def test_loader_rejects_malformed_and_oversized_payloads(tmp_path: Path) -> None:
    """Bad JSONL and fields over budget fail before any database write."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    source = CORPUS_PATH.read_text(encoding="utf-8")
    write_json(corpus_dir / "corpus.json", source)
    for payload in (CORPUS_PATH.parent / "payloads").glob("*.jsonl"):
        (corpus_dir / "payloads").mkdir(exist_ok=True)
        (corpus_dir / "payloads" / payload.name).write_bytes(payload.read_bytes())

    first_payload = next((corpus_dir / "payloads").glob("*.jsonl"))
    first_payload.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"valid JSONL"):
        load_fixture_corpus(corpus_dir / "corpus.json")

    first_payload.write_text(
        '{"type":"user","message":{"content":"' + ("x" * (33 * 1024)) + '"}}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"budget|too large"):
        load_fixture_corpus(corpus_dir / "corpus.json")


def test_loader_rejects_duplicate_keys_and_unlisted_files(tmp_path: Path) -> None:
    """Stable identifiers and the corpus file allowlist are both fail-closed."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    source = CORPUS_PATH.read_text(encoding="utf-8")
    (corpus_dir / "payloads").mkdir()
    for payload in (CORPUS_PATH.parent / "payloads").glob("*.jsonl"):
        (corpus_dir / "payloads" / payload.name).write_bytes(payload.read_bytes())
    duplicate = source.replace(
        '"badCaseId": "badcase-synthetic-0002"',
        '"badCaseId": "badcase-synthetic-0001"',
        1,
    )
    write_json(corpus_dir / "corpus.json", duplicate)
    with pytest.raises(ValueError, match=r"duplicate bad case id"):
        load_fixture_corpus(corpus_dir / "corpus.json")

    write_json(corpus_dir / "corpus.json", source)
    (corpus_dir / "unlisted.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match=r"unlisted fixture file"):
        load_fixture_corpus(corpus_dir / "corpus.json")


async def test_seed_writes_real_tables_and_repeat_is_idempotent(tmp_path: Path) -> None:
    """The same corpus seeds real rows once and repeated runs add zero rows."""
    settings = sqlite_settings(tmp_path)
    first = await run_corpus_seed(settings, load_fixture_corpus(CORPUS_PATH))
    second = await run_corpus_seed(settings, load_fixture_corpus(CORPUS_PATH))

    assert first.inserted > 0
    assert second.inserted == 0
    assert second.changed == 0

    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        async with database.session() as session:
            counts = {
                table.name: int(
                    (await session.execute(select(func.count()).select_from(table))).scalar_one()
                )
                for table in (
                    trajectory_payloads,
                    source_records,
                    session_families,
                    agents,
                    agent_events,
                    user_turns,
                    bad_cases,
                    bad_case_analysis,
                    probe_reports,
                    evolution_targets,
                )
            }
        assert counts["session_families"] == 4
        assert counts["trajectory_payloads"] == 7
        assert counts["source_records"] == 7
        assert counts["agents"] == 8
        assert counts["agent_events"] > 0
        assert counts["user_turns"] == 4
        assert counts["bad_cases"] > 0
        assert counts["probe_reports"] > 0
        assert counts["evolution_targets"] == 1
    finally:
        await database.dispose()


async def test_seed_upserts_changed_values_without_replacing_ids(tmp_path: Path) -> None:
    """A changed source field updates the real row instead of being ignored."""
    settings = sqlite_settings(tmp_path)
    original = load_fixture_corpus(CORPUS_PATH)
    first = await run_corpus_seed(settings, original)
    assert first.inserted > 0

    target_session = original.root_sessions[0].record
    changed_title = "Synthetic corpus changed title"
    target_session.title = changed_title
    updated = await run_corpus_seed(settings, original)

    assert updated.inserted == 0
    assert updated.changed > 0

    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        async with database.session() as session:
            stored = await session.execute(
                select(session_families.c.id, session_families.c.title).where(
                    session_families.c.id == target_session.id,
                ),
            )
            row = stored.one()
        assert row.id == target_session.id
        assert row.title == changed_title
    finally:
        await database.dispose()


async def test_reseed_preserves_normalized_source_processing_state(tmp_path: Path) -> None:
    """Fixture upserts never overwrite runtime-owned source processing fields."""
    settings = sqlite_settings(tmp_path)
    corpus = load_fixture_corpus(CORPUS_PATH)
    await run_corpus_seed(settings, corpus)

    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        sync_run_id = "10000000-0000-4000-8000-000000000099"
        processed_at = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
        async with database.transaction() as session:
            await session.execute(
                sync_runs.insert().values(
                    id=sync_run_id,
                    source_type="synthetic",
                    started_at=processed_at,
                    finished_at=processed_at,
                    status="completed",
                    records_total=1,
                    records_done=1,
                    imported=1,
                    skipped=0,
                    errors=[],
                ),
            )
            source_id: int = (
                await session.execute(select(source_records.c.id).limit(1))
            ).scalar_one()
            await session.execute(
                update(source_records)
                .where(source_records.c.id == source_id)
                .values(
                    processed_at=processed_at,
                    processed_hash="normalized",
                    parser_version=3,
                    last_sync_run_id=sync_run_id,
                ),
            )
    finally:
        await database.dispose()

    reseeded = await run_corpus_seed(settings, corpus)
    assert reseeded.inserted == 0
    assert reseeded.changed == 0

    database = create_database(settings)
    await database.start()
    try:
        async with database.session() as session:
            row = (
                (
                    await session.execute(
                        select(source_records).where(source_records.c.id == source_id),
                    )
                )
                .mappings()
                .one()
            )
        assert row["processed_at"] is not None
        assert row["processed_hash"] == "normalized"
        assert row["parser_version"] == 3
        assert row["last_sync_run_id"] == sync_run_id
    finally:
        await database.dispose()


async def test_reseed_preserves_assigned_target_owner(tmp_path: Path) -> None:
    """Fixture upserts assign a target owner only when inserting the target."""
    settings = sqlite_settings(tmp_path)
    corpus = load_fixture_corpus(CORPUS_PATH)
    await run_corpus_seed(settings, corpus)

    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        user_id = "10000000-0000-4000-8000-000000000098"
        timestamp = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
        async with database.transaction() as session:
            await session.execute(
                users.insert().values(
                    id=user_id,
                    username="fixture-owner",
                    password_hash=FIXTURE_OWNER_CREDENTIAL_DIGEST,
                    display_name="Fixture Owner",
                    role="admin",
                    is_active=True,
                    must_change_password=False,
                    created_at=timestamp,
                    updated_at=timestamp,
                    last_login_at=None,
                    password_changed_at=None,
                ),
            )
            target_id: str = (
                await session.execute(select(evolution_targets.c.id).limit(1))
            ).scalar_one()
            await session.execute(
                update(evolution_targets)
                .where(evolution_targets.c.id == target_id)
                .values(created_by=user_id),
            )
    finally:
        await database.dispose()

    reseeded = await run_corpus_seed(settings, corpus)
    assert reseeded.inserted == 0
    assert reseeded.changed == 0

    database = create_database(settings)
    await database.start()
    try:
        async with database.session() as session:
            row = (
                (
                    await session.execute(
                        select(evolution_targets).where(
                            evolution_targets.c.id == target_id,
                        ),
                    )
                )
                .mappings()
                .one()
            )
        assert row["created_by"] == user_id
    finally:
        await database.dispose()


async def test_seed_refuses_live_and_production_before_writes(tmp_path: Path) -> None:
    """Fixture seeding is a development concern, never a production migration."""
    corpus = load_fixture_corpus(CORPUS_PATH)
    for settings in (
        sqlite_settings(tmp_path / "live", phase=ServicePhase.LIVE),
        Settings(db_dialect=DatabaseDialect.SQLITE, production=True),
    ):
        with pytest.raises(SeedEnvironmentError):
            await run_corpus_seed(settings, corpus)


async def test_foundational_schema_is_cross_dialect(tmp_path: Path) -> None:
    """The m2 fixture tables exist with the designed key invariants."""
    database = create_database(sqlite_settings(tmp_path))
    await database.start()
    try:
        await upgrade_database(database)
        async with database.engine.connect() as connection:
            sync_columns = await connection.run_sync(
                lambda sync_connection: {
                    column["name"]: column
                    for column in inspect(sync_connection).get_columns("sync_runs")
                },
            )
            source_foreign_keys = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_foreign_keys(
                    "source_records",
                ),
            )
            target_foreign_keys = await connection.run_sync(
                lambda sync_connection: inspect(sync_connection).get_foreign_keys(
                    "evolution_targets",
                ),
            )
        async with database.session() as session:
            names = {
                row[0]
                for row in (
                    await session.execute(
                        text("SELECT name FROM sqlite_master WHERE type = 'table'"),
                    )
                ).all()
            }
            payload_indexes = {
                row[1]
                for row in (
                    await session.execute(text("PRAGMA table_info('trajectory_payloads')"))
                ).all()
            }
            family_columns = {
                row[1]
                for row in (
                    await session.execute(text("PRAGMA table_info('session_families')"))
                ).all()
            }
        assert {
            "trajectory_payloads",
            "source_records",
            "session_families",
            "agents",
            "agent_events",
            "user_turns",
            "bad_cases",
            "bad_case_analysis",
            "probe_reports",
            "evolution_targets",
        } <= names
        assert {"root_session_id", "agent_id", "content_hash", "line_count"} <= payload_indexes
        assert {"models", "user_turns_count", "tokens_total", "main_record_id"} <= family_columns
        assert isinstance(sync_columns["id"]["type"], String)
        assert sync_columns["id"]["type"].length == 36
        assert not isinstance(sync_columns["id"]["type"], BigInteger)
        source_fk_tuples = {
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in source_foreign_keys
        }
        assert (
            ("last_sync_run_id",),
            "sync_runs",
            ("id",),
        ) in source_fk_tuples
        target_fk_tuples = {
            (
                tuple(foreign_key["constrained_columns"]),
                foreign_key["referred_table"],
                tuple(foreign_key["referred_columns"]),
            )
            for foreign_key in target_foreign_keys
        }
        assert (("created_by",), "users", ("id",)) in target_fk_tuples
    finally:
        await database.dispose()


def test_fixture_check_command_reports_deterministic_counts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The Node gate has a real Python CLI contract rather than duplicating parsing."""
    assert main(["fixtures-check", "--corpus", str(CORPUS_PATH)]) == 0
    output = capsys.readouterr().out
    assert '"agents": 8' in output
    assert '"root_sessions": 4' in output
    assert '"status": "valid"' in output


def test_fixture_check_missing_corpus_is_a_single_line_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing corpus is a stable CLI diagnostic, not a traceback."""
    missing = tmp_path / "missing.json"
    assert main(["fixtures-check", "--corpus", str(missing)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.count("\n") == 1
    assert "missing.json" in captured.err
    assert "Traceback" not in captured.err
