"""SQL-backed evolution event replay and recovery recording boundary."""

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from sqlalchemy import func, insert, inspect, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Database
from app.db.models.run_events import (
    RunEventPageRecord,
    RunEventRecord,
    evolution_run_events,
)
from app.service.events import ReplayEvent, RunEventReplayResult
from app.utils.redaction import sanitize_message
from app.utils.time import as_shanghai, now_shanghai


class SqlRunEventStore:
    """Read and append durable evolution event history."""

    def __init__(self, database: Database) -> None:
        """Bind the adapter to the shared storage lifecycle."""
        self._database = database
        self._table_exists: bool | None = None

    async def _has_table(self) -> bool:
        """Detect the future-owned table once without pretending it exists."""
        if self._table_exists is None:
            async with self._database.engine.connect() as connection:
                self._table_exists = await connection.run_sync(
                    lambda sync_connection: inspect(sync_connection).has_table(
                        "evolution_run_events",
                    ),
                )
        return self._table_exists

    async def read(
        self,
        topics: tuple[str, ...],
        cursors: Mapping[str, int],
        limit: int,
    ) -> RunEventReplayResult:
        """Return the next cross-topic page ordered by durable event identity."""
        if not await self._has_table():
            return RunEventReplayResult()
        run_ids = tuple(topic.removeprefix("run:") for topic in topics)
        conditions = [
            (
                (evolution_run_events.c.run_id == run_id)
                & (evolution_run_events.c.seq > cursors.get(f"run:{run_id}", 0))
            )
            for run_id in run_ids
        ]
        if not conditions:
            return RunEventReplayResult()
        async with self._database.session() as session:
            rows = (
                (
                    await session.execute(
                        select(evolution_run_events)
                        .where(or_(*conditions))
                        .order_by(
                            evolution_run_events.c.run_id,
                            evolution_run_events.c.seq,
                        )
                        .limit(limit + 1),
                    )
                )
                .mappings()
                .all()
            )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursors = dict(cursors)
        events: list[ReplayEvent] = []
        for row in page_rows:
            topic = f"run:{row['run_id']}"
            event_id = int(row["seq"])
            next_cursors[topic] = max(next_cursors.get(topic, 0), event_id)
            events.append(
                ReplayEvent(
                    topic=topic,
                    event_id=event_id,
                    event="run.event",
                    data=_event_data(row),
                ),
            )
        return RunEventReplayResult(
            events=tuple(events),
            next_cursors=next_cursors,
            has_more=has_more,
        )

    async def append(
        self,
        *,
        run_id: str,
        event_type: str,
        level: str,
        stage: str,
        message: str,
        step_index: int | None = None,
        cluster_id: str | None = None,
        round_id: str | None = None,
        job_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        error_detail: str | None = None,
    ) -> RunEventRecord:
        """Append one run event with a collision-safe monotonic run sequence."""
        if not await self._has_table():
            raise RuntimeError("evolution_run_events table is not available")
        for attempt in range(5):
            try:
                created_at = now_shanghai()
                async with self._database.transaction() as session:
                    sequence = await self._next_sequence(session, run_id)
                    values = {
                        "run_id": run_id,
                        "seq": sequence,
                        "event_type": event_type,
                        "level": level,
                        "stage": stage,
                        "step_index": step_index,
                        "cluster_id": cluster_id,
                        "evolution_round_id": round_id,
                        "job_id": job_id,
                        "message": message,
                        "payload": deepcopy(dict(payload)) if payload is not None else None,
                        "error_type": error_type,
                        "error_message": error_message,
                        "error_detail": error_detail,
                        "created_at": created_at,
                    }
                    await session.execute(insert(evolution_run_events).values(**values))
                return _record_from_values(values)
            except IntegrityError:
                if attempt == 4:
                    raise
        raise RuntimeError("unreachable event append retry state")

    async def _next_sequence(self, session: AsyncSession, run_id: str) -> int:
        """Allocate the next run-local sequence inside the append transaction."""
        latest = (
            await session.execute(
                select(func.max(evolution_run_events.c.seq)).where(
                    evolution_run_events.c.run_id == run_id,
                ),
            )
        ).scalar_one()
        return int(latest or 0) + 1

    async def read_page(
        self,
        run_id: str,
        *,
        after_seq: int,
        limit: int,
        level: str | None,
    ) -> RunEventPageRecord:
        """Return one stable sequence page with an optional level filter."""
        if not await self._has_table():
            return RunEventPageRecord(items=(), has_more=False)
        conditions = [
            evolution_run_events.c.run_id == run_id,
            evolution_run_events.c.seq > after_seq,
        ]
        if level is not None:
            conditions.append(evolution_run_events.c.level == level)
        async with self._database.session() as session:
            rows = (
                (
                    await session.execute(
                        select(evolution_run_events)
                        .where(*conditions)
                        .order_by(evolution_run_events.c.run_id, evolution_run_events.c.seq)
                        .limit(limit + 1),
                    )
                )
                .mappings()
                .all()
            )
        has_more = len(rows) > limit
        return RunEventPageRecord(
            items=tuple(_record_from_row(row) for row in rows[:limit]),
            has_more=has_more,
        )

    async def max_seq(self, run_id: str) -> int:
        """Return the latest durable sequence for one run, or zero for empty history."""
        if not await self._has_table():
            return 0
        async with self._database.session() as session:
            latest = (
                await session.execute(
                    select(func.max(evolution_run_events.c.seq)).where(
                        evolution_run_events.c.run_id == run_id,
                    ),
                )
            ).scalar_one()
        return int(latest or 0)

    async def record_interrupted(
        self,
        *,
        run_id: str,
        stage: str,
        message: str,
        job_id: str,
    ) -> int | None:
        """Persist one run interruption and return its monotonic run sequence."""
        if not await self._has_table():
            return None
        safe_message = sanitize_message(message, limit=2_000)
        event = await self.append(
            run_id=run_id,
            event_type="run_interrupted",
            level="error",
            stage=stage,
            job_id=job_id,
            message=safe_message,
            error_type="ProcessInterrupted",
            error_message=safe_message,
        )
        return event.seq


