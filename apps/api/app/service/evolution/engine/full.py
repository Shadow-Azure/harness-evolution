"""Full evolution stage declarations delegated to later implementations."""

from typing import ClassVar

from app.db.models.jobs import JobRunRecord
from app.service.evolution.engine.base import EvolutionEngine
from app.service.evolution.engine.contracts import ConfigError


class FullEvolutionEngine(EvolutionEngine):
    """Expose the complete five-stage evolution lifecycle."""

    KIND_TO_METHOD: ClassVar[dict[str, str]] = {
        **EvolutionEngine.KIND_TO_METHOD,
        "evolution_advance": "advance_one_round",
        "evolution_apply": "apply_eval",
        "evolution_finalize": "finalize",
        "evolution_retry": "retry",
    }

    def stages(self) -> tuple[str, ...]:
        """Return the five stage kinds in canonical execution order."""
        return tuple(self.KIND_TO_METHOD)

    async def prepare(self, job: JobRunRecord) -> None:
        """Delegate prepare orchestration to the injected stage handler."""
        await self._delegate(job)

    async def advance_one_round(self, job: JobRunRecord) -> None:
        """Delegate one round advance to the injected stage handler."""
        await self._delegate(job)

    async def apply_eval(self, job: JobRunRecord) -> None:
        """Delegate evaluation application to the injected stage handler."""
        await self._delegate(job)

    async def finalize(self, job: JobRunRecord) -> None:
        """Delegate final evaluation to the injected stage handler."""
        await self._delegate(job)

    async def retry(self, job: JobRunRecord) -> None:
        """Delegate blocked-stage recovery to the injected stage handler."""
        await self._delegate(job)

    async def _delegate(self, job: JobRunRecord) -> None:
        """Run the future concrete handler registered for this stage."""
        handler = self.deps.full_stages.get(job.kind)
        if handler is None:
            raise ConfigError(
                f"{type(self).__name__} has no handler for stage {job.kind}",
            )
        await handler(job)
