"""Interrupted advance resumes its durable round instead of starting over."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.db.models.jobs import JobRunRecord
from app.service.evolution.advance import EvolutionAdvanceService

NOW = datetime(2026, 11, 21, 9, 30, tzinfo=UTC)


class FakeRuns:
    """Serve one run and its persisted rounds without a database."""

    def __init__(self, round_: Any) -> None:
        """Store the round that recovery must inspect."""
        self.round = round_
        self.claimed: list[str] = []
        self.reset: list[str] = []

    async def get_run(self, run_id: str) -> Any:
        """Return a running full-mode run."""
        return SimpleNamespace(id=run_id, mode="full", status="running")

    async def list_rounds(self, run_id: str) -> tuple[Any, ...]:
        """Return the one persisted round."""
        return (self.round,)

    async def claim_round_for_advance(self, round_id: str, *, started_at: Any) -> bool:
        """Record an unexpected fresh-round claim."""
        self.claimed.append(round_id)
        return True

    async def reset_round_for_eval_retry(self, run_id: str, round_id: str) -> Any:
        """Clear a stale external evaluation and return the resettable round."""
        self.reset.append(round_id)
        return SimpleNamespace(
            **{
                **vars(self.round),
                "eval_external_id": None,
                "eval_status": "pending",
                "eval_next_poll_at": None,
            },
        )

    async def list_clusters(self, run_id: str) -> tuple[Any, ...]:
        """Return one cluster backing the round's trace."""
        return (
            SimpleNamespace(
                probe_cluster_id="cluster-1",
                probe_cluster_description="cluster",
            ),
        )

    async def list_cluster_probes(self, run_id: str) -> tuple[Any, ...]:
        """Return one probe link."""
        return (SimpleNamespace(probe_cluster_id="cluster-1", probe_id="probe-1"),)


class FakeCandidates:
    """Record which recovery operation the advance service selected."""

    def __init__(self, round_: Any) -> None:
        """Store the round returned by both operations."""
        self.round = round_
        self.published: list[str] = []
        self.repushed: list[str] = []

    async def publish(
        self,
        run: Any,
        round_: Any,
        trace: Any,
        *,
        job_id: str | None,
        resume: bool = False,
    ) -> Any:
        """Record a candidate regeneration."""
        self.published.append(round_.id)
        return SimpleNamespace(**{**vars(round_), "status": "evaluating"})

    async def repush_existing(
        self,
        run: Any,
        round_: Any,
        *,
        job_id: str | None = None,
    ) -> Any:
        """Record a candidate re-push from its persisted checkpoint."""
        self.repushed.append(round_.id)
        return SimpleNamespace(**{**vars(round_), "status": "evaluating"})


class FakeProbes:
    """Return one probe row for trace reconstruction."""

    async def list_rows_by_ids(self, probe_ids: tuple[str, ...]) -> tuple[Any, ...]:
        """Return complete source evidence."""
        return (
            SimpleNamespace(
                probe_id="probe-1",
                bad_case_id="case-1",
                probe_session_id=None,
                probe_description="",
                probe_analysis="",
            ),
        )


class FakeEval:
    """Record evaluation submissions."""

    def __init__(self) -> None:
        """Start with no submissions."""
        self.submitted: list[str] = []

    async def submit(self, run: Any, round_: Any) -> Any:
        """Record one external evaluation submission."""
        self.submitted.append(round_.id)
        return SimpleNamespace(**{**vars(round_), "eval_external_id": "eval-1"})


def _job(run_id: str) -> JobRunRecord:
    """Build the durable job identity under test."""
    return JobRunRecord(
        id="job-recovered",
        kind="evolution_advance",
        ref_id=run_id,
        status="running",
        progress=0.0,
        executor="local",
        external_job_id=None,
        attempt=2,
        payload={"runId": run_id},
        result=None,
        error=None,
        created_by=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
        updated_at=NOW,
    )


@pytest.mark.asyncio
async def test_pushing_round_repushes_the_persisted_candidate() -> None:
    """A committed candidate is reused instead of creating a second commit."""
    round_ = SimpleNamespace(
        id="round-1",
        status="pushing",
        candidate_ref="evo/20261121-run/candidate/r1",
        candidate_commit="a" * 40,
        candidate_message="message",
        eval_external_id=None,
        probe_cluster_id="cluster-1",
        seq=1,
    )
    runs = FakeRuns(round_)
    candidates = FakeCandidates(round_)
    eval_submitter = FakeEval()
    service = EvolutionAdvanceService(
        runs,  # type: ignore[arg-type]
        candidates,  # type: ignore[arg-type]
        FakeProbes(),  # type: ignore[arg-type]
        eval_submitter,
    )

    result = await service.handle(_job("run-1"))

    assert candidates.repushed == ["round-1"]
    assert candidates.published == []
    assert runs.claimed == []
    assert eval_submitter.submitted == ["round-1"]
    assert result["published"] is True


@pytest.mark.asyncio
async def test_stale_evaluating_round_is_reset_and_resubmitted() -> None:
    """A failed or deadline-less eval is resubmitted instead of polling forever."""
    round_ = SimpleNamespace(
        id="round-3",
        status="evaluating",
        candidate_ref="evo/20261121-run/candidate/r1",
        candidate_commit="a" * 40,
        candidate_message="message",
        eval_external_id="old-eval",
        eval_status="failed",
        eval_next_poll_at=None,
        probe_cluster_id="cluster-1",
        seq=1,
    )
    runs = FakeRuns(round_)
    eval_submitter = FakeEval()
    service = EvolutionAdvanceService(
        runs,  # type: ignore[arg-type]
        FakeCandidates(round_),  # type: ignore[arg-type]
        FakeProbes(),  # type: ignore[arg-type]
        eval_submitter,
    )

    result = await service.handle(_job("run-3"))

    assert runs.reset == ["round-3"]
    assert eval_submitter.submitted == ["round-3"]
    assert result["published"] is True


@pytest.mark.asyncio
async def test_patching_round_without_checkpoint_regenerates_the_candidate() -> None:
    """A round killed before its candidate checkpoint is rebuilt from trace data."""
    round_ = SimpleNamespace(
        id="round-2",
        status="patching",
        candidate_ref=None,
        candidate_commit=None,
        candidate_message=None,
        eval_external_id=None,
        probe_cluster_id="cluster-1",
        seq=1,
    )
    runs = FakeRuns(round_)
    candidates = FakeCandidates(round_)
    service = EvolutionAdvanceService(
        runs,  # type: ignore[arg-type]
        candidates,  # type: ignore[arg-type]
        FakeProbes(),  # type: ignore[arg-type]
        FakeEval(),
    )

    await service.handle(_job("run-2"))

    assert candidates.published == ["round-2"]
    assert candidates.repushed == []
    assert runs.claimed == []
