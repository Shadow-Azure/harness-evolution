"""Creation-time eval snapshot must keep the apiKeyRef indirect name intact.

The real-process smoke for this slice (reports/2026-11-18-m12-03-smoke) hit a
run that stayed blocked(stage=eval) with "apiKeyRef points to unset env var":
the blanket credential-key redaction in ``launch._snapshot_eval`` erases the
``apiKeyRef`` value even though that value is an environment-variable NAME,
not a credential. These tests pin the creation-time snapshot contract.
"""

from __future__ import annotations

import pytest

from app.db.crud.evolution_targets import EvolutionTargetRecord
from app.errors import AppError
from app.service.evolution.launch import _snapshot_eval


def _target(**overrides: object) -> EvolutionTargetRecord:
    """Build one enabled target row with complete evaluation identity."""
    values: dict[str, object] = {
        "id": "target-1",
        "object_type": "skill",
        "object_name": "deep-research",
        "repo_url": "https://example.invalid/skills.git",
        "sub_dir": "skills/deep-research",
        "default_ref": "main",
        "validation_project_id": "val-2026-q3",
        "test_project_id": "test-2026-q3",
        "primary_metric_key": "resolved_rate",
        "enabled": True,
    }
    values.update(overrides)
    return EvolutionTargetRecord(**values)  # type: ignore[arg-type]


def test_snapshot_keeps_api_key_ref_environment_name() -> None:
    """The indirect reference name survives the redaction pass untouched."""
    snapshot = _snapshot_eval(
        {
            "mode": "ai-eval-platform",
            "baseUrl": "https://eval-platform.example",
            "apiKeyRef": "HE_EVAL_API_KEY_REF",
            "patchMode": "minimal-config",
        },
        config=_target(),
        default_mode="fake",
    )
    assert snapshot["apiKeyRef"] == "HE_EVAL_API_KEY_REF"
    assert snapshot["mode"] == "ai-eval-platform"
    assert snapshot["baseUrl"] == "https://eval-platform.example"
    assert snapshot["patchMode"] == "minimal-config"
    assert snapshot["validationProjectId"] == "val-2026-q3"
    assert snapshot["testProjectId"] == "test-2026-q3"
    assert snapshot["primaryMetricKey"] == "resolved_rate"
    assert snapshot["subDir"] == "skills/deep-research"


def test_snapshot_still_redacts_credential_shaped_keys() -> None:
    """Credential-named keys keep their blanket redaction inside eval config."""
    snapshot = _snapshot_eval(
        {
            "mode": "ai-eval-platform",
            "apiKey": "sk-should-vanish",
            "token": "bearer-value",
            "password": "hunter2",
        },
        config=_target(),
        default_mode="fake",
    )
    assert snapshot["apiKey"] == "<redacted>"
    assert snapshot["token"] == "<redacted>"
    assert snapshot["password"] == "<redacted>"


def test_snapshot_handles_missing_and_empty_ref() -> None:
    """Empty or absent references stay absent instead of becoming literals."""
    assert (
        _snapshot_eval({"mode": "fake"}, config=_target(), default_mode="fake").get("apiKeyRef")
        is None
    )
    assert "apiKeyRef" not in _snapshot_eval(
        {"mode": "ai-eval-platform", "apiKeyRef": "   "},
        config=_target(),
        default_mode="fake",
    )
    assert _snapshot_eval(None, config=_target(), default_mode="fake")


def test_real_platform_snapshot_requires_target_identity() -> None:
    """A real platform run without a template ID or metric key returns 422."""
    with pytest.raises(AppError) as excinfo:
        _snapshot_eval(
            {"mode": "ai-eval-platform"},
            config=_target(primary_metric_key=""),
            default_mode="fake",
        )

    assert excinfo.value.status_code == 422
    assert excinfo.value.details == {"field": "primaryMetricKey"}
