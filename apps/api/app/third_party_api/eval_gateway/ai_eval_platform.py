"""ai-eval-platform adapter: launch, status, results and error envelopes."""

# ruff: noqa: RUF001

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast
from urllib.parse import quote

from app.service.evolution.engine.contracts import (
    EvalDirection,
    EvalGatewayConfigError,
    EvalMeasurement,
    EvalRequest,
    EvalStatus,
    EvalStatusValue,
    EvalSubmission,
    FrozenValue,
    freeze_json,
)
from app.third_party_api.eval_gateway.base import BaseEvalGateway, EvalGatewayError

PARTIAL_MIN_COMPLETION_PERCENT = 50

_STATUS_MAP: dict[str, EvalStatusValue] = {
    "preparing": "queued",
    "queued": "queued",
    "running": "running",
    "finalizing": "running",
    "cancelling": "running",
    "completed": "completed",
    "partial": "completed",
    "failed": "failed",
    "cancelled": "failed",
    "pausing_budget": "failed",
    "paused_budget": "failed",
}


class AiEvalPlatformGateway(BaseEvalGateway):
    """Adapt HE to the ai-eval-platform machine contract.

    The platform returns measurements, never a verdict: the service layer
    compares the measured primary metric with the active baseline.
    """

    provider = "ai-eval-platform"

    async def submit(self, request: EvalRequest) -> EvalSubmission:
        """Launch one validation/test template at the pinned commit."""
        if request.target_type == "knowledge":
            raise EvalGatewayConfigError(
                "ai-eval-platform does not support knowledge targets",
            )
        if request.purpose in {"test_baseline", "test_final"}:
            template_id = request.project_id.strip() or self.config_text(
                "testProjectId",
                required=True,
            )
        else:
            template_id = request.project_id.strip() or self.config_text(
                "validationProjectId",
                required=True,
            )
        sub_dir = request.sub_dir or self.config_text("subDir")
        body: dict[str, Any] = {
            "asset_override": self._asset_override(request, sub_dir),
            "lineage": self._lineage(request),
        }
        payload = await self._request_json(
            "POST",
            f"/api/v1/eval-templates/{quote(template_id, safe='')}/launch",
            context="submission",
            json_body=body,
            extra_headers={"Idempotency-Key": request.idempotency_key},
        )
        eval_id = payload.get("run_id") or payload.get("runId")
        if not isinstance(eval_id, str) or not eval_id.strip():
            raise EvalGatewayError(
                "evaluation submission payload has no run_id",
            )
        asset = payload.get("asset")
        resolved = asset.get("resolved_commit") if isinstance(asset, Mapping) else None
        if isinstance(resolved, str) and resolved.strip() != request.commit:
            raise EvalGatewayError(
                "evaluation platform resolved a different candidate commit",
            )
        raw_warnings = payload.get("warnings")
        warnings = (
            tuple(str(item) for item in raw_warnings if str(item).strip())
            if isinstance(raw_warnings, list)
            else ()
        )
        return EvalSubmission(eval_id=eval_id.strip(), warnings=warnings)

    async def get_status(self, eval_id: str) -> EvalStatus:
        """Map the platform's 11 states onto HE's five-state seam."""
        payload = await self._request_json(
            "GET",
            f"/api/v1/eval-runs/{quote(eval_id, safe='')}/status",
            context="status",
        )
        raw = payload.get("status")
        mapped = _STATUS_MAP.get(raw) if isinstance(raw, str) else None
        if mapped is None:
            raise EvalGatewayError(
                f"evaluation platform returned an unknown status: {raw!r}",
            )
        if raw == "partial":
            percent = _completion_percent(payload)
            if percent is not None and percent < PARTIAL_MIN_COMPLETION_PERCENT:
                return EvalStatus(
                    status="failed",
                    message=(
                        "评测平台部分完成，完成率 "
                        f"{percent}% 低于最低完成率 {PARTIAL_MIN_COMPLETION_PERCENT}%"
                    ),
                )
            return EvalStatus(status="completed")
        if raw in {"pausing_budget", "paused_budget"}:
            return EvalStatus(
                status="failed",
                message="评测平台预算暂停，增加预算后请重试该评测",
            )
        if raw == "cancelled":
            return EvalStatus(status="failed", message="评测平台已取消该评测")
        return EvalStatus(status=mapped)

    async def get_result(self, eval_id: str) -> EvalMeasurement:
        """Read measurement items and extract the configured primary metric."""
        payload = await self._request_json(
            "GET",
            f"/api/v1/eval-runs/{quote(eval_id, safe='')}/results",
            context="result",
        )
        items = payload.get("items")
        if not isinstance(items, list):
            raise EvalGatewayError(
                "evaluation platform results payload has no items",
            )
        primary = self.config_text("primaryMetricKey", required=True)
        for item in items:
            if not isinstance(item, Mapping) or item.get("metric_key") != primary:
                continue
            value = item.get("value")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EvalGatewayError(
                    f"evaluation platform primary metric {primary} has no numeric value",
                )
            direction_value = item.get("direction", "higher_is_better")
            if direction_value not in {"higher_is_better", "lower_is_better"}:
                raise EvalGatewayError(
                    f"evaluation platform primary metric {primary} has an invalid direction",
                )
            metrics = tuple(
                cast(Mapping[str, FrozenValue], freeze_json(metric))
                for metric in items
                if isinstance(metric, Mapping)
            )
            return EvalMeasurement(
                candidate_score=float(value),
                primary_metric_key=primary,
                direction=cast(EvalDirection, direction_value),
                metrics=metrics,
            )
        raise EvalGatewayError(
            f"evaluation platform results payload has no primary metric {primary}",
        )

    def _asset_override(self, request: EvalRequest, sub_dir: str) -> dict[str, Any]:
        """Map one HE target onto the platform's whole-field asset override."""
        override: dict[str, Any] = {
            "ref": request.ref or request.commit,
            "commit": request.commit,
        }
        if sub_dir:
            override["asset_paths"] = [sub_dir]
            if request.target_type == "agent":
                override["asset_types"] = {sub_dir: "subagent"}
        return override

    @staticmethod
    def _lineage(request: EvalRequest) -> dict[str, Any]:
        """Record caller provenance without making it part of evaluation."""
        lineage: dict[str, Any] = {"evolutionRunId": request.run_id}
        if request.purpose == "candidate" and request.evolution_round_id:
            lineage["evolutionRoundId"] = request.evolution_round_id
        if request.purpose == "candidate" and request.round_seq > 0:
            lineage["roundSeq"] = request.round_seq
        if request.parent_commit:
            lineage["parentCommit"] = request.parent_commit
        return lineage


def _completion_percent(payload: Mapping[str, Any]) -> float | None:
    """Read the platform progress percentage without inventing one."""
    progress = payload.get("progress")
    if not isinstance(progress, Mapping):
        return None
    percent = progress.get("percent")
    if isinstance(percent, bool) or not isinstance(percent, (int, float)):
        return None
    return float(percent)


__all__ = [
    "PARTIAL_MIN_COMPLETION_PERCENT",
    "AiEvalPlatformGateway",
]
