"""Deterministic evaluation gateway used by tests and offline runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from app.service.evolution.engine.contracts import (
    EvalDirection,
    EvalGatewayConfig,
    EvalMeasurement,
    EvalRequest,
    EvalStatus,
    EvalStatusValue,
    EvalSubmission,
    FrozenValue,
)
from app.third_party_api.eval_gateway.base import BaseEvalGateway, EvalGatewayError

_VALID_STATUSES = {"queued", "running", "completed", "failed", "timeout"}
_BASELINE_KEYS = {"validation_baseline", "test_baseline"}


class FakeEvalGateway(BaseEvalGateway):
    """Deterministic gateway that needs no external service or memory state.

    Baseline evaluations report ``currentScore`` and candidate/test-final
    evaluations report ``candidateScore``; the same service-layer gate compares
    them, so offline runs exercise the production decision path.
    """

    provider = "fake"

    def __init__(self, config: EvalGatewayConfig) -> None:
        """Bind the frozen run configuration."""
        super().__init__(config)

    async def submit(self, request: EvalRequest) -> EvalSubmission:
        """Return a stable identifier derived from the durable request identity."""
        key = request.evolution_round_id or request.purpose
        return EvalSubmission(
            eval_id=f"fake:{request.run_id}:{key}:{request.commit}",
        )

    async def get_status(self, eval_id: str) -> EvalStatus:
        """Return the configured placeholder lifecycle state."""
        self._require_eval_id(eval_id)
        configured = self.config.get("status", "completed")
        if configured not in _VALID_STATUSES:
            raise EvalGatewayError("fake evaluation status is invalid")
        message = self.config.get("message")
        return EvalStatus(
            status=cast(EvalStatusValue, configured),
            message=str(message) if message is not None else None,
        )

    async def get_result(self, eval_id: str) -> EvalMeasurement:
        """Return configured scores without retaining process state."""
        key = self._require_eval_id(eval_id)
        raw_score = (
            self.config.get("currentScore", 80.0)
            if key in _BASELINE_KEYS
            else self.config.get("candidateScore", 85.0)
        )
        if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
            raise EvalGatewayError("fake evaluation scores must be numeric")
        score = float(raw_score)
        metric_key_value = self.config.get("primaryMetricKey", "score")
        metric_key = (
            metric_key_value.strip()
            if isinstance(metric_key_value, str) and metric_key_value.strip()
            else "score"
        )
        direction_value = self.config.get("direction", "higher_is_better")
        if direction_value not in {"higher_is_better", "lower_is_better"}:
            raise EvalGatewayError("fake evaluation direction is invalid")
        direction = cast(EvalDirection, direction_value)
        configured_metrics = self.config.get("metrics", ())
        if not isinstance(configured_metrics, tuple) or any(
            not isinstance(metric, Mapping) for metric in configured_metrics
        ):
            raise EvalGatewayError("fake evaluation metrics must be objects")
        metrics = tuple(cast(Mapping[str, FrozenValue], metric) for metric in configured_metrics)
        if not metrics:
            metrics = (
                {
                    "metric_key": metric_key,
                    "value": score,
                    "direction": direction,
                    "is_final": True,
                },
            )
        try:
            return EvalMeasurement(
                candidate_score=score,
                primary_metric_key=metric_key,
                direction=direction,
                metrics=metrics,
            )
        except ValueError as exc:
            raise EvalGatewayError(str(exc)) from None

    @staticmethod
    def _require_eval_id(eval_id: str) -> str:
        """Reject blank/foreign identifiers and return the request key."""
        parts = eval_id.split(":")
        if not eval_id.startswith("fake:") or len(parts) < 4:
            raise EvalGatewayError("fake evaluation id is invalid")
        return parts[2]


__all__ = ["FakeEvalGateway"]
