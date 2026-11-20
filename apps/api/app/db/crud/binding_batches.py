"""Transactional leasing for attribution requested by a target configuration write."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update

from app.db.base import Database
from app.db.models.domain import evolution_targets
from app.utils.ids import new_id
from app.utils.time import as_shanghai, now_shanghai


@dataclass(frozen=True)
class BindingClaim:
    target: str
    workspace: str
    generation: str
    cutoff: datetime
    owner: str
    snapshot: dict[str, Any] | None


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
                    )
                    .where(t.enabled.is_(True), t.attribution_due <= now)
                    .order_by(t.attribution_due, t.id)
                    .limit(1)
                    .with_for_update()
                )
            ).first()
            if row is None:
                return None
            result = await session.execute(
                update(evolution_targets)
                .where(
                    t.id == row.id,
                    t.attribution_generation == row.attribution_generation,
                    t.attribution_due <= now,
                )
                .values(attribution_due=lease, attribution_owner=owner)
            )
            if not getattr(result, "rowcount", 0):
                return None
            return BindingClaim(
                row.id,
                row.workspace_id,
                row.attribution_generation,
                as_shanghai(row.attribution_cutoff),
                owner,
                row.attribution_snapshot,
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

    async def release(self, claim: BindingClaim, *, retry: bool) -> None:
        await self.update_claim(
            claim,
            attribution_owner=None,
            attribution_due=now_shanghai() + timedelta(seconds=30) if retry else None,
        )
