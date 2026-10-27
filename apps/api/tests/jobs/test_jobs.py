"""Job persistence, serial execution, recovery, and HTTP status behavior."""

import asyncio
from pathlib import Path
from typing import ClassVar, cast

import httpx
import pytest
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.jobs import JobRepository
from app.db.models.jobs import JobRunRecord
from app.errors import AppError, ErrorCode
from app.main import create_app
from app.service.events import EventBus
from app.service.evolution.engine.contracts import EvolutionBlockedStage, RunBlocked
from app.service.identity.tokens import TokenService
from app.service.jobs import JobRunner

JobEnvironment = tuple[Database, JobRepository, EventBus, JobRunner]


async def test_repository_round_trip_preserves_audit_fields(
    job_environment: JobEnvironment,
) -> None:
    """Queued jobs persist payload, creator, timestamps, and default progress."""
    _, repository, _, _ = job_environment
    job = await repository.insert(
        kind="sync",
        payload={"source": "manual"},
        ref_id="sync-1",
        created_by=None,
    )

    loaded = await repository.get(job.id)

    assert loaded is not None
    assert loaded.kind == "sync"
    assert loaded.ref_id == "sync-1"
    assert loaded.payload == {"source": "manual"}
    assert loaded.created_by is None
    assert loaded.status == "queued"
    assert loaded.progress == 0
    assert loaded.attempt == 0
    offset = loaded.created_at.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 8 * 60 * 60


async def test_submit_returns_before_handler_completion_and_runs_serially(
    job_environment: JobEnvironment,
) -> None:
    """The queue returns immediately while a single global lock serializes handlers."""
    _, _, _, runner = job_environment
    release = asyncio.Event()
    first_started = asyncio.Event()
    active = 0
    max_active = 0
    order: list[str] = []

    async def slow(job: JobRunRecord) -> dict[str, object]:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        order.append(job.id)
        first_started.set()
        await release.wait()
        active -= 1
        return {"ok": True}

    adapter = runner
    adapter.register_handler("sync", slow)
    await adapter.start()

    first = await adapter.submit(kind="sync", payload={}, ref_id="a", created_by=None)
    await asyncio.wait_for(first_started.wait(), timeout=1)
    second = await adapter.submit(kind="sync", payload={}, ref_id="b", created_by=None)

    release.set()
    await asyncio.wait_for(adapter.wait(first.id), timeout=1)
    await asyncio.wait_for(adapter.wait(second.id), timeout=1)

    assert max_active == 1
    assert order == [first.id, second.id]
    assert (await adapter.get(first.id)).result == {"ok": True}
    assert (await adapter.get(second.id)).status == "completed"


async def test_duplicate_policy_reuses_retryable_and_rejects_stage_jobs(
    job_environment: JobEnvironment,
) -> None:
    """Only sync/retry reuse an active job; evolution stages fail with RUN_BUSY."""
    _, _, _, runner = job_environment
    gate = asyncio.Event()

    async def hold(_job: JobRunRecord) -> None:
        await gate.wait()

    adapter = runner
    adapter.register_handler("sync", hold)
    adapter.register_handler("evolution_retry", hold)
    adapter.register_handler("evolution_prepare", hold)
    await adapter.start()

    existing = await adapter.submit(kind="sync", payload={"v": 1}, ref_id="same", created_by=None)
    reused = await adapter.submit(kind="sync", payload={"v": 2}, ref_id="same", created_by=None)
    retry = await adapter.submit(
        kind="evolution_retry",
        payload={},
        ref_id="run-1",
        created_by=None,
    )
    retry_reused = await adapter.submit(
        kind="evolution_retry",
        payload={},
        ref_id="run-1",
        created_by=None,
    )
    prepare = await adapter.submit(
        kind="evolution_prepare",
        payload={},
        ref_id="run-2",
        created_by=None,
    )

    with pytest.raises(AppError) as conflict:
        await adapter.submit(
            kind="evolution_prepare",
            payload={},
            ref_id="run-2",
            created_by=None,
        )

    gate.set()
    for job_id in (existing.id, retry.id, prepare.id):
        await adapter.wait(job_id)
    assert reused.id == existing.id
    assert reused.reused is True
    assert retry_reused.id == retry.id
    assert retry_reused.reused is True
    assert conflict.value.code == ErrorCode.RUN_BUSY


