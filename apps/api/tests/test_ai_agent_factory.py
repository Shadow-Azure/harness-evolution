"""Contracts, registry, fake behavior, settings, and startup wiring for ai_agent."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, Field, ValidationError

from app.config import DatabaseDialect, Settings
from app.main import _record_ai_agent_health, create_app
from app.third_party_api.ai_agent import (
    AgentProviderError,
    AgentUsage,
    AIAgentProvider,
    AnalysisRequest,
    AnalysisResult,
    EditRequest,
    EditResult,
    FakeAIAgentProvider,
    ProviderHealth,
    build_agent_provider,
    registered_provider_ids,
)
from app.third_party_api.ai_agent.base import (
    ANALYZE_TIMEOUT_SECONDS,
    EDIT_TIMEOUT_SECONDS,
    PERMISSION_MODE,
)


class ClusterReviewOutput(BaseModel):
    """Minimal caller schema for the review task."""

    clusters: list[dict[str, object]] = Field(default_factory=list)


class ClusterScoreOutput(BaseModel):
    """Minimal caller schema for the cluster confidence task."""

    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)


class SeverityScoreOutput(BaseModel):
    """Minimal caller schema for the severity task."""

    overall: float
    vector: str


class EchoOutput(BaseModel):
    """Minimal caller schema for an unknown task key."""

    task: str


class TitleOnlyOutput(BaseModel):
    """Caller schema that the fake's default cluster score cannot satisfy."""

    title: str


