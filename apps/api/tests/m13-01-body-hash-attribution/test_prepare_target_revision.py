"""Historical NULL runs resolve once and attribution writes the same digest."""

from __future__ import annotations

import pytest
from sqlalchemy import insert, select

from app.db.crud.evolution import EvolutionRepository
from app.db.models.domain import agent_events, probe_reports
from app.errors import AppError, ErrorCode
from app.service.evolution.target_content import (
    ResolvedTargetVersion,
    target_content_unresolved,
)
from tests.m10_02_potential_support import (
    NOW,
    TARGET_NAME,
    TARGET_VERSION,
    Harness,
    seed_case,
    seed_session,
)
from tests.v2_acceptance_support import prepare_job, prepare_service

BODY_HASH = "d" * 64
"""The digest a successful fake content read returns for both stages."""


class DigestResolver:
    """Resolve every bare version to one deterministic body hash."""

    async def resolve(
        self,
        *,
        object_type: str,
        repo_url: str,
        sub_dir: str,
        version: str,
    ) -> ResolvedTargetVersion:
        """Return the same digest prepare must persist for attribution."""
        del object_type, repo_url, sub_dir
        return ResolvedTargetVersion(version, f"digest:{BODY_HASH}")


class FailingResolver:
    """Report content-unresolved for every bare version."""

    async def resolve(
        self,
        *,
        object_type: str,
        repo_url: str,
        sub_dir: str,
        version: str,
    ) -> ResolvedTargetVersion:
        """Raise the stable 422 before any association or write."""
        del repo_url, sub_dir, version
        raise target_content_unresolved(
            object_type=object_type,
            reason="content_not_found",
        )


async def _seed_body_hash_session(harness: Harness, session_id: str) -> None:
    """Seed one Session whose only identity is the body hash."""
    main_id = await seed_session(harness.database, session_id=session_id, started_at=NOW)
    async with harness.database.transaction() as session:
        await session.execute(
            insert(agent_events).values(
                agent_id=main_id,
                event_index=0,
                line_no=1,
                message_offset=0,
                kind="skill",
                name=TARGET_NAME,
                definition_hash=BODY_HASH,
                triggered_at=NOW,
            ),
        )
    await seed_case(
        harness.database,
        case_id=f"case-{session_id}",
        session_id=session_id,
        case_type="self",
        object_name=TARGET_NAME,
        created_at=NOW,
    )


async def _create_null_run(harness: Harness, run_id: str) -> None:
    """Create a cluster-only run snapshot with an unresolved historical revision."""
    await EvolutionRepository(harness.database).create_run(
        {
            "id": run_id,
            "title": f"{TARGET_NAME} {TARGET_VERSION} 自进化",
            "workspace_id": "ws-m10-02-a",
            "mode": "cluster_only",
            "engine_key": "cluster_only",
            "eval_config": {},
            "potential_policy": {"preset": "default"},
            "cache_enabled": False,
            "attribution_engine": "rule-v1",
            "target_config_id": None,
            "target_type": "skill",
            "target_name": TARGET_NAME,
            "target_version": TARGET_VERSION,
            "target_revision": None,
            "repo_url": "https://example.invalid/repo.git",
            "sub_dir": "skills/deep-research",
            "validation_project_id": "validation",
            "test_project_id": "test",
            "window_from": NOW.date(),
            "window_to": NOW.date(),
            "models": [],
            "status": "preparing",
            "progress_unit": 0,
            "stats": {},
        },
    )


async def test_prepare_persists_the_resolved_revision_for_attribution(harness: Harness) -> None:
    """A successful prepare writes target_revision before attribution runs."""
    run_id = "run-m13-null-revision"
    session_id = "session-m13-null-revision"
    await _seed_body_hash_session(harness, session_id)
    await _create_null_run(harness, run_id)

    await prepare_service(harness.database, resolver=DigestResolver()).handle(
        prepare_job(run_id),
    )

    restored = await EvolutionRepository(harness.database).get_run(run_id)
    assert restored is not None
    assert restored.target_revision == f"digest:{BODY_HASH}"
    async with harness.database.session() as session:
        probes = (await session.execute(select(probe_reports))).mappings().all()
    assert [row["object_version"] for row in probes] == [f"digest:{BODY_HASH}"]


async def test_prepare_failure_keeps_the_revision_null(harness: Harness) -> None:
    """Content-unresolved fails before any write and keeps the historical NULL."""
    run_id = "run-m13-null-failure"
    await _create_null_run(harness, run_id)

    with pytest.raises(AppError) as error:
        await prepare_service(harness.database, resolver=FailingResolver()).handle(
            prepare_job(run_id),
        )

    assert error.value.code is ErrorCode.TARGET_CONTENT_UNRESOLVED
    restored = await EvolutionRepository(harness.database).get_run(run_id)
    assert restored is not None
    assert restored.target_revision is None
    async with harness.database.session() as session:
        probes = (await session.execute(select(probe_reports))).mappings().all()
    assert probes == []
