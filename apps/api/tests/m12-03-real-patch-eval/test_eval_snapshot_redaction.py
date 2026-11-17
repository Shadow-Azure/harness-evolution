"""Creation-time eval snapshot must keep the apiKeyRef indirect name intact.

The real-process smoke for this slice (reports/2026-11-18-m12-03-smoke) hit a
run that stayed blocked(stage=eval) with "apiKeyRef points to unset env var":
the blanket credential-key redaction in ``launch._snapshot_eval`` erases the
``apiKeyRef`` value even though that value is an environment-variable NAME,
not a credential. These tests pin the creation-time snapshot contract.
"""

from __future__ import annotations

from app.service.evolution.launch import _snapshot_eval


def test_snapshot_keeps_api_key_ref_environment_name() -> None:
    """The indirect reference name survives the redaction pass untouched."""
    snapshot = _snapshot_eval(
        {
            "mode": "http",
            "baseUrl": "https://eval-platform.example",
            "apiKeyRef": "HE_EVAL_API_KEY_REF",
            "patchMode": "minimal-config",
        },
    )
    assert snapshot["apiKeyRef"] == "HE_EVAL_API_KEY_REF"
    assert snapshot["mode"] == "http"
    assert snapshot["baseUrl"] == "https://eval-platform.example"
    assert snapshot["patchMode"] == "minimal-config"


def test_snapshot_still_redacts_credential_shaped_keys() -> None:
    """Credential-named keys keep their blanket redaction inside eval config."""
    snapshot = _snapshot_eval(
        {
            "mode": "http",
            "apiKey": "sk-should-vanish",
            "token": "bearer-value",
            "password": "hunter2",
        },
    )
    assert snapshot["apiKey"] == "<redacted>"
    assert snapshot["token"] == "<redacted>"
    assert snapshot["password"] == "<redacted>"


def test_snapshot_handles_missing_and_empty_ref() -> None:
    """Empty or absent references stay absent instead of becoming literals."""
    assert _snapshot_eval({"mode": "fake"}).get("apiKeyRef") is None
    assert "apiKeyRef" not in _snapshot_eval({"mode": "http", "apiKeyRef": "   "})
    assert _snapshot_eval(None) == {}