def _event_data(row: RowMapping) -> dict[str, Any]:
    """Map one durable row to the documented run event wire object."""
    created_at = as_shanghai(row["created_at"])
    return {
        "runId": row["run_id"],
        "seq": int(row["seq"]),
        "eventType": row["event_type"],
        "level": row["level"],
        "stage": row["stage"],
        "stepIndex": row["step_index"],
        "clusterId": row["cluster_id"],
        "roundId": row["evolution_round_id"],
        "jobId": row["job_id"],
        "message": row["message"],
        "createdAt": created_at.isoformat(),
        "payload": row["payload"],
        "error": (
            {
                "type": row["error_type"],
                "message": row["error_message"],
                "detail": row["error_detail"],
            }
            if row["error_type"] or row["error_message"] or row["error_detail"]
            else None
        ),
    }


def _record_from_row(row: RowMapping) -> RunEventRecord:
    """Map one selected row to the database-neutral event record."""
    payload = row["payload"]
    return RunEventRecord(
        run_id=str(row["run_id"]),
        seq=int(row["seq"]),
        event_type=str(row["event_type"]),
        level=str(row["level"]),
        stage=str(row["stage"]),
        step_index=int(row["step_index"]) if row["step_index"] is not None else None,
        cluster_id=str(row["cluster_id"]) if row["cluster_id"] is not None else None,
        round_id=(
            str(row["evolution_round_id"]) if row["evolution_round_id"] is not None else None
        ),
        job_id=str(row["job_id"]) if row["job_id"] is not None else None,
        message=str(row["message"]),
        payload=deepcopy(dict(payload)) if isinstance(payload, Mapping) else None,
        error_type=str(row["error_type"]) if row["error_type"] is not None else None,
        error_message=(str(row["error_message"]) if row["error_message"] is not None else None),
        error_detail=(str(row["error_detail"]) if row["error_detail"] is not None else None),
        created_at=as_shanghai(row["created_at"]),
    )


def _record_from_values(values: Mapping[str, Any]) -> RunEventRecord:
    """Build the append result from the exact values committed to storage."""
    payload = values.get("payload")
    return RunEventRecord(
        run_id=str(values["run_id"]),
        seq=int(values["seq"]),
        event_type=str(values["event_type"]),
        level=str(values["level"]),
        stage=str(values["stage"]),
        step_index=(int(values["step_index"]) if values.get("step_index") is not None else None),
        cluster_id=(str(values["cluster_id"]) if values.get("cluster_id") is not None else None),
        round_id=(
            str(values["evolution_round_id"])
            if values.get("evolution_round_id") is not None
            else None
        ),
        job_id=str(values["job_id"]) if values.get("job_id") is not None else None,
        message=str(values["message"]),
        payload=deepcopy(dict(payload)) if isinstance(payload, Mapping) else None,
        error_type=(str(values["error_type"]) if values.get("error_type") is not None else None),
        error_message=(
            str(values["error_message"]) if values.get("error_message") is not None else None
        ),
        error_detail=(
            str(values["error_detail"]) if values.get("error_detail") is not None else None
        ),
        created_at=as_shanghai(values["created_at"]),
    )
