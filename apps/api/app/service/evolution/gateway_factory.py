"""Mode-driven evaluation gateway selection for the composition root.

The provider registry lives in :mod:`app.third_party_api.eval_gateway.factory`;
this service module keeps the historical composition-root entry point so
business code and wiring stay unchanged.
"""

from __future__ import annotations

from app.third_party_api.eval_gateway.factory import (
    EVAL_GATEWAY_MODES,
    EvalGatewayFactory,
    build_eval_gateway_factory,
)

__all__ = [
    "EVAL_GATEWAY_MODES",
    "EvalGatewayFactory",
    "build_eval_gateway_factory",
]
