"""Exercise target-owned rules against migrated SQLite and production-dialect storage."""

import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import insert, update

from app.config import DatabaseDialect, Settings
from app.db.crud.candidate_sources import CandidateSourcesRepository
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.db.crud.potential import PotentialRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_cases, workspace_bad_cases
from app.errors import AppError
from app.service.evolution.candidate_policy import CandidatePolicy
from app.service.evolution.potential import MatchCondition, PotentialMatcher, resolve_policy
from tests.m10_02_potential_support import NOW, seed_case, seed_event, seed_session, seed_workspace


@pytest.mark.parametrize("mysql", [False, pytest.param(True, marks=pytest.mark.mysql)])
async def test_roundtrip_source_policy(tmp_path: Path, mysql: bool) -> None:
    url = os.environ.get("HE_DB_URL", "") if mysql else f"sqlite+aiosqlite:///{tmp_path}/policy.db"
    if mysql and not url.startswith("mysql+asyncmy://"):
        pytest.skip("MySQL integration requires HE_DB_URL")
    db = create_database(
        Settings(db_dialect=DatabaseDialect.MYSQL if mysql else DatabaseDialect.SQLITE, db_url=url)
    )
    await db.start()
    try:
        await upgrade_database(db)
        key = uuid4().hex[:10]
        wid, other, sid = "rules-" + key, "other-" + key, "session-" + key
        await seed_workspace(db, wid)
        await seed_workspace(db, other)
        agent = await seed_session(db, session_id=sid, started_at=NOW, title=sid)
        for index, name in enumerate(("A", "B", "A", "B")):
            await seed_event(db, agent_id=agent, event_index=index, kind="skill", name=name)
        await seed_event(db, agent_id=agent, event_index=4, kind="skill", name="a")
        events = await PotentialRepository(db).list_object_events(
            [sid], object_type="skill", object_name="A"
        )
        assert [e.event_index for e in events] == [0, 2]
        for suffix, kind, name, typ, space, line in [
            ("1", "skill", "A", "self", wid, 1),
            ("2", "skill", "A", "self", wid, 3),
            ("3", "skill", "A", "discovery", wid, None),
            ("4", "agent", "A", "self", wid, None),
            ("5", "skill", "private", "self", other, None),
            ("6", "skill", "a", "self", wid, None),
        ]:
            await seed_case(
                db,
                case_id=key + suffix,
                session_id=sid,
                object_name=name,
                object_type=kind,
                case_type=typ,
                workspace_id=space,
            )
            if line:
                async with db.transaction() as session:
                    await session.execute(
                        update(bad_cases)
                        .where(bad_cases.c.bad_case_id == key + suffix)
                        .values(trigger_line=line, catalog_label="quality")
                    )
        # Two assignments in the same space must still represent just one case.
        async with db.transaction() as session:
            await session.execute(
                insert(workspace_bad_cases).values(
                    workspace_id=wid,
                    bad_case_id=key + "1",
                    assignment_source="catalog_label",
                    label="quality",
                    assigned_at=NOW,
                )
            )
        async with db.transaction() as session:
            await session.execute(
                update(bad_cases)
                .where(bad_cases.c.bad_case_id == key + "1")
                .values(origin="report", meta_data={"label": "direct"}, catalog_label=None)
            )
        sources = CandidateSourcesRepository(db)
        start, end = NOW - timedelta(days=1), NOW + timedelta(days=1)
        counts = await sources.counts(wid, start, end)
        assert {(r["kind"], r["name"], r["self_count"], r["discovery_count"]) for r in counts} == {
            ("skill", "A", 2, 1),
            ("agent", "A", 1, 0),
            ("skill", "a", 1, 0),
        }
        assert all(
            row["self_count"] == row["discovery_count"] == 0
            for row in await sources.counts(wid, end, end + timedelta(days=1))
        )
        rows = await sources.reports(
            wid,
            start,
            end,
            kind="skill",
            name="A",
            types=["self", "discovery"],
            labels=[],
            unlabelled=True,
            filter_type=None,
            page=1,
            page_size=20,
        )
        assert set(rows["labels"]) == {"direct", "quality", None}
        assert rows["source_total"] == 3 and [r["id"] for r in rows["items"]] == [key + "3"]
        policy = CandidatePolicy.model_validate(
            {
                "mode": "custom",
                "rules": [{"kind": "skill", "name": "A", "types": ["self"], "relation": "after"}],
            }
        )
        repo = EvolutionTargetRepository(db)
        values = dict(
            workspace_id=wid,
            object_type="skill",
            object_name="A",
            repo_url="https://example.com/skills",
            sub_dir="skills/A",
            default_ref="main",
            validation_project_id="val",
            test_project_id="test",
            enabled=True,
            candidate_policy=policy.model_dump(),
        )
        target = await repo.insert(values)
        assert target.candidate_policy == policy.model_dump()
        condition = MatchCondition(
            wid, "skill", "A", "main", "tag:main", start, end, candidate_policy=policy
        )
        matcher = PotentialMatcher(PotentialRepository(db))
        sessions = await matcher.associated_sessions(condition)
        matched = await matcher.potential_cases(condition, sessions, resolve_policy(None))
        assert [(row.bad_case_id, row.object_trigger.event_index) for row in matched.included] == [
            (key + "1", 2)
        ]
        assert matched.included[0].matched_sources[0]["rule"] == 1
        assert policy.rules
        policy.rules[0].name = "private"
        with pytest.raises(AppError):
            await repo.save_policy(wid, target.id, policy.model_dump())
        policy.rules[0].name = "A"
        assert (await repo.get(target.id)) == target
        policy.rules[0].relation = "any"
        await repo.save_policy(wid, target.id, policy.model_dump())
        saved = await repo.get(target.id)
        assert saved and saved.candidate_policy == policy.model_dump()
        assert saved.attribution_generation != target.attribution_generation
        updated = await repo.update(
            target.id, {k: v for k, v in values.items() if k != "candidate_policy"}
        )
        assert updated.candidate_policy == saved.candidate_policy
        condition = MatchCondition(
            wid, "skill", "A", "main", "tag:main", start, end, candidate_policy=policy
        )
        assert {
            row.bad_case_id
            for row in (
                await matcher.potential_cases(condition, sessions, resolve_policy(None))
            ).included
        } == {key + "1", key + "2"}
    finally:
        await db.dispose()
