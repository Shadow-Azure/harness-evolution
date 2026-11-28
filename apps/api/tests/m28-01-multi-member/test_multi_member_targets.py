"""Multi-member evolution target persistence, matching, and evaluation contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import func, select, text

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.evolution_targets import (
    EvolutionTargetMemberConflict,
    EvolutionTargetMemberRecord,
    EvolutionTargetRepository,
)
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import evolution_target_members, evolution_targets
from app.db.models.evolution import evolution_run_candidates, evolution_run_targets, evolution_runs
from app.service.evolution.engine.contracts import EvalRequest, EvalTarget
from app.service.evolution.potential import MatchTarget
from app.service.evolution.targets import (
    EvolutionTargetMemberWrite,
    EvolutionTargetService,
    EvolutionTargetWrite,
)
from app.third_party_api.eval_gateway.ai_eval_platform import AiEvalPlatformGateway
from app.utils.time import now_shanghai
from tests.m10_02_potential_support import harness as harness
from tests.m10_02_potential_support import seed_case


class _Remote:
    """Accept every repository and return one deterministic tag list."""

    async def validate(self, repo_url: str, ref: str) -> None:
        """Accept one configured repository and ref."""
        del repo_url, ref

    async def list_tags(self, repo_url: str) -> list[str]:
        """Return one stable tag."""
        del repo_url
        return ["v2.4.0"]


def alembic_config(database: Database) -> Config:
    """Build an Alembic config for explicit revision-path migration tests."""
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database.url.replace("%", "%%"))
    config.attributes["configure_logger"] = False
    return config


def _settings(tmp_path: Path) -> Settings:
    """Return one isolated SQLite database target."""
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'multi-member.db'}",
    )


def _definition(name: str) -> dict[str, str]:
    """Return one frozen member definition."""
    return {
        "commit": "a" * 40,
        "path": f"skills/{name}/SKILL.md",
        "revision": "digest:" + name[0] * 64,
        "key": name,
        "preview": f"# {name}",
    }


def _write(*names: str) -> EvolutionTargetWrite:
    """Build one two-member configuration write."""
    return EvolutionTargetWrite(
        repo_url="https://git.example.com/agent-skills.git",
        default_ref="v2.4.0",
        validation_project_id="val-skills",
        test_project_id="test-skills",
        primary_metric_key="resolved_rate",
        enabled=True,
        members=[
            EvolutionTargetMemberWrite(
                object_type="skill",
                object_name=name,
                sub_dir=f"skills/{name}",
            )
            for name in names
        ],
    )


@pytest.mark.asyncio
async def test_repository_round_trips_members_and_rejects_cross_config_duplicates(
    tmp_path: Path,
) -> None:
    """One configuration stores N members and a member may belong to only one."""
    database = create_database(_settings(tmp_path))
    await database.start()
    await upgrade_database(database)
    repository = EvolutionTargetRepository(database)
    try:
        created = await repository.insert(
            {
                "repo_url": "https://git.example.com/agent-skills.git",
                "default_ref": "v2.4.0",
                "validation_project_id": "val",
                "test_project_id": "test",
                "primary_metric_key": "resolved_rate",
                "enabled": True,
                "object_type": "skill",
                "object_name": "deep-research",
                "sub_dir": "skills/deep-research",
                "definition": _definition("deep-research"),
                "members": [
                    {
                        "object_type": "skill",
                        "object_name": name,
                        "sub_dir": f"skills/{name}",
                        "definition": _definition(name),
                    }
                    for name in ("deep-research", "code-review")
                ],
            },
        )
        loaded = await repository.get(created.id)
        assert loaded is not None
        assert [member.object_name for member in loaded.members] == [
            "deep-research",
            "code-review",
        ]
        assert loaded.member_for("skill", "code-review") is not None
        found = await repository.find_all("skill", "code-review")
        assert [row.id for row in found] == [created.id]

        with pytest.raises(EvolutionTargetMemberConflict):
            await repository.insert(
                {
                    "repo_url": "https://git.example.com/other.git",
                    "default_ref": "main",
                    "validation_project_id": "val",
                    "test_project_id": "test",
                    "primary_metric_key": "resolved_rate",
                    "enabled": True,
                    "object_type": "skill",
                    "object_name": "code-review",
                    "sub_dir": "skills/code-review",
                    "members": [
                        {
                            "object_type": "skill",
                            "object_name": "code-review",
                            "sub_dir": "skills/code-review",
                        },
                    ],
                },
            )

        updated = await repository.update(
            created.id,
            {
                "repo_url": "https://git.example.com/agent-skills.git",
                "default_ref": "v2.4.0",
                "validation_project_id": "val",
                "test_project_id": "test",
                "primary_metric_key": "resolved_rate",
                "enabled": True,
                "object_type": "skill",
                "object_name": "deep-research",
                "sub_dir": "skills/deep-research",
                "members": [
                    {
                        "object_type": "skill",
                        "object_name": "deep-research",
                        "sub_dir": "skills/deep-research",
                    },
                    {
                        "object_type": "agent",
                        "object_name": "writer",
                        "sub_dir": "agents/writer",
                    },
                ],
            },
        )
        assert [member.object_name for member in updated.members] == [
            "deep-research",
            "writer",
        ]
        assert await repository.find_all("skill", "code-review") == ()

        assert await repository.delete(created.id) is True
        async with database.session() as session:
            count = (
                await session.execute(
                    select(func.count()).select_from(evolution_target_members),
                )
            ).scalar_one()
        assert int(count) == 0
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_target_service_rejects_duplicate_members_and_reports_member_fields(
    tmp_path: Path,
) -> None:
    """The service deduplicates members and anchors global conflicts to one row."""
    database = create_database(_settings(tmp_path))
    await database.start()
    await upgrade_database(database)
    repository = EvolutionTargetRepository(database)
    service = EvolutionTargetService(repository, _Remote())  # type: ignore[arg-type]
    try:
        first = await service.create(_write("deep-research", "code-review"), created_by=None)
        assert [member.object_name for member in first.members] == [
            "deep-research",
            "code-review",
        ]

        with pytest.raises(Exception) as duplicate:
            await service.create(_write("code-review"), created_by=None)
        assert getattr(duplicate.value, "code", None) == "MEMBER_ALREADY_CONFIGURED"
        assert getattr(duplicate.value, "details", {}).get("field") == ("members[0].objectName")

        with pytest.raises(Exception) as local_duplicate:
            await service.create(_write("writer", "writer"), created_by=None)
        assert getattr(local_duplicate.value, "details", {}).get("reason") == ("member_duplicated")
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_run_repository_snapshots_targets(tmp_path: Path) -> None:
    """A run keeps one frozen member row per configuration member."""
    database = create_database(_settings(tmp_path))
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    try:
        run = await repository.create_run(
            {
                "title": "skills 自进化",
                "mode": "full",
                "engine_key": "full",
                "eval_config": {},
                "target_config_id": None,
                "target_type": "skill",
                "target_name": "deep-research",
                "target_version": "v2.4.0",
                "target_revision": "digest:" + "a" * 64,
                "repo_url": "https://git.example.com/agent-skills.git",
                "sub_dir": "skills/deep-research",
                "targets": [
                    {
                        "object_type": "skill",
                        "object_name": "deep-research",
                        "target_version": "v2.4.0",
                        "target_revision": "digest:" + "a" * 64,
                        "sub_dir": "skills/deep-research",
                        "base_commit": "b" * 40,
                    },
                    {
                        "object_type": "skill",
                        "object_name": "code-review",
                        "target_version": "v2.4.0",
                        "target_revision": "digest:" + "c" * 64,
                        "sub_dir": "skills/code-review",
                        "base_commit": "b" * 40,
                    },
                ],
            },
        )
        loaded = await repository.get_run(run.id)
        assert loaded is not None
        assert [item.object_name for item in loaded.targets] == [
            "deep-research",
            "code-review",
        ]
        assert [item.target_revision for item in loaded.targets] == [
            "digest:" + "a" * 64,
            "digest:" + "c" * 64,
        ]
    finally:
        await database.dispose()


def test_eval_asset_override_covers_every_member() -> None:
    """One platform launch submits every member's built asset path."""
    request = EvalRequest(
        run_id="run",
        evolution_round_id="round",
        repo_url="https://git.example.com/agent-skills.git",
        ref="candidate",
        commit="a" * 40,
        target_type="skill",
        target_name="deep-research",
        target_version="v2.4.0",
        cluster_id="cluster",
        idempotency_key="key",
        targets=(
            EvalTarget("skill", "deep-research", "skills/deep-research"),
            EvalTarget("agent", "writer", "agents/writer"),
        ),
    )
    override = AiEvalPlatformGateway._asset_override(None, request, "")  # type: ignore[arg-type]
    assert override["asset_paths"] == [
        ".claude/skills/deep-research",
        ".claude/agents/writer.md",
    ]
    assert override["asset_types"] == {
        ".claude/skills/deep-research": "skill",
        ".claude/agents/writer.md": "subagent",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("preview_stamp", [None, "0035", "0036"])
async def test_migration_backfills_members_and_run_targets(
    tmp_path: Path, preview_stamp: str | None
) -> None:
    """Mainline and both candidate previews retain their targets, runs and policies."""
    database = create_database(_settings(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0034")
        now = now_shanghai()
        async with database.transaction() as session:
            await session.execute(
                evolution_targets.insert().values(
                    id="legacy-target",
                    workspace_id="ws-default",
                    object_type="skill",
                    object_name="deep-research",
                    repo_url="https://git.example.com/agent-skills.git",
                    sub_dir="skills/deep-research",
                    default_ref="v2.4.0",
                    validation_project_id="val",
                    test_project_id="test",
                    primary_metric_key="resolved_rate",
                    enabled=True,
                    attribution_snapshot={"definition": _definition("deep-research")},
                    created_at=now,
                    updated_at=now,
                ),
            )
            await session.execute(
                evolution_runs.insert().values(
                    id="legacy-run",
                    workspace_id="ws-default",
                    title="legacy",
                    mode="full",
                    engine_key="full",
                    eval_config={},
                    target_config_id="legacy-target",
                    target_type="skill",
                    target_name="deep-research",
                    target_version="v2.4.0",
                    target_revision="digest:" + "a" * 64,
                    repo_url="https://git.example.com/agent-skills.git",
                    sub_dir="skills/deep-research",
                    created_at=now,
                ),
            )

        policy = {
            "mode": "custom",
            "rules": [{"kind": "skill", "name": "source", "relation": "after", "types": ["self"]}],
        }
        evidence = {"kind": "skill", "name": "source", "type": "self", "matches": [{"rule": 1}]}
        if preview_stamp:
            await seed_case(
                database,
                case_id="legacy-case",
                session_id="legacy-session",
                workspace_id="ws-default",
                object_name="source",
                case_type="self",
            )
            if preview_stamp == "0036":
                # The second preview had official member tables, but no result_commit.
                await asyncio.to_thread(command.upgrade, alembic_config(database), "0035")
            async with database.transaction() as session:
                run_columns = (
                    await session.execute(text("PRAGMA table_info(evolution_runs)"))
                ).mappings()
                if "result_commit" in {row["name"] for row in run_columns}:
                    await session.execute(
                        text("ALTER TABLE evolution_runs DROP COLUMN result_commit")
                    )
                for table, column in (
                    ("evolution_targets", "candidate_policy"),
                    ("evolution_run_candidates", "source_evidence"),
                ):
                    columns = (
                        await session.execute(text(f"PRAGMA table_info({table})"))
                    ).mappings()
                    if column not in {row["name"] for row in columns}:
                        await session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} JSON"))
                await session.execute(
                    evolution_targets.update()
                    .where(evolution_targets.c.id == "legacy-target")
                    .values(candidate_policy=policy)
                )
                await session.execute(
                    evolution_run_candidates.insert().values(
                        id="legacy-candidate",
                        run_id="legacy-run",
                        bad_case_id="legacy-case",
                        session_id="legacy-session",
                        workspace_id="ws-default",
                        order_state="comparable",
                        included=True,
                        included_reason="custom_source",
                        source_evidence=evidence,
                        created_at=now,
                    )
                )
            await asyncio.to_thread(command.stamp, alembic_config(database), preview_stamp)
        await upgrade_database(database)

        async with database.session() as session:
            result_commit = await session.execute(
                select(evolution_runs.c.result_commit).where(evolution_runs.c.id == "legacy-run")
            )
            assert result_commit.scalar_one() is None
            if preview_stamp:
                assert (
                    await session.scalar(
                        select(evolution_run_candidates.c.source_evidence).where(
                            evolution_run_candidates.c.id == "legacy-candidate"
                        )
                    )
                    == evidence
                )
                assert (
                    await session.scalar(
                        select(evolution_targets.c.candidate_policy).where(
                            evolution_targets.c.id == "legacy-target"
                        )
                    )
                    == policy
                )
            members = (
                (
                    await session.execute(
                        select(evolution_target_members).where(
                            evolution_target_members.c.target_id == "legacy-target",
                        ),
                    )
                )
                .mappings()
                .all()
            )
            run_targets = (
                (
                    await session.execute(
                        select(evolution_run_targets).where(
                            evolution_run_targets.c.run_id == "legacy-run",
                        ),
                    )
                )
                .mappings()
                .all()
            )
        assert [row["object_name"] for row in members] == ["deep-research"]
        assert members[0]["match_by_name"] is False
        assert run_targets[0]["match_by_name"] is False
        assert members[0]["definition"]["commit"] == "a" * 40
        assert [row["object_name"] for row in run_targets] == ["deep-research"]
    finally:
        await database.dispose()


def test_member_targets_keep_one_identity_per_object() -> None:
    """The matcher condition accepts one identity per configured member."""
    member = EvolutionTargetMemberRecord(
        id="member-1",
        target_id="target-1",
        workspace_id="ws-default",
        seq=0,
        object_type="skill",
        object_name="deep-research",
        sub_dir="skills/deep-research",
    )
    target = MatchTarget(
        object_type=member.object_type,
        object_name=member.object_name,
        target_version="v2.4.0",
        target_revision="digest:" + "a" * 64,
    )
    assert target.key == ("skill", "deep-research")
    assert target.revision_candidates == frozenset(
        {"v2.4.0", "digest:" + "a" * 64, "a" * 64},
    )


@pytest.mark.asyncio
async def test_matcher_uses_each_members_own_entry_point(harness: object) -> None:
    """A multi-member condition associates the union and compares per member."""
    from app.service.evolution.potential import MatchCondition, MatchTarget, resolve_policy
    from tests.m10_02_potential_support import (
        NOW,
        seed_case,
        seed_event,
        seed_session,
    )

    database = harness.database  # type: ignore[attr-defined]
    matcher = harness.matcher  # type: ignore[attr-defined]
    session_id = "session-multi-entry"
    main_id = await seed_session(database, session_id=session_id, started_at=NOW)
    await seed_event(
        database,
        agent_id=main_id,
        event_index=0,
        kind="skill",
        name="deep-research",
        object_version="v2.0.0",
        object_revision="tag:v2.0.0",
        triggered_at=NOW,
    )
    later = NOW.replace(hour=11)
    await seed_event(
        database,
        agent_id=main_id,
        event_index=1,
        kind="skill",
        name="code-review",
        object_version="v2.0.0",
        object_revision="tag:v2.0.0",
        triggered_at=later,
    )
    await seed_case(
        database,
        case_id="case-before-code-review",
        session_id=session_id,
        object_name="code-review",
        created_at=NOW.replace(hour=10),
    )
    condition = MatchCondition(
        workspace_id="ws-m10-02-a",
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        target_revision="tag:v2.0.0",
        window_start=NOW.replace(hour=0),
        window_end=NOW.replace(hour=23, minute=59),
        targets=(
            MatchTarget("skill", "deep-research", "v2.0.0", "tag:v2.0.0"),
            MatchTarget("skill", "code-review", "v2.0.0", "tag:v2.0.0"),
        ),
    )
    association = await matcher.associated_sessions(condition)
    session = next(item for item in association.sessions if item.session_id == session_id)
    assert {entry.object_name for entry in session.object_entries} == {
        "deep-research",
        "code-review",
    }
    assert session.entry_for("skill", "code-review").triggered_at == later
    match = await matcher.potential_cases(condition, association, resolve_policy(None))
    case = next(item for item in match.cases if item.bad_case_id == "case-before-code-review")
    assert case.object_trigger.triggered_at == later


class _Definitions:
    """Freeze one deterministic definition per member."""

    async def freeze(
        self,
        workspace: str,
        kind: str,
        repo: str,
        sub_dir: str,
        ref: str,
    ) -> dict[str, str]:
        """Return one frozen definition keyed by the member directory."""
        del workspace, repo, ref
        name = sub_dir.rsplit("/", 1)[-1]
        definition = _definition(name)
        definition["path"] = f"{sub_dir}/{'SKILL.md' if kind == 'skill' else 'AGENT.md'}"
        return definition


@pytest.mark.asyncio
async def test_service_freezes_every_member_and_exposes_previews(tmp_path: Path) -> None:
    """Each member keeps its own frozen definition in the response."""
    database = create_database(_settings(tmp_path))
    await database.start()
    await upgrade_database(database)
    service = EvolutionTargetService(
        EvolutionTargetRepository(database),
        _Remote(),  # type: ignore[arg-type]
        _Definitions(),  # type: ignore[arg-type]
        default_package_id="default-attribute-badcases",
    )
    try:
        created = await service.create(_write("deep-research", "writer"), created_by=None)
        assert [member.object_name for member in created.members] == [
            "deep-research",
            "writer",
        ]
        assert created.members[0].definition is not None
        assert created.members[0].definition.path == "skills/deep-research/SKILL.md"
        assert created.members[1].definition is not None
        assert created.members[1].definition.path == "skills/writer/SKILL.md"

        with pytest.raises(Exception) as blank:
            await service.create(_write("deep-research"), created_by=None)
        assert getattr(blank.value, "details", {}).get("field") == "members[0].objectName"

        updated = await service.update(
            created.id,
            EvolutionTargetWrite(
                repo_url="https://git.example.com/agent-skills.git",
                default_ref="v2.4.0",
                validation_project_id="val-skills",
                test_project_id="test-skills",
                primary_metric_key="resolved_rate",
                enabled=False,
                members=[
                    EvolutionTargetMemberWrite(
                        object_type="skill",
                        object_name="writer",
                        sub_dir="skills/writer",
                    ),
                ],
            ),
        )
        assert [member.object_name for member in updated.members] == ["writer"]
        assert updated.enabled is False

        with pytest.raises(Exception) as missing:
            await service.update("missing", _write("writer"))
        assert getattr(missing.value, "status_code", None) == 404

        with pytest.raises(Exception) as disabled:
            await service.enabled_config_by_id(created.id)
        assert getattr(disabled.value, "code", None) == "TARGET_NOT_CONFIGURED"

        versions = await service.versions(created.id)
        assert versions.versions == ["v2.4.0"]
    finally:
        await database.dispose()


def test_patch_allowed_paths_cover_each_member() -> None:
    """The agent edit boundary accepts every member directory."""
    from app.db.models.evolution import EvolutionRunRecord, EvolutionRunTargetRecord
    from app.service.evolution.patch_source import _run_allowed_paths

    run = EvolutionRunRecord(
        id="run",
        title="run",
        mode="full",
        engine_key="full",
        eval_config={},
        target_config_id="target",
        target_type="skill",
        target_name="deep-research",
        target_version="v2.4.0",
        repo_url="https://git.example.com/agent-skills.git",
        sub_dir="skills/deep-research",
        repo_path=None,
        base_ref=None,
        base_commit=None,
        branch_name=None,
        workspace_path=None,
        remote_name="origin",
        push_status="pending",
        pushed_at=None,
        push_error=None,
        window_from=None,
        window_to=None,
        models=[],
        status="running",
        blocked_stage=None,
        retry_attempts=0,
        next_retry_at=None,
        eval_status="pending",
        error_stage=None,
        error_message=None,
        error_at=None,
        progress_unit=0,
        stats={},
        created_by=None,
        created_at=now_shanghai(),
        finished_at=None,
        targets=(
            EvolutionRunTargetRecord(
                id="t1",
                run_id="run",
                seq=0,
                object_type="skill",
                object_name="deep-research",
                target_version="v2.4.0",
                target_revision=None,
                sub_dir="skills/deep-research",
            ),
            EvolutionRunTargetRecord(
                id="t2",
                run_id="run",
                seq=1,
                object_type="agent",
                object_name="writer",
                target_version="v2.4.0",
                target_revision=None,
                sub_dir="agents/writer",
            ),
        ),
    )
    assert _run_allowed_paths(run) == (
        "skills/deep-research/**",
        "agents/writer/**",
    )