async def test_evolution_stages_conflict_across_job_kinds(
    job_environment: JobEnvironment,
) -> None:
    """A run may have only one active stage even when the stage kind changes."""
    _, _, _, runner = job_environment
    gate = asyncio.Event()

    async def hold(_job: JobRunRecord) -> None:
        await gate.wait()

    for kind in (
        "evolution_prepare",
        "evolution_advance",
        "evolution_apply",
        "evolution_retry",
    ):
        runner.register_handler(kind, hold)
    await runner.start()

    prepare = await runner.submit(
        kind="evolution_prepare",
        payload={},
        ref_id="run-shared",
        created_by=None,
    )
    for kind in ("evolution_advance", "evolution_apply", "evolution_retry"):
        with pytest.raises(AppError) as conflict:
            await runner.submit(
                kind=kind,
                payload={},
                ref_id="run-shared",
                created_by=None,
            )
        assert conflict.value.code == ErrorCode.RUN_BUSY
        assert conflict.value.details["jobId"] == prepare.id

    gate.set()
    await runner.wait(prepare.id)


async def test_failure_is_bounded_and_redacts_secret_material(
    job_environment: JobEnvironment,
) -> None:
    """Failed jobs retain a sanitized diagnostic without secrets or payload dumps."""
    _, _, _, runner = job_environment

    async def fail(_job: JobRunRecord) -> None:
        raise RuntimeError(
            "password=super-secret token=bearer-secret " + "internal detail " * 300,
        )

    adapter = runner
    adapter.register_handler("sync", fail)
    await adapter.start()
    submitted = await adapter.submit(
        kind="sync",
        payload={"password": "payload-secret"},
        ref_id="sync-fail",
        created_by=None,
    )
    completed = await adapter.wait(submitted.id)

    assert completed.status == "failed"
    assert completed.finished_at is not None
    assert completed.error is not None
    assert len(completed.error) <= 2_000
    assert "super-secret" not in completed.error
    assert "bearer-secret" not in completed.error
    assert "payload-secret" not in completed.error


async def test_evolution_failure_is_written_to_durable_run_history(
    job_environment: JobEnvironment,
) -> None:
    """Uncaught evolution-stage failures cross the job boundary as run_failed."""
    _, repository, bus, _ = job_environment

    class RecordingRunEvents:
        """Capture terminal failure writes requested by the runner."""

        calls: ClassVar[list[tuple[str, str, str, str]]] = []

        async def record_interrupted(
            self,
            *,
            run_id: str,
            stage: str,
            message: str,
            job_id: str,
        ) -> int:
            """Keep the recorder protocol complete without using this path."""
            del run_id, stage, message
            return int(job_id == "") or 1

        async def record_failed(
            self,
            run_id: str,
            *,
            stage: str,
            message: str,
            job_id: str,
            error: BaseException,
            error_detail: str | None = None,
        ) -> int:
            """Record the stage failure and its actual exception."""
            del error_detail
            self.calls.append((run_id, stage, message, type(error).__name__))
            return 9

    recorder = RecordingRunEvents()
    runner = JobRunner(repository, bus, run_events=recorder)

    async def fail(_job: JobRunRecord) -> None:
        raise RuntimeError("candidate generation failed")

    runner.register_handler("evolution_advance", fail)
    await runner.start()
    submitted = await runner.submit(
        kind="evolution_advance",
        payload={},
        ref_id="run-failed",
        created_by=None,
    )
    await runner.wait(submitted.id)

    assert recorder.calls == [
        ("run-failed", "step", "任务执行失败", "RuntimeError"),
    ]


