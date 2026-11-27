"""Durable external-evaluation polling for the placeholder evolution loop."""

# ruff: noqa: RUF001

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, Protocol

from app.db.crud.evolution import EvolutionRepository
from app.db.models.evolution import (
    EvolutionEvaluationRecord,
    EvolutionRoundRecord,
    EvolutionRunRecord,
)
from app.errors import AppError, ErrorCode
from app.service.evolution.control import checkpoint
from app.service.evolution.engine.contracts import (
    EVAL_PURPOSES,
    EvalGateway,
    EvalPurpose,
    EvalRequest,
    EvalTarget,
    RunBlocked,
)
from app.service.evolution.events import EvolutionRunEventService
from app.utils.redaction import sanitize_message, sanitize_value
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)


class EvalJobSubmitter(Protocol):
    """Follow-up job queue used when an evaluation reaches a terminal state."""

    async def submit(
        self,
        *,
        kind: str,
        payload: Mapping[str, Any],
        ref_id: str | None,
        created_by: str | None,
    ) -> object:
        """Persist and schedule one durable job."""


type GatewayResolver = Callable[[EvolutionRunRecord], EvalGateway]


class EvolutionEvalSubmitter:
    """Submit one published candidate using the run's immutable gateway snapshot."""

    def __init__(
        self,
        runs: EvolutionRepository,
        gateway_for_run: GatewayResolver,
        *,
        events: EvolutionRunEventService | None,
        now: Callable[[], datetime] = now_shanghai,
        poll_interval: timedelta = timedelta(minutes=5),
    ) -> None:
        """Bind persistence, gateway resolution, and the durable poll cadence."""
        if poll_interval.total_seconds() <= 0:
            raise ValueError("evaluation poll interval must be positive")
        self._runs = runs
        self._gateway_for_run = gateway_for_run
        self._events = events
        self._now = now
        self._poll_interval = poll_interval

    async def submit(
        self,
        run: EvolutionRunRecord,
        round_: EvolutionRoundRecord,
        *,
        previous_external_id: str | None = None,
    ) -> EvolutionRoundRecord:
        """Submit once, preserving an existing external id across restart."""
        if round_.eval_external_id is not None:
            return round_
        if (
            run.mode != "full"
            or run.status != "running"
            or round_.status != "evaluating"
            or round_.push_status != "succeeded"
            or round_.candidate_ref is None
            or round_.candidate_commit is None
        ):
            return round_
        await checkpoint(self._runs, run.id)
        try:
            # Gateway construction resolves the frozen snapshot config (a missing
            # baseUrl or a dangling apiKeyRef raises EvalGatewayConfigError), so it
            # must share the try with gateway.submit: config errors take the same
            # blocked(stage=eval) semantics as the polling side, keeping /retry
            # reachable instead of escaping into a failed(error_stage="step") run.
            gateway = self._gateway_for_run(run)
            # eval_attempts counts accepted submissions. A transport failure that
            # never received a 202 leaves the counter unchanged, so retrying the
            # same observation reuses the idempotency key and cannot create a
            # second platform run; a confirmed terminal failure is reset after
            # the accepted submission and therefore gets a fresh key.
            attempt = round_.eval_attempts + 1
            parent_commit = await self._parent_commit(run, round_)
            submission = await gateway.submit(
                EvalRequest(
                    run_id=run.id,
                    evolution_round_id=round_.id,
                    repo_url=run.push_repo_url or run.repo_url,
                    ref=round_.candidate_ref,
                    commit=round_.candidate_commit,
                    target_type=run.target_type,
                    target_name=run.target_name,
                    target_version=run.target_version,
                    cluster_id=round_.probe_cluster_id,
                    idempotency_key=(f"{run.id}:{round_.seq}:{round_.candidate_commit}:{attempt}"),
                    purpose="candidate",
                    project_id=_project_id(run, "validation_baseline"),
                    sub_dir=_sub_dir(run),
                    attempt=attempt,
                    round_seq=round_.seq,
                    parent_commit=parent_commit,
                    targets=_eval_targets(run),
                ),
            )
            if not submission.eval_id.strip():
                raise ValueError("evaluation submission returned a blank id")
        except Exception as exc:
            safe = sanitize_message(
                f"evaluation submission failed: {exc}",
                limit=2_000,
            )
            await self._runs.mark_eval_failed(
                run.id,
                round_.id,
                status="failed",
                error=safe,
                finished_at=self._now(),
            )
            await self._record(
                run.id,
                "eval_failed",
                level="error",
                message=safe,
                round_id=round_.id,
                payload={"ref": round_.candidate_ref, "commit": round_.candidate_commit},
                error=exc,
            )
            raise RunBlocked(safe, stage="eval") from None
        current = self._now()
        submitted = await self._runs.mark_eval_submitted(
            run.id,
            round_.id,
            external_id=submission.eval_id,
            started_at=current,
            next_poll_at=current + self._poll_interval,
        )
        payload: dict[str, Any] = {
            "externalId": submission.eval_id,
            "ref": round_.candidate_ref,
            "commit": round_.candidate_commit,
        }
        if submission.warnings:
            payload["warnings"] = list(submission.warnings)
        if previous_external_id is not None:
            payload["previousExternalId"] = previous_external_id
        await self._record(
            run.id,
            "eval_submitted",
            level="info",
            message=f"已提交评测 {submission.eval_id}",
            round_id=round_.id,
            payload=payload,
        )
        return submitted

    async def submit_validation_baseline(self, run: EvolutionRunRecord) -> None:
        """Submit only the validation baseline before the first round starts."""
        if run.mode != "full" or run.status != "running" or not run.base_commit:
            return
        await self._submit_run_evaluation(
            run,
            "validation_baseline",
            commit=run.base_commit,
            ref=run.base_ref or run.base_commit,
        )

    async def submit_test_evaluations(self, run: EvolutionRunRecord) -> None:
        """Submit the held-out test baseline and final together at finalization.

        Both submissions are in flight in parallel: the baseline targets
        ``base_commit`` and the final targets the last accepted round or the
        no-acceptance result commit.
        """
        if run.mode != "full" or run.status != "running" or not run.base_commit:
            return
        await self._submit_run_evaluation(
            run,
            "test_baseline",
            commit=run.base_commit,
            ref=run.base_ref or run.base_commit,
        )
        await self.submit_test_final(run)

    async def submit_test_final(
        self,
        run: EvolutionRunRecord,
    ) -> EvolutionEvaluationRecord:
        """Submit the held-out test-set final at the final run commit."""
        existing = await self._runs.get_run_evaluation(run.id, "test_final")
        if existing is not None and existing.eval_external_id is not None:
            return existing
        final_commit = await self._test_final_commit(run)
        return await self._submit_run_evaluation(
            run,
            "test_final",
            commit=final_commit,
            ref=run.branch_name or final_commit,
        )

    async def _test_final_commit(self, run: EvolutionRunRecord) -> str:
        """Resolve the final evaluation target without falling back to base."""
        rounds = await self._runs.list_rounds(run.id)
        accepted = [round_ for round_ in rounds if round_.accepted and round_.commit_hash]
        if accepted:
            return max(accepted, key=lambda item: item.seq).commit_hash or ""
        if run.result_commit:
            return run.result_commit
        raise RunBlocked(
            "run has no accepted commit or no-acceptance result commit for the test-set final",
            stage="eval",
        )

    async def resubmit_run_evaluation(
        self,
        run: EvolutionRunRecord,
        kind: str,
    ) -> EvolutionEvaluationRecord:
        """Resubmit one cleared run-level evaluation after a manual retry."""
        if kind not in EVAL_PURPOSES:
            raise ValueError(f"unknown run evaluation kind: {kind}")
        purpose: EvalPurpose = kind
        if purpose == "test_final":
            return await self.submit_test_final(run)
        if not run.base_commit:
            raise RunBlocked(
                "run has no base commit for the baseline evaluation",
                stage="eval",
            )
        return await self._submit_run_evaluation(
            run,
            purpose,
            commit=run.base_commit,
            ref=run.base_ref or run.base_commit,
        )

    async def _submit_run_evaluation(
        self,
        run: EvolutionRunRecord,
        kind: EvalPurpose,
        *,
        commit: str,
        ref: str,
    ) -> EvolutionEvaluationRecord:
        """Submit one run-level evaluation, preserving an existing external id."""
        existing = await self._runs.ensure_run_evaluation(run.id, kind)
        if existing.eval_external_id is not None:
            return existing
        await checkpoint(self._runs, run.id)
        # Same rule as round submissions: only accepted submissions advance the
        # attempt count, so a lost acknowledgment retries with the same key.
        attempt = existing.eval_attempts + 1
        try:
            gateway = self._gateway_for_run(run)
            submission = await gateway.submit(
                EvalRequest(
                    run_id=run.id,
                    evolution_round_id="",
                    repo_url=run.push_repo_url or run.repo_url,
                    ref=ref,
                    commit=commit,
                    target_type=run.target_type,
                    target_name=run.target_name,
                    target_version=run.target_version,
                    cluster_id="",
                    idempotency_key=f"{run.id}:{kind}:{commit}:{attempt}",
                    purpose=kind,
                    project_id=_project_id(run, kind),
                    sub_dir=_sub_dir(run),
                    attempt=attempt,
                    targets=_eval_targets(run),
                ),
            )
            if not submission.eval_id.strip():
                raise ValueError("evaluation submission returned a blank id")
        except RunBlocked:
            raise
        except Exception as exc:
            safe = sanitize_message(
                f"{kind} evaluation submission failed: {exc}",
                limit=2_000,
            )
            await self._runs.mark_run_eval_failed(
                existing.id,
                status="failed",
                error=safe,
                finished_at=self._now(),
            )
            await self._runs.mark_blocked(
                run.id,
                stage="eval",
                message=safe,
                error_stage="eval",
                next_retry_at=None,
                retry_attempts=0,
            )
            await self._record(
                run.id,
                "eval_failed",
                level="error",
                message=safe,
                round_id="",
                payload={"kind": kind, "commit": commit},
                error=exc,
            )
            raise RunBlocked(safe, stage="eval") from None
        current = self._now()
        submitted = await self._runs.mark_run_eval_submitted(
            existing.id,
            external_id=submission.eval_id,
            started_at=current,
            next_poll_at=current + self._poll_interval,
        )
        payload: dict[str, Any] = {
            "externalId": submission.eval_id,
            "kind": kind,
            "commit": commit,
            "ref": ref,
        }
        if submission.warnings:
            payload["warnings"] = list(submission.warnings)
        await self._record(
            run.id,
            "eval_submitted",
            level="info",
            message=f"已提交{_evaluation_label(kind)}评测 {submission.eval_id}",
            round_id="",
            payload=payload,
        )
        return submitted

    async def _parent_commit(
        self,
        run: EvolutionRunRecord,
        round_: EvolutionRoundRecord,
    ) -> str:
        """Return the commit the candidate was branched from for lineage."""
        rounds = await self._runs.list_rounds(run.id)
        accepted = [
            item for item in rounds if item.accepted and item.commit_hash and item.seq < round_.seq
        ]
        if accepted:
            return max(accepted, key=lambda item: item.seq).commit_hash or ""
        return run.base_commit or ""

    async def _record(
        self,
        run_id: str,
        event_type: str,
        *,
        level: str,
        message: str,
        round_id: str,
        payload: Mapping[str, Any] | None = None,
        error: BaseException | None = None,
    ) -> None:
        """Persist a best-effort submission event without losing the eval row."""
        if self._events is None:
            return
        try:
            await self._events.record(
                run_id,
                event_type,  # type: ignore[arg-type]
                level=level,  # type: ignore[arg-type]
                stage="eval",
                message=message,
                round_id=round_id,
                payload=payload,
                error=error,
            )
        except Exception:
            logger.exception(
                "failed to record evaluation submission event",
                extra={"run_id": run_id},
            )


