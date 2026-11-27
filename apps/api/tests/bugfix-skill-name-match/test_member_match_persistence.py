"""Member-level name matching persists on targets, run snapshots, and the API shape."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import select

from alembic import command
from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import evolution_target_members, evolution_targets
from app.db.models.evolution import (
    evolution_run_targets,
    evolution_runs,
    record_from_evolution_run_target,
)
from app.service.evolution.targets import (
    EvolutionTargetMemberWrite,
    EvolutionTargetService,
    EvolutionTargetWrite,
)
from app.utils.time import now_shanghai


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
        db_url=f"sqlite+aiosqlite:///{tmp_path / 'member-match.db'}",
    )


class _Remote:
    """Accept every repository and return one deterministic tag list."""

    async def validate(self, repo_url: str, ref: str) -> None:
        """Accept one configured repository and ref."""
        del repo_url, ref

    async def list_tags(self, repo_url: str) -> tuple[str, ...]:
        """Return one stable tag."""
        del repo_url
        return ("v2.4.0",)


def _write(*members: tuple[str, str, bool]) -> EvolutionTargetWrite:
    """Build one configuration write with explicit member switches."""
    return EvolutionTargetWrite(
        repo_url="https://git.example.com/agent-skills.git",
        default_ref="v2.4.0",
        validation_project_id="val-skills",
        test_project_id="test-skills",
        primary_metric_key="resolved_rate",
        enabled=True,
        members=[
            EvolutionTargetMemberWrite(
                object_type=object_type,  # type: ignore[arg-type]
                object_name=name,
                sub_dir=f"{object_type}s/{name}",
                match_by_name=match_by_name,
            )
            for object_type, name, match_by_name in members
        ],
    )


@pytest.mark.asyncio
async def test_migration_defaults_the_switch_to_false(tmp_path: Path) -> None:
    """Revision 0036 adds the column without backfilling any row to true."""
    database = create_database(_settings(tmp_path))
    await database.start()
    try:
        await asyncio.to_thread(command.upgrade, alembic_config(database), "0035")
        now = now_shanghai()
        async with database.transaction() as session:
            await session.execute(
                evolution_targets.insert().values(
                    id="legacy-target",
                    workspace_id="ws-default",
                    object_type="agent",
                    object_name="Explore",
                    repo_url="https://git.example.com/agent-skills.git",
                    sub_dir="agents/Explore",
                    default_ref="v2.4.0",
                    validation_project_id="val",
                    test_project_id="test",
                    primary_metric_key="resolved_rate",
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                ),
            )
            await session.execute(
                evolution_target_members.insert().values(
                    id="legacy-member",
                    workspace_id="ws-default",
                    target_id="legacy-target",
                    seq=0,
                    object_type="agent",
                    object_name="Explore",
                    sub_dir="agents/Explore",
                    created_at=now,
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
                    target_type="agent",
                    target_name="Explore",
                    target_version="v2.4.0",
                    target_revision="digest:" + "a" * 64,
                    repo_url="https://git.example.com/agent-skills.git",
                    sub_dir="agents/Explore",
                    created_at=now,
                ),
            )
            await session.execute(
                evolution_run_targets.insert().values(
                    id="legacy-run-target",
                    run_id="legacy-run",
                    seq=0,
                    object_type="agent",
                    object_name="Explore",
                    target_version="v2.4.0",
                    target_revision="digest:" + "a" * 64,
                    sub_dir="agents/Explore",
                ),
            )

        await upgrade_database(database)

        async with database.session() as session:
            member = (
                (
                    await session.execute(
                        select(evolution_target_members).where(
                            evolution_target_members.c.id == "legacy-member",
                        ),
                    )
                )
                .mappings()
                .one()
            )
            run_target = (
                (
                    await session.execute(
                        select(evolution_run_targets).where(
                            evolution_run_targets.c.id == "legacy-run-target",
                        ),
                    )
                )
                .mappings()
                .one()
            )
        assert member["match_by_name"] is False
        assert run_target["match_by_name"] is False
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_repository_round_trips_each_member_switch(tmp_path: Path) -> None:
    """Every member keeps its own flag through insert, update, and reload."""
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
                "members": [
                    {
                        "object_type": "skill",
                        "object_name": "deep-research",
                        "sub_dir": "skills/deep-research",
                        "match_by_name": True,
                    },
                    {
                        "object_type": "agent",
                        "object_name": "writer",
                        "sub_dir": "agents/writer",
                        "match_by_name": False,
                    },
                ],
            },
        )
        loaded = await repository.get(created.id)
        assert loaded is not None
        assert [member.match_by_name for member in loaded.members] == [True, False]
        assert [member.match_by_name for member in loaded.member_objects] == [True, False]

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
                        "match_by_name": False,
                    },
                    {
                        "object_type": "agent",
                        "object_name": "writer",
                        "sub_dir": "agents/writer",
                        "match_by_name": True,
                    },
                ],
            },
        )
        assert [member.match_by_name for member in updated.members] == [False, True]
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_service_exposes_member_switch_and_forces_knowledge_off(
    tmp_path: Path,
) -> None:
    """The public member model carries the flag; knowledge never opts in."""
    database = create_database(_settings(tmp_path))
    await database.start()
    await upgrade_database(database)
    service = EvolutionTargetService(
        EvolutionTargetRepository(database),
        _Remote(),
    )
    try:
        created = await service.create(
            _write(("skill", "deep-research", True), ("knowledge", "handbook", True)),
            created_by=None,
        )
        assert [(member.object_name, member.match_by_name) for member in created.members] == [
            ("deep-research", True),
            ("handbook", False),
        ]

        legacy_member = await service.create(
            _write(("agent", "Explore", False)),
            created_by=None,
        )
        assert legacy_member.members[0].match_by_name is False
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_run_snapshot_keeps_the_member_switch(tmp_path: Path) -> None:
    """A run freezes the switch it was admitted with and replays the same rows."""
    database = create_database(_settings(tmp_path))
    await database.start()
    await upgrade_database(database)
    repository = EvolutionRepository(database)
    try:
        run = await repository.create_run(
            {
                "title": "mixed members",
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
                        "match_by_name": True,
                    },
                    {
                        "object_type": "agent",
                        "object_name": "writer",
                        "target_version": "v2.4.0",
                        "target_revision": "digest:" + "b" * 64,
                        "sub_dir": "agents/writer",
                        "match_by_name": False,
                    },
                ],
            },
        )
        loaded = await repository.get_run(run.id)
        assert loaded is not None
        assert [item.match_by_name for item in loaded.targets] == [True, False]
    finally:
        await database.dispose()


def test_run_target_record_defaults_the_missing_switch_to_false() -> None:
    """Pre-0036 snapshots read back as hash-matched, never guessed as name mode."""
    record = record_from_evolution_run_target(
        {
            "id": "target",
            "run_id": "run",
            "seq": 0,
            "object_type": "agent",
            "object_name": "Explore",
            "target_version": "v2.4.0",
            "target_revision": None,
            "sub_dir": "agents/Explore",
        },
    )
    assert record.match_by_name is False
