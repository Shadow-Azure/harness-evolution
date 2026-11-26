"""FastAPI application composition root."""

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, cast

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.acquisition import router as acquisition_router
from app.api.app_config import router as app_config_router
from app.api.attribution_skill_packages import router as attribution_skill_packages_router
from app.api.attribution_skills import router as attribution_skills_router
from app.api.auth import router as auth_router
from app.api.catalogs import router as catalogs_router
from app.api.events import router as events_router
from app.api.evolution_launch import preview_router, probe_router
from app.api.evolution_runs import router as evolution_runs_router
from app.api.evolution_targets import router as evolution_targets_router
from app.api.evolution_workspace import catalog_router as workspace_catalogs_router
from app.api.evolution_workspace import router as workspace_evolution_router
from app.api.health import router as health_router
from app.api.ingest import router as ingest_router
from app.api.jobs import router as jobs_router
from app.api.overview import router as overview_router
from app.api.problems import router as problems_router
from app.api.problems import workspace_router as workspace_problems_router
from app.api.sessions import router as sessions_router
from app.api.sessions import workspace_router as workspace_sessions_router
from app.api.users import router as users_router
from app.api.workspaces import router as workspaces_router
from app.config import Settings
from app.data_dir import probe_data_directory
from app.db.base import Database
from app.db.crud.attribution_skill_packages import AttributionSkillPackageRepository
from app.db.crud.attribution_skills import AttributionSkillRepository
from app.db.crud.attributions import AttributionRepository, EvolutionRunCandidateRepository
from app.db.crud.bad_case_catalog_sync import BadCaseCatalogSyncRepository
from app.db.crud.bad_case_ingest import BadCaseIngestRepository
from app.db.crud.bad_case_sync import BadCaseRootSyncRepository
from app.db.crud.bad_cases import BadCaseRepository
from app.db.crud.binding_batches import BindingQueue
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.evolution_control import EvolutionControlRepository
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.db.crud.jobs import JobRepository
from app.db.crud.overview import OverviewRepository
from app.db.crud.overview_targets import TargetOverviewRepository
from app.db.crud.potential import PotentialRepository
from app.db.crud.probe_query import ProbeQueryRepository
from app.db.crud.problems import ProblemRepository
from app.db.crud.run_events import SqlRunEventStore
from app.db.crud.sessions import SessionRepository
from app.db.crud.workspace_bad_case_labels import WorkspaceBadCaseLabelRepository
from app.db.crud.workspaces import WorkspaceRepository
from app.db.external_contract import ExternalContractMonitor
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.jobs import JobRunRecord
from app.errors import register_exception_handlers
from app.logging import configure_logging
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import LoginRateLimiter, LoginRateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.service.acquisition.bad_case_catalog_sync import (
    KIND as BAD_CASE_CATALOG_SYNC_KIND,
)
from app.service.acquisition.bad_case_catalog_sync import BadCaseCatalogSyncService
from app.service.acquisition.bad_case_catalog_sync_coordinator import (
    BadCaseCatalogSyncCoordinator,
)
from app.service.acquisition.bad_case_sync import BadCaseRootSyncService
from app.service.acquisition.bad_case_sync_coordinator import (
    KIND as BAD_CASE_ROOT_SYNC_KIND,
)
from app.service.acquisition.bad_case_sync_coordinator import (
    BadCaseRootSyncCoordinator,
)
from app.service.acquisition.sync import SyncCoordinator
from app.service.acquisition.upstream_pull import UpstreamPullService
from app.service.bad_cases.attribution import AttributionReadService
from app.service.bad_cases.service import BadCaseService
from app.service.catalogs import CatalogService
from app.service.events import EventBus
from app.service.evolution.advance import EvolutionAdvanceService, EvolutionJobLifecycle
from app.service.evolution.apply_final import (
    EvolutionApplyService,
    EvolutionFinalizeService,
)
from app.service.evolution.attribution import AttributionRunner, resolve_attribution_engine
from app.service.evolution.attribution_context import AttributionContextProvider
from app.service.evolution.attribution_jobs import (
    ATTRIBUTION_JOB_KIND,
    AttributionJobService,
)
from app.service.evolution.attribution_skill_packages import (
    DEFAULT_PACKAGE_ID,
    AttributionSkillPackageService,
)
from app.service.evolution.attribution_skills import AttributionSkillService
from app.service.evolution.binding_worker import BindingWorker
from app.service.evolution.blocked_sweeper import EvolutionBlockedSweeper
from app.service.evolution.control import EvolutionControlService
from app.service.evolution.engine.contracts import EngineDeps
from app.service.evolution.engine.factory import EngineFactory
from app.service.evolution.eval_poller import (
    EvolutionEvalPoller,
    EvolutionEvalSubmitter,
)
from app.service.evolution.events import (
    EvolutionRunEventService,
    EvolutionRunTopicAuthorizer,
)
from app.service.evolution.gateway_factory import build_eval_gateway_factory
from app.service.evolution.git_candidate import EvolutionCandidateService
from app.service.evolution.launch import EvolutionLaunchService
from app.service.evolution.local_attribution import LocalAttribution
from app.service.evolution.patch_source import default_patch_source_factory
from app.service.evolution.potential import PotentialMatcher, PotentialPreviewService
from app.service.evolution.prepare import EvolutionPrepareService, WorkspacePreparer
from app.service.evolution.probe_query import ProbeQueryService
from app.service.evolution.retry import EvolutionRetryService
from app.service.evolution.runs import EvolutionRunService
from app.service.evolution.stages import EvolutionStageService
from app.service.evolution.target_content import (
    CommitContentSource,
    TargetContentResolver,
    TargetVersionResolver,
)
from app.service.evolution.target_definition import TargetDefinitions
from app.service.evolution.targets import EvolutionTargetService
from app.service.identity.service import IdentityService
from app.service.jobs import JobRunner
from app.service.overview.service import OverviewService
from app.service.overview.targets import TargetOverviewService
from app.service.problems.service import ProblemService
from app.service.sessions.service import SessionService
from app.service.workspaces.bad_case_labels import WorkspaceBadCaseLabelService
from app.service.workspaces.ingest import BadCaseIngestService
from app.service.workspaces.service import WorkspaceService
from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.ai_agent.factory import build_agent_provider
from app.third_party_api.bad_case_sync_source import (
    BadCaseSyncSourceFactory,
    BaseBadCaseSyncSource,
)
from app.third_party_api.git.content import SubprocessGitContent
from app.third_party_api.git.provider import GitPushProviderFactory
from app.third_party_api.git.proxy import GitProxyController, ProxyAwareGitRunner
from app.third_party_api.git.remote import GitRemote, SubprocessGitRemote
from app.third_party_api.git.workspace import GitWorkspaceManager
from app.third_party_api.session_source import HttpSessionSourceClient
from app.third_party_api.trajectory.http import HttpTrajectorySource
from app.third_party_api.trajectory.source import TrajectorySource

