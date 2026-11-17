"""Real closed-loop evidence: patch → push → eval → decision → final.

Real git operations only: a local bare remote, real workspace commits, real
`git push` of the candidate tag and the run branch, and a real opt-in HTTP
evaluation gateway against a local stub platform. No git mocking anywhere.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest_asyncio
from eval_stub import StubEvalPlatform, git
from pydantic import SecretStr
from sqlalchemy import insert

from app.config import DatabaseDialect, Settings
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.probe_query import ProbeQueryRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.domain import bad_case_analysis, bad_cases, probe_reports
from app.db.models.evolution import evolution_rounds, probe_cluster_probes, probe_clusters
from app.db.models.jobs import JobRunRecord
from app.service.evolution.advance import EvolutionAdvanceService
from app.service.evolution.apply_final import EvolutionApplyService, EvolutionFinalizeService
from app.service.evolution.engine.contracts import EvalGatewayConfig
from app.service.evolution.eval_poller import EvolutionEvalPoller, EvolutionEvalSubmitter
from app.service.evolution.gateway_factory import build_eval_gateway_factory
from app.service.evolution.git_candidate import EvolutionCandidateService
from app.service.evolution.patch_source import MinimalConfigPatchSource
from app.third_party_api.git.workspace import GitWorkspaceManager

SH = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 11, 17, 10, 0, tzinfo=SH)
RUN_ID = "e2e-run-m12-03"
ROUND_ID = "e2e-round-m12-03"
CLUSTER_ID = "e2e-cluster-C1"
PROBE_ID = "probe-e2e-01"
BAD_CASE_ID = "bc-e2e-03"
SESSION_ID = "s-e2e-01"
API_KEY_REF = "HE_M12_03_STUB_KEY"


def _seed_remote(tmp_path: Path) -> tuple[Path, Path, str]:
    """Create a bare remote whose seed already carries a real config file."""
    bare = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    git(tmp_path, "init", "--bare", str(bare))
    git(tmp_path, "clone", str(bare), str(seed))
    git(seed, "config", "user.name", "Harness E2E")
    git(seed, "config", "user.email", "e2e@harness.invalid")
    target = seed / "skills" / "deep-research"
    (target / "config").mkdir(parents=True)
    (target / "SKILL.md").write_text("# Deep Research\n", encoding="utf-8")
    (target / "config" / "deep-research.json").write_text(
        json.dumps({"maxRetries": 2}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    git(seed, "add", ".")
    git(seed, "commit", "-m", "initial target")
    git(seed, "tag", "v2.0.0")
    git(seed, "push", "origin", "HEAD:refs/heads/main", "--tags")
    return bare, seed, git(seed, "rev-parse", "HEAD")


def _settings(tmp_path: Path, base_url: str) -> Settings:
    return Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path / "db",
        jwt_secret=SecretStr("m12-03-e2e-secret"),
        eval_mode="http",
        eval_base_url=base_url,
        patch_source_mode="minimal-config",
    )


@pytest_asyncio.fixture
async def loop_state(
    tmp_path: Path,
) -> AsyncIterator[tuple[Any, ...]]:
    """Provide the full durable and git state for one real closed loop."""
    database = create_database(
        Settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path / "db-meta",
            jwt_secret=SecretStr("m12-03-e2e-meta-secret"),
        ),
    )
    await database.start()
    await upgrade_database(database)
    bare, seed, base_commit = _seed_remote(tmp_path)
    repository = EvolutionRepository(database)
    probes = ProbeQueryRepository(database)
    await repository.create_run(
        {
            "id": RUN_ID,
            "title": "deep-research 真实闭环",
            "mode": "full",
            "engine_key": "full",
            "eval_config": {},
            "target_config_id": None,
            "target_type": "skill",
            "target_name": "deep-research",
            "target_version": "v2.0.0",
            "repo_url": str(bare),
            "sub_dir": "skills/deep-research",
            "base_ref": "v2.0.0",
            "base_commit": None,
            "branch_name": None,
            "repo_path": None,
            "workspace_path": None,
            "status": "preparing",
            "progress_unit": 0,
            "stats": {},
            "created_by": None,
            "created_at": NOW,
        },
    )
    async with database.transaction() as session:
        await session.execute(
            insert(bad_cases).values(
                bad_case_id=BAD_CASE_ID,
                bad_case_session_id=SESSION_ID,
                bad_case_type="error",
                object_name="deep-research",
                object_type="skill",
                object_version="v2.0.0",
                title="检索索引读取失败",
                bad_case_description="读取快照前未校验索引字段导致越界 ENOENT",
                meta_data={},
                created_at=NOW,
                updated_at=NOW,
            ),
        )
        await session.execute(
            insert(probe_reports).values(
                probe_id=PROBE_ID,
                session_id=SESSION_ID,
                probe_type="skill",
                probe_object="deep-research",
                object_version="v2.0.0",
                attribute_type="rule",
                probe_description="索引读取未校验快照字段",
                probe_analysis=(
                    "读取前未校验快照字段；同批次带校验的 subagent 未报错，"
                    "属步骤缺失。最小配置修复：启用 snapshotFieldCheckEnabled。"
                ),
                created_at=NOW,
                updated_at=NOW,
            ),
        )
        await session.execute(
            insert(bad_case_analysis).values(
                bad_case_id=BAD_CASE_ID,
                analysis_status="attributed",
                probe_id=PROBE_ID,
                updated_at=NOW,
            ),
        )
        await session.execute(
            insert(probe_clusters).values(
                probe_cluster_id=CLUSTER_ID,
                run_id=RUN_ID,
                seq=1,
                probe_cluster_description="检索索引读取失败",
                probe_cluster_type="error",
                confidence=0.9,
                impact=0.8,
                severity=0.8,
                rank=1,
                created_at=NOW,
            ),
        )
        await session.execute(
            insert(probe_cluster_probes).values(
                probe_cluster_id=CLUSTER_ID,
                probe_id=PROBE_ID,
            ),
        )
        await session.execute(
            insert(evolution_rounds).values(
                id=ROUND_ID,
                run_id=RUN_ID,
                probe_cluster_id=CLUSTER_ID,
                seq=1,
                status="pending",
            ),
        )
    try:
        yield database, repository, probes, bare, seed, base_commit
    finally:
        await database.dispose()


def _job(kind: str, payload: dict[str, Any], run_id: str = RUN_ID) -> JobRunRecord:
    return JobRunRecord(
        id=f"job-{kind}",
        kind=kind,
        ref_id=run_id,
        status="running",
        progress=0.0,
        executor="e2e",
        external_job_id=None,
        attempt=1,
        payload=payload,
        result=None,
        error=None,
        created_by=None,
        created_at=NOW,
        started_at=None,
        finished_at=None,
        updated_at=NOW,
    )


def _evidence(path: str | None, payload: dict[str, Any]) -> None:
    """Optionally dump the traceable evidence summary for the report file."""
    if not path:
        return
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


async def _prepare_workspace(
    repository: EvolutionRepository,
    workspaces: GitWorkspaceManager,
    base_commit: str,
) -> Any:
    """Run the real prepare step and persist its snapshot like production."""
    run = await repository.get_run(RUN_ID)
    assert run is not None
    prepared = await workspaces.prepare(run)
    await repository.mark_prepared(
        RUN_ID,
        status="running",
        progress_unit=5,
        repo_path=str(prepared.repo_path),
        base_ref="v2.0.0",
        base_commit=prepared.base_commit,
        branch_name=prepared.branch,
        workspace_path=str(prepared.path),
        stats={},
    )
    return await repository.get_run(RUN_ID)


def _gateway_for_run(
    tmp_path: Path,
    base_url: str,
    env: dict[str, str],
) -> Any:
    """Bind the mode-driven factory the same way the composition root does."""
    factory = build_eval_gateway_factory(_settings(tmp_path, base_url))

    def resolve(run: Any) -> Any:
        return factory(
            EvalGatewayConfig.from_mapping(run.eval_config),
            env=env,
        )

    return resolve


async def _drive_accept_loop(
    tmp_path: Path,
    loop_state: tuple[Any, ...],
    evidence_out: str | None = None,
) -> dict[str, Any]:
    """Run the whole accept loop end to end and collect traceable evidence."""
    _database, repository, probes, bare, _seed, base_commit = loop_state
    platform = StubEvalPlatform(status_sequence=["completed"])
    server, stub_url = platform.build()
    env = {API_KEY_REF: "stub-secret-value"}
    eval_config = {
        "mode": "http",
        "baseUrl": stub_url,
        "apiKeyRef": API_KEY_REF,
    }
    try:
        workspaces = GitWorkspaceManager(
            repos_root=tmp_path / "repos",
            workspaces_root=tmp_path / "workspaces",
            push_enabled=True,
        )
        run = await _prepare_workspace(repository, workspaces, base_commit)
        await repository.update_run_eval_config(RUN_ID, eval_config)
        candidates = EvolutionCandidateService(
            repository,
            workspaces,
            patch_source_factory=lambda _run: MinimalConfigPatchSource(),
        )
        gateway_for_run = _gateway_for_run(tmp_path, stub_url, env)
        submitter = EvolutionEvalSubmitter(
            repository,
            gateway_for_run,
            events=None,
            now=lambda: datetime.now(SH),
            poll_interval=timedelta(seconds=1),
        )
        advance = EvolutionAdvanceService(repository, candidates, probes, submitter)
        advanced = await advance.handle(_job("evolution_advance", {"runId": RUN_ID}))
        assert advanced["published"] is True
        round_ = await repository.get_round(ROUND_ID)
        assert round_ is not None
        candidate_ref = round_.candidate_ref
        candidate_commit = round_.candidate_commit
        assert candidate_ref and candidate_commit
        assert round_.push_status == "succeeded"
        assert round_.eval_external_id == "eval-e2e-1"

        # The candidate tag really exists on the bare remote at this commit.
        assert git(bare, "rev-parse", f"refs/tags/{candidate_ref}") == candidate_commit
        pushed_config = git(
            bare,
            "show",
            f"{candidate_commit}:skills/deep-research/config/deep-research.json",
        )
        assert json.loads(pushed_config) == {
            "maxRetries": 2,
            "snapshotFieldCheckEnabled": True,
        }
        trailers = round_.candidate_message
        assert f"Harness-Run-Id: {RUN_ID}" in trailers
        assert f"Harness-Cluster-Id: {CLUSTER_ID}" in trailers
        assert f"Harness-Bad-Cases: {BAD_CASE_ID}" in trailers
        assert f"Harness-Probes: {PROBE_ID}" in trailers

        jobs: list[tuple[str, Mapping[str, Any]]] = []

        class CapturingJobs:
            async def submit(
                self,
                *,
                kind: str,
                payload: Mapping[str, Any],
                ref_id: str | None,
                created_by: str | None,
            ) -> JobRunRecord:
                jobs.append((kind, dict(payload)))
                return _job(kind, dict(payload))

        poller = EvolutionEvalPoller(
            repository,
            gateway_for_run,
            CapturingJobs(),
            events=None,
            poll_interval=timedelta(seconds=1),
            timeout=timedelta(hours=2),
            now=lambda: datetime.now(SH) + timedelta(seconds=5),
        )
        await poller.run_once()
        round_ = await repository.get_round(ROUND_ID)
        assert round_ is not None
        assert round_.eval_status == "completed"
        assert round_.eval_result is not None
        assert any(kind == "evolution_apply" for kind, _payload in jobs)

        apply_service = EvolutionApplyService(repository, candidates, probes)
        applied = await apply_service.handle(
            _job("evolution_apply", {"evolutionRoundId": ROUND_ID}),
        )
        assert applied["applied"] is True
        assert applied["accepted"] is True
        round_ = await repository.get_round(ROUND_ID)
        assert round_ is not None and round_.status == "accepted"
        final_commit = round_.commit_hash
        final_message = round_.commit_message or ""
        assert final_commit
        assert "为什么接纳" in final_message

        # Acceptance rewrote the run branch on the remote and removed the tag.
        assert git(bare, "rev-parse", f"refs/heads/{run.branch_name}") == final_commit
        remote_tags = git(bare, "tag", "--list", f"{candidate_ref}")
        assert remote_tags == ""

        finalize = EvolutionFinalizeService(repository, workspaces)
        finished = await finalize.handle(_job("evolution_finalize", {"runId": RUN_ID}))
        assert finished["finalized"] is True
        run = await repository.get_run(RUN_ID)
        assert run is not None and run.status == "completed"
        final_row = await repository.get_final(RUN_ID)
        assert final_row is not None and final_row.verdict is True

        evidence = {
            "loop": "accept",
            "runId": RUN_ID,
            "clusterId": CLUSTER_ID,
            "probeId": PROBE_ID,
            "badCaseId": BAD_CASE_ID,
            "sessionId": SESSION_ID,
            "candidateRef": candidate_ref,
            "candidateCommit": candidate_commit,
            "patchFile": round_.patch.get("file") if isinstance(round_.patch, dict) else None,
            "patchNote": round_.patch.get("note") if isinstance(round_.patch, dict) else None,
            "evalExternalId": round_.eval_external_id,
            "evalResult": round_.eval_result,
            "accepted": True,
            "finalCommit": final_commit,
            "runBranch": run.branch_name,
            "remoteRefs": {
                "runBranch": git(bare, "rev-parse", f"refs/heads/{run.branch_name}"),
                "candidateTag": git(bare, "tag", "--list", candidate_ref) or None,
            },
            "finalVerdict": final_row.verdict,
            "evalReceivedBodies": platform.received_bodies,
            "evalReceivedAuth": platform.received_auth,
        }
        _evidence(evidence_out, evidence)
        return evidence
    finally:
        server.shutdown()


async def test_real_loop_accept_path_is_fully_traceable(
    tmp_path: Path,
    loop_state: tuple[Any, ...],
) -> None:
    """The accept loop leaves a complete run/cluster/probe/bad_case trail."""
    evidence = await _drive_accept_loop(
        tmp_path,
        loop_state,
        evidence_out=os.environ.get("HE_M12_03_EVIDENCE_OUT"),
    )

    assert evidence["candidateRef"] == f"evo/20261117-{RUN_ID}/candidate/r1"
    assert evidence["remoteRefs"]["runBranch"] == evidence["finalCommit"]
    assert evidence["remoteRefs"]["candidateTag"] is None
    assert evidence["evalResult"]["externalVerdict"] == "accept"
    assert evidence["evalReceivedAuth"] == ["Bearer stub-secret-value"]
    body = evidence["evalReceivedBodies"][0]
    assert body["idempotencyKey"] == f"{RUN_ID}:1:" + evidence["candidateCommit"]
    assert body["ref"] == evidence["candidateRef"]


async def test_real_loop_reject_path_keeps_run_branch_untouched(
    tmp_path: Path,
    loop_state: tuple[Any, ...],
) -> None:
    """Rejection deletes the candidate ref and never rewrites the run branch."""
    _database, repository, probes, bare, _seed, base_commit = loop_state
    platform = StubEvalPlatform(
        status_sequence=["completed"],
        result_payload={
            "currentScore": 82.0,
            "candidateScore": 79.0,
            "externalVerdict": "reject",
            "metrics": [],
        },
    )
    server, stub_url = platform.build()
    env = {API_KEY_REF: "stub-secret-value"}
    eval_config = {"mode": "http", "baseUrl": stub_url, "apiKeyRef": API_KEY_REF}
    try:
        workspaces = GitWorkspaceManager(
            repos_root=tmp_path / "repos",
            workspaces_root=tmp_path / "workspaces",
            push_enabled=True,
        )
        run = await _prepare_workspace(repository, workspaces, base_commit)
        await repository.update_run_eval_config(RUN_ID, eval_config)
        from app.service.evolution.patch_source import MinimalConfigPatchSource

        candidates = EvolutionCandidateService(
            repository,
            workspaces,
            patch_source_factory=lambda _run: MinimalConfigPatchSource(),
        )
        gateway_for_run = _gateway_for_run(tmp_path, stub_url, env)
        submitter = EvolutionEvalSubmitter(
            repository,
            gateway_for_run,
            events=None,
            now=lambda: datetime.now(SH),
            poll_interval=timedelta(seconds=1),
        )
        advance = EvolutionAdvanceService(repository, candidates, probes, submitter)
        advanced = await advance.handle(_job("evolution_advance", {"runId": RUN_ID}))
        assert advanced["published"] is True
        round_ = await repository.get_round(ROUND_ID)
        assert round_ is not None
        candidate_ref = round_.candidate_ref
        assert candidate_ref
        assert git(bare, "rev-parse", f"refs/tags/{candidate_ref}") == round_.candidate_commit
        assert "Harness-Run-Id: " + RUN_ID in round_.candidate_message

        poller = EvolutionEvalPoller(
            repository,
            gateway_for_run,
            _NoJobs(),
            events=None,
            poll_interval=timedelta(seconds=1),
            timeout=timedelta(hours=2),
            now=lambda: datetime.now(SH) + timedelta(seconds=5),
        )
        await poller.run_once()
        apply_service = EvolutionApplyService(repository, candidates, probes)
        applied = await apply_service.handle(
            _job("evolution_apply", {"evolutionRoundId": ROUND_ID}),
        )
        assert applied["accepted"] is False
        reason = applied.get("reason") or ""
        assert "拒绝" in reason
        round_ = await repository.get_round(ROUND_ID)
        assert round_ is not None and round_.status == "rejected"

        # The remote lost the candidate tag and its run branch is untouched
        # (prepare pushed it at base_commit; rejection must not rewrite it).
        assert git(bare, "tag", "--list", candidate_ref) == ""
        assert git(bare, "rev-parse", f"refs/heads/{run.branch_name}") == base_commit

        finalize = EvolutionFinalizeService(repository, workspaces)
        finished = await finalize.handle(_job("evolution_finalize", {"runId": RUN_ID}))
        assert finished["finalized"] is True
        run = await repository.get_run(RUN_ID)
        assert run is not None and run.status == "completed"
        final_row = await repository.get_final(RUN_ID)
        assert final_row is not None
        assert final_row.verdict is False
    finally:
        server.shutdown()


class _NoJobs:
    """Job seam that records submissions without scheduling anything."""

    async def submit(self, **kwargs: Any) -> None:
        """Absorb one follow-up submission."""
        return None