class EvolutionEvalPoller:
    """Poll due evaluations without occupying the global JobRunner worker."""

    def __init__(
        self,
        runs: EvolutionRepository,
        gateway_for_run: GatewayResolver,
        jobs: EvalJobSubmitter,
        *,
        events: EvolutionRunEventService | None,
        now: Callable[[], datetime] = now_shanghai,
        scan_interval: timedelta = timedelta(seconds=30),
        poll_interval: timedelta = timedelta(minutes=5),
        timeout: timedelta = timedelta(hours=2),
        batch_size: int = 100,
    ) -> None:
        """Bind persistence, gateway resolution, scheduling, and timing."""
        if scan_interval.total_seconds() <= 0:
            raise ValueError("evaluation scan interval must be positive")
        if poll_interval.total_seconds() <= 0:
            raise ValueError("evaluation poll interval must be positive")
        if timeout.total_seconds() <= 0:
            raise ValueError("evaluation timeout must be positive")
        if batch_size < 1:
            raise ValueError("evaluation batch size must be positive")
        self._runs = runs
        self._gateway_for_run = gateway_for_run
        self._jobs = jobs
        self._events = events
        self._now = now
        self._scan_interval = scan_interval
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._batch_size = batch_size
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the process-local lightweight loop once."""
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self.run_forever(), name="evolution-eval-poller")

    async def stop(self) -> None:
        """Stop the loop and await task cleanup."""
        self._stop.set()
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def run_forever(self) -> None:
        """Scan timers forever until graceful shutdown."""
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("evaluation poller scan failed")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._scan_interval.total_seconds(),
                )
            except TimeoutError:
                continue

    async def run_once(self) -> int:
        """Process one durable due batch and return the number of acted-on rounds."""
        current = self._now()
        due = await self._runs.list_eval_due(current, limit=self._batch_size)
        acted_on: set[tuple[str, str, str | None]] = set()
        for round_ in due:
            try:
                if await self._poll_round(round_, current):
                    acted_on.add(("round", round_.id, None))
            except Exception as exc:
                logger.exception(
                    "evaluation round poll failed",
                    extra={"round_id": round_.id, "run_id": round_.run_id},
                )
                run = await self._runs.get_run(round_.run_id)
                if run is not None:
                    try:
                        await self._fail(
                            run,
                            round_,
                            status="failed",
                            message=f"evaluation poll failed: {exc}",
                            current=current,
                            error=exc,
                        )
                    except Exception:
                        logger.exception(
                            "failed to isolate malformed evaluation round",
                            extra={"round_id": round_.id, "run_id": round_.run_id},
                        )

        for evaluation in await self._runs.list_run_eval_due(
            current,
            limit=self._batch_size,
        ):
            try:
                if await self._poll_run_evaluation(evaluation, current):
                    acted_on.add(("evaluation", evaluation.id, None))
            except Exception as exc:
                logger.exception(
                    "run-level evaluation poll failed",
                    extra={"evaluation_id": evaluation.id, "run_id": evaluation.run_id},
                )
                run = await self._runs.get_run(evaluation.run_id)
                if run is not None:
                    try:
                        await self._fail_run_evaluation(
                            run,
                            evaluation,
                            status="failed",
                            message=f"evaluation poll failed: {exc}",
                            current=current,
                            error=exc,
                        )
                    except Exception:
                        logger.exception(
                            "failed to isolate malformed run evaluation",
                            extra={
                                "evaluation_id": evaluation.id,
                                "run_id": evaluation.run_id,
                            },
                        )

        for round_ in await self._runs.list_eval_followups(limit=self._batch_size):
            run = await self._runs.get_run(round_.run_id)
            if run is None:
                continue
            # A new-format candidate cannot be decided before its validation
            # baseline completes; skip re-enqueueing until then. A legacy run
            # without a baseline row still follows the legacy apply path.
            baseline = await self._runs.get_run_evaluation(
                run.id,
                "validation_baseline",
            )
            if baseline is not None and baseline.eval_status != "completed":
                continue
            if await self._ensure_followup(
                run_id=run.id,
                kind="evolution_apply",
                payload={"evolutionRoundId": round_.id},
                created_by=None,
            ):
                acted_on.add(("round", round_.id, None))

        for run in await self._runs.list_running_full_runs(limit=self._batch_size):
            rounds = await self._runs.list_rounds(run.id)
            if not rounds:
                continue
            active = {
                "patching",
                "pushing",
                "evaluating",
                "deciding",
                "failed",
            }
            if any(round_.status in active for round_ in rounds):
                continue
            pending = any(round_.status == "pending" for round_ in rounds)
            terminal = all(
                round_.status in {"accepted", "rejected", "skipped"} for round_ in rounds
            )
            if not pending and not terminal:
                continue
            if pending:
                kind = "evolution_advance"
            else:
                if not await self._test_evaluations_ready(run.id):
                    continue
                kind = "evolution_finalize"
            if await self._ensure_followup(
                run_id=run.id,
                kind=kind,
                payload={"runId": run.id},
                created_by=run.created_by,
            ):
                acted_on.add(("run", run.id, kind))
        return len(acted_on)

    async def _test_evaluations_ready(self, run_id: str) -> bool:
        """Return whether finalize can progress without a test evaluation in flight.

        A missing row still admits finalize so it can submit both test-set
        evaluations. A row that exists but has no external id is not in flight
        either: it was created but never accepted by the platform, so finalize
        must be able to resubmit it.
        """
        for kind in ("test_baseline", "test_final"):
            evaluation = await self._runs.get_run_evaluation(run_id, kind)
            if (
                evaluation is not None
                and evaluation.eval_external_id is not None
                and evaluation.eval_status != "completed"
            ):
                return False
        return True

    async def _poll_round(
        self,
        round_: EvolutionRoundRecord,
        current: datetime,
    ) -> bool:
        """Poll one round unless it is no longer active or has timed out."""
        run = await self._runs.get_run(round_.run_id)
        if (
            run is None
            or run.mode != "full"
            or run.status != "running"
            or run.push_status == "skipped"
            or round_.eval_external_id is None
        ):
            return False
        try:
            status = await self._gateway_for_run(run).get_status(
                round_.eval_external_id,
            )
            if status.status not in {"queued", "running", "completed", "failed", "timeout"}:
                raise ValueError(f"unknown evaluation status: {status.status}")
        except Exception as exc:
            if await self._defer_retryable(run, round_, exc, current):
                return True
            await self._fail(
                run,
                round_,
                status="failed",
                message=f"evaluation status request failed: {exc}",
                current=current,
                error=exc,
            )
            return True
        if status.status in {"queued", "running"}:
            if await self._expire_if_due(run, round_, current):
                return True
            next_poll = current + self._poll_interval
            await self._runs.mark_eval_waiting(
                round_.id,
                next_poll_at=next_poll,
            )
            await self._record(
                run.id,
                "eval_polled",
                level="info",
                message=f"评测仍在 {status.status}",
                round_id=round_.id,
                payload={
                    "externalId": round_.eval_external_id,
                    "status": status.status,
                    "nextPollAt": next_poll.isoformat(),
                },
            )
            return True
        if status.status == "completed":
            try:
                result = await self._gateway_for_run(run).get_result(
                    round_.eval_external_id,
                )
                result_payload = sanitize_value(result.to_payload())
                if not isinstance(result_payload, Mapping):
                    raise ValueError("sanitized evaluation result is invalid")
                saved = await self._runs.save_eval_result(
                    run.id,
                    round_.id,
                    result=result_payload,
                    finished_at=current,
                )
            except Exception as exc:
                if await self._defer_retryable(run, round_, exc, current):
                    return True
                await self._fail(
                    run,
                    round_,
                    status="failed",
                    message=f"evaluation result request failed: {exc}",
                    current=current,
                    error=exc,
                )
                return True
            if not saved:
                return False
            await self._record(
                run.id,
                "eval_completed",
                level="info",
                message="评测完成，等待应用结果",
                round_id=round_.id,
                payload={
                    "externalId": round_.eval_external_id,
                    **result_payload,
                },
            )
            return True
        await self._fail(
            run,
            round_,
            status=status.status,
            message=status.message or f"evaluation {status.status}",
            current=current,
        )
        return True

    async def _poll_run_evaluation(
        self,
        evaluation: EvolutionEvaluationRecord,
        current: datetime,
    ) -> bool:
        """Poll one run-level evaluation unless its run is no longer active."""
        run = await self._runs.get_run(evaluation.run_id)
        if (
            run is None
            or run.mode != "full"
            or run.status != "running"
            or evaluation.eval_external_id is None
        ):
            return False
        try:
            status = await self._gateway_for_run(run).get_status(
                evaluation.eval_external_id,
            )
            if status.status not in {"queued", "running", "completed", "failed", "timeout"}:
                raise ValueError(f"unknown evaluation status: {status.status}")
        except Exception as exc:
            if await self._defer_run_retryable(run, evaluation, exc, current):
                return True
            await self._fail_run_evaluation(
                run,
                evaluation,
                status="failed",
                message=f"evaluation status request failed: {exc}",
                current=current,
                error=exc,
            )
            return True
        if status.status in {"queued", "running"}:
            if await self._expire_run_if_due(run, evaluation, current):
                return True
            next_poll = current + self._poll_interval
            await self._runs.mark_run_eval_waiting(
                evaluation.id,
                next_poll_at=next_poll,
            )
            await self._record(
                run.id,
                "eval_polled",
                level="info",
                message=f"{_evaluation_label(evaluation.kind)}评测仍在 {status.status}",
                round_id="",
                payload={
                    "externalId": evaluation.eval_external_id,
                    "kind": evaluation.kind,
                    "status": status.status,
                    "nextPollAt": next_poll.isoformat(),
                },
            )
            return True
        if status.status == "completed":
            try:
                measurement = await self._gateway_for_run(run).get_result(
                    evaluation.eval_external_id,
                )
                result_payload = sanitize_value(measurement.to_payload())
                if not isinstance(result_payload, Mapping):
                    raise ValueError("sanitized evaluation result is invalid")
                saved = await self._runs.save_run_eval_result(
                    evaluation.id,
                    result=result_payload,
                    score=measurement.candidate_score,
                    finished_at=current,
                )
            except Exception as exc:
                if await self._defer_run_retryable(run, evaluation, exc, current):
                    return True
                await self._fail_run_evaluation(
                    run,
                    evaluation,
                    status="failed",
                    message=f"evaluation result request failed: {exc}",
                    current=current,
                    error=exc,
                )
                return True
            if not saved:
                return False
            await self._record(
                run.id,
                "eval_completed",
                level="info",
                message=f"{_evaluation_label(evaluation.kind)}评测完成",
                round_id="",
                payload={
                    "externalId": evaluation.eval_external_id,
                    "kind": evaluation.kind,
                    **result_payload,
                },
            )
            return True
        await self._fail_run_evaluation(
            run,
            evaluation,
            status=status.status,
            message=status.message or f"evaluation {status.status}",
            current=current,
        )
        return True

    async def _expire_run_if_due(
        self,
        run: EvolutionRunRecord,
        evaluation: EvolutionEvaluationRecord,
        current: datetime,
    ) -> bool:
        """Charge only active observation time for one run-level evaluation."""
        observed = await self._runs.get_run_evaluation(run.id, evaluation.kind)
        if observed is None or observed.eval_started_at is None:
            return False
        if current - observed.eval_started_at < self._timeout + timedelta(
            seconds=observed.eval_paused_seconds
        ):
            return False
        return await self._fail_run_evaluation(
            run,
            observed,
            status="timeout",
            message="evaluation timed out",
            current=current,
            expected_paused_seconds=observed.eval_paused_seconds,
        )

    async def _defer_run_retryable(
        self,
        run: EvolutionRunRecord,
        evaluation: EvolutionEvaluationRecord,
        exc: BaseException,
        current: datetime,
    ) -> bool:
        """Absorb one retryable run-level polling failure by deferring."""
        if not bool(getattr(exc, "retryable", False)):
            return False
        if await self._expire_run_if_due(run, evaluation, current):
            return True
        next_poll = current + self._poll_interval
        await self._runs.mark_run_eval_waiting(
            evaluation.id,
            next_poll_at=next_poll,
        )
        await self._record(
            run.id,
            "eval_polled",
            level="warn",
            message=f"评测平台暂时不可用，已推迟下一次轮询：{exc}",
            round_id="",
            payload={
                "externalId": evaluation.eval_external_id,
                "kind": evaluation.kind,
                "transient": True,
                "nextPollAt": next_poll.isoformat(),
            },
            error=exc,
        )
        return True

    async def _fail_run_evaluation(
        self,
        run: EvolutionRunRecord,
        evaluation: EvolutionEvaluationRecord,
        *,
        status: str,
        message: str,
        current: datetime,
        error: BaseException | None = None,
        expected_paused_seconds: float | None = None,
    ) -> bool:
        """Persist one run-level failure and block the run at the eval stage."""
        safe = sanitize_message(message, limit=2_000)
        changed = await self._runs.mark_run_eval_failed(
            evaluation.id,
            status=status,
            error=safe,
            finished_at=current,
        )
        if not changed:
            return False
        event_type = "eval_timeout" if status == "timeout" else "eval_failed"
        await self._record(
            run.id,
            event_type,
            level="error",
            message=safe,
            round_id="",
            payload={
                "externalId": evaluation.eval_external_id,
                "kind": evaluation.kind,
                "status": status,
            },
            error=error,
        )
        await self._runs.mark_blocked(
            run.id,
            stage="eval",
            message=safe,
            error_stage="eval",
            next_retry_at=None,
            retry_attempts=0,
        )
        current_run = await self._runs.get_run(run.id)
        if self._events is not None and current_run and current_run.status == "blocked":
            await self._events.record_blocked(
                run.id,
                stage="eval",
                blocked_stage="eval",
                message=safe,
                retry_attempts=0,
                error=error,
            )
        return True

    async def _expire_if_due(
        self, run: EvolutionRunRecord, round_: EvolutionRoundRecord, current: datetime
    ) -> bool:
        """Charge only active observation time, after querying the original external ID."""
        observed = await self._runs.get_round(round_.id)
        if observed is None or observed.eval_started_at is None:
            return False
        if current - observed.eval_started_at < self._timeout + timedelta(
            seconds=observed.eval_paused_seconds
        ):
            return False
        return await self._fail(
            run,
            observed,
            status="timeout",
            message="evaluation timed out",
            current=current,
            expected_paused_seconds=observed.eval_paused_seconds,
        )

    async def _defer_retryable(
        self,
        run: EvolutionRunRecord,
        round_: EvolutionRoundRecord,
        exc: BaseException,
        current: datetime,
    ) -> bool:
        """Absorb one retryable polling failure by deferring the next poll.

        The platform saying "failed" and our poll request failing are different
        facts: the gateway layer flags transport transience (network timeouts,
        connection failures, 5xx/429) with ``retryable`` and this loop only
        consumes the boolean — push ``next_poll_at`` forward and keep waiting,
        still capped by the existing 2h ``eval_timeout`` fallback. Non-retryable
        errors fall through to the caller's existing blocked(stage=eval) path.
        """
        if not bool(getattr(exc, "retryable", False)):
            return False
        if await self._expire_if_due(run, round_, current):
            return True
        next_poll = current + self._poll_interval
        await self._runs.mark_eval_waiting(round_.id, next_poll_at=next_poll)
        await self._record(
            run.id,
            "eval_polled",
            level="warn",
            message=f"评测平台暂时不可用，已推迟下一次轮询：{exc}",
            round_id=round_.id,
            payload={
                "externalId": round_.eval_external_id,
                "transient": True,
                "nextPollAt": next_poll.isoformat(),
            },
            error=exc,
        )
        return True

    async def _fail(
        self,
        run: EvolutionRunRecord,
        round_: EvolutionRoundRecord,
        *,
        status: str,
        message: str,
        current: datetime,
        error: BaseException | None = None,
        expected_paused_seconds: float | None = None,
    ) -> bool:
        """Persist one external failure and its two user-facing events."""
        safe = sanitize_message(message, limit=2_000)
        changed = await self._runs.mark_eval_failed(
            run.id,
            round_.id,
            status=status,
            error=safe,
            finished_at=current,
            expected_paused_seconds=expected_paused_seconds,
        )
        if not changed:
            return False
        event_type = "eval_timeout" if status == "timeout" else "eval_failed"
        await self._record(
            run.id,
            event_type,
            level="error",
            message=safe,
            round_id=round_.id,
            payload={"externalId": round_.eval_external_id, "status": status},
            error=error,
        )
        current_run = await self._runs.get_run(run.id)
        if self._events is not None and current_run and current_run.status == "blocked":
            await self._events.record_blocked(
                run.id,
                stage="eval",
                blocked_stage="eval",
                message=safe,
                retry_attempts=0,
                error=error,
            )
        return True

    async def _ensure_followup(
        self,
        *,
        run_id: str,
        kind: str,
        payload: Mapping[str, Any],
        created_by: str | None,
    ) -> bool:
        """Create a missing durable follow-up while tolerating an already-active stage."""
        try:
            await self._jobs.submit(
                kind=kind,
                payload=payload,
                ref_id=run_id,
                created_by=created_by,
            )
            return True
        except AppError as exc:
            if exc.code == ErrorCode.RUN_BUSY:
                return False
            logger.exception(
                "failed to create evaluation follow-up job",
                extra={"run_id": run_id, "kind": kind},
            )
            return False
        except Exception:
            logger.exception(
                "failed to create evaluation follow-up job",
                extra={"run_id": run_id, "kind": kind},
            )
            return False

    async def _record(
        self,
        run_id: str,
        event_type: str,
        *,
        level: str,
        message: str,
        round_id: str,
        payload: Mapping[str, Any] | None = None,
        error: BaseException | None = None,
    ) -> None:
        """Record one best-effort poller event after durable state is committed."""
        if self._events is None:
            return
        try:
            await self._events.record(
                run_id,
                event_type,  # type: ignore[arg-type]
                level=level,  # type: ignore[arg-type]
                stage="eval",
                message=message,
                round_id=round_id,
                payload=payload,
                error=error,
            )
        except Exception:
            logger.exception(
                "failed to record evaluation poller event",
                extra={"run_id": run_id, "event_type": event_type},
            )


def _project_id(run: EvolutionRunRecord, purpose: str) -> str:
    """Read the template ID from the run snapshot, falling back to the column."""
    key = "testProjectId" if purpose in {"test_baseline", "test_final"} else "validationProjectId"
    value = run.eval_config.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    if purpose in {"test_baseline", "test_final"}:
        return run.test_project_id
    return run.validation_project_id


def _sub_dir(run: EvolutionRunRecord) -> str:
    """Read the target subdirectory from the snapshot, falling back to the run."""
    value = run.eval_config.get("subDir")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return run.sub_dir


def _eval_targets(run: EvolutionRunRecord) -> tuple[EvalTarget, ...]:
    """Return every frozen member asset for one platform launch."""
    if run.targets:
        return tuple(
            EvalTarget(item.object_type, item.object_name, item.sub_dir) for item in run.targets
        )
    return (EvalTarget(run.target_type, run.target_name, _sub_dir(run)),)


def _evaluation_label(kind: str) -> str:
    """Render one run-level evaluation kind for Chinese run events."""
    return {
        "validation_baseline": "验证集基线",
        "test_baseline": "测试集基线",
        "test_final": "测试集终评",
    }.get(kind, kind)