@pytest.fixture(autouse=True)
def isolated_ai_agent_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ambient deployment variables from changing provider selection."""
    for name in (
        "AI_AGENT_PROVIDER",
        "HE_AI_AGENT_PROVIDER",
        "HE_AI_AGENT_CLAUDE_BIN",
    ):
        monkeypatch.delenv(name, raising=False)


def settings(**overrides: Any) -> Settings:
    """Build minimal settings without reading a repository .env file."""
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_timeouts_and_permission_mode_are_code_constants() -> None:
    """The design fixes these values in code instead of adding deployment knobs."""
    assert ANALYZE_TIMEOUT_SECONDS == 300
    assert EDIT_TIMEOUT_SECONDS == 1_800
    assert PERMISSION_MODE == "dontAsk"


def test_settings_defaults_to_the_reserved_claude_code_backend() -> None:
    """Zero-config startup selects the reserved default and its deployment path."""
    configured = settings()

    assert configured.ai_agent_provider == "claude-code"
    assert configured.ai_agent_claude_bin == "~/.local/bin/claude"
    assert registered_provider_ids() == frozenset({"claude-code", "fake"})


def test_factory_selects_the_registered_fake() -> None:
    """One settings value resolves to one implementation, never a service branch."""
    provider = build_agent_provider(settings(ai_agent_provider="fake"))

    assert isinstance(provider, FakeAIAgentProvider)
    assert provider.provider_id == "fake"


def test_factory_normalizes_case_and_surrounding_whitespace() -> None:
    """A deployment value is case-insensitive and trimmed before lookup."""
    provider = build_agent_provider(settings(ai_agent_provider=" FaKe "))

    assert provider.provider_id == "fake"


def test_unknown_provider_fails_startup_via_kwarg() -> None:
    """An unknown provider id is a startup failure, never a silent fallback."""
    with pytest.raises(ValidationError, match="unknown AI agent provider"):
        settings(ai_agent_provider="unknown")


def test_unknown_provider_fails_startup_via_bare_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The documented bare env alias is validated exactly like the HE_ prefix."""
    monkeypatch.delenv("HE_AI_AGENT_PROVIDER", raising=False)
    monkeypatch.setenv("AI_AGENT_PROVIDER", "unknown")

    with pytest.raises(ValidationError, match="unknown AI agent provider"):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_both_environment_aliases_select_the_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AI_AGENT_PROVIDER and HE_AI_AGENT_PROVIDER are interchangeable."""
    monkeypatch.delenv("AI_AGENT_PROVIDER", raising=False)
    monkeypatch.setenv("HE_AI_AGENT_PROVIDER", "fake")
    assert Settings(_env_file=None).ai_agent_provider == "fake"  # type: ignore[call-arg]

    monkeypatch.delenv("HE_AI_AGENT_PROVIDER", raising=False)
    monkeypatch.setenv("AI_AGENT_PROVIDER", "fake")
    assert Settings(_env_file=None).ai_agent_provider == "fake"  # type: ignore[call-arg]


def test_blank_claude_bin_fails_startup() -> None:
    """An empty deployment path is a configuration error, not a silent default."""
    with pytest.raises(ValidationError, match="AI_AGENT_CLAUDE_BIN"):
        settings(ai_agent_claude_bin="   ")


def test_factory_rejects_an_unknown_value_that_bypasses_settings() -> None:
    """The factory keeps its own guard for callers that mutate settings."""
    configured = settings().model_copy(update={"ai_agent_provider": "missing"})

    with pytest.raises(ValueError, match="unknown AI agent provider"):
        build_agent_provider(configured)


@pytest.mark.parametrize(
    ("task", "output_model", "expected"),
    [
        (
            "cluster.review",
            ClusterReviewOutput,
            {"clusters": []},
        ),
        (
            "cluster.score",
            ClusterScoreOutput,
            {"confidence": 0.5, "evidence_refs": []},
        ),
        (
            "severity.score",
            SeverityScoreOutput,
            {
                "overall": 5.0,
                "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L",
            },
        ),
        ("unknown.task", EchoOutput, {"task": "unknown.task"}),
    ],
)
async def test_fake_analyze_is_task_keyed_and_deterministic(
    task: str,
    output_model: type[BaseModel],
    expected: dict[str, object],
) -> None:
    """The fake returns one fixed structure per task key without external state."""
    provider = FakeAIAgentProvider()
    request = AnalysisRequest(
        task=task,
        prompt="analyse deterministically",
        output_model=output_model,
    )

    first = await provider.analyze(request)
    second = await provider.analyze(request)

    assert first == second
    assert dict(first.output) == expected
    assert first.provider_id == "fake"
    assert first.usage == AgentUsage(model="fake")
    assert first.session_id == "fake-session"
    assert first.latency_ms == 0
    assert first.retryable is False


async def test_fake_analyze_accepts_per_task_overrides() -> None:
    """Callers can pin a task-specific structure without touching the fake."""
    provider = FakeAIAgentProvider(
        outputs={
            "cluster.review": {
                "clusters": [
                    {"from": ["D1", "D2"], "title": "Merged", "summary": "Same root"},
                ],
            },
        },
        session_id="scripted-session",
        latency_ms=12,
    )
    request = AnalysisRequest(
        task="cluster.review",
        prompt="review",
        output_model=ClusterReviewOutput,
    )

    result = await provider.analyze(request)

    assert result.output["clusters"] == [
        {"from": ["D1", "D2"], "title": "Merged", "summary": "Same root"},
    ]
    assert result.session_id == "scripted-session"
    assert result.latency_ms == 12


async def test_fake_analyze_normalizes_schema_failures() -> None:
    """A canned output that violates the caller model becomes a provider error."""
    provider = FakeAIAgentProvider()
    request = AnalysisRequest(
        task="cluster.score",
        prompt="score",
        output_model=TitleOnlyOutput,
    )

    with pytest.raises(AgentProviderError) as caught:
        await provider.analyze(request)

    error = caught.value
    assert error.message == "fake analysis output failed the caller schema"
    assert error.retryable is False
    assert error.provider_id == "fake"
    assert error.detail is not None
    assert "title" in error.detail
    assert "input_value" not in error.detail


async def test_fake_edit_workspace_returns_a_fixed_result(tmp_path: Path) -> None:
    """The fake never touches the workspace and reports no changes."""
    provider = FakeAIAgentProvider()
    request = EditRequest(workspace=tmp_path, prompt="make it faster")

    first = await provider.edit_workspace(request)
    second = await provider.edit_workspace(request)

    assert first == second
    assert first == EditResult(
        summary="fake edit: no changes",
        provider_id="fake",
        changed_files=(),
        unified_diff="",
        usage=AgentUsage(model="fake"),
        session_id="fake-session",
        latency_ms=0,
        retryable=False,
    )


def test_error_keeps_normalized_fields() -> None:
    """The error's normalized fields stay available to callers and logs."""
    error = AgentProviderError(
        "provider failed",
        retryable=True,
        provider_id="fake",
        detail="bounded detail",
    )

    assert isinstance(error, RuntimeError)
    assert str(error) == "provider failed"
    assert error.retryable is True
    assert error.provider_id == "fake"
    assert error.detail == "bounded detail"


def test_contracts_reject_blank_and_negative_values(tmp_path: Path) -> None:
    """Frozen value objects fail fast instead of carrying unusable values."""
    with pytest.raises(ValueError, match=r"AgentUsage\.model"):
        AgentUsage(model=" ")
    with pytest.raises(ValueError, match="input_tokens"):
        AgentUsage(model="fake", input_tokens=-1)
    with pytest.raises(ValueError, match="cost_usd"):
        AgentUsage(model="fake", cost_usd=-0.01)

    request = AnalysisRequest(
        task="cluster.review",
        prompt="review",
        output_model=ClusterReviewOutput,
    )
    with pytest.raises(TypeError, match="Pydantic model"):
        AnalysisRequest(task="x", prompt="y", output_model=dict)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="workspace"):
        EditRequest(workspace=Path("relative"), prompt="edit")
    with pytest.raises(ValueError, match="summary"):
        EditResult(summary=" ", provider_id="fake")
    with pytest.raises(ValueError, match="provider_id"):
        ProviderHealth(provider_id="", healthy=True)

    result = AnalysisResult(output={}, provider_id="fake", usage=AgentUsage(model="fake"))
    assert result.retryable is False
    assert request.task == "cluster.review"


