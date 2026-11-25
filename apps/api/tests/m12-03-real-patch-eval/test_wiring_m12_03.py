"""Composition-root wiring for the m12-03 patch and evaluation seams."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.models.evolution import EvolutionRunRecord
from app.main import create_app
from app.service.evolution.gateway_factory import build_eval_gateway_factory
from app.service.evolution.patch_source import (
    MinimalConfigPatchSource,
    PlaceholderPatchSource,
    default_patch_source_factory,
)
from app.third_party_api.eval_gateway.ai_eval_platform import AiEvalPlatformGateway
from app.third_party_api.eval_gateway.fake import FakeEvalGateway

NOW = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "db_dialect": DatabaseDialect.SQLITE,
        "data_dir": tmp_path / "db",
        "jwt_secret": SecretStr("m12-03-composition-secret"),
    }
    values.update(overrides)
    return Settings(**values)


def _run(eval_config: dict[str, object]) -> EvolutionRunRecord:
    return EvolutionRunRecord(
        id="run-wiring",
        title="wiring",
        mode="full",
        engine_key="full",
        eval_config=eval_config,
        target_config_id=None,
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        repo_url="https://example.invalid/repo.git",
        sub_dir="skills/deep-research",
        repo_path=None,
        base_ref="v2.0.0",
        base_commit="a" * 40,
        branch_name=None,
        workspace_path=None,
        remote_name="origin",
        push_status="pending",
        pushed_at=None,
        push_error=None,
        window_from=None,
        window_to=None,
        models=[],
        status="preparing",
        blocked_stage=None,
        retry_attempts=0,
        next_retry_at=None,
        eval_status="pending",
        error_stage=None,
        error_message=None,
        error_at=None,
        progress_unit=0,
        stats={},
        created_by=None,
        created_at=NOW,
        finished_at=None,
    )


def test_create_app_keeps_default_seams_without_configuration(tmp_path: Path) -> None:
    """An unconfigured environment still resolves fake gateway + placeholder patch."""
    from app.service.evolution.engine.contracts import EvalGatewayConfig

    settings = _settings(tmp_path)
    assert settings.eval_mode == "fake"
    assert settings.patch_source_mode == "placeholder"
    assert isinstance(default_patch_source_factory(_run({})), PlaceholderPatchSource)

    app = create_app(settings)

    assert app.state.evolution_eval_poller is not None
    gateway = app.state.evolution_gateway_factory(EvalGatewayConfig.from_mapping({}))
    assert isinstance(gateway, FakeEvalGateway)
    assert app.state.evolution_patch_source_factory(_run({})).__class__ is (PlaceholderPatchSource)


def test_create_app_respects_configured_modes(tmp_path: Path) -> None:
    """Settings-configured modes flip the composition seams without run config."""
    from app.service.evolution.engine.contracts import EvalGatewayConfig

    app = create_app(
        _settings(
            tmp_path,
            eval_mode="ai-eval-platform",
            eval_base_url="http://127.0.0.1:9",
            patch_source_mode="minimal-config",
        ),
    )

    gateway = app.state.evolution_gateway_factory(EvalGatewayConfig.from_mapping({}))
    assert isinstance(gateway, AiEvalPlatformGateway)
    patch_source = app.state.evolution_patch_source_factory(_run({}))
    assert isinstance(patch_source, MinimalConfigPatchSource)
    # Distinguishing assertion: under http settings a run snapshot can still
    # explicitly select fake — the snapshot wins over the env default.
    snapshot_gateway = app.state.evolution_gateway_factory(
        EvalGatewayConfig.from_mapping({"mode": "fake"}),
    )
    assert isinstance(snapshot_gateway, FakeEvalGateway)


def test_run_snapshot_mode_selects_http_gateway(tmp_path: Path) -> None:
    """Engine gateway() resolves through the same mode-driven factory."""
    from app.service.evolution.engine.base import EvolutionEngine
    from app.service.evolution.engine.contracts import EngineDeps, EvalGatewayConfig
    from app.service.evolution.engine.factory import EngineFactory as _EngineFactory

    settings = _settings(tmp_path)
    factory = build_eval_gateway_factory(settings)

    gateway = factory(
        EvalGatewayConfig.from_mapping(
            {"mode": "ai-eval-platform", "baseUrl": "http://127.0.0.1:9"},
        ),
    )

    assert isinstance(gateway, AiEvalPlatformGateway)
    engine = _EngineFactory.for_run(
        _run({"mode": "ai-eval-platform", "baseUrl": "http://127.0.0.1:9"}),
        EngineDeps(reads=None, writes=None, gateway_factory=factory),  # type: ignore[arg-type]
    )
    assert isinstance(engine, EvolutionEngine)
    assert isinstance(engine.gateway(), AiEvalPlatformGateway)


def test_minimal_config_mode_selects_the_config_source(tmp_path: Path) -> None:
    """HE_PATCH_SOURCE_MODE flips the fallback without a run snapshot key."""
    settings = _settings(tmp_path, patch_source_mode="minimal-config")

    assert isinstance(
        default_patch_source_factory(
            _run({}),
            fallback_mode=settings.patch_source_mode,
        ),
        MinimalConfigPatchSource,
    )