@pytest.mark.parametrize(
    ("blocked_stage", "event_stage"),
    [("patch", "candidate"), ("push", "push"), ("eval", "eval")],
)
async def test_evolution_blocked_is_not_written_as_run_failure(
    job_environment: JobEnvironment,
    blocked_stage: str,
    event_stage: str,
) -> None:
    """Retryable external failures cross the job boundary as run_blocked."""
    _, repository, bus, _ = job_environment

    class RecordingRunEvents:
        """Capture blocked and failed boundary calls separately."""

        blocked: ClassVar[list[tuple[str, str, str, int]]] = []
        failed: ClassVar[list[str]] = []

        async def record_interrupted(
            self,
            *,
            run_id: str,
            stage: str,
            message: str,
            job_id: str,
        ) -> int:
            """Keep the recorder protocol complete without using this path."""
            del run_id, stage, message, job_id
            return 1

        async def record_blocked(
            self,
            run_id: str,
            *,
            stage: str,
            blocked_stage: str,
            message: str,
            job_id: str,
            next_retry_at: object,
            retry_attempts: int,
            error: BaseException,
        ) -> int:
            """Record the retryable stage boundary."""
            del message, job_id, next_retry_at, error
            self.blocked.append((run_id, stage, blocked_stage, retry_attempts))
            return 11

        async def record_failed(self, *_args: object, **_kwargs: object) -> int:
            """Fail the test if a blocked error is reclassified."""
            self.failed.append("called")
            return 12

    recorder = RecordingRunEvents()
    runner = JobRunner(repository, bus, run_events=recorder)

    async def block(_job: JobRunRecord) -> None:
        raise RunBlocked(
            f"{blocked_stage} timed out",
            stage=cast(EvolutionBlockedStage, blocked_stage),
            retry_attempts=1,
        )

    runner.register_handler("evolution_advance", block)
    await runner.start()
    submitted = await runner.submit(
        kind="evolution_advance",
        payload={},
        ref_id="run-blocked",
        created_by=None,
    )
    terminal = await runner.wait(submitted.id)

    assert terminal.status == "failed"
    assert terminal.error == f"{blocked_stage} timed out"
    assert recorder.blocked == [("run-blocked", event_stage, blocked_stage, 1)]
    assert recorder.failed == []


async def test_progress_is_persisted_and_published_to_the_run_topic(
    job_environment: JobEnvironment,
) -> None:
    """Handlers can advance durable progress and notify the run page without blocking."""
    _, _, bus, runner = job_environment
    subscription = await bus.subscribe(("run:progress",))

    async def progress(job: JobRunRecord) -> None:
        await runner.update_progress(job.id, 0.42)

    runner.register_handler("evolution_advance", progress)
    await runner.start()
    submitted = await runner.submit(
        kind="evolution_advance",
        payload={},
        ref_id="progress",
        created_by=None,
    )
    completed = await runner.wait(submitted.id)
    notification = subscription.queue.get_nowait()
    await subscription.close()

    assert completed.status == "completed"
    assert completed.progress == 1.0
    assert notification.event == "run.progress"
    assert notification.event_id is None
    assert notification.data == {
        "runId": "progress",
        "unit": None,
        "total": None,
        "percent": 42,
        "status": "running",
        "stageLabel": None,
        "doneRounds": 0,
        "accepted": 0,
    }


async def test_sync_progress_is_persisted_without_an_sse_notification(
    job_environment: JobEnvironment,
) -> None:
    """Sync tracks progress through REST and never publishes an event topic."""
    _, repository, bus, runner = job_environment
    subscription = await bus.subscribe(("run:sync-progress",))
    job = await repository.insert(
        kind="sync",
        payload={"source": "manual"},
        ref_id="sync-progress",
        created_by=None,
    )

    updated = await runner.update_progress(job.id, 0.5, unit="payloads", total=2)
    assert subscription.queue.empty()
    await subscription.close()
    assert updated.progress == 0.5


