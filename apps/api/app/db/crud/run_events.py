"""SQL-backed evolution event replay and recovery recording boundary."""

from collections.abc import Mapping
from typing import Any

from sqlalchemy import func, insert, inspect, or_, select
from sqlalchemy.engine import RowMapping

from app.db.base import Database
from app.db.models.run_events import evolution_run_events
from app.service.events import ReplayEvent, RunEventReplayResult
from app.utils.time import as_shanghai, now_shanghai


class SqlRunEventStore:
    """Read and append events once the m5-owned history table exists."""

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
                            evolution_run_events.c.created_at,
                            evolution_run_events.c.id,
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
        async with self._database.transaction() as session:
            latest = (
                await session.execute(
                    select(func.max(evolution_run_events.c.seq)).where(
                        evolution_run_events.c.run_id == run_id,
                    ),
                )
            ).scalar_one()
            sequence = int(latest or 0) + 1
            await session.execute(
                insert(evolution_run_events).values(
                    run_id=run_id,
                    seq=sequence,
                    event_type="run_interrupted",
                    level="error",
                    stage=stage,
                    step_index=None,
                    cluster_id=None,
                    evolution_round_id=None,
                    job_id=job_id,
                    message=message,
                    payload=None,
                    error_type="ProcessInterrupted",
                    error_message=message,
                    error_detail=None,
                    created_at=now_shanghai(),
                ),
            )
        return sequence


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
