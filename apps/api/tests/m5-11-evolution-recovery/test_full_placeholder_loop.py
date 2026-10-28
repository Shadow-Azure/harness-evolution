"""End-to-end placeholder loop over real SQLite state and a real local bare git remote.

This is the acceptance smoke test for m5-11: one full run prepares a workspace from
a tagged local repository, publishes two real candidates (one accepted, one
rejected), applies both verdicts, finalizes the run, and leaves a complete,
monotonic run-event history. No network and no API process are involved.
"""

from __future__ import annotations

import subprocess
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.base import Database
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.probe_query import ProbeHitRow
from app.db.crud.run_events import SqlRunEventStore
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import probe_reports
from app.db.models.evolution import (
    ClusterWrite,
    EvolutionRunRecord,
    ProbeClusterRecord,
)
from app.db.models.jobs import JobRunRecord
from app.service.events import EventBus
from app.service.evolution.apply_final import (
    EvolutionApplyService,
    EvolutionFinalizeService,
)
from app.service.evolution.engine.contracts import (
    EvalGatewayConfig,
    EvalRequest,
    EvalResult,
    EvalStatus,
    EvalSubmission,
    FakeEvalGateway,
)
from app.service.evolution.eval_poller import EvolutionEvalPoller, EvolutionEvalSubmitter
from app.service.evolution.events import EvolutionRunEventService
from app.service.evolution.git_candidate import (
    CandidateTrace,
    EvolutionCandidateService,
)
from app.third_party_api.git.workspace import GitWorkspaceManager

