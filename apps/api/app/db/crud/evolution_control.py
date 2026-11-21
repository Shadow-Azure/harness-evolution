"""Transactional admission and pause control for evolution jobs."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from sqlalchemy import insert, select, update
from sqlalchemy.engine import ScalarResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.crud.evolution_lock import lock_run_row
from app.db.crud.jobs import ACTIVE_JOB_STATUSES, EVOLUTION_JOB_KINDS, queued_job_values
from app.db.crud.run_events import insert_run_event, next_run_event_sequence
from app.db.models.evolution import (
    EvolutionRunRecord,
    evolution_rounds,
    evolution_runs,
    record_from_evolution_run,
)
from app.db.models.jobs import job_runs
from app.db.models.run_events import RunEventRecord
from app.errors import AppError, ErrorCode
from app.service.evolution.backoff import MAX_RETRY_ATTEMPTS
from app.utils.ids import new_id
from app.utils.time import as_shanghai, now_shanghai

ACTIVE_RUN = ("preparing", "running")
type ControlEvent = Literal["run_pause_requested", "run_paused", "run_continued"]


@dataclass(frozen=True)
class ControlChange:
    run: EvolutionRunRecord
    events: tuple[RunEventRecord, ...] = ()
    job_id: str | None = None


async def _locked_run(
    session: AsyncSession, run_id: str, wid: str | None = None
) -> EvolutionRunRecord:
    # An initial write serializes control/admission on SQLite as well as InnoDB.
    where = [evolution_runs.c.id == run_id]
    if wid is not None:
        where.append(evolution_runs.c.workspace_id == wid)
    await lock_run_row(session, run_id, wid)
    row = (await session.execute(select(evolution_runs).where(*where))).mappings().one_or_none()
    if row is None:
        raise AppError(
            status_code=404, code=ErrorCode.RUN_NOT_FOUND, message="evolution run not found"
        )
    return record_from_evolution_run(cast(Mapping[str, Any], row))


async def _audit(
    session: AsyncSession,
    run: EvolutionRunRecord,
    events: tuple[ControlEvent, ...],
    actor: str | None,
    job_id: str | None = None,
) -> ControlChange:
    messages = {
        "run_pause_requested": "已请求暂停",
        "run_paused": "运行已暂停",
        "run_continued": "运行已继续",
    }
    seq = await next_run_event_sequence(session, run.id)
    records = []
    for offset, event in enumerate(events):
        records.append(
            await insert_run_event(
                session,
                {
                    "workspace_id": run.workspace_id,
                    "run_id": run.id,
                    "seq": seq + offset,
                    "event_type": event,
                    "level": "info",
                    "stage": "step",
                    "message": messages[event],
                    "payload": {"actor": actor},
                    "created_at": now_shanghai(),
                },
            )
        )
    return ControlChange(run, tuple(records), job_id)


async def _active(session: AsyncSession, run_id: str) -> str | None:
    return (
        await session.execute(
            select(job_runs.c.id)
            .where(
                job_runs.c.ref_id == run_id,
                job_runs.c.kind.in_(EVOLUTION_JOB_KINDS),
                job_runs.c.status.in_(ACTIVE_JOB_STATUSES),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


def _conflict(run: EvolutionRunRecord) -> AppError:
    return AppError(
        status_code=409,
        code=ErrorCode.RUN_CONTROL_CONFLICT,
        message="action unavailable for the current run state",
        details={"status": run.status, "controlState": run.control_state},
    )


async def _retire_queued(session: AsyncSession, run_id: str, now: datetime) -> None:
    """Fence pending worker callbacks before exposing an acknowledged pause."""
    await session.execute(
        update(job_runs)
        .where(
            job_runs.c.ref_id == run_id,
            job_runs.c.kind.in_(EVOLUTION_JOB_KINDS),
            job_runs.c.status == "queued",
        )
        .values(
            status="completed",
            result={"runId": run_id, "yielded": True},
            progress=1.0,
            finished_at=now,
            updated_at=now,
        )
    )


async def _continuation(
    session: AsyncSession, run: EvolutionRunRecord, now: datetime
) -> tuple[str, dict[str, Any]] | None:
    payload: dict[str, Any] = {"runId": run.id, "continuation": True}
    if run.status == "preparing" or (
        run.attribution_engine != "legacy-probe-import" and run.progress_unit < 5
    ):
        return "evolution_prepare", payload
    round_ = (
        (
            await session.execute(
                select(evolution_rounds)
                .where(
                    evolution_rounds.c.run_id == run.id,
                    evolution_rounds.c.status.notin_(("accepted", "rejected", "skipped")),
                )
                .order_by(evolution_rounds.c.seq)
                .limit(1)
            )
        )
        .mappings()
        .one_or_none()
    )
    if round_ is None:
        if run.mode == "cluster_only" or (
            run.attribution_engine != "legacy-probe-import" and not run.workspace_path
        ):
            return "evolution_prepare", payload
        return "evolution_finalize", payload
    if round_["eval_status"] in {"failed", "timeout"}:
        await session.execute(
            update(evolution_runs)
            .where(evolution_runs.c.id == run.id)
            .values(
                status="blocked",
                blocked_stage="eval",
                eval_status="failed",
                error_stage="eval",
                error_message=round_["eval_error"],
                error_at=round_["eval_finished_at"],
            )
        )
        return None
    if round_["eval_status"] == "completed":
        return "evolution_apply", {**payload, "evolutionRoundId": round_["id"]}
    if round_["eval_external_id"] and round_["eval_started_at"] and run.paused_at:
        elapsed = (now - max(run.paused_at, as_shanghai(round_["eval_started_at"]))).total_seconds()
        await session.execute(
            update(evolution_rounds)
            .where(evolution_rounds.c.id == round_["id"])
            .values(
                eval_paused_seconds=evolution_rounds.c.eval_paused_seconds + max(elapsed, 0),
                eval_next_poll_at=now,
            )
        )
        return None
    return "evolution_advance", payload


class EvolutionControlRepository:
    """Serialize requests, checkpoint acknowledgement and stage admission on the run row."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def pending_acknowledgements(self) -> tuple[str, ...]:
        async with self._database.session() as session:
            rows: ScalarResult[str] = await session.scalars(
                select(evolution_runs.c.id).where(
                    evolution_runs.c.control_state == "pause_requested"
                )
            )
            return tuple(rows)

    async def pause(self, run_id: str, wid: str, actor: str) -> ControlChange:
        async with self._database.transaction() as session:
            run = await _locked_run(session, run_id, wid)
            if run.status not in ACTIVE_RUN:
                raise _conflict(run)
            if run.control_state != "running":
                return ControlChange(run)
            now = now_shanghai()
            await _retire_queued(session, run_id, now)
            active = await _active(session, run.id)
            await session.execute(
                update(evolution_runs)
                .where(evolution_runs.c.id == run_id)
                .values(
                    control_state="pause_requested" if active else "paused",
                    pause_requested_at=now,
                    paused_at=None if active else now,
                    paused_by=actor,
                )
            )
            events: tuple[ControlEvent, ...] = (
                ("run_pause_requested",) if active else ("run_pause_requested", "run_paused")
            )
            return await _audit(session, await _locked_run(session, run_id), events, actor)

    async def acknowledge(self, run_id: str) -> ControlChange | None:
        async with self._database.transaction() as session:
            run = await _locked_run(session, run_id)
            if run.control_state != "pause_requested" or run.status not in ACTIVE_RUN:
                return None
            await _retire_queued(session, run_id, now_shanghai())
            if not await _active(session, run.id):
                await session.execute(
                    update(evolution_runs)
                    .where(evolution_runs.c.id == run_id)
                    .values(
                        control_state="paused",
                        paused_at=now_shanghai(),
                    )
                )
                return await _audit(
                    session, await _locked_run(session, run_id), ("run_paused",), run.paused_by
                )
            return None

    async def resume(self, run_id: str, wid: str, actor: str) -> ControlChange:
        async with self._database.transaction() as session:
            run = await _locked_run(session, run_id, wid)
            if run.status not in ACTIVE_RUN:
                raise _conflict(run)
            if run.control_state == "running" and run.resumed_at:
                return ControlChange(run)
            if run.control_state != "paused":
                raise _conflict(run)
            now = now_shanghai()
            job_id = await _active(session, run_id)
            if job_id is None:
                task = await _continuation(session, run, now)
                if task:
                    kind, payload = task
                    job_id = new_id()
                    await session.execute(
                        insert(job_runs).values(
                            **queued_job_values(
                                job_id=job_id,
                                kind=kind,
                                payload=payload,
                                ref_id=run_id,
                                created_by=actor,
                            )
                        )
                    )
            await session.execute(
                update(evolution_runs)
                .where(evolution_runs.c.id == run_id)
                .values(
                    control_state="running",
                    paused_at=None,
                    pause_requested_at=None,
                    paused_by=None,
                    resumed_at=now,
                )
            )
            return await _audit(
                session, await _locked_run(session, run_id), ("run_continued",), actor, job_id
            )

    async def admit(
        self, run_id: str, kind: str, payload: Mapping[str, Any], actor: str | None
    ) -> tuple[str, bool]:
        async with self._database.transaction() as session:
            run = await _locked_run(session, run_id)
            active = await _active(session, run_id)
            required = ("blocked",) if kind == "evolution_retry" else ACTIVE_RUN
            if (
                kind == "evolution_retry"
                and payload.get("automatic") is True
                and (
                    run.blocked_stage != "push"
                    or run.next_retry_at is None
                    or run.next_retry_at > now_shanghai()
                    or run.retry_attempts >= MAX_RETRY_ATTEMPTS
                )
            ):
                raise AppError(status_code=409, code=ErrorCode.RUN_BUSY, message="retry is not due")
            if run.control_state != "running" or run.status not in required or active:
                if active and kind == "evolution_retry":
                    existing_kind: str = (
                        await session.execute(
                            select(job_runs.c.kind).where(job_runs.c.id == active)
                        )
                    ).scalar_one()
                    if existing_kind == kind:
                        return active, True
                raise AppError(
                    status_code=409,
                    code=ErrorCode.RUN_BUSY,
                    message="evolution run cannot admit another stage job",
                )
            job_id = new_id()
            await session.execute(
                insert(job_runs).values(
                    **queued_job_values(
                        job_id=job_id,
                        kind=kind,
                        payload=payload,
                        ref_id=run_id,
                        created_by=actor,
                    )
                )
            )
            return job_id, False
