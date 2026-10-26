"""Cluster-preview engine with prepare as its only capability."""

from app.db.models.jobs import JobRunRecord
from app.service.evolution.engine.base import EvolutionEngine
from app.service.evolution.engine.contracts import ConfigError


class ClusterOnlyEngine(EvolutionEngine):
    """Cluster once and stop before iteration or final evaluation."""

    def stages(self) -> tuple[str, ...]:
        """Declare prepare as the engine's complete stage capability."""
        return ("evolution_prepare",)

    async def prepare(self, job: JobRunRecord) -> None:
        """Delegate cluster preview preparation to the future implementation."""
        prepare = self.deps.prepare_cluster_only
        if prepare is None:
            raise ConfigError("cluster-only prepare handler is not configured")
        await prepare(self.run, job.payload)
