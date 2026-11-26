"""Settings and target-overview behavior for the agent name-match toggle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import httpx
import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.fixtures import ensure_fixture_external_tables
from app.db.models.domain import agent_events, bad_case_analysis, probe_reports
from app.main import create_app
from app.utils.time import SHANGHAI
from tests.identity.helpers import identity_settings
from tests.m10_02_potential_support import (
    FakeGitRemote,
    seed_case,
    seed_event,
    seed_session,
    seed_target,
    seed_workspace,
)
from tests.target_content_support import FakeTargetVersionResolver
from tests.workspaces.helpers import access_token, bearer, create_user, insert_member

WORKSPACE = "ws-name-match"
TARGET_ID = "target-name-match-agent"
AGENT_NAME = "name-match-agent"
STABLE_REF = "stable"
"""The configured ref that owns the only version row in name-match mode."""
BODY_HASH = "a" * 64
"""The target body hash resolved from the configured ref."""
TRACE_HASH = "b" * 64
"""The first Session's different body hash."""
OTHER_HASH = "c" * 64
"""The second Session's different body hash."""
BODY_REVISION = f"digest:{BODY_HASH}"
TRACE_REVISION = f"digest:{TRACE_HASH}"
OTHER_REVISION = f"digest:{OTHER_HASH}"
SESSION_A = "nm-session-a"
SESSION_B = "nm-session-b"
CASE_A = "nm-case-a"
CASE_B = "nm-case-b"
WINDOW = {"from": "2026-11-01", "to": "2026-11-30"}
OBJECT_ENTRY = datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI)


def _settings() -> Settings:
    """Build offline settings while inheriting the shared test secret."""
    return Settings(db_dialect=DatabaseDialect.SQLITE)


def test_agent_match_by_name_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unconfigured deployment keeps the body-hash overview behavior."""
    monkeypatch.delenv("HE_AGENT_MATCH_BY_NAME", raising=False)

    assert _settings().agent_match_by_name is False


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("false", False), ("true", True), ("0", False), ("1", True)],
)
def test_agent_match_by_name_reads_the_he_prefixed_env(
    monkeypatch: pytest.MonkeyPatch,
    raw: str,
    expected: bool,
) -> None:
    """Deployment overrides arrive through ``HE_AGENT_MATCH_BY_NAME``."""
    monkeypatch.setenv("HE_AGENT_MATCH_BY_NAME", raw)

    assert _settings().agent_match_by_name is expected


def test_agent_match_by_name_rejects_an_invalid_boolean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unusable value fails settings validation before the app starts."""
    monkeypatch.setenv("HE_AGENT_MATCH_BY_NAME", "sometimes")

    with pytest.raises(ValidationError):
        _settings()


@dataclass(frozen=True, slots=True)
class NameMatchApi:
    """One app configured with the toggle, its seeded space, and a reader."""

    client: httpx.AsyncClient
    database: Database
    workspace_id: str
    reader: dict[str, str]
    name_match: bool


def _at(hour: int, minute: int) -> datetime:
    """Return one deterministic Asia/Shanghai instant on 2026-11-17."""
    return datetime(2026, 11, 17, hour, minute, tzinfo=SHANGHAI)


async def _seed_agent_event(
    database: Database,
    *,
    agent_id: str,
    object_version: str | None,
    object_revision: str,
    definition_hash: str,
) -> None:
    """Insert one agent entry whose trace identity differs from the target body."""
    async with database.transaction() as session:
        await session.execute(
            insert(agent_events).values(
                agent_id=agent_id,
                event_index=0,
                line_no=1,
                message_offset=0,
                kind="agent",
                name=AGENT_NAME,
                object_version=object_version,
                object_revision=object_revision,
                definition_hash=definition_hash,
                triggered_at=OBJECT_ENTRY,
            ),
        )


