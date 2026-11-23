"""Unit contract for the normalized ``ai_agent_call`` event payload."""

from __future__ import annotations

import pytest

from app.service.evolution.ai_observability import AiAgentCall
from app.third_party_api.ai_agent.contracts import AgentCallTrace, AgentProviderError


def test_agent_call_trace_derives_retries_and_rejects_impossible_counters() -> None:
    """The trace derives feedback retries and refuses impossible provenance."""
    trace = AgentCallTrace(
        attempts=2,
        submission_rounds=2,
        submission_parse_failures=1,
        submission_validation_failures=0,
        parsed_by="json5",
    )

    assert trace.feedback_retries == 1
    assert trace.submission_failures == 1
    assert trace.repaired is False

    with pytest.raises(ValueError, match="attempts"):
        AgentCallTrace(attempts=0)
    with pytest.raises(ValueError, match="attempts"):
        AgentCallTrace(attempts=-1)
    with pytest.raises(ValueError, match="submission_rounds"):
        AgentCallTrace(submission_rounds=-1)
    with pytest.raises(ValueError, match="cannot exceed attempts"):
        AgentCallTrace(attempts=1, submission_rounds=2)
    with pytest.raises(ValueError, match="parse_failures"):
        AgentCallTrace(submission_parse_failures=-1)
    with pytest.raises(ValueError, match="validation_failures"):
        AgentCallTrace(submission_validation_failures=-1)
    with pytest.raises(ValueError, match="cannot exceed submission rounds"):
        AgentCallTrace(
            attempts=1,
            submission_rounds=1,
            submission_parse_failures=1,
            submission_validation_failures=1,
        )
    with pytest.raises(ValueError, match="repaired"):
        AgentCallTrace(repaired=True)


def test_payload_carries_every_operational_field() -> None:
    """One payload answers cost, latency, outcome, and submission provenance."""
    call = AiAgentCall(
        task="cluster.review",
        provider="claude-code",
        model="MiniMax-M3.1-Flash",
        input_tokens=120,
        output_tokens=30,
        cost_usd=0.002,
        latency_ms=850,
        outcome="ok",
        session_id="session-1",
        trace=AgentCallTrace(
            attempts=2,
            submission_rounds=2,
            submission_validation_failures=1,
            parsed_by="strict",
        ),
    )

    assert call.payload() == {
        "task": "cluster.review",
        "provider": "claude-code",
        "model": "MiniMax-M3.1-Flash",
        "inputTokens": 120,
        "outputTokens": 30,
        "totalTokens": 150,
        "costUsd": 0.002,
        "latencyMs": 850,
        "outcome": "ok",
        "sessionId": "session-1",
        "attempts": 2,
        "feedbackRetries": 1,
        "submissionRounds": 2,
        "submissionParsedBy": "strict",
        "submissionRepaired": False,
        "submissionParseFailures": 0,
        "submissionValidationFailures": 1,
    }


def test_failed_call_keeps_the_provider_error_trace() -> None:
    """A raised provider call still reports its attempts and parse failures."""
    error = AgentProviderError(
        "submission missing",
        retryable=False,
        provider_id="claude-code",
        trace=AgentCallTrace(attempts=2, submission_rounds=2, submission_parse_failures=2),
    )

    payload = AiAgentCall.failed("agent.edit", error).payload()

    assert payload["task"] == "agent.edit"
    assert payload["provider"] == "claude-code"
    assert payload["model"] == "unknown"
    assert payload["outcome"] == "error"
    assert payload["attempts"] == 2
    assert payload["feedbackRetries"] == 1
    assert payload["submissionRounds"] == 2
    assert payload["submissionParseFailures"] == 2