async def test_submit_redacts_secret_payload_fields_before_persistence(
    job_environment: JobEnvironment,
) -> None:
    """Durable job payloads cannot retain credentials or nested secrets."""
    _, _, _, runner = job_environment
    observed: dict[str, object] = {}

    async def inspect(job: JobRunRecord) -> None:
        observed.update(job.payload)

    runner.register_handler("pull", inspect)
    await runner.start()
    submitted = await runner.submit(
        kind="pull",
        payload={
            "source": "upstream",
            "password": "plain-secret",
            "nested": {"apiKey": "nested-secret", "safe": "visible"},
        },
        ref_id=None,
        created_by=None,
    )
    await runner.wait(submitted.id)

    assert observed == {
        "source": "upstream",
        "password": "<redacted>",
        "nested": {"apiKey": "<redacted>", "safe": "visible"},
    }


async def test_restart_marks_running_interrupted_and_requeues_sync(
    job_environment: JobEnvironment,
) -> None:
    """Recovery preserves the interrupted audit row and only retries sync work."""
    _, repository, _, runner = job_environment
    recovered_sync = await repository.insert(
        kind="sync",
        payload={"source": "recovery"},
        ref_id="sync-recover",
        created_by=None,
    )
    recovered_stage = await repository.insert(
        kind="evolution_prepare",
        payload={"run": "run-1"},
        ref_id="run-1",
        created_by=None,
    )
    await repository.claim(recovered_sync.id)
    await repository.claim(recovered_stage.id)

    async def complete(_job: JobRunRecord) -> None:
        return None

    adapter = runner
    adapter.register_handler("sync", complete)
    await adapter.start()
    replacement = await repository.find_active_kind("sync")
    assert replacement is not None
    assert replacement.ref_id != "sync-recover"
    await adapter.wait(replacement.id)

    sync_original = await adapter.get(recovered_sync.id)
    stage_original = await adapter.get(recovered_stage.id)
    sync_retry = await adapter.get(replacement.id)
    assert sync_original.status == "interrupted"
    assert stage_original.status == "interrupted"
    assert sync_retry.status == "completed"


async def test_restart_persists_interrupted_event_before_publishing(
    job_environment: JobEnvironment,
) -> None:
    """Recovery records a durable run event and publishes its persisted sequence."""
    _, repository, bus, _ = job_environment
    interrupted = await repository.insert(
        kind="evolution_prepare",
        payload={},
        ref_id="run-recovered",
        created_by=None,
    )
    await repository.claim(interrupted.id)

    class RecordingRunEvents:
        """Capture the recovery write requested by the job runner."""

        calls: ClassVar[list[tuple[str, str, str, str]]] = []

        async def record_interrupted(
            self,
            *,
            run_id: str,
            stage: str,
            message: str,
            job_id: str,
        ) -> int:
            """Return the durable sequence assigned by the persisted event."""
            self.calls.append((run_id, stage, message, job_id))
            return 41

    recorder = RecordingRunEvents()
    runner = JobRunner(repository, bus, run_events=recorder)
    subscription = await bus.subscribe(("run:run-recovered",))
    try:
        await runner.start()
        notification = subscription.queue.get_nowait()
    finally:
        await runner.close()
        await subscription.close()

    assert recorder.calls == [
        (
            "run-recovered",
            "prepare",
            "job interrupted by process restart",
            interrupted.id,
        ),
    ]
    assert notification.event == "run.interrupted"
    assert notification.event_id == 41
    assert notification.data["eventSeq"] == 41


