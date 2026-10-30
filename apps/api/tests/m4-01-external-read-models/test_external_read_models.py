"""Read-only external problem, analysis, and probe contracts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import event, text

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.bad_cases import (
    AnalysisProgress,
    BadCaseAnalysisRow,
    BadCaseRepository,
    BadCaseRow,
    BadCaseSnapshot,
    ProbeReportRow,
    ProbeSnapshot,
    ProbeSourceCandidate,
)
from app.db.crud.fixtures import run_corpus_seed
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.fixture_corpus import load_fixture_corpus
from app.main import create_app
from app.service.bad_cases.schemas import ProbeReportLookup
from app.service.bad_cases.service import BadCaseService
from app.service.bad_cases.title import UNNAMED_TITLE

ROOT = Path(__file__).resolve().parents[4]
SESSION_1 = "10000000-0000-4000-8000-000000000001"
SESSION_2 = "10000000-0000-4000-8000-000000000002"
SESSION_3 = "10000000-0000-4000-8000-000000000003"
SESSION_4 = "10000000-0000-4000-8000-000000000004"
CASE_1 = "badcase-synthetic-0001"
CASE_2 = "badcase-synthetic-0002"
CASE_3 = "badcase-synthetic-0003"
CASE_4 = "badcase-synthetic-0004"
CASE_5 = "badcase-synthetic-0005"
PROBE_1 = "probe-synthetic-0001"
PROBE_2 = "probe-synthetic-0002"
PROBE_3 = "probe-synthetic-0003"
NOW = datetime(2026, 10, 26, 10, 0, tzinfo=UTC)


@pytest_asyncio.fixture
async def external_database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide a migrated database seeded with the synthetic external tables."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        db_pool_size=2,
        db_max_overflow=1,
        jwt_secret=SecretStr("external-read-model-test-signing-secret"),
    )
    corpus = load_fixture_corpus(ROOT / "fixtures" / "m2-synthetic" / "corpus.json")
    await run_corpus_seed(settings, corpus)
    database = create_database(settings)
    await database.start()
    await upgrade_database(database)
    try:
        yield database
    finally:
        await database.dispose()


class FakeRepository:
    """Repository double for direct row-drift and inconsistent-link tests."""

    def __init__(
        self,
        *,
        cases: tuple[BadCaseRow, ...] = (),
        analyses: tuple[BadCaseAnalysisRow, ...] = (),
        probes: tuple[ProbeReportRow, ...] = (),
        source_candidates: tuple[ProbeSourceCandidate, ...] = (),
        force_probe_lookup: bool = False,
    ) -> None:
        self.cases = cases
        self.analyses = analyses
        self.probes = probes
        self.source_candidates = source_candidates
        self.force_probe_lookup = force_probe_lookup

    async def list_by_session(self, session_id: str) -> tuple[BadCaseRow, ...]:
        """Return supplied cases to exercise row-level validation."""
        return self.cases

    async def list_snapshot(self, session_id: str) -> BadCaseSnapshot:
        """Return all supplied rows as one service-facing snapshot."""
        return BadCaseSnapshot(
            cases=self.cases,
            analyses=self.analyses,
            probes=self.probes,
        )

    async def get_case(self, case_id: str) -> BadCaseRow | None:
        """Return one supplied case by id."""
        return next((case for case in self.cases if case.bad_case_id == case_id), None)

    async def get_case_snapshot(self, case_id: str) -> BadCaseSnapshot:
        """Return one supplied case and its related rows as a snapshot."""
        case = next(
            (case for case in self.cases if case.bad_case_id == case_id),
            None,
        )
        if case is None:
            return BadCaseSnapshot(cases=(), analyses=(), probes=())
        return BadCaseSnapshot(
            cases=(case,),
            analyses=tuple(row for row in self.analyses if row.bad_case_id == case_id),
            probes=self.probes,
        )

    async def analyses_by_case_ids(
        self,
        case_ids: tuple[str, ...],
    ) -> tuple[BadCaseAnalysisRow, ...]:
        """Return supplied analysis rows for the requested cases."""
        wanted = set(case_ids)
        return tuple(analysis for analysis in self.analyses if analysis.bad_case_id in wanted)

    async def get_analysis(self, case_id: str) -> BadCaseAnalysisRow | None:
        """Return the supplied analysis row for one case."""
        return next(
            (analysis for analysis in self.analyses if analysis.bad_case_id == case_id),
            None,
        )

    async def analysis_progress(self) -> AnalysisProgress:
        """Return empty aggregate counts; drift tests do not read the popover."""
        return AnalysisProgress(
            total=0,
            analyzed=0,
            pending=0,
            issue=0,
            non_issue=0,
        )

    async def probes_by_ids(
        self,
        probe_ids: tuple[str, ...],
    ) -> tuple[ProbeReportRow, ...]:
        """Return supplied probes for the requested ids."""
        wanted = set(probe_ids)
        return tuple(probe for probe in self.probes if probe.probe_id in wanted)

    async def get_probe(self, probe_id: str) -> ProbeReportRow | None:
        """Return one supplied probe by id."""
        if self.force_probe_lookup:
            return self.probes[0] if self.probes else None
        return next((probe for probe in self.probes if probe.probe_id == probe_id), None)

    async def probe_source_candidates(
        self,
        probe_id: str,
    ) -> tuple[ProbeSourceCandidate, ...]:
        """Return the supplied reverse probe-to-case candidates."""
        return self.source_candidates

    async def get_probe_snapshot(self, probe_id: str) -> ProbeSnapshot:
        """Return one supplied probe and its reverse links as a snapshot."""
        probe = (
            self.probes[0]
            if self.force_probe_lookup
            else next(
                (probe for probe in self.probes if probe.probe_id == probe_id),
                None,
            )
        )
        return ProbeSnapshot(probe=probe, sources=self.source_candidates)


def row(
    *,
    case_id: str | None = CASE_1,
    session_id: str | None = SESSION_1,
    bad_case_type: object = "self",
    object_type: object = "agent",
    object_version: object = "v1",
    meta_data: object = None,
    title: object = "problem title",
    reason: object = "problem",
) -> BadCaseRow:
    """Build one external row while retaining intentionally malformed fields."""
    return BadCaseRow(
        bad_case_id=cast(str, case_id),
        bad_case_session_id=cast(str, session_id),
        bad_case_type=cast(str, bad_case_type),
        object_name="Explore",
        object_type=cast(str, object_type),
        object_version=cast(str | None, object_version),
        bad_case_agent_id=None,
        title=cast(str, title),
        reason=cast(str, reason),
        meta_data=meta_data,
        source="external-test",
        created_at=NOW,
        updated_at=NOW,
    )


def analysis(
    *,
    case_id: str = CASE_1,
    status: object = "analyzed_issue",
    probe_id: object = PROBE_1,
    result: object = None,
) -> BadCaseAnalysisRow:
    """Build one analysis row with an optional invalid probe link."""
    return BadCaseAnalysisRow(
        bad_case_id=case_id,
        analysis_status=cast(str, status),
        probe_id=cast(str | None, probe_id),
        analysis_result=result,
        updated_at=NOW,
    )


def probe(
    *,
    probe_id: object = PROBE_1,
    session_id: object = SESSION_1,
    attribute_type: object = "model",
    probe_object: object = "Explore",
    probe_description: object = "description",
    probe_analysis: object = "analysis",
) -> ProbeReportRow:
    """Build one probe row with an optional invalid attribute type."""
    return ProbeReportRow(
        probe_id=cast(str, probe_id),
        session_id=cast(str, session_id),
        probe_type="agent",
        probe_object=cast(str, probe_object),
        object_version="v1",
        attribute_type=cast(str, attribute_type),
        probe_description=cast(str, probe_description),
        probe_analysis=cast(str, probe_analysis),
        created_at=NOW,
        updated_at=NOW,
    )


async def test_seeded_rows_expose_all_five_display_states(
    external_database: Database,
) -> None:
    """The fixture-backed read path derives five stable display states."""
    service = BadCaseService(BadCaseRepository(external_database))

    first = await service.list_for_session(SESSION_1)
    second = await service.list_for_session(SESSION_2)
    third = await service.list_for_session(SESSION_3)
    fourth = await service.list_for_session(SESSION_4)

    assert [item.bad_case_id for item in first.items] == [CASE_1, CASE_5]
    assert [item.display_state for item in first.items] == [
        "analyzed_issue_prompt",
        "analyzed_issue_model",
    ]
    assert [item.display_state for item in second.items] == ["analyzed_nonissue"]
    assert [item.display_state for item in third.items] == ["analyzed_issue_error"]
    assert [item.display_state for item in fourth.items] == ["unanalyzed"]
    assert [item.title for item in first.items] == [
        "检查结论缺少目标文件",
        "推理步骤越过工具边界",
    ]
    assert first.warnings == ()


async def test_empty_and_valid_nonissue_analysis_are_non_errors(
    external_database: Database,
) -> None:
    """Missing analysis is an empty view while analyzed_nonissue links no probe."""
    service = BadCaseService(BadCaseRepository(external_database))

    unanalyzed = await service.get_case(CASE_4)
    nonissue = await service.get_case(CASE_2)

    assert unanalyzed is not None
    assert unanalyzed.analysis.status == "unanalyzed"
    assert unanalyzed.analysis.probe_id is None
    assert unanalyzed.analysis.attribute_type is None
    assert unanalyzed.analysis.result is None
    assert nonissue is not None
    assert nonissue.analysis.status == "analyzed_nonissue"
    assert nonissue.analysis.probe_id is None
    assert nonissue.analysis.attribute_type is None
    assert nonissue.display_state == "analyzed_nonissue"


@pytest.mark.parametrize(
    ("analysis_row", "probe_row", "warning_code"),
    [
        (analysis(probe_id=None), probe(), "ANALYSIS_PROBE_MISMATCH"),
        (analysis(), probe(session_id=SESSION_2), "PROBE_SESSION_MISMATCH"),
        (analysis(probe_id="missing"), probe(), "PROBE_NOT_FOUND"),
        (
            analysis(status="analyzed_nonissue", probe_id=PROBE_1),
            probe(),
            "ANALYSIS_PROBE_MISMATCH",
        ),
        (analysis(), probe(attribute_type="unknown"), "INVALID_ATTRIBUTE_TYPE"),
    ],
)
async def test_inconsistent_analysis_links_degrade_to_unanalyzed(
    analysis_row: BadCaseAnalysisRow,
    probe_row: ProbeReportRow,
    warning_code: str,
) -> None:
    """Every unsafe attribution link degrades without leaking raw row values."""
    service = BadCaseService(
        FakeRepository(
            cases=(row(meta_data={"safe": True}),),
            analyses=(analysis_row,),
            probes=(probe_row,),
        ),
    )

    result = await service.get_case(CASE_1)

    assert result is not None
    assert result.analysis.status == "unanalyzed"
    assert result.analysis.probe_id is None
    assert result.analysis.attribute_type is None
    assert result.analysis.result is None
    assert warning_code in {warning.code for warning in result.warnings}
    assert "unknown" not in str(result)
    assert "SESSION_2" not in str(result.warnings)


@pytest.mark.parametrize(
    ("case_row", "warning_code"),
    [
        (row(case_id=None), "EXTERNAL_FIELD_MISSING"),
        (row(session_id=None), "EXTERNAL_FIELD_MISSING"),
    ],
)
async def test_missing_identity_rows_are_skipped(
    case_row: BadCaseRow,
    warning_code: str,
) -> None:
    """Identity drift produces a stable diagnostic and never a fake case."""
    service = BadCaseService(FakeRepository(cases=(case_row,)))

    result = await service.list_for_session(SESSION_1)

    assert result.items == ()
    assert [warning.code for warning in result.warnings] == [warning_code]


async def test_null_and_unknown_non_identity_fields_remain_readable() -> None:
    """Malformed presentation fields degrade safely without exposing their raw values."""
    service = BadCaseService(
        FakeRepository(
            cases=(
                row(
                    bad_case_type="unexpected-type",
                    object_type="unexpected-object",
                    object_version=None,
                    reason=None,
                    meta_data=["not", "a", "mapping"],
                ),
            ),
        ),
    )

    result = await service.get_case(CASE_1)

    assert result is not None
    assert result.bad_case_type is None
    assert result.object_type is None
    assert result.object_version is None
    assert result.reason == ""
    assert result.meta_data is None
    assert {warning.code for warning in result.warnings} == {
        "EXTERNAL_FIELD_INVALID",
        "EXTERNAL_FIELD_MISSING",
    }


@pytest.mark.parametrize(
    ("title", "reason", "expected"),
    [
        (None, "第一句。第二句。", "第一句。"),
        ("   ", "只有一句没有标点", "只有一句没有标点"),
        ("", "First sentence. Second.", "First sentence."),
        (None, None, UNNAMED_TITLE),
        (None, "   ", UNNAMED_TITLE),
        (None, "长" * 300, "长" * 255),
    ],
)
async def test_blank_or_missing_title_is_derived_from_the_description(
    title: object,
    reason: object,
    expected: str,
) -> None:
    """A missing short title falls back to the description's first sentence."""
    service = BadCaseService(
        FakeRepository(cases=(row(title=title, reason=reason),)),
    )

    result = await service.get_case(CASE_1)

    assert result is not None
    assert result.title == expected
    assert [
        (warning.code, warning.field) for warning in result.warnings if warning.field == "title"
    ] == [("EXTERNAL_FIELD_MISSING", "title")]


