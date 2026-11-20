"""Transactional leasing for attribution requested by a target configuration write."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from app.db.base import Database
from app.db.models.domain import evolution_targets
from app.utils.ids import new_id
from app.utils.time import as_shanghai, now_shanghai

MAX_FAILURES = 3
POLL_SECONDS = 30


@dataclass(frozen=True)
class BindingClaim:
    target: str
    workspace: str
    generation: str
    cutoff: datetime
    owner: str
    snapshot: dict[str, Any] | None
    failures: int


class BindingQueue:
    def __init__(self, database: Database):
        self.database = database

    async def claim(self, duration: int) -> BindingClaim | None:
        t = evolution_targets.c
        owner = new_id()
        now = now_shanghai()
        lease = (now + timedelta(seconds=duration)).replace(microsecond=0)
        async with self.database.transaction() as session:
            row = (
                await session.execute(
                    select(
                        t.id,
                        t.workspace_id,
                        t.attribution_generation,
                        t.attribution_cutoff,
                        t.attribution_snapshot,
                        t.attribution_failures,
                        t.attribution_owner,
                    )
                    .where(t.enabled.is_(True), t.attribution_due <= now)
                    .order_by(t.attribution_due, t.id)
                    .limit(1)
                    .with_for_update()
                )
            ).first()
            if row is None:
                return None
            # Expiry means the previous process never released its claim. Charge that
            # execution to the same retry budget as an explicit failure before rerunning it.
            values = (
                self._failure(row.attribution_failures, "worker_interrupted", now)
                if row.attribution_owner
                else {"attribution_due": lease, "attribution_owner": owner}
            )
            result = await session.execute(
                update(evolution_targets)
                .where(
                    t.id == row.id,
                    t.attribution_generation == row.attribution_generation,
                    t.attribution_due <= now,
                    t.attribution_owner == row.attribution_owner,
                )
                .values(**values)
            )
            if not getattr(result, "rowcount", 0) or row.attribution_owner:
                return None
            return BindingClaim(
                row.id,
                row.workspace_id,
                row.attribution_generation,
                as_shanghai(row.attribution_cutoff),
                owner,
                row.attribution_snapshot,
                row.attribution_failures,
            )

    async def update_claim(self, claim: BindingClaim, **values: Any) -> bool:
        t = evolution_targets.c
        async with self.database.transaction() as session:
            result = await session.execute(
                update(evolution_targets)
                .where(
                    t.attribution_generation == claim.generation,
                    t.attribution_owner == claim.owner,
                )
                .values(**values)
            )
            return bool(getattr(result, "rowcount", 0))

    @staticmethod
    def _failure(failures: int, reason: str, now: datetime) -> dict[str, Any]:
        due = None
        if failures + 1 < MAX_FAILURES:
            due = now + timedelta(seconds=POLL_SECONDS * 2**failures)
        return dict(
            attribution_failures=failures + 1,
            attribution_error=reason,
            attribution_owner=None,
            attribution_due=due,
        )

    async def fail(self, claim: BindingClaim, reason: str) -> None:
        await self.update_claim(claim, **self._failure(claim.failures, reason, now_shanghai()))

    async def complete(self, claim: BindingClaim, *, waiting_for_traces: bool) -> None:
        await self.update_claim(
            claim,
            attribution_owner=None,
            attribution_failures=0,
            attribution_error=None,
            attribution_due=now_shanghai() + timedelta(seconds=POLL_SECONDS)
            if waiting_for_traces
            else None,
        )