async def test_shutdown_persists_the_same_interruption_history(
    job_environment: JobEnvironment,
) -> None:
    """Graceful shutdown records the run event before publishing it."""
    _, repository, bus, _ = job_environment
    started = asyncio.Event()

    async def wait_forever(_job: JobRunRecord) -> None:
        started.set()
        await asyncio.Event().wait()

    class RecordingRunEvents:
        """Capture shutdown interruption writes."""

        calls: ClassVar[list[tuple[str, str, str, str]]] = []

        async def record_interrupted(
            self,
            *,
            run_id: str,
            stage: str,
            message: str,
            job_id: str,
        ) -> int:
            """Return a durable sequence for the published interruption."""
            self.calls.append((run_id, stage, message, job_id))
            return 52

    recorder = RecordingRunEvents()
    runner = JobRunner(repository, bus, run_events=recorder)
    runner.register_handler("evolution_advance", wait_forever)
    subscription = await bus.subscribe(("run:run-shutdown",))
    job = await repository.insert(
        kind="evolution_advance",
        payload={},
        ref_id="run-shutdown",
        created_by=None,
    )
    try:
        await runner.start()
        await asyncio.wait_for(started.wait(), timeout=1)
        await runner.close()
        notification = subscription.queue.get_nowait()
    finally:
        await subscription.close()

    interrupted_job = await repository.get(job.id)
    assert interrupted_job is not None
    assert interrupted_job.status == "interrupted"
    assert recorder.calls == [
        (
            "run-shutdown",
            "step",
            "job interrupted during shutdown",
            job.id,
        ),
    ]
    assert notification.event == "run.interrupted"
    assert notification.event_id == 52


async def test_start_resumes_jobs_persisted_as_queued(
    job_environment: JobEnvironment,
) -> None:
    """A graceful shutdown leaves queued rows schedulable on the next startup."""
    _, repository, _, runner = job_environment
    queued = await repository.insert(
        kind="pull",
        payload={},
        ref_id=None,
        created_by=None,
    )

    async def complete(_job: JobRunRecord) -> dict[str, object]:
        return {"resumed": True}

    runner.register_handler("pull", complete)
    await runner.start()
    completed = await runner.wait(queued.id)

    assert completed.status == "completed"
    assert completed.result == {"resumed": True}


async def test_shutdown_cancels_active_work_and_marks_it_interrupted(
    job_environment: JobEnvironment,
) -> None:
    """Closing the application cancels handlers and leaves no running audit row."""
    _, _, bus, runner = job_environment
    started = asyncio.Event()

    async def wait_forever(_job: JobRunRecord) -> None:
        started.set()
        await asyncio.Event().wait()

    adapter = runner
    adapter.register_handler("sync", wait_forever)
    await adapter.start()
    job = await adapter.submit(kind="sync", payload={}, ref_id="cancel", created_by=None)
    await asyncio.wait_for(started.wait(), timeout=1)

    await adapter.close()

    assert (await adapter.get(job.id)).status == "interrupted"
    assert bus.subscriber_count == 0


async def test_job_status_endpoint_uses_camel_case_and_stable_not_found(
    tmp_path: Path,
) -> None:
    """Clients can read the database source of truth through the protected API."""
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("job-api-test-signing-secret-with-enough-bytes"),
    )
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    token = TokenService(settings).create_access_token(
        user_id="user-1",
        role="member",
        must_change_password=False,
    )
    headers = {"Authorization": f"Bearer {token}"}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        existing = await app.state.jobs.repository.insert(
            kind="sync",
            payload={},
            ref_id="sync-http",
            created_by=None,
        )
        found = await client.get(f"/api/jobs/{existing.id}", headers=headers)
        missing = await client.get("/api/jobs/missing", headers=headers)

    assert found.status_code == 200
    assert found.json()["jobId"] == existing.id
    assert found.json()["refId"] == "sync-http"
    assert found.json()["createdBy"] is None
    assert found.json()["progress"] == 0
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"


async def test_sanitizer_handles_empty_and_control_characters() -> None:
    """Sanitization is deterministic for empty messages and line breaks."""
    from app.service.jobs import sanitize_job_error

    assert sanitize_job_error("") == "job failed"
    value = sanitize_job_error("first\nsecond\tpassword=secret")
    assert "\n" not in value
    assert "\t" not in value
    assert "secret" not in value
