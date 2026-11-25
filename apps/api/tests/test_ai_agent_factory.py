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
from app.third_party_api.ai_agent.base import ANALYZE_TIMEOUT_SECONDS, EDIT_TIMEOUT_SECONDS
from app.third_party_api.ai_agent.claude_code import PERMISSION_MODE


class ClusterReviewOutput(BaseModel):
    """Minimal caller schema for the review task."""

    clusters: list[dict[str, object]] = Field(default_factory=list)


class ClusterScoreOutput(BaseModel):
    """Minimal caller schema for the batch cluster confidence task."""

    scores: list[dict[str, object]] = Field(default_factory=list)


class SeverityScoreOutput(BaseModel):
    """Minimal caller schema for the batch severity task."""

    severities: list[dict[str, object]] = Field(default_factory=list)


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
        "HE_AI_AGENT_CLAUDE_SETTINGS",
        "AI_AGENT_BIN",
        "HE_AI_AGENT_BIN",
        "AI_AGENT_SETTINGS",
        "HE_AI_AGENT_SETTINGS",
        "HE_AI_AGENT_FAILURE_POLICY",
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


def test_failure_policy_defaults_from_the_provider() -> None:
    """A real provider is strict; fake keeps the documented offline fallback."""
    assert settings(ai_agent_provider="claude-code").effective_ai_agent_failure_policy == "strict"
    assert settings(ai_agent_provider="fake").effective_ai_agent_failure_policy == "degrade"


def test_explicit_failure_policy_wins_over_the_provider_default() -> None:
    """An explicit policy is the only way to degrade a real provider."""
    assert (
        settings(
            ai_agent_provider="claude-code", ai_agent_failure_policy="degrade"
        ).effective_ai_agent_failure_policy
        == "degrade"
    )
    assert (
        settings(
            ai_agent_provider="fake", ai_agent_failure_policy="strict"
        ).effective_ai_agent_failure_policy
        == "strict"
    )


def test_failure_policy_reads_the_he_environment_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HE_AI_AGENT_FAILURE_POLICY is the documented deployment key."""
    monkeypatch.setenv("HE_AI_AGENT_FAILURE_POLICY", "degrade")
    assert Settings(_env_file=None).effective_ai_agent_failure_policy == "degrade"  # type: ignore[call-arg]


def test_blank_failure_policy_uses_the_provider_default() -> None:
    """The env template's empty value must not fail startup."""
    assert (
        settings(
            ai_agent_provider="claude-code", ai_agent_failure_policy=""
        ).effective_ai_agent_failure_policy
        == "strict"
    )


def test_unknown_failure_policy_fails_startup() -> None:
    """An unknown policy is a configuration error, never a silent default."""
    with pytest.raises(ValidationError, match="ai_agent_failure_policy"):
        settings(ai_agent_failure_policy="lenient")


def test_blank_claude_settings_path_is_unset() -> None:
    """A blank optional path must not beat the config-dir/home fallbacks."""
    assert settings(ai_agent_claude_settings="   ").ai_agent_claude_settings is None
    assert (
        settings(
            ai_agent_claude_settings="/opt/harness/shared/claude-code/config/settings.json"
        ).ai_agent_claude_settings
        == "/opt/harness/shared/claude-code/config/settings.json"
    )


def test_blank_claude_bin_fails_startup() -> None:
    """An empty deployment path is a configuration error, not a silent default."""
    with pytest.raises(ValidationError, match="AI_AGENT_CLAUDE_BIN"):
        settings(ai_agent_claude_bin="   ")


def test_generic_bin_entry_wins_over_the_legacy_alias() -> None:
    """All three env combinations resolve deterministically; the generic name wins."""
    legacy_only = settings(ai_agent_claude_bin="/opt/legacy/claude")
    assert legacy_only.effective_ai_agent_bin == "/opt/legacy/claude"

    generic_only = settings(ai_agent_bin="/opt/generic/agent")
    assert generic_only.effective_ai_agent_bin == "/opt/generic/agent"

    both = settings(ai_agent_bin="/opt/generic/agent", ai_agent_claude_bin="/opt/legacy/claude")
    assert both.effective_ai_agent_bin == "/opt/generic/agent"

    neither = settings()
    assert neither.effective_ai_agent_bin == "~/.local/bin/claude"


def test_generic_settings_entry_wins_over_the_legacy_alias() -> None:
    """The settings path resolves the same way: generic wins, legacy fallback."""
    legacy_only = settings(ai_agent_claude_settings="/opt/legacy/settings.json")
    assert legacy_only.effective_ai_agent_settings == "/opt/legacy/settings.json"

    generic_only = settings(ai_agent_settings="/opt/generic/settings.json")
    assert generic_only.effective_ai_agent_settings == "/opt/generic/settings.json"

    both = settings(
        ai_agent_settings="/opt/generic/settings.json",
        ai_agent_claude_settings="/opt/legacy/settings.json",
    )
    assert both.effective_ai_agent_settings == "/opt/generic/settings.json"

    assert settings().effective_ai_agent_settings is None


