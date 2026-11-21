"""User control independent of evolution execution and blocked-run recovery."""

from collections.abc import Callable
from datetime import datetime
from typing import Literal

from app.db.crud.evolution import EvolutionRepository
from app.db.crud.evolution_control import ACTIVE_RUN, ControlChange, EvolutionControlRepository
from app.db.models.evolution import EvolutionRunRecord
from app.service.evolution.events import EvolutionRunEventService
from app.service.identity.schemas import IdentityModel


class EvolutionRunControl(IdentityModel):
    """Server-authoritative controls shared by mutations, cards and details."""

    run_id: str
    control_state: Literal["running", "pause_requested", "paused"] = "running"
    pause_requested_at: datetime | None = None
    paused_at: datetime | None = None
    paused_by: str | None = None
    can_pause: bool = False
    can_resume: bool = False


def control_view(run: EvolutionRunRecord) -> EvolutionRunControl:
    active = run.status in ACTIVE_RUN
    return EvolutionRunControl(
        run_id=run.id,
        control_state=run.control_state,
        pause_requested_at=run.pause_requested_at,
        paused_at=run.paused_at,
        paused_by=run.paused_by,
        can_pause=active and run.control_state == "running",
        can_resume=active and run.control_state == "paused",
    )


class PauseAtCheckpoint(Exception):
    """The handler has persisted its current unit and can release the worker."""


async def checkpoint(runs: EvolutionRepository, run_id: str) -> None:
    run = await runs.get_run(run_id)
    if run and run.control_state != "running":
        raise PauseAtCheckpoint


class EvolutionControlService:
    def __init__(
        self,
        repository: EvolutionControlRepository,
        events: EvolutionRunEventService,
        schedule: Callable[[str], None],
    ) -> None:
        self.repository = repository
        self._events = events
        self._schedule = schedule

    def _publish(self, change: ControlChange) -> EvolutionRunControl:
        for event in change.events:
            self._events.publish_committed(event)
        return control_view(change.run)

    async def pause(self, run_id: str, wid: str, actor: str) -> EvolutionRunControl:
        return self._publish(await self.repository.pause(run_id, wid, actor))

    async def resume(self, run_id: str, wid: str, actor: str) -> EvolutionRunControl:
        change = await self.repository.resume(run_id, wid, actor)
        try:
            return self._publish(change)
        finally:
            if change.job_id:
                self._schedule(change.job_id)

    async def acknowledge(self, run_id: str) -> None:
        change = await self.repository.acknowledge(run_id)
        if change:
            self._publish(change)
