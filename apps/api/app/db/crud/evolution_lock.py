"""Serialize evolution transitions before reading their current state."""

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.evolution import evolution_runs


async def lock_run_row(session: AsyncSession, run_id: str, wid: str | None = None) -> None:
    """Acquire the same first-write lock on SQLite and InnoDB."""
    lock = update(evolution_runs).where(evolution_runs.c.id == run_id)
    if wid is not None:
        lock = lock.where(evolution_runs.c.workspace_id == wid)
    await session.execute(lock.values(control_state=evolution_runs.c.control_state))
