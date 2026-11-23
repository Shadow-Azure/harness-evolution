"""Synchronous launch validation and asynchronous run admission."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol, cast

from app.db.crud.attributions import AttributionRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.evolution_targets import EvolutionTargetRecord
from app.db.crud.potential import ObjectType, window_day_boundaries
from app.errors import AppError, ErrorCode
from app.service.evolution.attribution import DEFAULT_ATTRIBUTION_ENGINE
from app.service.evolution.attribution_contracts import is_platform_rule
from app.service.evolution.attribution_executor import AGENT_SKILL_STUB_ENGINE
from app.service.evolution.engine.factory import EngineFactory
from app.service.evolution.events import EvolutionRunEventService
from app.service.evolution.potential import (
    MatchCondition,
    PotentialMatcher,
    ResolvedPolicy,
    resolve_policy,
    resolve_window,
)
from app.service.evolution.probe_query import (
    ProbeQueryRequest,
    RunAccepted,
    normalized_query,
)
from app.service.evolution.target_content import (
    ResolvedTargetVersion,
    TargetVersionResolver,
)
from app.service.jobs import JobRunner, sanitize_job_payload
from app.utils.ids import new_id

logger = logging.getLogger(__name__)


class LaunchTargetStore(Protocol):
    """Persistence operations consumed by the launch service."""

    async def enabled_config(
        self,
        object_type: str,
        object_name: str,
        *,
        workspace_ids: Sequence[str] | None = None,
    ) -> EvolutionTargetRecord:
        """Return the one enabled pair inside the optional workspace scope."""
        ...


class LaunchAttributionSkill(Protocol):
    """Resolved immutable Skill facts frozen into a run."""

    skill_key: str
    revision: int
    content_hash: str
    executor_type: str


class LaunchAttributionSkillResolver(Protocol):
    """Resolve the effective Skill for a configured target."""

    async def resolve_for_run(
        self, target: EvolutionTargetRecord, package_id: str | None
    ) -> LaunchAttributionSkill:
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
        events: EvolutionRunEventService | None,
        resolver: TargetVersionResolver,
        *,
        reports: AttributionRepository | None = None,
        attribution_skills: LaunchAttributionSkillResolver | None = None,
    ) -> None:
        """Bind launch collaborators for both run modes."""
        self._targets = targets
        self._matcher = matcher
        self._runs = runs
        self._jobs = jobs
        self._events = events
        self._attribution_skills = attribution_skills
        self._reports = reports
        self._resolver = resolver

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
        latest_only = bool(self._reports and config.attribution_package_id and body.cache_enabled)
        effective_skill = None
        if body.attribution_package_id and (body.cache_enabled or self._attribution_skills is None):
            raise AppError(
                status_code=422,
                code=ErrorCode.VALIDATION_INVALID,
                message="select a Skill only for recomputation using a configured agent",
            )
        if self._attribution_skills and not latest_only:
            effective_skill = await self._attribution_skills.resolve_for_run(
                config, body.attribution_package_id
            )
        query = normalized_query(
            body,
            default_version=config.default_ref,
            workspace_ids=(config.workspace_id,),
        )
        resolved = await self._resolve_version(body, query.target_version, config)
        policy = resolve_policy(body.policy)
        condition = _match_condition(query, config.workspace_id, resolved)
        cases = await self._require_potential(condition, policy)
        if (
            self._reports
            and latest_only
            and not await self._reports.latest_reports(
                config.workspace_id,
                body.target_type,
                body.target_name,
                resolved.target_revision,
                cases,
            )
        ):
            raise AppError(
                status_code=409,
                code=ErrorCode.NO_POTENTIAL_MATCHED,
                message="no cached attribution reports for these cases",
            )
        job_id = new_id()
        run = await self._runs.create_run(
            self._run_values(
                body,
                query,
                config,
                resolved=resolved,
                policy=policy,
                created_by=created_by,
                effective_skill=effective_skill,
                latest_only=latest_only,
            ),
            initial_job_id=job_id,
        )
        try:
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
        except Exception:
            logger.exception(
                "failed to record run creation event", extra={"run_id": run.id, "job_id": job_id}
            )
        finally:
            self._jobs.schedule(job_id)
        return RunAccepted(run_id=run.id, job_id=job_id, status="preparing")

    async def _require_potential(
        self,
        condition: MatchCondition,
        policy: Any,
    ) -> tuple[str, ...]:
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

        return tuple(case.bad_case_id for case in match.included)

    def _run_values(
        self,
        body: ProbeQueryRequest,
        query: Any,
        config: EvolutionTargetRecord,
        *,
        resolved: ResolvedTargetVersion,
        policy: ResolvedPolicy,
        created_by: str | None,
        effective_skill: LaunchAttributionSkill | None,
        latest_only: bool,
    ) -> Mapping[str, Any]:
        """Build the immutable run snapshot inserted before enqueueing.

        Args:
            body: Original wizard condition including engine selection.
            query: Normalized condition with the resolved version.
            config: Enabled target configuration backing the launch.
            resolved: User-facing version plus the resolved body-hash revision.
            policy: Validated potential policy resolved from the request.
            created_by: Authenticated principal that started the run.

        Returns:
            Column values for one `preparing` run row.
        """
        start, end = resolve_window(query.window_from, query.window_to)
        legacy_rule = not config.attribution_package_id and (
            effective_skill is None
            or is_platform_rule(effective_skill.skill_key, effective_skill.executor_type)
        )
        return {
            "title": f"{query.target_name} {resolved.target_version} 自进化",
            "workspace_id": config.workspace_id,
            "mode": body.mode,
            "engine_key": body.engine_key or body.mode,
            "eval_config": _snapshot_eval(body.eval),
            "potential_policy": {
                **policy.snapshot(),
                **({"latestReportsOnly": True} if latest_only else {}),
                **({"legacyRule": True} if legacy_rule else {}),
                **(
                    {"attributionPackageId": body.attribution_package_id}
                    if body.attribution_package_id
                    else {}
                ),
            },
            "cache_enabled": body.cache_enabled,
            "attribution_engine": _attribution_engine(effective_skill),
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
            "target_version": resolved.target_version,
            "target_revision": resolved.target_revision,
            "base_commit": resolved.base_commit,
            "repo_url": config.repo_url,
            "sub_dir": config.sub_dir,
            "validation_project_id": config.validation_project_id,
            "test_project_id": config.test_project_id,
            "base_ref": resolved.target_version,
            "window_from": start,
            "window_to": end,
            "models": list(query.models),
            "status": "preparing",
            "created_by": created_by,
        }

    async def _resolve_version(
        self,
        body: ProbeQueryRequest,
        version: str,
        config: EvolutionTargetRecord,
    ) -> ResolvedTargetVersion:
        """Resolve the launch version, refusing to guess when content is absent."""
        return await self._resolver.resolve(
            object_type=body.target_type,
            repo_url=config.repo_url,
            sub_dir=config.sub_dir,
            version=version,
        )


def _snapshot_eval(eval_config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Redact credential fields from eval config before the run snapshot is durable.

    Args:
        eval_config: Credential-bearing eval selection from the wizard body.

    Returns:
        The snapshot dictionary with the same redaction applied to job payloads.

    The ``apiKeyRef`` value is an environment-variable NAME, not a credential:
    the blanket credential-key redaction would erase it and leave the http
    gateway pointing at an unset variable at submit time, so the original name
    is restored after the pass.
    """
    source = dict(eval_config or {})
    sanitized = sanitize_job_payload(source)
    if not isinstance(sanitized, dict):
        return {}
    snapshot = {str(key): value for key, value in sanitized.items()}
    ref = source.get("apiKeyRef")
    if isinstance(ref, str) and ref.strip():
        snapshot["apiKeyRef"] = ref.strip()
    else:
        # Nothing to reference: drop the redacted placeholder so the gateway
        # falls back to the env-provided key instead of an unset literal.
        snapshot.pop("apiKeyRef", None)
    return snapshot


