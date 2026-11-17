"""Synchronous launch validation and asynchronous run admission."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol, cast

from app.db.crud.evolution import EvolutionRepository
from app.db.crud.potential import ObjectType, window_day_boundaries
from app.errors import AppError, ErrorCode
from app.service.evolution.attribution import DEFAULT_ATTRIBUTION_ENGINE
from app.service.evolution.engine.factory import EngineFactory
from app.service.evolution.events import EvolutionRunEventService
from app.service.evolution.potential import (
    MatchCondition,
    PotentialMatcher,
    ResolvedPolicy,
    resolve_policy,
    resolve_target_revision,
    resolve_window,
)
from app.service.evolution.probe_query import (
    ProbeQueryRequest,
    RunAccepted,
    normalized_query,
)
from app.service.jobs import JobRunner, sanitize_job_payload


class LaunchTargetRecord(Protocol):
    """Read-only enabled-target facts consumed from configuration storage."""

    @property
    def id(self) -> str:
        """Return the configured target id."""

    @property
    def object_type(self) -> str:
        """Return the configured object type."""

    @property
    def object_name(self) -> str:
        """Return the configured object name."""

    @property
    def default_ref(self) -> str:
        """Return the configured default reference."""

    @property
    def repo_url(self) -> str:
        """Return the configured git remote."""

    @property
    def sub_dir(self) -> str:
        """Return the configured repository sub directory."""

    @property
    def validation_project_id(self) -> str:
        """Return the configured validation-set test project id."""

    @property
    def test_project_id(self) -> str:
        """Return the configured test-set test project id."""

    @property
    def enabled(self) -> bool:
        """Return whether the target accepts launches."""

    @property
    def workspace_id(self) -> str:
        """Return the workspace that owns this configuration."""


class LaunchTargetStore(Protocol):
    """Persistence operations consumed by the launch service."""

    async def enabled_config(
        self,
        object_type: str,
        object_name: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> LaunchTargetRecord:
        """Return the one enabled pair inside the optional workspace scope."""
        ...


class LaunchAttributionSkill(Protocol):
    """Resolved immutable Skill facts frozen into a run."""

    skill_key: str
    revision: int
    content_hash: str


class LaunchAttributionSkillResolver(Protocol):
    """Resolve the effective Skill for a configured target."""

    async def resolve(self, workspace_id: str, target_id: str) -> LaunchAttributionSkill:
        """Return target, workspace, or platform fallback resolution."""
        ...


class EvolutionLaunchService:
    """Validate wizard conditions, snapshot the run, and enqueue preparation."""

    def __init__(
        self,
        targets: LaunchTargetStore,
        matcher: PotentialMatcher,
        runs: EvolutionRepository,
        jobs: JobRunner,
        events: EvolutionRunEventService | None = None,
        *,
        attribution_skills: LaunchAttributionSkillResolver | None = None,
    ) -> None:
        """Bind launch collaborators for both run modes."""
        self._targets = targets
        self._matcher = matcher
        self._runs = runs
        self._jobs = jobs
        self._events = events
        self._attribution_skills = attribution_skills

    async def request_run(
        self,
        body: ProbeQueryRequest,
        *,
        expected_mode: Literal["full", "cluster_only"],
        created_by: str | None,
        workspace_ids: Sequence[str] | None = None,
    ) -> RunAccepted:
        """Validate one launch and admit its asynchronous preparation.

        Args:
            body: Validated wizard condition including the requested mode.
            expected_mode: Mode served by the calling endpoint.
            created_by: Authenticated principal that started the run.
            workspace_ids: Visible or explicit workspace scope for the target.

        Returns:
            The accepted run identifier, job identifier, and preparing status.

        Raises:
            AppError: On mode mismatch, inverted windows, a disabled or
                ambiguous target, or when no analyzed probe matches.
        """
        if body.mode != expected_mode:
            raise AppError(
                status_code=422,
                code=ErrorCode.VALIDATION_INVALID,
                message="launch mode does not match the endpoint",
            )
        engine_key = body.engine_key or body.mode
        policy = resolve_policy(body.policy)
        if not EngineFactory.is_registered(engine_key):
            raise AppError(
                status_code=422,
                code=ErrorCode.ENGINE_INVALID,
                message="evolution engine is not registered",
                details={"engineKey": engine_key},
            )
        config = await self._targets.enabled_config(
            body.target_type,
            body.target_name,
            workspace_ids=workspace_ids,
        )
        effective_skill = (
            await self._attribution_skills.resolve(config.workspace_id, config.id)
            if self._attribution_skills is not None
            else None
        )
        query = normalized_query(
            body,
            default_version=config.default_ref,
            workspace_ids=(config.workspace_id,),
        )
        policy = resolve_policy(body.policy)
        condition = _match_condition(query, config.workspace_id)
        await self._require_potential(condition, policy)
        run = await self._runs.create_run(
            self._run_values(
                body,
                query,
                config,
                policy=policy,
                created_by=created_by,
                effective_skill=effective_skill,
            ),
        )
        if self._events is not None:
            await self._events.record(
                run.id,
                "run_created",
                level="info",
                stage="prepare",
                message="运行已创建",
                payload={
                    "mode": run.mode,
                    "targetType": run.target_type,
                    "targetName": run.target_name,
                    "targetVersion": run.target_version,
                },
            )
        job = await self._jobs.submit(
            kind="evolution_prepare",
            payload={"runId": run.id},
            ref_id=run.id,
            created_by=created_by,
        )
        return RunAccepted(run_id=run.id, job_id=job.id, status="preparing")

    async def _require_potential(
        self,
        condition: MatchCondition,
        policy: Any,
    ) -> None:
        """Fail the launch before any write when nothing can be attributed.

        Args:
            condition: Normalized matcher condition with resolved revision.
            policy: Validated policy switches.

        Raises:
            AppError: With `NO_ASSOCIATED_SESSIONS` or `NO_POTENTIAL_MATCHED`
                when the shared matcher finds no work.
        """
        association = await self._matcher.associated_sessions(condition)
        if not association.sessions:
            raise AppError(
                status_code=409,
                code=ErrorCode.NO_ASSOCIATED_SESSIONS,
                message="no Session contains the requested object version",
                details={
                    "summary": {
                        "reported": association.reported,
                        "associated": association.associated,
                        "skipped": association.skipped,
                        "versionUnresolved": association.version_unresolved,
                        "pending": association.pending,
                    },
                },
            )
        match = await self._matcher.potential_cases(condition, association, policy)
        if not match.included:
            raise AppError(
                status_code=409,
                code=ErrorCode.NO_POTENTIAL_MATCHED,
                message="no potential bad case matches the run policy",
                details={
                    "summary": {
                        "badCases": len(match.cases),
                        "potential": match.potential,
                    },
                },
            )

    def _run_values(
        self,
        body: ProbeQueryRequest,
        query: Any,
        config: LaunchTargetRecord,
        *,
        policy: ResolvedPolicy,
        created_by: str | None,
        effective_skill: LaunchAttributionSkill | None,
    ) -> Mapping[str, Any]:
        """Build the immutable run snapshot inserted before enqueueing.

        Args:
            body: Original wizard condition including engine selection.
            query: Normalized condition with the resolved version.
            config: Enabled target configuration backing the launch.
            policy: Validated potential policy resolved from the request.
            created_by: Authenticated principal that started the run.

        Returns:
            Column values for one `preparing` run row.
        """
        return {
            "title": f"{query.target_name} {query.target_version} 自进化",
            "workspace_id": config.workspace_id,
            "mode": body.mode,
            "engine_key": body.engine_key or body.mode,
            "eval_config": _snapshot_eval(body.eval),
            "potential_policy": policy.snapshot(),
            "cache_enabled": body.cache_enabled,
            "attribution_engine": DEFAULT_ATTRIBUTION_ENGINE,
            "attribution_skill_key": (
                effective_skill.skill_key if effective_skill is not None else None
            ),
            "attribution_skill_revision": (
                effective_skill.revision if effective_skill is not None else None
            ),
            "attribution_skill_content_hash": (
                effective_skill.content_hash if effective_skill is not None else None
            ),
            "target_config_id": config.id,
            "target_type": query.target_type,
            "target_name": query.target_name,
            "target_version": query.target_version,
            "repo_url": config.repo_url,
            "sub_dir": config.sub_dir,
            "validation_project_id": config.validation_project_id,
            "test_project_id": config.test_project_id,
            "base_ref": config.default_ref,
            "window_from": query.window_from,
            "window_to": query.window_to,
            "models": list(query.models),
            "status": "preparing",
            "created_by": created_by,
        }


def _snapshot_eval(eval_config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Redact credential fields from eval config before the run snapshot is durable.

    Args:
        eval_config: Credential-bearing eval selection from the wizard body.

    Returns:
        The snapshot dictionary with the same redaction applied to job payloads.
    """
    sanitized = sanitize_job_payload(dict(eval_config or {}))
    if not isinstance(sanitized, dict):
        return {}
    return {str(key): value for key, value in sanitized.items()}


def _match_condition(query: Any, workspace_id: str) -> MatchCondition:
    """Build the shared matcher condition from the validated launch request."""
    target_version, target_revision = resolve_target_revision(query.target_version)
    start, end = resolve_window(query.window_from, query.window_to)
    window_start, window_end = window_day_boundaries(start, end)
    return MatchCondition(
        workspace_id=workspace_id,
        target_type=cast(ObjectType, query.target_type),
        target_name=query.target_name,
        target_version=target_version,
        target_revision=target_revision,
        window_start=window_start,
        window_end=window_end,
    )