logger = logging.getLogger(__name__)


async def _record_ai_agent_health(provider: AIAgentProvider) -> None:
    """Probe the configured provider and record one structured startup event."""
    try:
        health = await provider.health_check()
    except Exception as exc:
        logger.warning(
            "ai agent provider health check failed",
            extra={
                "event": "ai_agent_health",
                "provider_id": provider.provider_id,
                "healthy": False,
                "error_type": type(exc).__name__,
            },
        )
        return
    level = logging.INFO if health.healthy else logging.WARNING
    logger.log(
        level,
        "ai agent provider health",
        extra={
            "event": "ai_agent_health",
            "provider_id": health.provider_id,
            "healthy": health.healthy,
            "auth": health.auth,
            "detail": health.detail,
            "latency_ms": health.latency_ms,
        },
    )


def create_default_app() -> FastAPI:
    """Build the environment-configured application for uvicorn's factory mode."""
    settings = Settings()
    configure_logging(settings)
    return create_app(settings)


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    trajectory_source: TrajectorySource | None = None,
    bad_case_sync_source: BaseBadCaseSyncSource | None = None,
    git_remote: GitRemote | None = None,
    git_workspaces: WorkspacePreparer | None = None,
    target_version_resolver: TargetVersionResolver | None = None,
    definition_source: CommitContentSource | None = None,
) -> FastAPI:
    """Compose middleware, exception handling, and routes."""
    resolved_settings = settings or Settings()
    # Resolve and probe the data directory before any component captures the path.
    # A failure stays visible in /api/health instead of crashing the whole process.
    data_directory = probe_data_directory(resolved_settings.data_dir)
    resolved_settings = resolved_settings.model_copy(update={"data_dir": data_directory.path})
    resolve_attribution_engine(resolved_settings.attribution_engine)
    proxy_controller = GitProxyController.from_settings(resolved_settings)
    git_push_provider = GitPushProviderFactory.create(resolved_settings)
    ai_agent_provider = build_agent_provider(resolved_settings)
    proxy_runner = ProxyAwareGitRunner(
        proxy_controller,
        extra_environment=git_push_provider.auth_environment,
    )
    resolved_database = database or create_database(resolved_settings)
    external_contract = ExternalContractMonitor(
        resolved_database,
        interval_seconds=resolved_settings.external_contract_check_interval_seconds,
    )
    identity = IdentityService(resolved_settings, resolved_database)
    event_bus = EventBus(queue_capacity=resolved_settings.sse_queue_capacity)
    run_event_store = SqlRunEventStore(resolved_database)
    evolution_repository = EvolutionRepository(resolved_database)
    evolution_events = EvolutionRunEventService(
        run_event_store,
        evolution_repository,
        event_bus,
    )
    job_repository = JobRepository(resolved_database)
    jobs = JobRunner(
        job_repository,
        event_bus,
        evolution_events,
        lease_seconds=resolved_settings.job_lease_seconds,
        heartbeat_seconds=resolved_settings.job_heartbeat_seconds,
        drain_timeout_seconds=resolved_settings.job_drain_timeout_seconds,
    )
    evolution_control = EvolutionControlService(
        EvolutionControlRepository(resolved_database),
        evolution_events,
        jobs.schedule,
    )
    jobs.set_evolution_control(evolution_control, evolution_repository)
    upstream_client: httpx.AsyncClient | None = None
    resolved_source = trajectory_source
    if resolved_source is None and resolved_settings.upstream_configured:
        token = resolved_settings.upstream_token
        if token is None:
            raise RuntimeError("upstream configuration lost its token")
        upstream_client = httpx.AsyncClient(
            base_url=resolved_settings.upstream_base_url or "",
            headers={"Authorization": f"Bearer {token.get_secret_value()}"},
            timeout=resolved_settings.upstream_timeout_seconds,
            follow_redirects=False,
        )
        resolved_source = HttpTrajectorySource(
            upstream_client,
            supported_major=resolved_settings.upstream_api_major,
            max_retries=resolved_settings.upstream_retry_attempts,
            backoff_seconds=resolved_settings.upstream_retry_backoff_seconds,
            max_pages=resolved_settings.upstream_max_pages,
        )
    pull_service = UpstreamPullService(resolved_database, jobs, resolved_source)
    jobs.register_handler("pull", pull_service.handle)
    resolved_bad_case_sync_source = bad_case_sync_source
    if resolved_bad_case_sync_source is None:
        resolved_bad_case_sync_source = BadCaseSyncSourceFactory.from_settings(
            resolved_settings,
        )
    session_source_http_client = httpx.AsyncClient(
        timeout=resolved_settings.session_query_timeout_seconds,
        follow_redirects=False,
    )
    session_source_fetcher = HttpSessionSourceClient(
        session_source_http_client,
        max_retries=resolved_settings.session_query_retry_attempts,
        backoff_seconds=resolved_settings.session_query_retry_backoff_seconds,
    )
    bad_case_sync_repository = BadCaseRootSyncRepository(resolved_database)
    bad_case_sync_service = BadCaseRootSyncService.from_settings(
        resolved_database,
        bad_case_sync_repository,
        resolved_bad_case_sync_source,
        resolved_settings,
        session_source_fetcher=session_source_fetcher,
    )
    bad_case_sync = BadCaseRootSyncCoordinator(
        jobs,
        bad_case_sync_repository,
        resolved_settings,
        available=resolved_bad_case_sync_source is not None,
    )
    jobs.register_handler(BAD_CASE_ROOT_SYNC_KIND, bad_case_sync_service.handle)
    catalog_repository = BadCaseCatalogSyncRepository(resolved_database)
    catalog_service = BadCaseCatalogSyncService.from_settings(
        catalog_repository,
        resolved_bad_case_sync_source,
        resolved_settings,
    )
    catalog_sync = BadCaseCatalogSyncCoordinator(
        jobs,
        catalog_repository,
        resolved_settings,
        catalog_service,
        available=resolved_bad_case_sync_source is not None,
    )
    jobs.register_handler(BAD_CASE_CATALOG_SYNC_KIND, catalog_service.handle)
    sync = SyncCoordinator(
        resolved_database,
        jobs,
        job_repository,
        resolved_settings,
    )
    jobs.set_terminal_hook(sync.release_terminal_job)
    sessions = SessionService(SessionRepository(resolved_database))
    overview = OverviewService(
        OverviewRepository(resolved_database),
        bad_case_sync.source_available,
    )
    workspaces = WorkspaceService(WorkspaceRepository(resolved_database))
    bad_case_labels = WorkspaceBadCaseLabelService(
        WorkspaceBadCaseLabelRepository(resolved_database),
    )
    bad_case_ingest = BadCaseIngestService(
        BadCaseIngestRepository(resolved_database),
        workspaces,
    )
    bad_case_repository = BadCaseRepository(resolved_database)
    problems = ProblemService(
        ProblemRepository(resolved_database),
        BadCaseService(bad_case_repository),
        source_available=bad_case_sync.source_available,
    )
    attribution_read = AttributionReadService(
        AttributionRepository(resolved_database),
        ProblemRepository(resolved_database),
    )
    target_repository = EvolutionTargetRepository(resolved_database)
    resolved_git_remote = git_remote or SubprocessGitRemote(
        runner=cast(Any, proxy_runner.run_remote),
    )
    git_content = SubprocessGitContent(
        cache_root=resolved_settings.data_dir / "target-content",
        runner=cast(Any, proxy_runner.run),
    )
    resolver = target_version_resolver or TargetContentResolver(git_content)
    attribution_error = ai_agent_provider.skill_preflight_error()
    attribution_enabled = attribution_error is None
    evolution_targets = EvolutionTargetService(
        target_repository,
        resolved_git_remote,
        TargetDefinitions(
            definition_source or git_content, resolved_settings.attribution_package_dir
        ),
        default_package_id=DEFAULT_PACKAGE_ID if attribution_enabled else None,
    )
    attribution_skills = AttributionSkillService(
        AttributionSkillRepository(resolved_database),
        resolved_settings.attribution_golden_set_path,
    )
    attribution_skill_packages = AttributionSkillPackageService(
        AttributionSkillPackageRepository(resolved_database),
        resolved_settings.attribution_package_dir,
        resolved_settings.attribution_default_skill_path,
        runtime_enabled=attribution_enabled,
    )
    potential_repository = PotentialRepository(resolved_database)
    attribution_repository = AttributionRepository(resolved_database)
    potential_preview = PotentialPreviewService(
        evolution_targets,
        PotentialMatcher(
            potential_repository,
            agent_match_by_name=resolved_settings.agent_match_by_name,
        ),
        resolver,
        reports=attribution_repository,
        rule_skills=attribution_skills,
        local_agent=attribution_enabled,
    )
    probe_query_repository = ProbeQueryRepository(resolved_database)
    evolution_runs = EvolutionRunService(evolution_repository, run_event_store)
    run_candidate_repository = EvolutionRunCandidateRepository(resolved_database)
    potential_matcher = PotentialMatcher(
        potential_repository,
        agent_match_by_name=resolved_settings.agent_match_by_name,
    )
    target_overview = TargetOverviewService(
        target_repository,
        TargetOverviewRepository(resolved_database),
        potential_matcher,
        resolver,
        agent_match_by_name=resolved_settings.agent_match_by_name,
    )
    local_attribution = LocalAttribution(
        resolved_settings,
        attribution_skill_packages,
        attribution_skills,
        resolved_database,
        git_content,
        ai_agent_provider,
    )
    attribution_runner = AttributionRunner(
        attribution_repository,
        context_provider=AttributionContextProvider(potential_repository),
        skill_resolver=local_attribution,
        engine_factory=local_attribution.engine,
        prepare_inputs=local_attribution.prepare_inputs,
        max_concurrency=resolved_settings.attribution_case_concurrency,
    )
    binding_worker = BindingWorker(
        BindingQueue(resolved_database),
        bad_case_sync,
        local_attribution,
        resolver,
        potential_matcher,
        attribution_repository,
        attribution_runner,
    )
    attribution_jobs = AttributionJobService(
        jobs,
        evolution_repository,
        run_candidate_repository,
        attribution_repository,
        attribution_runner,
    )
    evolution_stages = EvolutionStageService(
        evolution_repository,
        probe_query_repository,
        run_candidate_repository,
        attribution_repository,
        bad_case_repository,
    )
    evolution_launch = EvolutionLaunchService(
        evolution_targets,
        potential_matcher,
        evolution_repository,
        jobs,
        evolution_events,
        resolver,
        reports=attribution_repository,
        attribution_skills=local_attribution if attribution_enabled else attribution_skills,
        default_eval_mode=resolved_settings.eval_mode,
    )
    probe_query = ProbeQueryService(probe_query_repository, target_repository)
    default_workspace_manager = GitWorkspaceManager(
        repos_root=resolved_settings.data_dir / "repos",
        workspaces_root=resolved_settings.data_dir / "workspaces",
        runner=cast(Any, proxy_runner.run),
        push_enabled=resolved_settings.git_push,
        push_url=resolved_settings.git_push_url,
        provider=git_push_provider,
    )
    workspace_manager = git_workspaces or default_workspace_manager
    candidate_workspace_manager = cast(GitWorkspaceManager, workspace_manager)
    lifecycle_workspace_manager = cast(Any, workspace_manager)
    prepare_service = EvolutionPrepareService(
        evolution_repository,
        run_candidate_repository,
        attribution_repository,
        potential_matcher,
        attribution_runner,
        workspace_manager,
        evolution_events,
        resolver,
        attribution_jobs=attribution_jobs,
        agent=ai_agent_provider,
        failure_policy=resolved_settings.effective_ai_agent_failure_policy,
    )
    evolution_candidates = EvolutionCandidateService(
        evolution_repository,
        candidate_workspace_manager,
        events=evolution_events,
        web_base_url=resolved_settings.web_base_url,
        patch_source_factory=lambda run: default_patch_source_factory(
            run,
            fallback_mode=resolved_settings.patch_source_mode,
            provider=ai_agent_provider,
        ),
    )
    eval_gateway_factory = build_eval_gateway_factory(resolved_settings)

    def gateway_for_run(run: Any) -> Any:
        """Resolve a gateway through the run's registered engine and frozen config."""
        engine = EngineFactory.for_run(
            run,
            EngineDeps(
                reads=cast(Any, probe_query_repository),
                writes=evolution_repository,
                events=evolution_events,
                gateway_factory=eval_gateway_factory,
            ),
        )
        return engine.gateway()

    evolution_eval_submitter = EvolutionEvalSubmitter(
        evolution_repository,
        gateway_for_run,
        events=evolution_events,
        poll_interval=timedelta(seconds=resolved_settings.eval_poll_seconds),
    )
    evolution_advance = EvolutionAdvanceService(
        evolution_repository,
        evolution_candidates,
        probe_query_repository,
        evolution_eval_submitter,
    )
    evolution_apply = EvolutionApplyService(
        evolution_repository,
        evolution_candidates,
        probe_query_repository,
    )
    evolution_finalize = EvolutionFinalizeService(
        evolution_repository,
        candidate_workspace_manager,
        events=evolution_events,
        eval_submitter=evolution_eval_submitter,
    )
    evolution_eval_poller = EvolutionEvalPoller(
        evolution_repository,
        gateway_for_run,
        jobs,
        events=evolution_events,
        scan_interval=timedelta(seconds=resolved_settings.eval_scan_seconds),
        poll_interval=timedelta(seconds=resolved_settings.eval_poll_seconds),
        timeout=timedelta(seconds=resolved_settings.eval_timeout_seconds),
    )
    evolution_lifecycle = EvolutionJobLifecycle(
        evolution_repository,
        jobs,
        lifecycle_workspace_manager,
        before_terminal=sync.release_terminal_job,
        schedule_candidate_advance=getattr(
            workspace_manager,
            "supports_candidate_lifecycle",
            False,
        ),
    )
    jobs.set_terminal_hook(evolution_lifecycle.on_terminal)
    evolution_retry = EvolutionRetryService(
        evolution_repository,
        evolution_candidates,
        jobs,
        apply=evolution_apply,
        finalize=evolution_finalize,
        advance=evolution_advance,
        eval_submitter=evolution_eval_submitter,
        probes=probe_query_repository,
        events=evolution_events,
    )
    evolution_blocked_sweeper = EvolutionBlockedSweeper(
        evolution_repository,
        jobs,
        scan_interval_seconds=resolved_settings.blocked_sweep_seconds,
    )

    async def prepare_handler(job: JobRunRecord) -> Mapping[str, Any]:
        """Run the real prepare workflow for one admitted run."""
        return await prepare_service.handle(job)

    async def advance_handler(job: JobRunRecord) -> Mapping[str, Any]:
        """Publish the first pending round through the real candidate boundary."""
        return await evolution_advance.handle(job)

    async def apply_handler(job: JobRunRecord) -> Mapping[str, Any]:
        """Apply one completed placeholder evaluation."""
        return await evolution_apply.handle(job)

    async def finalize_handler(job: JobRunRecord) -> Mapping[str, Any]:
        """Persist and publish the placeholder terminal evaluation."""
        return await evolution_finalize.handle(job)

    jobs.register_handler(
        ATTRIBUTION_JOB_KIND,
        attribution_jobs.handle,
        concurrency_limit=resolved_settings.attribution_batch_concurrency,
    )
    jobs.register_handler("evolution_prepare", prepare_handler, concurrency_limit=2)
    jobs.register_handler("evolution_advance", advance_handler)
    jobs.register_handler("evolution_apply", apply_handler)
    jobs.register_handler("evolution_finalize", finalize_handler)
    jobs.register_handler("evolution_retry", evolution_retry.handle)
    catalogs = CatalogService(target_repository, resolved_git_remote)

    @asynccontextmanager
    async def lifespan(lifespan_app: FastAPI) -> AsyncIterator[None]:
        """Start storage and migrations without turning outages into crashes."""
        phase = "startup"
        logger.log(
            logging.WARNING if attribution_error else logging.INFO,
            "attribution runtime preflight",
            extra={
                "event": "attribution.preflight",
                "bwrap_enabled": resolved_settings.attribution_bwrap_enabled,
                "provider_id": ai_agent_provider.provider_id,
                "ready": attribution_enabled,
                "error_code": attribution_error,
            },
        )
        await _record_ai_agent_health(ai_agent_provider)
        proxy_controller.start()
        try:
            await resolved_database.start()
            phase = "migration"
            await upgrade_database(
                resolved_database,
                bootstrap_external_tables=False,
            )
            phase = "identity-seed"
            await identity.seed_admin_if_empty()
            phase = "job-recovery"
            await jobs.recover()
            phase = "sync-scheduler"
            await sync.start_scheduler()
            phase = "bad-case-sync-scheduler"
            await bad_case_sync.start()
            phase = "bad-case-catalog-sync-scheduler"
            await catalog_sync.start()
            phase = "external-contract-monitor"
            await external_contract.start()
            phase = "job-dispatch"
            await jobs.start_queued()
            phase = "eval-poller"
            evolution_eval_poller.start()
            phase = "blocked-sweeper"
            evolution_blocked_sweeper.start()
            phase = "binding-attribution"
            if attribution_enabled:
                binding_worker.start()
            logger.info(
                "binding attribution worker",
                extra={
                    "event": "attribution_binding_worker",
                    "provider_id": ai_agent_provider.provider_id,
                    "started": attribution_enabled,
                },
            )
        except Exception as exc:
            logger.error(
                "database initialization failed",
                extra={
                    "dialect": resolved_settings.db_dialect.value,
                    "phase": phase,
                    "error_type": type(exc).__name__,
                },
            )
            lifespan_app.state.database_start_error = "startup or migration failed"
        try:
            yield
        finally:
            await binding_worker.stop()
            await proxy_controller.stop()
            await external_contract.stop()
            try:
                await evolution_blocked_sweeper.stop()
            finally:
                try:
                    await evolution_eval_poller.stop()
                finally:
                    try:
                        await sync.stop_scheduler()
                    finally:
                        try:
                            await bad_case_sync.stop()
                        finally:
                            try:
                                await catalog_sync.stop()
                            finally:
                                try:
                                    await jobs.close()
                                finally:
                                    try:
                                        if resolved_source is not None:
                                            await resolved_source.close()
                                    finally:
                                        try:
                                            if resolved_bad_case_sync_source is not None:
                                                await resolved_bad_case_sync_source.close()
                                        finally:
                                            try:
                                                await session_source_http_client.aclose()
                                            finally:
                                                try:
                                                    await event_bus.close()
                                                finally:
                                                    await resolved_database.dispose()

    docs_url = "/api/docs" if resolved_settings.docs_enabled else None
    openapi_url = "/api/openapi.json" if resolved_settings.docs_enabled else None
    app = FastAPI(
        title="harness-evolution-api",
        version=resolved_settings.version,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=openapi_url,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.database = resolved_database
    app.state.data_directory = data_directory
    app.state.ai_agent = ai_agent_provider
    app.state.identity = identity
    app.state.event_bus = event_bus
    app.state.jobs = jobs
    app.state.sync = sync
    app.state.bad_case_sync = bad_case_sync
    app.state.bad_case_catalog_sync = catalog_sync
    app.state.external_contract = external_contract
    app.state.upstream_pull = pull_service
    app.state.run_events = run_event_store
    app.state.evolution_events = evolution_events
    app.state.sessions = sessions
    app.state.overview = overview
    app.state.target_overview = target_overview
    app.state.workspaces = workspaces
    app.state.bad_case_labels = bad_case_labels
    app.state.bad_case_ingest = bad_case_ingest
    app.state.problems = problems
    app.state.attribution_read = attribution_read
    app.state.evolution_repository = evolution_repository
    app.state.evolution_targets = evolution_targets
    # Package bindings stay readable and editable while the execution sandbox is unavailable.
    app.state.local_attribution = local_attribution if ai_agent_provider.supports_skills else None
    app.state.attribution_skills = attribution_skills
    app.state.attribution_skill_packages = attribution_skill_packages
    app.state.attribution_jobs = attribution_jobs
    app.state.target_version_resolver = resolver
    app.state.potential_preview = potential_preview
    app.state.evolution_runs = evolution_runs
    app.state.evolution_stages = evolution_stages
    app.state.evolution_candidates = evolution_candidates
    app.state.evolution_gateway_factory = eval_gateway_factory
    app.state.evolution_patch_source_factory = evolution_candidates.patch_source_factory
    app.state.evolution_advance = evolution_advance
    app.state.evolution_apply = evolution_apply
    app.state.evolution_finalize = evolution_finalize
    app.state.evolution_control = evolution_control
    app.state.evolution_retry = evolution_retry
    app.state.blocked_sweeper = evolution_blocked_sweeper
    app.state.evolution_eval_poller = evolution_eval_poller
    app.state.evolution_lifecycle = evolution_lifecycle
    app.state.git_workspaces = workspace_manager
    app.state.evolution_launch = evolution_launch
    app.state.probe_query = probe_query
    app.state.catalogs = catalogs
    app.state.run_event_replay = run_event_store
    app.state.run_topic_authorizer = EvolutionRunTopicAuthorizer(
        evolution_repository,
        workspaces,
    )
    app.state.login_rate_limiter = LoginRateLimiter(limit=resolved_settings.login_rate_limit)
    app.state.database_start_error = None

    app.add_middleware(AuthMiddleware)
    app.add_middleware(LoginRateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(app_config_router)
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(workspaces_router)
    app.include_router(ingest_router)
    app.include_router(jobs_router)
    app.include_router(sessions_router)
    app.include_router(workspace_sessions_router)
    app.include_router(problems_router)
    app.include_router(workspace_problems_router)
    app.include_router(overview_router)
    app.include_router(evolution_runs_router)
    app.include_router(probe_router)
    app.include_router(preview_router)
    app.include_router(evolution_targets_router)
    app.include_router(attribution_skills_router)
    app.include_router(attribution_skill_packages_router)
    app.include_router(workspace_evolution_router)
    app.include_router(catalogs_router)
    app.include_router(workspace_catalogs_router)
    app.include_router(events_router)
    app.include_router(acquisition_router)
    return app
