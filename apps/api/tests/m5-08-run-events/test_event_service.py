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
from app.db.crud.jobs import JobRepository
from app.db.crud.run_events import SqlRunEventStore
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.evolution import evolution_runs
from app.db.models.run_events import evolution_run_events
from app.errors import AppError
from app.service.events import EventBus
from app.service.evolution.engine.contracts import RunBlocked
from app.service.evolution.events import (
    EvolutionRunEventService,
    EvolutionRunTopicAuthorizer,
)
from app.service.jobs import JobRunner

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
            message=(
                "candidate committed token=message-secret "
                "HE_DATABASE_URL=postgres://alice:env-secret@db/app "
                "password_hash=hash-secret secret_key=key-secret "
                "Authorization: Basic dXNlcjpwYXNz "
                "https://alice:url-secret@example.com/repo.git "
                "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE "
                "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY "
                "sk-proj-live-secret "
                "ghp_1234567890abcdefghijklmnopqrstuvwxyz "
                "AWS Secret Access Key: spaced-aws-service-secret "
                "API key: spaced-api-service-secret "
                "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvcGVyYXRvciJ9"
                ".c2lnbmF0dXJlLXZhbHVl "
                "-----BEGIN PRIVATE KEY-----\n"
                "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ\n"
                "-----END PRIVATE KEY-----"
            ),
            payload={
                "commit": "abc",
                "authorization": "Bearer header-secret",
                "nested": {"OPENAI_API_KEY": "payload-secret"},
                "HE_DATABASE_URL": "postgres://alice:payload-env-secret@db/app",
                "url": "https://alice:payload-url-secret@example.com/repo.git",
                "document": '{"password_hash":"json-hash-secret"}',
                "client_secret": "client-secret",
                "AWS_ACCESS_KEY_ID": "ASIAIOSFODNN7EXAMPLE",
                "AWS_SECRET_ACCESS_KEY": "payload-aws-secret",
                "note": "provider sk-proj-payload-secret ghp_payload1234567890abcdef",
            },
            error=RuntimeError(
                "Authorization: Bearer detail-secret "
                "password_hash=detail-hash-secret "
                "secret_key=detail-key-secret "
                "Authorization: Basic ZGV0YWlsOnNlY3JldA== "
                "postgres://alice:detail-url-secret@db/app " + "x" * 9000
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

    serialized = str(dict(row)) + str(event.model_dump(mode="json")) + str(notification.data)
    assert "message-secret" not in serialized
    assert "header-secret" not in serialized
    assert "payload-secret" not in serialized
    assert "detail-secret" not in serialized
    assert "env-secret" not in serialized
    assert "hash-secret" not in serialized
    assert "key-secret" not in serialized
    assert "dXNlcjpwYXNz" not in serialized
    assert "url-secret" not in serialized
    assert "payload-env-secret" not in serialized
    assert "payload-url-secret" not in serialized
    assert "json-hash-secret" not in serialized
    assert "client-secret" not in serialized
    assert "detail-hash-secret" not in serialized
    assert "detail-key-secret" not in serialized
    assert "ZGV0YWlsOnNlY3JldA==" not in serialized
    assert "detail-url-secret" not in serialized
    assert "AKIAIOSFODNN7EXAMPLE" not in serialized
    assert "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY" not in serialized
    assert "sk-proj-live-secret" not in serialized
    assert "ghp_1234567890abcdefghijklmnopqrstuvwxyz" not in serialized
    assert "spaced-aws-service-secret" not in serialized
    assert "spaced-api-service-secret" not in serialized
    assert "eyJhbGciOiJIUzI1NiJ9" not in serialized
    assert "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ" not in serialized
    assert "ASIAIOSFODNN7EXAMPLE" not in serialized
    assert "payload-aws-secret" not in serialized
    assert "sk-proj-payload-secret" not in serialized
    assert "ghp_payload1234567890abcdef" not in serialized
    assert "<redacted>" in serialized
    assert event.error is not None
    assert event.error.detail is not None
    assert len(event.error.detail.encode()) <= 8192
    assert row["error_detail"] is not None
    assert len(str(row["error_detail"]).encode()) <= 8192
    assert notification.event == "run.event"
    assert notification.event_id == event.seq
    assert notification.data["runId"] == "run-live"


async def test_interrupted_run_state_and_event_share_full_redaction(
    service_environment: tuple[Database, EvolutionRunEventService, EventBus],
) -> None:
    """The interrupted run row cannot bypass the event sanitizer."""
    database, service, bus = service_environment
    subscription = await bus.subscribe(("run:run-live",))
    try:
        await service.record_interrupted(
            run_id="run-live",
            stage="prepare",
            message=(
                "HE_DATABASE_URL=postgres://alice:interrupted-env@db/app "
                "password_hash=interrupted-hash secret_key=interrupted-key "
                "Authorization: Basic aW50ZXJydXB0ZWQ6c2VjcmV0 "
                "AWS_ACCESS_KEY_ID=ASIAIOSFODNN7EXAMPLE "
                "AWS_SECRET_ACCESS_KEY=interrupted-aws-secret "
                "sk-proj-interrupted-openai-secret "
                "Password Hash: interrupted-spaced-secret"
            ),
            job_id="job-interrupted",
        )
        notification = subscription.queue.get_nowait()
    finally:
        await subscription.close()

    run = await EvolutionRepository(database).get_run("run-live")
    async with database.session() as session:
        event_row = (
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

    assert run is not None
    serialized = str(run) + str(dict(event_row)) + str(notification.data)
    for secret in (
        "interrupted-env",
        "interrupted-hash",
        "interrupted-key",
        "aW50ZXJydXB0ZWQ6c2VjcmV0",
        "ASIAIOSFODNN7EXAMPLE",
        "interrupted-aws-secret",
        "sk-proj-interrupted-openai-secret",
        "interrupted-spaced-secret",
    ):
        assert secret not in serialized


async def test_failed_and_interrupted_events_update_run_state(
    service_environment: tuple[Database, EvolutionRunEventService, EventBus],
) -> None:
    """Job-boundary failures persist both history and terminal run facts."""
    _, service, bus = service_environment
    subscription = await bus.subscribe(("run:run-live",))
    try:
        failed_seq = await service.record_failed(
            "run-live",
            stage="prepare",
            message="prepare crashed token=secret",
            job_id="job-1",
            error=RuntimeError("clone failed"),
        )
        event_notification = subscription.queue.get_nowait()
        failed_notification = subscription.queue.get_nowait()
    finally:
        await subscription.close()
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
    assert event_notification.event == "run.event"
    assert failed_notification.event == "run.failed"
    assert failed_notification.data == {
        "runId": "run-live",
        "stage": "prepare",
        "message": "prepare crashed token=<redacted>",
        "eventSeq": failed_seq,
    }


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
    database, service, bus = service_environment
    repository = EvolutionRepository(database)
    subscription = await bus.subscribe(("run:run-live",))

    try:
        blocked_seq = await service.record_blocked(
            "run-live",
            stage="candidate",
            blocked_stage="patch",
            message="patch failed",
            job_id="job-2",
            retry_attempts=2,
            error=RuntimeError("invalid patch"),
        )
        blocked_event_notification = subscription.queue.get_nowait()
        blocked_notification = subscription.queue.get_nowait()
    finally:
        await subscription.close()
    blocked = await repository.get_run("run-live")
    resumed_subscription = await bus.subscribe(("run:run-live",))
    try:
        resumed_seq = await service.record_resumed(
            "run-live",
            stage="candidate",
            job_id="job-3",
        )
        resumed_event_notification = resumed_subscription.queue.get_nowait()
        resumed_notification = resumed_subscription.queue.get_nowait()
    finally:
        await resumed_subscription.close()
    resumed = await repository.get_run("run-live")

    assert blocked_seq == 1
    assert blocked is not None
    assert blocked.status == "blocked"
    assert blocked.blocked_stage == "patch"
    assert blocked.retry_attempts == 2
    assert blocked_event_notification.event == "run.event"
    assert blocked_notification.event == "run.blocked"
    assert blocked_notification.data == {
        "runId": "run-live",
        "stage": "candidate",
        "blockedStage": "patch",
        "retryAttempts": 2,
        "nextRetryAt": None,
        "message": "patch failed",
    }
    assert resumed_seq == 2
    assert resumed is not None
    assert resumed.status == "running"
    assert resumed.blocked_stage is None
    assert resumed_event_notification.event == "run.event"
    assert resumed_notification.event == "run.resumed"
    assert resumed_notification.data == {
        "runId": "run-live",
        "stage": "candidate",
        "retryAttempts": 2,
    }


async def test_blocked_event_persists_original_error_stage(
    service_environment: tuple[Database, EvolutionRunEventService, EventBus],
) -> None:
    """Patch blocking preserves commit as the concrete recovery stage."""
    database, service, _ = service_environment
    repository = EvolutionRepository(database)

    await service.record_blocked(
        "run-live",
        stage="candidate",
        blocked_stage="patch",
        message="commit timed out",
        error=RunBlocked(
            "commit timed out",
            stage="patch",
            error_stage="commit",
        ),
    )

    run = await repository.get_run("run-live")
    assert run is not None
    assert run.blocked_stage == "patch"
    assert run.error_stage == "commit"


async def test_eval_block_resume_restores_pending_evaluation_state(
    service_environment: tuple[Database, EvolutionRunEventService, EventBus],
) -> None:
    """A resumed evaluation is no longer presented as failed."""
    database, service, _ = service_environment
    repository = EvolutionRepository(database)

    await service.record_blocked(
        "run-live",
        stage="eval",
        blocked_stage="eval",
        message="evaluation timed out",
        job_id="job-eval-1",
        retry_attempts=1,
        error=RuntimeError("evaluation timed out"),
    )
    blocked = await repository.get_run("run-live")
    await service.record_resumed(
        "run-live",
        stage="eval",
        job_id="job-eval-2",
    )
    resumed = await repository.get_run("run-live")

    assert blocked is not None
    assert blocked.status == "blocked"
    assert blocked.eval_status == "failed"
    assert resumed is not None
    assert resumed.status == "running"
    assert resumed.blocked_stage is None
    assert resumed.eval_status == "pending"


async def test_job_runner_records_retryable_failure_as_blocked(
    service_environment: tuple[Database, EvolutionRunEventService, EventBus],
) -> None:
    """RunBlocked leaves the run blocked and never writes run_failed."""
    database, service, bus = service_environment
    jobs = JobRepository(database)
    runner = JobRunner(jobs, bus, run_events=service)

    async def block(_job: object) -> None:
        raise RunBlocked(
            "push timed out",
            stage="push",
            next_retry_at=NOW,
            retry_attempts=3,
        )

    runner.register_handler("evolution_advance", block)
    await runner.start()
    subscription = await bus.subscribe(("run:run-live",))
    try:
        submitted = await runner.submit(
            kind="evolution_advance",
            payload={},
            ref_id="run-live",
            created_by=None,
        )
        terminal = await runner.wait(submitted.id)
        notifications = [subscription.queue.get_nowait() for _ in range(2)]
    finally:
        await runner.close()
        await subscription.close()

    run = await EvolutionRepository(database).get_run("run-live")
    detail = await service.list(
        "run-live",
        after_seq=0,
        limit=100,
        level=None,
    )

    assert terminal.status == "failed"
    assert run is not None
    assert run.status == "blocked"
    assert run.blocked_stage == "push"
    assert run.retry_attempts == 3
    assert [item.event_type for item in detail.items] == ["run_blocked"]
    assert [item.event for item in notifications] == ["run.event", "run.blocked"]
    assert notifications[1].data["stage"] == "push"
    assert notifications[1].data["retryAttempts"] == 3


async def test_job_runner_records_fatal_failure_as_failed(
    service_environment: tuple[Database, EvolutionRunEventService, EventBus],
) -> None:
    """Ordinary exceptions remain terminal run_failed events."""
    database, service, bus = service_environment
    jobs = JobRepository(database)
    runner = JobRunner(jobs, bus, run_events=service)

    async def fail(_job: object) -> None:
        raise RuntimeError("fatal candidate failure")

    runner.register_handler("evolution_advance", fail)
    await runner.start()
    subscription = await bus.subscribe(("run:run-live",))
    try:
        submitted = await runner.submit(
            kind="evolution_advance",
            payload={},
            ref_id="run-live",
            created_by=None,
        )
        terminal = await runner.wait(submitted.id)
        notifications = [subscription.queue.get_nowait() for _ in range(2)]
    finally:
        await runner.close()
        await subscription.close()

    run = await EvolutionRepository(database).get_run("run-live")
    detail = await service.list(
        "run-live",
        after_seq=0,
        limit=100,
        level=None,
    )

    assert terminal.status == "failed"
    assert run is not None
    assert run.status == "failed"
    assert [item.event_type for item in detail.items] == ["run_failed"]
    assert [item.event for item in notifications] == ["run.event", "run.failed"]