async def test_default_backend_health_is_unhealthy_and_fails_loudly(tmp_path: Path) -> None:
    """The zero-config claude-code placeholder starts but never fakes capability."""
    provider = build_agent_provider(settings())

    assert provider.provider_id == "claude-code"
    health = await provider.health_check()
    assert health.provider_id == "claude-code"
    assert health.healthy is False
    assert health.detail is not None
    assert "bugfix-17" in health.detail

    with pytest.raises(NotImplementedError, match="bugfix-17"):
        await provider.analyze(
            AnalysisRequest(
                task="cluster.score",
                prompt="score",
                output_model=ClusterScoreOutput,
            ),
        )
    with pytest.raises(NotImplementedError, match="bugfix-17"):
        await provider.edit_workspace(EditRequest(workspace=tmp_path, prompt="edit"))


def test_create_app_exposes_the_configured_provider(tmp_path: Path) -> None:
    """The composition root owns exactly one provider singleton on app.state."""
    app = create_app(
        settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            ai_agent_provider="fake",
        ),
    )

    assert isinstance(app.state.ai_agent, FakeAIAgentProvider)
    assert app.state.ai_agent.provider_id == "fake"


async def test_lifespan_records_the_provider_health_event(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Startup probes the provider once and records a structured health event."""
    app = create_app(
        settings(
            db_dialect=DatabaseDialect.SQLITE,
            data_dir=tmp_path,
            ai_agent_provider="fake",
        ),
    )

    with caplog.at_level(logging.INFO, logger="app.main"):
        async with app.router.lifespan_context(app):
            pass

    record = next(
        entry for entry in caplog.records if getattr(entry, "event", None) == "ai_agent_health"
    )
    assert getattr(record, "provider_id", None) == "fake"
    assert getattr(record, "healthy", None) is True
    assert getattr(record, "detail", None) == "deterministic fake provider"
    assert getattr(record, "latency_ms", None) == 0


def test_registry_ids_are_derived_from_declared_provider_ids() -> None:
    """Every registered key matches its implementation's declared identifier."""
    from app.third_party_api.ai_agent import factory

    for provider_id, implementation in factory._REGISTRY.items():
        assert issubclass(implementation, AIAgentProvider)
        assert implementation.provider_id == provider_id


def test_register_provider_adds_one_backend_without_business_changes() -> None:
    """A new backend is one subclass plus one registry entry."""
    from app.third_party_api.ai_agent import factory

    class StubProvider(AIAgentProvider):
        provider_id = "unit-test-stub"

        async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
            raise NotImplementedError

        async def edit_workspace(self, request: EditRequest) -> EditResult:
            raise NotImplementedError

        async def health_check(self) -> ProviderHealth:
            return ProviderHealth(provider_id=self.provider_id, healthy=True)

    factory.register_provider("unit-test-stub", StubProvider)
    try:
        provider = build_agent_provider(settings(ai_agent_provider="unit-test-stub"))
        assert isinstance(provider, StubProvider)
    finally:
        factory._REGISTRY.pop("unit-test-stub", None)

    assert "unit-test-stub" not in registered_provider_ids()
    with pytest.raises(ValueError, match="declares"):
        factory.register_provider("other-id", StubProvider)
    with pytest.raises(ValueError, match="must not be empty"):
        factory.register_provider("   ", StubProvider)


async def test_health_probe_failure_is_logged_without_failing_startup(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A provider probe exception becomes a warning event, not a startup crash."""

    class BrokenProvider(AIAgentProvider):
        provider_id = "broken"

        async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
            raise NotImplementedError

        async def edit_workspace(self, request: EditRequest) -> EditResult:
            raise NotImplementedError

        async def health_check(self) -> ProviderHealth:
            raise RuntimeError("probe exploded")

    with caplog.at_level(logging.WARNING, logger="app.main"):
        await _record_ai_agent_health(BrokenProvider())

    record = next(
        entry for entry in caplog.records if getattr(entry, "event", None) == "ai_agent_health"
    )
    assert getattr(record, "provider_id", None) == "broken"
    assert getattr(record, "healthy", None) is False
    assert getattr(record, "error_type", None) == "RuntimeError"
