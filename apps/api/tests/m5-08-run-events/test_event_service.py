"""Run event sanitization, state transitions, and resource authorization."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import insert, select

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.run_events import SqlRunEventStore
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import evolution_runs
from app.db.models.run_events import evolution_run_events
from app.errors import AppError
from app.service.events import EventBus
from app.service.evolution.events import (
    EvolutionRunEventService,
    EvolutionRunTopicAuthorizer,
)

NOW = datetime(2026, 10, 28, 8, 0, tzinfo=UTC)


def _run_values(run_id: str, status: str = "running") -> dict[str, object]:
    """Build the complete run row consumed by event writes and authorization."""
    return {
        "id": run_id,
        "title": "event fixture",
        "mode": "full",
        "engine_key": "full",
        "eval_config": {},
        "target_config_id": None,
        "target_type": "skill",
        "target_name": "deep-research",
        "target_version": "v2.0.0",
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "repo_path": None,
        "base_ref": "v2.0.0",
        "base_commit": None,
        "branch_name": f"evo/{run_id}",
        "workspace_path": None,
        "remote_name": "origin",
        "push_status": "pending",
        "pushed_at": None,
        "push_error": None,
        "window_from": None,
        "window_to": None,
        "models": [],
        "status": status,
        "blocked_stage": None,
        "retry_attempts": 0,
        "next_retry_at": None,
        "eval_status": "pending",
        "error_stage": None,
        "error_message": None,
        "error_at": None,
        "progress_unit": 0,
        "stats": {},
        "created_by": None,
        "created_at": NOW,
        "finished_at": None,
    }


@pytest_asyncio.fixture
async def service_environment(
    tmp_path: Path,
) -> AsyncIterator[tuple[Database, EvolutionRunEventService, EventBus]]:
    """Provide a real event service over an isolated migrated database."""
    database = create_database(
        Settings(db_dialect=DatabaseDialect.SQLITE, data_dir=tmp_path),
    )
    await database.start()
    await upgrade_database(database)
    async with database.transaction() as session:
        await session.execute(insert(evolution_runs).values(**_run_values("run-live")))
        await session.execute(
            insert(evolution_runs).values(**_run_values("run-done", status="completed")),
        )
    bus = EventBus(queue_capacity=10)
    repository = EvolutionRepository(database)
    store = SqlRunEventStore(database)
    service = EvolutionRunEventService(store, repository, bus)
    try:
        yield database, service, bus
    finally:
        await bus.close()
        await database.dispose()


async def test_record_redacts_secrets_and_publishes_sanitized_event(
    service_environment: tuple[Database, EvolutionRunEventService, EventBus],
) -> None:
    """Credential values never enter the durable event row or live notification."""
    database, service, bus = service_environment
    subscription = await bus.subscribe(("run:run-live",))
    try:
        event = await service.record(
            "run-live",
            "candidate_committed",
            level="info",
            stage="candidate",
            step_index=4,
            cluster_id="cluster-1",
            message="candidate committed with token=message-secret",
            payload={
                "commit": "abc",
                "authorization": "Bearer header-secret",
                "nested": {"OPENAI_API_KEY": "payload-secret"},
            },
            error=RuntimeError(
                "Authorization: Bearer detail-secret PASSWORD=hunter2 " + "x" * 9000,
            ),
        )
        notification = subscription.queue.get_nowait()
    finally:
        await subscription.close()

    async with database.session() as session:
        row = (
            (
                await session.execute(
                    select(evolution_run_events).where(
                        evolution_run_events.c.run_id == "run-live",
                    ),
                )
            )
            .mappings()
            .one()
        )

    serialized = str(dict(row)) + str(notification.data)
    assert "message-secret" not in serialized
    assert "header-secret" not in serialized
    assert "payload-secret" not in serialized
    assert "detail-secret" not in serialized
    assert "hunter2" not in serialized
    assert "<redacted>" in serialized
    assert event.error is not None
    assert event.error.detail is not None
    assert len(event.error.detail.encode()) <= 8192
    assert row["error_detail"] is not None
    assert len(str(row["error_detail"]).encode()) <= 8192
    assert notification.event == "run.event"
    assert notification.event_id == event.seq


async def test_failed_and_interrupted_events_update_run_state(
    service_environment: tuple[Database, EvolutionRunEventService, EventBus],
) -> None:
    """Job-boundary failures persist both history and terminal run facts."""
    _, service, _ = service_environment

    failed_seq = await service.record_failed(
        "run-live",
        stage="prepare",
        message="prepare crashed token=secret",
        job_id="job-1",
        error=RuntimeError("clone failed"),
    )
    detail = await service.list(
        "run-live",
        after_seq=0,
        limit=100,
        level=None,
    )

    assert failed_seq == 1
    assert [item.event_type for item in detail.items] == ["run_failed"]
    run = await EvolutionRepository(service_environment[0]).get_run("run-live")
    assert run is not None
    assert run.status == "failed"
    assert run.error_stage == "prepare"
    assert run.error_message == "clone failed"


async def test_topic_authorizer_rejects_missing_and_terminal_runs(
    service_environment: tuple[Database, EvolutionRunEventService, EventBus],
) -> None:
    """SSE tickets only target existing runs that are still active."""
    database, _, _ = service_environment
    authorizer = EvolutionRunTopicAuthorizer(EvolutionRepository(database))

    await authorizer.authorize(("run:run-live",), user_id="user-1")
    with pytest.raises(AppError) as terminal:
        await authorizer.authorize(("run:run-done",), user_id="user-1")
    with pytest.raises(AppError) as missing:
        await authorizer.authorize(("run:missing",), user_id="user-1")

    assert terminal.value.code == "TICKET_INVALID"
    assert missing.value.code == "TICKET_INVALID"


async def test_blocked_and_resumed_events_keep_patch_stage_distinct(
    service_environment: tuple[Database, EvolutionRunEventService, EventBus],
) -> None:
    """Patch failures use candidate as event stage and patch as the blocked stage."""
    database, service, _ = service_environment
    repository = EvolutionRepository(database)

    blocked_seq = await service.record_blocked(
        "run-live",
        stage="candidate",
        blocked_stage="patch",
        message="patch failed",
        job_id="job-2",
        error=RuntimeError("invalid patch"),
    )
    blocked = await repository.get_run("run-live")
    resumed_seq = await service.record_resumed(
        "run-live",
        stage="candidate",
        job_id="job-3",
    )
    resumed = await repository.get_run("run-live")

    assert blocked_seq == 1
    assert blocked is not None
    assert blocked.status == "blocked"
    assert blocked.blocked_stage == "patch"
    assert resumed_seq == 2
    assert resumed is not None
    assert resumed.status == "running"
    assert resumed.blocked_stage is None