async def test_external_title_is_trimmed_and_preserved_without_a_warning() -> None:
    """A usable external title is authoritative and is not reported as drift."""
    service = BadCaseService(
        FakeRepository(cases=(row(title="  检索索引读取失败  "),)),
    )

    result = await service.get_case(CASE_1)

    assert result is not None
    assert result.title == "检索索引读取失败"
    assert not [warning for warning in result.warnings if warning.field == "title"]


async def test_session_list_is_stably_ordered_and_uses_one_query_per_model(
    external_database: Database,
) -> None:
    """Cases and analyses use stable ordering without a per-case query loop."""
    statements: list[str] = []

    def capture(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(external_database.engine.sync_engine, "before_cursor_execute", capture)
    try:
        result = await BadCaseService(BadCaseRepository(external_database)).list_for_session(
            SESSION_1,
        )
    finally:
        event.remove(external_database.engine.sync_engine, "before_cursor_execute", capture)

    assert [item.bad_case_id for item in result.items] == [CASE_1, CASE_5]
    assert statements == ["SELECT", "SELECT", "SELECT"]


async def test_probe_read_model_includes_reverse_case_sources(
    external_database: Database,
) -> None:
    """Probe reads derive their source bad-case ids without storing denormalized data."""
    service = BadCaseService(BadCaseRepository(external_database))

    result = await service.get_probe(PROBE_1)

    assert result is not None
    assert result.probe_id == PROBE_1
    assert result.from_bad_cases == (CASE_1,)
    assert result.from_bad_cases_count == 1
    assert result.attribute_type == "prompt"


@pytest.mark.parametrize(
    ("probe_row", "field"),
    [
        (probe(probe_id=None), "probe_id"),
        (probe(session_id=None), "session_id"),
    ],
)
async def test_probe_missing_identity_is_skipped_with_diagnostic(
    probe_row: ProbeReportRow,
    field: str,
) -> None:
    """Missing probe identity yields no fabricated model and a stable diagnostic."""
    service = BadCaseService(
        FakeRepository(
            probes=(probe_row,),
            force_probe_lookup=True,
        ),
    )

    lookup = await service.get_probe_result(PROBE_1)

    assert isinstance(lookup, ProbeReportLookup)
    assert lookup.model is None
    assert [(warning.code, warning.field) for warning in lookup.warnings] == [
        ("EXTERNAL_FIELD_MISSING", field),
    ]
    assert await service.get_probe(PROBE_1) is None


async def test_probe_reverse_sources_reject_invalid_links() -> None:
    """Only analyzed issue links with matching existing case/probe sessions count."""
    service = BadCaseService(
        FakeRepository(
            probes=(probe(),),
            source_candidates=(
                ProbeSourceCandidate(CASE_1, "analyzed_issue", SESSION_1, SESSION_1),
                ProbeSourceCandidate(CASE_2, "analyzed_nonissue", SESSION_1, SESSION_1),
                ProbeSourceCandidate(CASE_3, "analyzed_issue", SESSION_2, SESSION_1),
                ProbeSourceCandidate(CASE_4, "analyzed_issue", None, SESSION_1),
                ProbeSourceCandidate(CASE_5, "analyzed_issue", SESSION_1, None),
            ),
        ),
    )

    lookup = await service.get_probe_result(PROBE_1)

    assert lookup.model is not None
    assert lookup.model.from_bad_cases == (CASE_1,)
    assert lookup.model.from_bad_cases_count == 1
    assert "INVALID_PROBE_SOURCE_LINK" in {warning.code for warning in lookup.warnings}


@pytest.mark.parametrize(
    ("analysis_row", "expected_status"),
    [
        (analysis(result=None), "analyzed_issue"),
        (analysis(result={"summary": 1}), "analyzed_issue"),
        (
            analysis(
                status="analyzed_nonissue",
                probe_id=None,
                result={"reason": "because", "reasoning": [1]},
            ),
            "analyzed_nonissue",
        ),
        (
            analysis(
                status="analyzed_nonissue",
                probe_id=None,
                result={"reason": 1, "reasoning": ["because"]},
            ),
            "analyzed_nonissue",
        ),
    ],
)
async def test_analysis_result_shape_drift_is_sanitized(
    analysis_row: BadCaseAnalysisRow,
    expected_status: str,
) -> None:
    """Malformed snapshots are removed while status/link state is retained."""
    service = BadCaseService(
        FakeRepository(
            cases=(row(),),
            analyses=(analysis_row,),
            probes=(probe(),),
        ),
    )

    result = await service.get_case(CASE_1)

    assert result is not None
    assert result.analysis.status == expected_status
    assert result.analysis.result is None
    assert "ANALYSIS_RESULT_INVALID" in {warning.code for warning in result.warnings}


async def test_valid_analysis_result_shapes_are_preserved() -> None:
    """Canonical issue and non-issue snapshot shapes pass unchanged."""
    issue_service = BadCaseService(
        FakeRepository(
            cases=(row(),),
            analyses=(analysis(result={"summary": "valid"}),),
            probes=(probe(),),
        ),
    )
    nonissue_service = BadCaseService(
        FakeRepository(
            cases=(row(),),
            analyses=(
                analysis(
                    status="analyzed_nonissue",
                    probe_id=None,
                    result={"reason": "valid", "reasoning": ["checked"]},
                ),
            ),
        ),
    )

    issue = await issue_service.get_case(CASE_1)
    nonissue = await nonissue_service.get_case(CASE_1)

    assert issue is not None
    assert issue.analysis.result == {"summary": "valid"}
    assert nonissue is not None
    assert nonissue.analysis.result == {
        "reason": "valid",
        "reasoning": ["checked"],
    }


def test_repository_exposes_no_external_table_write_methods() -> None:
    """The runtime external read boundary cannot call insert, update, or delete helpers."""
    forbidden = ("insert", "update", "delete", "upsert", "create", "replace")
    public_methods = {name for name in dir(BadCaseRepository) if not name.startswith("_")}
    assert not {name for name in public_methods if any(term in name.lower() for term in forbidden)}


async def test_fixture_fifth_state_is_persisted(
    external_database: Database,
) -> None:
    """The checked-in corpus includes a real model-attributed issue."""
    service = BadCaseService(BadCaseRepository(external_database))

    result = await service.get_case(CASE_5)

    assert result is not None
    assert result.display_state == "analyzed_issue_model"
    assert result.analysis.probe_id == PROBE_3
    assert result.analysis.attribute_type == "model"


async def test_runtime_upgrade_does_not_create_external_tables(
    tmp_path: Path,
) -> None:
    """Application migrations leave externally owned tables to their owner."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        db_pool_size=2,
        db_max_overflow=1,
        jwt_secret=SecretStr("external-read-model-test-signing-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database, bootstrap_external_tables=False)
        async with database.session() as session:
            names: set[str] = set()
            rows = (
                await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'table'"),
                )
            ).all()
            for (name,) in rows:
                names.add(str(name))
    finally:
        await database.dispose()

    assert {"users", "session_families", "job_runs"} <= names
    assert not {"bad_cases", "bad_case_analysis", "probe_reports"} & names


async def test_application_startup_leaves_external_tables_to_their_owner(
    tmp_path: Path,
) -> None:
    """The composed lifespan applies the same runtime-only migration policy."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        db_pool_size=2,
        db_max_overflow=1,
        jwt_secret=SecretStr("external-read-model-test-signing-secret"),
        sync_interval_seconds=0,
    )
    database = create_database(settings)
    app = create_app(settings, database=database)

    async with app.router.lifespan_context(app):
        async with database.session() as session:
            rows = (
                await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'table'"),
                )
            ).all()
        names = {str(name) for (name,) in rows}

    assert {"users", "session_families", "job_runs"} <= names
    assert not {"bad_cases", "bad_case_analysis", "probe_reports"} & names


