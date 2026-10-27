"""Placeholder preparation handler for admitted evolution runs."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.db.models.jobs import JobRunRecord

logger = logging.getLogger(__name__)


async def handle_evolution_prepare(job: JobRunRecord) -> Mapping[str, Any]:
    """Acknowledge a prepare job without advancing the run.

    The real prepare orchestration (workspace clone, ref validation, probe
    filtering, and clustering) is provided by m5-06. This placeholder only lets
    the queued job terminate successfully while the run stays `preparing`.

    Args:
        job: Claimed durable job row carrying the admitted run id.

    Returns:
        Placeholder result recorded on the completed job row.
    """
    logger.info(
        "evolution prepare placeholder completed",
        extra={"job_id": job.id, "run_id": job.ref_id},
    )
    return {
        "placeholder": True,
        "runId": job.ref_id,
        "note": "real prepare orchestration is provided by m5-06",
    }