def test_generic_bin_reads_the_documented_environment_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HE_AI_AGENT_BIN 与裸 AI_AGENT_BIN 都注入通用字段。"""
    monkeypatch.setenv("HE_AI_AGENT_BIN", "/opt/generic/claude")
    monkeypatch.delenv("AI_AGENT_BIN", raising=False)
    assert Settings(_env_file=None).effective_ai_agent_bin == "/opt/generic/claude"  # type: ignore[call-arg]

    monkeypatch.delenv("HE_AI_AGENT_BIN", raising=False)
    monkeypatch.setenv("AI_AGENT_BIN", "/opt/generic/claude")
    assert Settings(_env_file=None).effective_ai_agent_bin == "/opt/generic/claude"  # type: ignore[call-arg]


def test_blank_generic_bin_fails_startup_and_blank_settings_is_unset() -> None:
    """A blank generic bin fails startup; a blank generic settings path is unset."""
    with pytest.raises(ValidationError, match="AI_AGENT_BIN"):
        settings(ai_agent_bin="   ")
    assert settings(ai_agent_settings="   ").effective_ai_agent_settings is None


def test_provider_health_rejects_an_unknown_auth_state() -> None:
    """The structured auth field is a closed three-state contract."""
    assert ProviderHealth(provider_id="fake", healthy=True).auth == "unknown"
    assert ProviderHealth(provider_id="fake", healthy=True, auth="ok").auth == "ok"
    assert ProviderHealth(provider_id="fake", healthy=True, auth="missing").auth == "missing"
    assert ProviderHealth(provider_id="fake", healthy=True, auth="unknown").auth == "unknown"
    with pytest.raises(ValueError, match="auth"):
        ProviderHealth(provider_id="fake", healthy=True, auth="expired")  # type: ignore[arg-type]


def _minimal_backend(provider_id: str, **properties: object) -> AIAgentProvider:
    """Build a minimal concrete backend instance with optional class attributes."""

    class MinimalBackend(AIAgentProvider):
        async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
            raise NotImplementedError

        async def edit_workspace(self, request: EditRequest) -> EditResult:
            raise NotImplementedError

        async def health_check(self) -> ProviderHealth:
            raise NotImplementedError

    MinimalBackend.provider_id = provider_id
    for name, value in properties.items():
        setattr(MinimalBackend, name, value)
    return MinimalBackend()


async def _unused_run_skill(request: object, *, diagnostics: dict[str, object]) -> int:
    raise NotImplementedError


def test_capabilities_declaration_wins_over_run_skill_derivation() -> None:
    """The declaration wins: no skill capability stays off despite a run_skill."""
    declared_without_skill = _minimal_backend(
        "declared-no-skill",
        capabilities=frozenset({"analyze", "edit"}),
        run_skill=_unused_run_skill,
    )
    assert declared_without_skill.supports_skills is False

    declared_with_skill = _minimal_backend(
        "declared-skill",
        capabilities=frozenset({"analyze", "edit", "skill"}),
    )
    assert declared_with_skill.supports_skills is True


def test_undeclared_backends_keep_the_run_skill_derivation() -> None:
    """Backends without a declaration keep the run_skill-override derivation."""
    derived = _minimal_backend("derived-skill", run_skill=_unused_run_skill)
    assert derived.supports_skills is True

    plain = _minimal_backend("no-skill")
    assert plain.supports_skills is False

    assert type(plain).capabilities == frozenset({"analyze", "edit"})


def test_stage_skill_default_refuses_staging(tmp_path: Path) -> None:
    """A backend without stage_skill fails with an attributable error pre-staging."""
    provider = FakeAIAgentProvider()
    with pytest.raises(AgentProviderError, match="does not support Skill staging"):
        provider.stage_skill(tmp_path, "attr", {"SKILL.md": b"text"})


def test_factory_builds_through_from_settings() -> None:
    """The factory assembles every backend through the from_settings hook."""

    constructed: list[object] = []

    class FromSettingsStub(FakeAIAgentProvider):
        provider_id = "from-settings-stub"

        @classmethod
        def from_settings(cls, settings: Settings | None) -> FromSettingsStub:
            constructed.append(settings)
            return super().from_settings(settings)

    from app.third_party_api.ai_agent import factory

    factory.register_provider("from-settings-stub", FromSettingsStub)
    try:
        configured = settings(ai_agent_provider="from-settings-stub")
        provider = build_agent_provider(configured)
    finally:
        factory._REGISTRY.pop("from-settings-stub", None)

    assert isinstance(provider, FromSettingsStub)
    assert constructed == [configured]


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
            {"scores": [{"cluster": "C1", "confidence": 0.5, "evidence_refs": []}]},
        ),
        (
            "severity.score",
            SeverityScoreOutput,
            {
                "severities": [
                    {
                        "cluster": "C1",
                        "overall": 5.0,
                        "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:L/A:L",
                    },
                ],
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


def test_default_backend_is_the_real_claude_code_provider() -> None:
    """The zero-config selection assembles the real subclass, not a placeholder."""
    from app.third_party_api.ai_agent.claude_code import ClaudeCodeProvider

    provider = build_agent_provider(settings())

    assert isinstance(provider, ClaudeCodeProvider)
    assert provider.provider_id == "claude-code"
    assert provider.settings is not None
    assert provider.settings.ai_agent_claude_bin == "~/.local/bin/claude"


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
    assert getattr(record, "auth", None) == "ok"
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