async def _seed_report(
    database: Database,
    *,
    probe_id: str,
    case_id: str,
    session_id: str,
    object_version: str,
    conclusion: Literal["attributed", "non_target"],
    category: str | None,
    updated_at: datetime,
) -> None:
    """Insert one completed V2 report link for an agent case."""
    async with database.transaction() as session:
        await session.execute(
            insert(probe_reports).values(
                probe_id=probe_id,
                report_schema_version="probe-report/v2",
                workspace_id=WORKSPACE,
                session_id=session_id,
                probe_type="agent",
                probe_object=AGENT_NAME,
                object_version=object_version,
                attribute_type=category,
                conclusion=conclusion,
                confidence=0.8,
                probe_description=f"description {probe_id}",
                probe_analysis=f"analysis {probe_id}",
                policy_version="v1",
                attribution_engine="rule-v1",
                cache_key=f"{probe_id}-cache".ljust(64, "0")[:64],
                created_at=updated_at,
                updated_at=updated_at,
            ),
        )
        await session.execute(
            insert(bad_case_analysis).values(
                bad_case_id=case_id,
                probe_id=probe_id,
                analysis_status=None,
                analysis_result=None,
                updated_at=updated_at,
            ),
        )


async def _seed_scenario(database: Database) -> None:
    """Seed two same-name Sessions whose hashes miss the target body hash."""
    main_a = await seed_session(database, session_id=SESSION_A, started_at=OBJECT_ENTRY, title="A")
    await _seed_agent_event(
        database,
        agent_id=main_a,
        object_version="v2.0.0",
        object_revision=TRACE_REVISION,
        definition_hash=TRACE_HASH,
    )
    await seed_event(
        database,
        agent_id=main_a,
        event_index=1,
        kind="skill",
        name="workflow",
        triggered_at=_at(10, 5),
    )
    await seed_case(
        database,
        case_id=CASE_A,
        workspace_id=WORKSPACE,
        session_id=SESSION_A,
        case_type="discovery",
        object_name="workflow",
        object_type="skill",
        created_at=_at(10, 10),
    )

    main_b = await seed_session(database, session_id=SESSION_B, started_at=OBJECT_ENTRY, title="B")
    await _seed_agent_event(
        database,
        agent_id=main_b,
        object_version=None,
        object_revision=OTHER_REVISION,
        definition_hash=OTHER_HASH,
    )
    await seed_event(
        database,
        agent_id=main_b,
        event_index=1,
        kind="skill",
        name="workflow",
        triggered_at=_at(10, 5),
    )
    await seed_case(
        database,
        case_id=CASE_B,
        workspace_id=WORKSPACE,
        session_id=SESSION_B,
        case_type="discovery",
        object_name="workflow",
        object_type="skill",
        created_at=_at(10, 10),
    )

    # Case A keeps an older non-target report and a newer attributed report.
    await _seed_report(
        database,
        probe_id="nm-old-a",
        case_id=CASE_A,
        session_id=SESSION_A,
        object_version=TRACE_REVISION,
        conclusion="non_target",
        category=None,
        updated_at=_at(10, 20),
    )
    await _seed_report(
        database,
        probe_id="nm-new-a",
        case_id=CASE_A,
        session_id=SESSION_A,
        object_version=TRACE_REVISION,
        conclusion="attributed",
        category="error",
        updated_at=_at(10, 30),
    )
    await _seed_report(
        database,
        probe_id="nm-b",
        case_id=CASE_B,
        session_id=SESSION_B,
        object_version=OTHER_REVISION,
        conclusion="non_target",
        category=None,
        updated_at=_at(10, 30),
    )


