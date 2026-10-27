"""Placeholder preparation handler for admitted evolution runs."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.db.models.jobs import JobRunRecord
from app.service.evolution.events import EvolutionRunEventService

logger = logging.getLogger(__name__)


async def handle_evolution_prepare(
    job: JobRunRecord,
    *,
    events: EvolutionRunEventService | None = None,
) -> Mapping[str, Any]:
    """Acknowledge a prepare job without advancing the run.

    The real prepare orchestration (workspace clone, ref validation, probe
    filtering, and clustering) arrives with the engine slices m5-09-m5-11.
    This placeholder only lets the queued job terminate successfully while the
    run stays `preparing`.

    Args:
        job: Claimed durable job row carrying the admitted run id.

    Returns:
        Placeholder result recorded on the completed job row.
    """
    logger.info(
        "evolution prepare placeholder completed",
        extra={"job_id": job.id, "run_id": job.ref_id},
    )
    if events is not None and job.ref_id is not None:
        await events.record(
            job.ref_id,
            "prepare_started",
            level="info",
            stage="prepare",
            job_id=job.id,
            message="准备阶段已启动",
        )
    return {
        "placeholder": True,
        "runId": job.ref_id,
        "note": "real prepare orchestration lands with the engine slices m5-09-m5-11",
    }
