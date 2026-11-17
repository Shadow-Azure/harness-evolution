"""One mapping seam between internal evaluation models and external JSON."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.service.evolution.engine.contracts import (
    EvalRequest,
    EvalResult,
    EvalStatus,
    EvalSubmission,
)


class HttpEvalError(RuntimeError):
    """A sanitized evaluation-platform failure raised to the polling loop.

    ``retryable`` marks observation-side transience (network timeouts,
    connection failures, HTTP 429/5xx) so the polling loop can defer the next
    poll instead of judging the evaluation itself failed; payload and 4xx
    contract errors stay final. The classification lives in the gateway layer
    per 07 §5.7 — business services only consume the boolean.
    """

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        """Store the safe message and retryability without retaining bodies."""
        super().__init__(message)
        self.retryable = retryable


class EvalMapper:
    """Translate internal stable models to and from the external JSON contract.

    External field changes are absorbed here and in :class:`HttpEvalGateway`;
    business services and persisted models stay untouched.
    """

    @staticmethod
    def submit_payload(request: EvalRequest) -> dict[str, str]:
        """Build the external submission body from the internal request."""
        return {
            "runId": request.run_id,
            "evolutionRoundId": request.evolution_round_id,
            "repoUrl": request.repo_url,
            "ref": request.ref,
            "commit": request.commit,
            "targetType": request.target_type,
            "targetName": request.target_name,
            "targetVersion": request.target_version,
            "clusterId": request.cluster_id,
            "idempotencyKey": request.idempotency_key,
        }

    @staticmethod
    def parse_submission(payload: Mapping[str, Any]) -> EvalSubmission:
        """Read the external submission acknowledgment."""
        eval_id = payload.get("evalId") or payload.get("id")
        if not isinstance(eval_id, str) or not eval_id.strip():
            raise HttpEvalError("evaluation submission payload has no evalId")
        return EvalSubmission(eval_id=eval_id.strip())

    @staticmethod
    def parse_status(payload: Mapping[str, Any]) -> EvalStatus:
        """Read one external lifecycle status and optional safe message."""
        status = payload.get("status")
        if status not in {"queued", "running", "completed", "failed", "timeout"}:
            raise HttpEvalError("evaluation status payload has an unknown status")
        message = payload.get("message")
        return EvalStatus(
            status=status,
            message=message.strip() if isinstance(message, str) and message.strip() else None,
        )

    @staticmethod
    def parse_result(payload: Mapping[str, Any]) -> EvalResult:
        """Read normalized scores and the external verdict."""
        try:
            return EvalResult.from_payload(
                {
                    "currentScore": payload.get("currentScore"),
                    "candidateScore": payload.get("candidateScore"),
                    "externalVerdict": payload.get(
                        "externalVerdict",
                        payload.get("verdict"),
                    ),
                    "metrics": payload.get("metrics", ()),
                },
            )
        except ValueError as exc:
            raise HttpEvalError(f"evaluation result payload is invalid: {exc}") from None