@pytest_asyncio.fixture(params=[False, True], ids=["hash-match", "name-match"])
async def name_match_api(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> AsyncIterator[NameMatchApi]:
    """Seed the same scenario twice, with the toggle off and on."""
    name_match = bool(request.param)
    app = create_app(
        identity_settings(tmp_path, agent_match_by_name=name_match),
        git_remote=FakeGitRemote(),
        target_version_resolver=FakeTargetVersionResolver(
            revision="digest",
            revisions={STABLE_REF: BODY_REVISION},
        ),
    )
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        database = app.state.database
        await ensure_fixture_external_tables(database)
        await seed_workspace(database, WORKSPACE)
        await seed_target(
            database,
            workspace_id=WORKSPACE,
            target_id=TARGET_ID,
            object_type="agent",
            object_name=AGENT_NAME,
            default_ref=STABLE_REF,
        )
        await _seed_scenario(database)
        user_id = await create_user(database, username="name-match-reader")
        await insert_member(
            database,
            workspace_id=WORKSPACE,
            user_id=user_id,
            role="viewer",
        )
        headers = bearer(access_token(app, user_id=user_id))
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            yield NameMatchApi(
                client=client,
                database=database,
                workspace_id=WORKSPACE,
                reader=headers,
                name_match=name_match,
            )


async def test_agent_detail_folds_to_one_ref_row_when_enabled(
    name_match_api: NameMatchApi,
) -> None:
    """Off keeps digest rows; on returns one ref row with name-matched Sessions/reports."""
    api = name_match_api
    detail = await api.client.get(
        f"/api/workspaces/{api.workspace_id}/overview/targets/{TARGET_ID}/detail",
        headers=api.reader,
        params=WINDOW,
    )
    assert detail.status_code == 200
    body = detail.json()

    if not api.name_match:
        assert set(body["target"]["versions"]) == {
            STABLE_REF,
            TRACE_REVISION,
            OTHER_REVISION,
        }
        assert body["stats"] == {
            "sessions": 2,
            "potential": 2,
            "distinctCases": 2,
            "versions": 3,
        }
        rows = {row["version"]: row for row in body["byVersion"]}
        assert rows[STABLE_REF]["potential"] == 0
        assert rows[TRACE_REVISION]["attributed"] == 1
        assert rows[OTHER_REVISION]["nonTarget"] == 1
    else:
        assert body["target"]["versions"] == [STABLE_REF]
        assert body["target"]["versionOptions"] == [
            {"version": STABLE_REF, "ref": STABLE_REF, "commit": None},
        ]
        assert body["stats"] == {
            "sessions": 2,
            "potential": 2,
            "distinctCases": 2,
            "versions": 1,
        }
        assert body["byVersion"] == [
            {
                "version": STABLE_REF,
                "ref": STABLE_REF,
                "commit": None,
                "potential": 2,
                "attributed": 1,
                "nonTarget": 1,
                "unanalyzed": 0,
            },
        ]

    cases = await api.client.get(
        f"/api/workspaces/{api.workspace_id}/overview/targets/cases",
        headers=api.reader,
        params={**WINDOW, "targets": TARGET_ID},
    )
    assert cases.status_code == 200
    rows = {row["badCaseId"]: row for row in cases.json()["items"]}
    assert set(rows) == {CASE_A, CASE_B}
    assert rows[CASE_A]["state"] == "attributed"
    assert rows[CASE_A]["attributionId"] == "nm-new-a"
    assert rows[CASE_B]["state"] == "nonTarget"
    expected_version = STABLE_REF if api.name_match else "v2.0.0"
    assert rows[CASE_A]["objectVersion"] == expected_version
    assert rows[CASE_B]["objectVersion"] == (STABLE_REF if api.name_match else OTHER_REVISION)

    if api.name_match:
        listed = await api.client.get(
            f"/api/workspaces/{api.workspace_id}/overview/targets",
            headers=api.reader,
            params={**WINDOW, "pageSize": 50},
        )
        assert listed.status_code == 200
        item = next(row for row in listed.json()["items"] if row["targetId"] == TARGET_ID)
        assert item["versions"] == [STABLE_REF]
        assert item["sessions"] == 2
