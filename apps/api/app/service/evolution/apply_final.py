"""Apply gated evaluation verdicts and finalize an evolution run."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn, Protocol

from app.db.crud.evolution import EvolutionRepository
from app.db.crud.probe_query import ProbeHitRow
from app.db.models.evolution import (
    EvolutionEvaluationRecord,
    EvolutionRoundRecord,
    EvolutionRunRecord,
)
from app.db.models.jobs import JobRunRecord
from app.service.evolution.advance import build_candidate_trace
from app.service.evolution.backoff import next_retry_at
from app.service.evolution.control import checkpoint
from app.service.evolution.engine.contracts import (
    EvalMeasurement,
    EvalResult,
    RunBlocked,
)
from app.service.evolution.eval_gate import (
    decision_sentence,
    gate_measurement,
)
from app.service.evolution.events import EvolutionRunEventService
from app.service.evolution.git_candidate import (
    CandidateTrace,
    EvolutionCandidateService,
    build_no_acceptance_message,
)
from app.service.evolution.git_failures import classify_git_failure
from app.third_party_api.git.workspace import (
    GitOperationError,
    GitWorkspaceManager,
    PreparedWorkspace,
)
from app.utils.redaction import sanitize_message
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)


class ProbeSourceReader(Protocol):
    """Load complete source rows for an evaluated round trace."""

    async def list_rows_by_ids(self, probe_ids: Sequence[str]) -> tuple[ProbeHitRow, ...]:
        """Return source evidence for selected probes."""


class EvolutionApplyService:
    """Apply one completed placeholder evaluation through the real candidate boundary."""

    def __init__(
        self,
        runs: EvolutionRepository,
        candidates: EvolutionCandidateService,
        probes: ProbeSourceReader,
        *,
        events: EvolutionRunEventService | None = None,
        now: Any = now_shanghai,
    ) -> None:
        """Bind durable evaluation, candidate publication, and trace evidence."""
        self._runs = runs
        self._candidates = candidates
        self._probes = probes
        self._events = events
        self._now = now

    async def handle(self, job: JobRunRecord) -> Mapping[str, Any]:
        """Accept or reject one evaluated candidate exactly once."""
        round_id = str(
            job.payload.get("evolutionRoundId") or job.payload.get("evolution_round_id") or "",
        )
        if not round_id:
            raise ValueError("apply job requires an evolution round id")
        round_ = await self._runs.get_round(round_id)
        if round_ is None:
            raise LookupError("evolution round not found")
        run = await self._runs.get_run(round_.run_id)
        if run is None:
            raise LookupError("evolution run not found")
        if run.status == "interrupted":
            await self._runs.mark_recovered(run.id)
            refreshed = await self._runs.get_run(run.id)
            if refreshed is not None:
                run = refreshed
        if round_.status in {"accepted", "rejected"}:
            return {
                "runId": run.id,
                "roundId": round_.id,
                "status": round_.status,
                "applied": False,
                "reason": "round already decided",
            }
        if run.mode != "full" or run.status != "running":
            return {
                "runId": run.id,
                "roundId": round_.id,
                "status": run.status,
                "applied": False,
                "reason": "run is not ready to apply an evaluation",
            }
        if round_.eval_status != "completed" or round_.eval_result is None:
            raise ValueError("apply job requires a completed durable evaluation result")
        legacy = _legacy_result(round_.eval_result)
        if legacy is not None:
            result = legacy
            accepted = result.external_verdict == "accept"
            reason = decision_sentence(result, accepted=accepted)
            gated = result.to_payload()
        else:
            measurement = EvalMeasurement.from_payload(round_.eval_result)
            baseline = await self._validation_baseline(run, round_)
            if baseline is None:
                return {
                    "runId": run.id,
                    "roundId": round_.id,
                    "status": round_.status,
                    "applied": False,
                    "reason": "validation baseline is not ready",
                }
            decision = gate_measurement(
                measurement,
                baseline_score=baseline[0],
                baseline_label=baseline[1],
            )
            result = decision.result
            accepted = decision.accepted
            reason = decision.reason
            gated = result.to_payload()
        trace = await self._trace(run, round_)
        await checkpoint(self._runs, run.id)
        if accepted:
            decided = await self._candidates.accept(
                run,
                round_,
                trace,
                current_score=result.current_score,
                candidate_score=result.candidate_score,
                reason=reason,
                job_id=job.id,
                retry_attempts=_job_retry_attempts(job),
                eval_result=gated,
            )
        else:
            decided = await self._candidates.reject(
                run,
                round_,
                reason=reason,
                job_id=job.id,
                eval_result=gated,
            )
        return {
            "runId": run.id,
            "roundId": decided.id,
            "status": decided.status,
            "accepted": accepted,
            "reason": reason,
            "applied": True,
        }

    async def _validation_baseline(
        self,
        run: EvolutionRunRecord,
        round_: EvolutionRoundRecord,
    ) -> tuple[float, str] | None:
        """Return the latest accepted candidate score, else the validation baseline."""
        rounds = await self._runs.list_rounds(run.id)
        accepted = [
            item for item in rounds if item.accepted and item.commit_hash and item.seq < round_.seq
        ]
        if accepted:
            latest = max(accepted, key=lambda item: item.seq)
            if latest.eval_result is not None:
                result = _legacy_result(latest.eval_result) or _measurement_result(
                    latest.eval_result,
                )
                if result is not None:
                    return result.candidate_score, f"第 {latest.seq} 轮已接纳候选分"
        baseline = await self._runs.get_run_evaluation(run.id, "validation_baseline")
        if baseline is None or baseline.eval_status != "completed" or baseline.eval_score is None:
            return None
        return baseline.eval_score, "验证集基线分"

    async def _trace(
        self,
        run: EvolutionRunRecord,
        round_: EvolutionRoundRecord,
    ) -> CandidateTrace:
        """Reconstruct the complete immutable trace from persisted evidence."""
        cluster = next(
            (
                item
                for item in await self._runs.list_clusters(run.id)
                if item.probe_cluster_id == round_.probe_cluster_id
            ),
            None,
        )
        if cluster is None:
            raise LookupError("round cluster not found")
        links = tuple(
            link.probe_id
            for link in await self._runs.list_cluster_probes(run.id)
            if link.probe_cluster_id == cluster.probe_cluster_id
        )
        rows = await self._probes.list_rows_by_ids(links)
        return build_candidate_trace(
            cluster.probe_cluster_id,
            cluster.probe_cluster_description,
            links,
            rows,
        )


class RunEvalFinalizer(Protocol):
    """Submit the held-out test-set evaluations that close one run."""

    async def submit_validation_baseline(self, run: EvolutionRunRecord) -> None:
        """Ensure the validation baseline exists for legacy runs."""

    async def submit_test_evaluations(self, run: EvolutionRunRecord) -> None:
        """Submit the test-set baseline and final together exactly once."""


class EvolutionFinalizeService:
    """Build the terminal final, publish the run branch, and finish the run."""

    def __init__(
        self,
        runs: EvolutionRepository,
        workspaces: GitWorkspaceManager,
        *,
        events: EvolutionRunEventService | None = None,
        eval_submitter: RunEvalFinalizer | None = None,
        now: Any = now_shanghai,
    ) -> None:
        """Bind durable finals, git publication, evaluation, and events."""
        self._runs = runs
        self._workspaces = workspaces
        self._events = events
        self._eval_submitter = eval_submitter
        self._now = now

    async def handle(self, job: JobRunRecord) -> Mapping[str, Any]:
        """Finalize only after every round reached a terminal decision."""
        run_id = job.ref_id or str(job.payload.get("runId") or "")
        run = await self._runs.get_run(run_id)
        if run is None:
            raise LookupError("evolution run not found")
        if run.mode != "full":
            return {
                "runId": run.id,
                "status": run.status,
                "finalized": False,
                "reason": "cluster-only runs do not have a final evaluation",
            }
        if run.status == "completed":
            return {
                "runId": run.id,
                "status": run.status,
                "finalized": False,
                "reason": "run is already complete",
            }
        if run.status == "interrupted":
            await self._runs.mark_recovered(run.id)
            refreshed = await self._runs.get_run(run.id)
            if refreshed is not None:
                run = refreshed
        if run.status != "running":
            return {
                "runId": run.id,
                "status": run.status,
                "finalized": False,
                "reason": "run is not ready to finalize",
            }
        rounds = await self._runs.list_rounds(run.id)
        if any(round_.status not in {"accepted", "rejected", "skipped"} for round_ in rounds):
            return {
                "runId": run.id,
                "status": run.status,
                "finalized": False,
                "reason": "rounds are still active",
            }
        retry_attempts = _job_retry_attempts(job)
        accepted_commits = [round_ for round_ in rounds if round_.accepted and round_.commit_hash]
        if self._eval_submitter is not None:
            await self._eval_submitter.submit_validation_baseline(run)
            if not accepted_commits:
                # A legacy no-acceptance run may already have a test final in
                # flight or completed on base_commit; keep that target instead
                # of adding an unused result commit to the run branch.
                existing_final = await self._runs.get_run_evaluation(run.id, "test_final")
                if existing_final is None or existing_final.eval_external_id is None:
                    run = await self._ensure_result_commit(run, rounds, retry_attempts)
            await self._eval_submitter.submit_test_evaluations(run)
            if not await self._test_evaluations_completed(run.id):
                return {
                    "runId": run.id,
                    "status": run.status,
                    "finalized": False,
                    "reason": "test-set evaluations are pending",
                }
        await checkpoint(self._runs, run.id)
        try:
            final = await self._runs.get_final(run.id) or await self._runs.write_final(
                await self._final_values(run, rounds),
            )
            prepared = _prepared_workspace(run)
        except Exception as exc:
            await self._raise_final_failure(run, exc, retry_attempts)
        await checkpoint(self._runs, run.id)
        try:
            await self._workspaces.publish_run_branch(
                prepared,
                run,
                expected_run_id=run.id,
                require_trailer=bool(accepted_commits) or run.result_commit is not None,
            )
        except GitOperationError as exc:
            await self._raise_push_failure(run, exc, retry_attempts)
        push_status = "succeeded" if self._workspaces.push_enabled else "skipped"
        completed = await self._runs.complete_run(
            run.id,
            finished_at=self._now(),
            push_status=push_status,
        )
        await self._record(
            run.id,
            message="运行终评已完成",
            job_id=job.id,
            payload={
                "verdict": final.verdict,
                "bestVersion": final.best_version,
                "bestScore": final.best_score,
                "initScore": final.init_score,
                "pushStatus": push_status,
            },
        )
        return {
            "runId": completed.id,
            "status": completed.status,
            "finalized": True,
            "pushStatus": push_status,
        }

    async def _final_values(
        self,
        run: EvolutionRunRecord,
        rounds: Sequence[EvolutionRoundRecord],
    ) -> Mapping[str, Any]:
        """Prefer the held-out test-set baseline and final over round rollups."""
        baseline = await self._runs.get_run_evaluation(run.id, "test_baseline")
        test_final = await self._runs.get_run_evaluation(run.id, "test_final")
        if (
            baseline is None
            or test_final is None
            or baseline.eval_status != "completed"
            or test_final.eval_status != "completed"
            or baseline.eval_score is None
            or test_final.eval_score is None
        ):
            return _final_values(run, rounds)
        return _test_final_values(run, rounds, baseline, test_final)

    async def _ensure_result_commit(
        self,
        run: EvolutionRunRecord,
        rounds: Sequence[EvolutionRoundRecord],
        retry_attempts: int,
    ) -> EvolutionRunRecord:
        """Create and persist the no-acceptance result commit exactly once.

        The empty commit changes no skill file, records the pre-test terminal
        facts, and is pushed before the test-set final is submitted so the
        evaluation platform can read it.
        """
        if run.result_commit:
            return run
        try:
            prepared = _prepared_workspace(run)
            init_score, best_score, direction, metrics = _no_acceptance_facts(run, rounds)
            message = build_no_acceptance_message(
                run,
                rounds,
                init_score=init_score,
                best_score=best_score,
                direction=direction,
                metrics=metrics,
            )
            commit = await self._workspaces.ensure_result_commit(
                prepared,
                run_id=run.id,
                message=message,
            )
            return await self._runs.record_result_commit(run.id, commit)
        except GitOperationError as exc:
            await self._raise_push_failure(run, exc, retry_attempts)
        except Exception as exc:
            await self._raise_final_failure(run, exc, retry_attempts)

    async def _test_evaluations_completed(self, run_id: str) -> bool:
        """Return whether both held-out test-set evaluations finished."""
        for kind in ("test_baseline", "test_final"):
            evaluation = await self._runs.get_run_evaluation(run_id, kind)
            if evaluation is None or evaluation.eval_status != "completed":
                return False
        return True

    async def _raise_push_failure(
        self,
        run: EvolutionRunRecord,
        exc: GitOperationError,
        retry_attempts: int,
    ) -> NoReturn:
        """Persist one push failure with its retry classification and raise."""
        disposition = classify_git_failure(exc)
        message = sanitize_message(str(exc), limit=2_000)
        retry_at = next_retry_at(self._now(), retry_attempts) if exc.retryable else None
        await self._runs.mark_blocked(
            run.id,
            stage="push",
            message=message,
            error_stage=disposition.error_stage,
            next_retry_at=retry_at,
            retry_attempts=retry_attempts,
        )
        raise RunBlocked(
            message,
            stage="push",
            error_stage=disposition.error_stage,
            next_retry_at=retry_at,
            retry_attempts=retry_attempts,
            retryable=exc.retryable,
            detail=exc.detail,
        ) from None

    async def _raise_final_failure(
        self,
        run: EvolutionRunRecord,
        exc: Exception,
        retry_attempts: int,
    ) -> NoReturn:
        """Persist one non-git finalization failure and raise the stable error."""
        message = sanitize_message(str(exc), limit=2_000)
        await self._runs.mark_blocked(
            run.id,
            stage="push",
            message=message,
            error_stage="final",
            next_retry_at=None,
            retry_attempts=retry_attempts,
        )
        raise RunBlocked(
            message,
            stage="push",
            error_stage="final",
            next_retry_at=None,
            retry_attempts=retry_attempts,
            retryable=False,
        ) from None

    async def _record(
        self,
        run_id: str,
        *,
        message: str,
        job_id: str,
        payload: Mapping[str, Any],
    ) -> None:
        """Record best-effort final evidence after the run is durably complete."""
        if self._events is None:
            return
        try:
            await self._events.record(
                run_id,
                "final_completed",
                level="info",
                stage="final",
                message=message,
                job_id=job_id,
                payload=payload,
            )
        except Exception:
            logger.exception(
                "failed to record final completion event",
                extra={"run_id": run_id},
            )


def _job_retry_attempts(job: JobRunRecord) -> int:
    """Read the retry counter a recovery job carries into finalization."""
    raw = job.payload.get("retryAttempts")
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return 0
    return raw


def _legacy_result(payload: Mapping[str, Any] | None) -> EvalResult | None:
    """Read a pre-gate verdict payload written before baseline gating existed."""
    if payload is None or "externalVerdict" not in payload:
        return None
    if "primaryMetricKey" in payload:
        return None
    return EvalResult.from_payload(payload)


def _measurement_result(payload: Mapping[str, Any] | None) -> EvalResult | None:
    """Project one measurement into the same score shape the UI reads."""
    if payload is None or "primaryMetricKey" not in payload:
        return None
    measurement = EvalMeasurement.from_payload(payload)
    return EvalResult(
        current_score=measurement.candidate_score,
        candidate_score=measurement.candidate_score,
        external_verdict="accept",
        metrics=measurement.metrics,
        direction=measurement.direction,
    )


def _no_acceptance_facts(
    run: EvolutionRunRecord,
    rounds: Sequence[EvolutionRoundRecord],
) -> tuple[float, float, str, list[dict[str, Any]]]:
    """Summarize the validation scores recorded before the test-set final."""
    evaluated: list[tuple[float, float]] = []
    direction = "higher_is_better"
    for round_ in rounds:
        payload = round_.eval_result
        if payload is None:
            continue
        current = payload.get("currentScore")
        candidate = payload.get("candidateScore")
        if (
            isinstance(current, bool)
            or not isinstance(current, (int, float))
            or isinstance(candidate, bool)
            or not isinstance(candidate, (int, float))
        ):
            continue
        if not evaluated:
            stored = payload.get("direction")
            if stored in {"higher_is_better", "lower_is_better"}:
                direction = stored
        evaluated.append((float(current), float(candidate)))
    init_score = evaluated[0][0] if evaluated else 0.0
    candidates = [candidate for _current, candidate in evaluated]
    best_score = (
        max((init_score, *candidates))
        if direction == "higher_is_better"
        else min((init_score, *candidates))
    )
    metric_key = run.eval_config.get("primaryMetricKey")
    name = metric_key.strip() if isinstance(metric_key, str) and metric_key.strip() else "score"
    metrics = [
        {
            "name": name,
            "init": init_score,
            "best": best_score,
            "delta": best_score - init_score,
            "unit": "",
            "direction": direction,
        },
    ]
    return init_score, best_score, direction, metrics


def _final_values(
    run: EvolutionRunRecord,
    rounds: Sequence[EvolutionRoundRecord],
) -> Mapping[str, Any]:
    """Build deterministic final metrics from completed round evaluations."""
    evaluated = [
        (round_, EvalResult.from_payload(round_.eval_result))
        for round_ in rounds
        if round_.eval_result is not None
    ]
    initial = evaluated[0][1].current_score if evaluated else 0.0
    accepted_scores = [result.candidate_score for round_, result in evaluated if round_.accepted]
    best = max((initial, *accepted_scores))
    metrics = []
    for round_, result in evaluated:
        metrics.append(
            {
                "round": round_.seq,
                "currentScore": result.current_score,
                "candidateScore": result.candidate_score,
                "delta": result.candidate_score - result.current_score,
                "accepted": round_.accepted,
                "candidateCommit": round_.candidate_commit,
                "finalCommit": round_.commit_hash,
            },
        )
    return {
        "run_id": run.id,
        "best_version": run.target_version,
        "verdict": bool(accepted_scores) and best > initial,
        "best_score": best,
        "init_score": initial,
        "metrics": metrics,
    }


def _test_final_values(
    run: EvolutionRunRecord,
    rounds: Sequence[EvolutionRoundRecord],
    baseline: EvolutionEvaluationRecord,
    test_final: EvolutionEvaluationRecord,
) -> Mapping[str, Any]:
    """Build the final row from the held-out test-set baseline and final."""
    init_score = float(baseline.eval_score or 0.0)
    best_score = float(test_final.eval_score or 0.0)
    direction = _measurement_direction(test_final.eval_result)
    accepted = any(round_.accepted for round_ in rounds)
    verdict = accepted and (
        best_score > init_score if direction == "higher_is_better" else best_score < init_score
    )
    metric_key = run.eval_config.get("primaryMetricKey")
    name = metric_key.strip() if isinstance(metric_key, str) and metric_key.strip() else "score"
    metrics: list[dict[str, Any]] = [
        {
            "name": name,
            "init": init_score,
            "best": best_score,
            "delta": best_score - init_score,
            "unit": "",
            "direction": direction,
        },
    ]
    return {
        "run_id": run.id,
        "best_version": run.target_version,
        "verdict": bool(verdict),
        "best_score": best_score,
        "init_score": init_score,
        "metrics": metrics,
    }


def _measurement_direction(payload: Mapping[str, Any] | None) -> str:
    """Read the metric direction from a persisted measurement payload."""
    if payload is None:
        return "higher_is_better"
    direction = payload.get("direction")
    return direction if direction in {"higher_is_better", "lower_is_better"} else "higher_is_better"


def _prepared_workspace(run: EvolutionRunRecord) -> PreparedWorkspace:
    """Reconstruct the prepared workspace snapshot persisted by m5-09."""
    if (
        run.workspace_path is None
        or run.repo_path is None
        or run.branch_name is None
        or run.base_commit is None
    ):
        raise ValueError("run has no prepared workspace")
    return PreparedWorkspace(
        repo_path=Path(run.repo_path),
        path=Path(run.workspace_path),
        ref=run.base_ref or run.target_version,
        base_commit=run.base_commit,
        branch=run.branch_name,
        push_url=(run.push_repo_url or None),
    )


__all__ = [
    "EvolutionApplyService",
    "EvolutionFinalizeService",
    "decision_sentence",
]
