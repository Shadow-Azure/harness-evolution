"""Provider-format credentials are redacted before diagnostics become durable."""

import pytest

from app.utils.redaction import redact_text, sanitize_value


@pytest.mark.parametrize(
    ("secret", "context"),
    [
        ("AKIAIOSFODNN7EXAMPLE", "AWS access key"),
        ("ASIAIOSFODNN7EXAMPLE", "AWS temporary access key"),
        ("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "AWS_SECRET_ACCESS_KEY"),
        ("sk-proj-live-secret", "OpenAI project key"),
        ("ghp_1234567890abcdefghijklmnopqrstuvwxyz", "GitHub token"),
        ("github_pat_11AAaaBBccDDeeFFggHHiiJJ", "GitHub fine-grained token"),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJvcGVyYXRvciJ9.c2lnbmF0dXJlLXZhbHVl", "JWT"),
        (
            "-----BEGIN PRIVATE KEY-----\n"
            "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ\n"
            "-----END PRIVATE KEY-----",
            "PEM private key",
        ),
    ],
)
def test_redact_text_removes_provider_credentials(secret: str, context: str) -> None:
    """Known credential formats never survive free-form diagnostics."""
    rendered = f"{context}: {secret}; retry=next"

    redacted = redact_text(rendered)

    assert secret not in redacted
    assert "<redacted>" in redacted
    assert "retry=next" in redacted


@pytest.mark.parametrize(
    "key",
    [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "accessKeyId",
        "secretAccessKey",
    ],
)
def test_sanitize_value_redacts_provider_environment_keys(key: str) -> None:
    """Provider credential keys are sensitive even without generic suffixes."""
    assert sanitize_value({key: "provider-secret"}) == {key: "<redacted>"}


@pytest.mark.parametrize(
    ("label", "secret"),
    [
        ("AWS Secret Access Key", "spaced-aws-secret"),
        ("API key", "spaced-api-secret"),
        ("Private Key", "spaced-private-secret"),
        ("Password Hash", "spaced-password-hash"),
    ],
)
def test_redact_text_removes_space_separated_sensitive_labels(
    label: str,
    secret: str,
) -> None:
    """Readable provider labels redact values without crossing line boundaries."""
    rendered = f"{label}: {secret}; retry=next"

    redacted = redact_text(rendered)

    assert secret not in redacted
    assert "<redacted>" in redacted
    assert "retry=next" in redacted