async def test_fixture_bootstrap_repairs_external_tables_after_runtime_upgrade(
    tmp_path: Path,
) -> None:
    """Fixture bootstrap creates external tables even when revision 0004 ran first."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        db_pool_size=2,
        db_max_overflow=1,
        jwt_secret=SecretStr("external-read-model-test-signing-secret"),
    )
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database, bootstrap_external_tables=False)
    finally:
        await database.dispose()

    corpus = load_fixture_corpus(ROOT / "fixtures" / "m2-synthetic" / "corpus.json")
    result = await run_corpus_seed(settings, corpus)

    assert result.inserted > 0
    database = create_database(settings)
    await database.start()
    try:
        service = BadCaseService(BadCaseRepository(database))
        assert await service.get_case(CASE_1) is not None
    finally:
        await database.dispose()


async def test_external_read_models_use_timezone_aware_shanghai_timestamps(
    external_database: Database,
) -> None:
    """External DATETIME values cross the API boundary with +08:00 timezone."""
    service = BadCaseService(BadCaseRepository(external_database))

    case = await service.get_case(CASE_1)
    probe_model = await service.get_probe(PROBE_1)

    assert case is not None
    assert probe_model is not None
    case_offset = case.created_at.utcoffset()
    probe_offset = probe_model.updated_at.utcoffset()
    assert case_offset is not None
    assert case_offset.total_seconds() == 8 * 60 * 60
    assert probe_offset is not None
    assert probe_offset.total_seconds() == 8 * 60 * 60


async def test_empty_probe_presentation_fields_emit_safe_warnings() -> None:
    """Probe presentation drift remains visible without exposing external text."""
    service = BadCaseService(
        FakeRepository(
            probes=(
                probe(
                    probe_object="",
                    probe_description="",
                    probe_analysis="",
                ),
            ),
        ),
    )

    lookup = await service.get_probe_result(PROBE_1)

    assert lookup.model is not None
    assert lookup.model.probe_object == ""
    assert lookup.model.probe_description == ""
    assert lookup.model.probe_analysis == ""
    assert [
        (warning.code, warning.field)
        for warning in lookup.warnings
        if warning.code == "EXTERNAL_FIELD_MISSING"
    ] == [
        ("EXTERNAL_FIELD_MISSING", "probe_object"),
        ("EXTERNAL_FIELD_MISSING", "probe_description"),
        ("EXTERNAL_FIELD_MISSING", "probe_analysis"),
    ]


async def test_every_public_repository_path_is_select_only(
    external_database: Database,
) -> None:
    """Every public read path emits SELECT statements and no mutation SQL."""
    statements: list[str] = []

    def capture(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    repository = BadCaseRepository(external_database)
    event.listen(external_database.engine.sync_engine, "before_cursor_execute", capture)
    try:
        await repository.list_by_session(SESSION_1)
        await repository.list_snapshot(SESSION_1)
        await repository.get_case(CASE_1)
        await repository.get_case_snapshot(CASE_1)
        await repository.analyses_by_case_ids((CASE_1,))
        await repository.get_analysis(CASE_1)
        await repository.probes_by_ids((PROBE_1,))
        await repository.get_probe(PROBE_1)
        await repository.probe_source_candidates(PROBE_1)
        await repository.get_probe_snapshot(PROBE_1)
    finally:
        event.remove(external_database.engine.sync_engine, "before_cursor_execute", capture)

    assert statements
    assert set(statements) == {"SELECT"}


async def test_read_models_use_one_database_session_per_snapshot(
    external_database: Database,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case, analysis, and probe rows cannot mix two replay versions."""
    session_count = 0
    original_session = external_database.session

    def counted_session() -> object:
        nonlocal session_count
        session_count += 1
        return original_session()

    monkeypatch.setattr(external_database, "session", counted_session)
    service = BadCaseService(BadCaseRepository(external_database))

    await service.list_for_session(SESSION_1)
    assert session_count == 1

    session_count = 0
    await service.get_case(CASE_1)
    assert session_count == 1

    session_count = 0
    await service.get_probe_result(PROBE_1)
    assert session_count == 1