NOW = datetime(2026, 10, 28, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
RUN_ID = "run-full-loop"
ROUND_ACCEPT = "round-full-1"
ROUND_REJECT = "round-full-2"
BRANCH = f"evo/{NOW:%Y%m%d}-{RUN_ID}"


def _git(cwd: Path | None, *args: str) -> str:
    """Run one local git command, surfacing stderr on failure for diagnosis."""
    result = subprocess.run(
        ("git", *args),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed with exit code {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
    return result.stdout.strip()


def _remote_tag(bare: Path, ref: str) -> str:
    """Return the remote tag commit or an empty string when the tag is absent."""
    return subprocess.run(
        ("git", "ls-remote", "--tags", str(bare), f"refs/tags/{ref}"),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


@pytest.fixture
def remote_repo(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create a bare remote with a tagged target directory and one seed commit."""
    bare = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(seed))
    _git(seed, "config", "user.name", "Test User")
    _git(seed, "config", "user.email", "test@example.invalid")
    target = seed / "skills" / "deep-research"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("# Deep Research\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "initial target")
    _git(seed, "tag", "v2.0.0")
    _git(seed, "push", "origin", "HEAD:refs/heads/main", "--tags")
    return bare, seed, _git(seed, "rev-parse", "HEAD")


@pytest_asyncio.fixture
async def database(tmp_path: Path) -> AsyncIterator[Database]:
    """Provide migrated real SQLite state bound to a temporary data directory."""
    db = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db",
            jwt_secret=SecretStr("m5-11-full-loop-signing-secret"),
        ),
    )
    await db.start()
    await upgrade_database(db)
    try:
        yield db
    finally:
        await db.dispose()


class ProbeReader:
    """Return one deterministic source row per requested probe id."""

    async def list_rows_by_ids(self, probe_ids: Sequence[str]) -> tuple[ProbeHitRow, ...]:
        """Build complete trace rows without another database dependency."""
        return tuple(
            ProbeHitRow(
                bad_case_id=f"case-{probe_id}",
                analysis_status="finished",
                probe_id=probe_id,
                probe_session_id="session-1",
                probe_type="error",
                probe_object="deep-research",
                object_version="v2.0.0",
                attribute_type="error",
                probe_description=f"probe {probe_id}",
                probe_analysis=f"analysis {probe_id}",
                session_title="placeholder session",
                case_agent_model=None,
                session_model=None,
                probe_started_at=NOW,
            )
            for probe_id in probe_ids
        )


class JobCapture:
    """Capture poller follow-up submissions without starting a worker."""

    def __init__(self) -> None:
        """Create an empty capture list."""
        self.items: list[tuple[str, Mapping[str, Any]]] = []

    async def submit(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        ref_id: str | None,
        created_by: str | None,
    ) -> object:
        """Record one follow-up scheduling call and report it as fresh."""
        del ref_id, created_by
        self.items.append((kind, dict(payload)))
        return object()


class RoundGateway:
    """Dispatch fake evaluation calls to the gateway configured for one round."""

    config = EvalGatewayConfig.from_mapping({})

    def __init__(self, gateways: Mapping[str, FakeEvalGateway]) -> None:
        """Bind one deterministic gateway per evolution round id."""
        self._gateways = dict(gateways)

    @staticmethod
    def _round_id(eval_id: str) -> str:
        """Read the embedded evolution round id from a fake evaluation id."""
        return eval_id.split(":")[2]

    async def submit(self, request: EvalRequest) -> EvalSubmission:
        """Delegate submission to the round's configured gateway."""
        return await self._gateways[request.evolution_round_id].submit(request)

    async def get_status(self, eval_id: str) -> EvalStatus:
        """Delegate status polling to the round's configured gateway."""
        return await self._gateways[self._round_id(eval_id)].get_status(eval_id)

    async def get_result(self, eval_id: str) -> EvalResult:
        """Delegate result retrieval to the round's configured gateway."""
        return await self._gateways[self._round_id(eval_id)].get_result(eval_id)


async def _no_sleep(seconds: float) -> None:
    """Remove production push pacing from the deterministic smoke run."""
    del seconds


def _job(
    kind: str,
    *,
    job_id: str,
    run_id: str | None,
    payload: Mapping[str, Any] | None = None,
) -> JobRunRecord:
    """Build one already-claimed durable job row for a service boundary."""
    return JobRunRecord(
        id=job_id,
        kind=kind,
        ref_id=run_id,
        status="running",
        progress=0.0,
        executor="local",
        external_job_id=None,
        attempt=1,
        payload=dict(payload or {}),
        result=None,
        error=None,
        created_by=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
        updated_at=NOW,
    )


async def _prepare_full_run(
    database: Database,
    repository: EvolutionRepository,
    workspaces: GitWorkspaceManager,
    *,
    repo_url: str,
    base_commit: str,
) -> tuple[EvolutionRunRecord, tuple[ProbeClusterRecord, ...]]:
    """Insert one run, create its real workspace, and persist clusters and rounds."""
    run = await repository.create_run(
        {
            "id": RUN_ID,
            "title": "full placeholder loop",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {"mode": "fake"},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": repo_url,
            "sub_dir": "skills/deep-research",
            "status": "preparing",
            "progress_unit": 0,
            "stats": {},
            "created_by": None,
            "created_at": NOW,
        },
    )
    async with database.transaction() as session:
        await session.execute(
            insert(probe_reports),
            [
                {
                    "probe_id": "probe-1",
                    "session_id": "session-1",
                    "probe_type": "error",
                    "probe_object": "deep-research",
                    "object_version": "v2.0.0",
                    "attribute_type": "error",
                    "probe_description": "probe-1 description",
                    "probe_analysis": "probe-1 analysis",
                    "created_at": NOW,
                    "updated_at": NOW,
                },
                {
                    "probe_id": "probe-2",
                    "session_id": "session-1",
                    "probe_type": "prompt",
                    "probe_object": "deep-research",
                    "object_version": "v2.0.0",
                    "attribute_type": "prompt",
                    "probe_description": "probe-2 description",
                    "probe_analysis": "probe-2 analysis",
                    "created_at": NOW,
                    "updated_at": NOW,
                },
            ],
        )

    await repository.advance_unit(run.id, expected=0, target=1, cluster_count=2)
    prepared = await workspaces.prepare(run)
    assert prepared.base_commit == base_commit

    clusters = await repository.replace_clusters(
        run.id,
        (
            ClusterWrite(
                type="error",
                description="retrieval index read failed",
                probes=("probe-1",),
                impact=0.9,
            ),
            ClusterWrite(
                type="prompt",
                description="prompt output constraints missing",
                probes=("probe-2",),
                impact=0.7,
            ),
        ),
    )
    assert len(clusters) == 2

    await repository.advance_unit(run.id, expected=1, target=2, cluster_count=2)
    await repository.write_cluster_confidence(
        run.id,
        {cluster.probe_cluster_id: 0.9 - index * 0.1 for index, cluster in enumerate(clusters)},
    )
    await repository.write_cluster_severity(
        run.id,
        {
            cluster.probe_cluster_id: (0.9 - index * 0.1, index + 1)
            for index, cluster in enumerate(clusters)
        },
    )
    await repository.insert_rounds(
        (
            {
                "id": ROUND_ACCEPT,
                "run_id": run.id,
                "probe_cluster_id": clusters[0].probe_cluster_id,
                "seq": 1,
                "status": "pending",
            },
            {
                "id": ROUND_REJECT,
                "run_id": run.id,
                "probe_cluster_id": clusters[1].probe_cluster_id,
                "seq": 2,
                "status": "pending",
            },
        ),
    )
    marked = await repository.mark_prepared(
        run.id,
        status="running",
        progress_unit=4,
        repo_path=str(prepared.repo_path),
        base_ref=prepared.ref,
        base_commit=prepared.base_commit,
        branch_name=prepared.branch,
        workspace_path=str(prepared.path),
        stats={"clusters": 2},
    )
    return marked, clusters


async def test_full_placeholder_loop_accepts_rejects_and_finalizes(
    tmp_path: Path,
    remote_repo: tuple[Path, Path, str],
    database: Database,
) -> None:
    """One full run reaches completed with accepted, rejected, and final evidence."""
    bare, _seed, base_commit = remote_repo
    repository = EvolutionRepository(database)
    events = EvolutionRunEventService(
        SqlRunEventStore(database),
        repository,
        EventBus(queue_capacity=32),
    )
    workspaces = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        push_enabled=True,
    )
    run, clusters = await _prepare_full_run(
        database,
        repository,
        workspaces,
        repo_url=str(bare),
        base_commit=base_commit,
    )
    assert run.status == "running"
    assert run.progress_unit == 4
    assert run.workspace_path is not None
    assert run.branch_name == BRANCH

    clock = NOW

    def now() -> datetime:
        """Return the mutable deterministic clock shared by all services."""
        return clock

    gateways = RoundGateway(
        {
            ROUND_ACCEPT: FakeEvalGateway(
                EvalGatewayConfig.from_mapping(
                    {
                        "status": "completed",
                        "currentScore": 80.0,
                        "candidateScore": 90.0,
                        "verdict": "accept",
                    },
                ),
            ),
            ROUND_REJECT: FakeEvalGateway(
                EvalGatewayConfig.from_mapping(
                    {
                        "status": "completed",
                        "currentScore": 80.0,
                        "candidateScore": 70.0,
                        "verdict": "reject",
                    },
                ),
            ),
        },
    )
    candidates = EvolutionCandidateService(
        repository,
        workspaces,
        events=events,
        push_interval_seconds=0,
        sleep=_no_sleep,
        now=now,
    )
    submitter = EvolutionEvalSubmitter(
        repository,
        lambda _run: gateways,
        events=events,
        now=now,
        poll_interval=timedelta(minutes=5),
    )
    poller = EvolutionEvalPoller(
        repository,
        lambda _run: gateways,
        JobCapture(),
        events=events,
        now=now,
        poll_interval=timedelta(minutes=5),
        timeout=timedelta(hours=2),
    )
    apply_service = EvolutionApplyService(
        repository,
        candidates,
        ProbeReader(),
        events=events,
        now=now,
    )
    finalize_service = EvolutionFinalizeService(
        repository,
        workspaces,
        events=events,
        now=now,
    )

    traces = {
        ROUND_ACCEPT: CandidateTrace(
            cluster_id=clusters[0].probe_cluster_id,
            cluster_title=clusters[0].probe_cluster_description,
            probes=("probe-1",),
            bad_cases=("case-probe-1",),
            analysis="missing field validation before reading the snapshot",
        ),
        ROUND_REJECT: CandidateTrace(
            cluster_id=clusters[1].probe_cluster_id,
            cluster_title=clusters[1].probe_cluster_description,
            probes=("probe-2",),
            bad_cases=("case-probe-2",),
            analysis="missing output constraints and a lower candidate score",
        ),
    }

    # Round 1: publish, evaluate, accept through real git.
    round_accept = await repository.get_round(ROUND_ACCEPT)
    assert round_accept is not None
    published = await candidates.publish(
        run,
        round_accept,
        traces[ROUND_ACCEPT],
        job_id="job-publish-1",
    )
    assert published.status == "evaluating"
    assert published.candidate_commit is not None
    assert published.candidate_ref is not None
    accepted_candidate_commit = published.candidate_commit
    submitted = await submitter.submit(run, published)
    assert submitted.eval_external_id is not None

    clock = NOW + timedelta(minutes=6)
    assert await poller.run_once() >= 1
    evaluated = await repository.get_round(ROUND_ACCEPT)
    assert evaluated is not None
    assert evaluated.eval_status == "completed"
    assert evaluated.eval_result is not None

    accepted = await apply_service.handle(
        _job(
            "evolution_apply",
            job_id="job-apply-1",
            run_id=RUN_ID,
            payload={"evolutionRoundId": ROUND_ACCEPT},
        ),
    )
    assert accepted["status"] == "accepted"
    assert accepted["accepted"] is True
    accepted_round = await repository.get_round(ROUND_ACCEPT)
    run_after_accept = await repository.get_run(RUN_ID)
    assert accepted_round is not None and run_after_accept is not None
    assert accepted_round.accepted is True
    assert accepted_round.commit_hash is not None
    assert run_after_accept.progress_unit == 5
    assert _remote_tag(bare, published.candidate_ref) == ""

    # Round 2: publish, evaluate, reject through real git.
    round_reject = await repository.get_round(ROUND_REJECT)
    assert round_reject is not None
    published_reject = await candidates.publish(
        run_after_accept,
        round_reject,
        traces[ROUND_REJECT],
        job_id="job-publish-2",
    )
    assert published_reject.status == "evaluating"
    assert published_reject.candidate_commit is not None
    assert published_reject.candidate_ref is not None
    submitted_reject = await submitter.submit(run_after_accept, published_reject)
    assert submitted_reject.eval_external_id is not None

    clock = NOW + timedelta(minutes=12)
    assert await poller.run_once() >= 1
    rejected_eval = await repository.get_round(ROUND_REJECT)
    assert rejected_eval is not None
    assert rejected_eval.eval_status == "completed"

    rejected = await apply_service.handle(
        _job(
            "evolution_apply",
            job_id="job-apply-2",
            run_id=RUN_ID,
            payload={"evolutionRoundId": ROUND_REJECT},
        ),
    )
    assert rejected["status"] == "rejected"
    assert rejected["accepted"] is False
    rejected_round = await repository.get_round(ROUND_REJECT)
    run_after_reject = await repository.get_run(RUN_ID)
    assert rejected_round is not None and run_after_reject is not None
    assert rejected_round.accepted is False
    assert run_after_reject.progress_unit == 6
    assert _remote_tag(bare, published_reject.candidate_ref) == ""

    # Finalize: durable final row, completed run, and a published run branch.
    finalized = await finalize_service.handle(
        _job("evolution_finalize", job_id="job-finalize", run_id=RUN_ID),
    )
    assert finalized["finalized"] is True
    completed = await repository.get_run(RUN_ID)
    final = await repository.get_final(RUN_ID)
    assert completed is not None and final is not None
    assert completed.status == "completed"
    assert completed.push_status == "succeeded"
    assert completed.blocked_stage is None
    assert final.verdict is True
    assert final.init_score == 80.0
    assert final.best_score == 90.0
    assert len(final.metrics) == 2
    assert [metric["accepted"] for metric in final.metrics] == [True, False]
    assert _git(bare, "rev-parse", f"refs/heads/{BRANCH}") == accepted_round.commit_hash
    branch_refs = _git(bare, "for-each-ref", "--format=%(refname)", "refs/heads").splitlines()
    assert f"refs/heads/{BRANCH}" in branch_refs
    assert accepted_candidate_commit != accepted_round.commit_hash

    # Event history is complete, typed, and strictly ordered.
    page = await events.list(RUN_ID, after_seq=0, limit=200, level=None)
    event_types = [item.event_type for item in page.items]
    for required in (
        "candidate_committed",
        "candidate_pushed",
        "eval_completed",
        "cluster_accepted",
        "cluster_rejected",
        "final_completed",
    ):
        assert required in event_types
    sequences = [item.seq for item in page.items]
    assert sequences == sorted(sequences)
    assert len(sequences) == len(set(sequences))
    assert sequences[0] == 1
    accepted_events = [item for item in page.items if item.event_type == "cluster_accepted"]
    rejected_events = [item for item in page.items if item.event_type == "cluster_rejected"]
    assert len(accepted_events) == 1
    assert len(rejected_events) == 1
    assert accepted_events[0].stage == "apply"
    assert accepted_events[0].payload is not None
    assert accepted_events[0].payload["finalCommit"] == accepted_round.commit_hash
    assert rejected_events[0].payload is not None
    assert rejected_events[0].payload["cleanupError"] is None
    final_events = [item for item in page.items if item.event_type == "final_completed"]
    assert len(final_events) == 1
    assert final_events[0].payload is not None
    assert final_events[0].payload["pushStatus"] == "succeeded"
