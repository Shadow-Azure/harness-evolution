"""Evolution engine stage contracts and factory selection."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, ClassVar, cast

import pytest

from app.db.models.evolution import EvolutionRunRecord
from app.db.models.jobs import JobRunRecord
from app.service.evolution.engine.base import EvolutionEngine
from app.service.evolution.engine.cluster_only import ClusterOnlyEngine
from app.service.evolution.engine.contracts import (
    ConfigError,
    EngineDeps,
    StageHandler,
)
from app.service.evolution.engine.factory import EngineFactory
from app.service.evolution.engine.full import FullEvolutionEngine

NOW = datetime(2026, 10, 27, 1, 2, 3, tzinfo=UTC)
FULL_STAGES = (
    "evolution_prepare",
    "evolution_advance",
    "evolution_apply",
    "evolution_finalize",
    "evolution_retry",
)


class _ProbeReader:
    """No-op probe reader accepted by the engine contract."""

    async def list_matching(
        self,
        query: Mapping[str, Any],
    ) -> Sequence[object]:
        """Return no probes for pure contract tests."""
        _ = query
        return ()


class _Repository:
    """No-op repository accepted by the engine contract."""


def _run(eval_config: Mapping[str, Any] | None = None) -> EvolutionRunRecord:
    """Build one complete immutable evolution run record."""
    return EvolutionRunRecord(
        id="run-1",
        title="prototype run",
        mode="full",
        engine_key="full",
        eval_config=dict(eval_config or {"gateway": "mock"}),
        target_config_id="target-1",
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        repo_url="https://example.invalid/agent-skills.git",
        sub_dir="skills/deep-research",
        repo_path=None,
        base_ref=None,
        base_commit=None,
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


def _job(kind: str) -> JobRunRecord:
    """Build one queued job record for a stage dispatch test."""
    return JobRunRecord(
        id=f"job-{kind}",
        kind=kind,
        ref_id="run-1",
        status="queued",
        progress=0.0,
        executor="local",
        external_job_id=None,
        attempt=0,
        payload={"run_id": "run-1"},
        result=None,
        error=None,
        created_by=None,
        created_at=NOW,
        started_at=None,
        finished_at=None,
        updated_at=NOW,
    )


def _deps(
    *,
    prepare_calls: list[tuple[EvolutionRunRecord, Mapping[str, Any]]] | None = None,
    full_calls: list[tuple[str, JobRunRecord]] | None = None,
) -> EngineDeps:
    """Build engine dependencies with observable test callbacks."""
    prepare_records = prepare_calls if prepare_calls is not None else []
    full_records = full_calls if full_calls is not None else []

    async def prepare_cluster_only(
        run: EvolutionRunRecord,
        payload: Mapping[str, Any],
    ) -> None:
        prepare_records.append((run, payload))

    def full_stage(kind: str) -> StageHandler:
        async def handle(job: JobRunRecord) -> None:
            full_records.append((kind, job))

        return handle

    return EngineDeps(
        reads=cast(Any, _ProbeReader()),
        writes=cast(Any, _Repository()),
        prepare_cluster_only=prepare_cluster_only,
        full_stages={kind: full_stage(kind) for kind in FULL_STAGES},
    )


async def test_cluster_only_dispatches_prepare_and_rejects_future_stages() -> None:
    """Cluster-only exposes prepare and delegates it exactly once."""
    calls: list[tuple[EvolutionRunRecord, Mapping[str, Any]]] = []
    full_calls: list[tuple[str, JobRunRecord]] = []
    engine = ClusterOnlyEngine(
        _run(),
        _deps(prepare_calls=calls, full_calls=full_calls),
    )

    assert engine.stages() == ("evolution_prepare",)
    assert hasattr(engine, engine.KIND_TO_METHOD["evolution_prepare"])

    await engine.handle(_job("evolution_prepare"))

    assert calls == [(engine.run, {"run_id": "run-1"})]
    assert full_calls == []
    for kind in (
        "evolution_advance",
        "evolution_apply",
        "evolution_finalize",
        "evolution_retry",
    ):
        with pytest.raises(ConfigError, match=kind):
            await engine.handle(_job(kind))


async def test_full_engine_declares_all_stage_methods() -> None:
    """Full dispatch exposes five stages with one callable per stage."""
    calls: list[tuple[str, JobRunRecord]] = []
    engine = FullEvolutionEngine(_run(), _deps(full_calls=calls))

    assert engine.stages() == FULL_STAGES
    assert engine.stages() == tuple(engine.KIND_TO_METHOD)
    for method_name in engine.KIND_TO_METHOD.values():
        assert callable(getattr(engine, method_name))

    for kind in FULL_STAGES:
        job = _job(kind)
        await engine.handle(job)

    assert [kind for kind, _job_record in calls] == list(FULL_STAGES)


async def test_missing_declared_method_fails_fast() -> None:
    """A stage mapping that names a missing method is a configuration defect."""

    class BrokenEngine(EvolutionEngine):
        KIND_TO_METHOD: ClassVar[dict[str, str]] = {
            "evolution_prepare": "missing_prepare",
        }

        def stages(self) -> tuple[str, ...]:
            return ("evolution_prepare",)

    engine = BrokenEngine(_run(), _deps())
    with pytest.raises(ConfigError, match="missing_prepare"):
        await engine.handle(_job("evolution_prepare"))


def test_factory_selects_registered_engines_and_fails_fast() -> None:
    """The engine registry is the only selection point."""
    deps = _deps()

    assert isinstance(
        EngineFactory.for_run(_run(), deps),
        FullEvolutionEngine,
    )
    assert isinstance(
        EngineFactory.for_run(
            replace(_run(), engine_key="cluster_only"),
            deps,
        ),
        ClusterOnlyEngine,
    )
    with pytest.raises(ConfigError, match="future"):
        EngineFactory.for_run(
            replace(_run(), engine_key="future"),
            deps,
        )


def test_gateway_freezes_the_run_eval_config_snapshot() -> None:
    """Gateway receives a deeply immutable copy of the creation-time config."""
    eval_config: dict[str, Any] = {
        "gateway": "mock",
        "nested": {"flags": ["stable"], "timeout": 30},
    }
    run = _run(eval_config)
    gateway = EngineFactory.for_run(run, _deps()).gateway()

    eval_config["gateway"] = "changed"
    cast(dict[str, Any], eval_config["nested"])["flags"].append("mutated")

    assert gateway.config["gateway"] == "mock"
    assert gateway.config["nested"] == MappingProxyType(
        {"flags": ("stable",), "timeout": 30},
    )
    with pytest.raises(TypeError):
        cast(dict[str, Any], gateway.config)["gateway"] = "mutated"
    assert isinstance(
        cast(Mapping[str, Any], gateway.config["nested"])["flags"],
        tuple,
    )


def test_every_engine_stage_mapping_matches_its_declared_capabilities() -> None:
    """No engine declares a stage without a method or vice versa."""
    for engine in (
        ClusterOnlyEngine(_run(), _deps()),
        FullEvolutionEngine(_run(), _deps()),
    ):
        assert engine.stages() == tuple(engine.KIND_TO_METHOD)
        assert isinstance(engine, EvolutionEngine)