def _attribution_engine(effective_skill: LaunchAttributionSkill | None) -> str:
    """Select the engine matching the resolved Skill executor boundary."""
    if effective_skill is None or effective_skill.executor_type == "builtin_rule":
        return DEFAULT_ATTRIBUTION_ENGINE
    if effective_skill.executor_type == "local_agent":
        return "local-agent-skill-v1"
    if effective_skill.executor_type == "agent_stub":
        return AGENT_SKILL_STUB_ENGINE
    raise AppError(
        status_code=409,
        code=ErrorCode.ATTRIBUTION_SKILL_INVALID,
        message="the selected attribution Skill executor is not available",
        details={"executorType": effective_skill.executor_type},
    )


def _match_condition(
    query: Any,
    workspace_id: str,
    resolved: ResolvedTargetVersion,
) -> MatchCondition:
    """Build the shared matcher condition from the validated launch request."""
    start, end = resolve_window(query.window_from, query.window_to)
    window_start, window_end = window_day_boundaries(start, end)
    return MatchCondition(
        workspace_id=workspace_id,
        target_type=cast(ObjectType, query.target_type),
        target_name=query.target_name,
        target_version=resolved.target_version,
        target_revision=resolved.target_revision,
        window_start=window_start,
        window_end=window_end,
    )
