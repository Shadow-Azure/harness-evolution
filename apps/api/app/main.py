"""FastAPI application composition root."""

import logging
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.acquisition import router as acquisition_router
from app.api.auth import router as auth_router
from app.api.catalogs import router as catalogs_router
from app.api.events import router as events_router
from app.api.evolution_launch import preview_router, probe_router
from app.api.evolution_runs import router as evolution_runs_router
from app.api.evolution_targets import router as evolution_targets_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.problems import router as problems_router
from app.api.sessions import router as sessions_router
from app.api.users import router as users_router
from app.config import Settings
from app.db.base import Database
from app.db.crud.bad_cases import BadCaseRepository
from app.db.crud.evolution import EvolutionRepository
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.db.crud.jobs import JobRepository
from app.db.crud.probe_query import ProbeQueryRepository
from app.db.crud.problems import ProblemRepository
from app.db.crud.run_events import SqlRunEventStore
from app.db.crud.sessions import SessionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.db.models.jobs import JobRunRecord
from app.errors import register_exception_handlers
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import LoginRateLimiter, LoginRateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.service.acquisition.sync import SyncCoordinator
from app.service.acquisition.upstream_pull import UpstreamPullService
from app.service.bad_cases.service import BadCaseService
from app.service.catalogs import CatalogService
from app.service.events import EventBus
from app.service.evolution.advance import EvolutionAdvanceService, EvolutionJobLifecycle
from app.service.evolution.events import (
    EvolutionRunEventService,
    EvolutionRunTopicAuthorizer,
)
from app.service.evolution.git_candidate import EvolutionCandidateService
from app.service.evolution.launch import EvolutionLaunchService
from app.service.evolution.prepare import (
    EvolutionPrepareService,
    RepositoryProbeReader,
    WorkspacePreparer,
)
from app.service.evolution.probe_query import ProbeQueryService
from app.service.evolution.runs import EvolutionRunService
from app.service.evolution.stages import EvolutionStageService
from app.service.evolution.targets import EvolutionTargetService
from app.service.identity.service import IdentityService
from app.service.jobs import JobRunner
from app.service.problems.service import ProblemService
from app.service.sessions.service import SessionService
from app.third_party_api.git.remote import GitRemote, SubprocessGitRemote
from app.third_party_api.git.workspace import GitWorkspaceManager
from app.third_party_api.trajectory.http import HttpTrajectorySource
from app.third_party_api.trajectory.source import TrajectorySource

logger = logging.getLogger(__name__)


def create_default_app() -> FastAPI:
    """Build the environment-configured application for uvicorn's factory mode."""
    return create_app(Settings())


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    trajectory_source: TrajectorySource | None = None,
    git_remote: GitRemote | None = None,
    git_workspaces: WorkspacePreparer | None = None,
) -> FastAPI:
    """Compose middleware, exception handling, and routes."""
    resolved_settings = settings or Settings()
    resolved_database = database or create_database(resolved_settings)
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
    jobs = JobRunner(job_repository, event_bus, evolution_events)
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
    sync = SyncCoordinator(
        resolved_database,
        jobs,
        job_repository,
        resolved_settings,
    )
    jobs.set_terminal_hook(sync.release_terminal_job)
    sessions = SessionService(SessionRepository(resolved_database))
    problems = ProblemService(
        ProblemRepository(resolved_database),
        BadCaseService(BadCaseRepository(resolved_database)),
    )
    target_repository = EvolutionTargetRepository(resolved_database)
    resolved_git_remote = git_remote or SubprocessGitRemote()
    evolution_targets = EvolutionTargetService(target_repository, resolved_git_remote)
    probe_query_repository = ProbeQueryRepository(resolved_database)
    evolution_runs = EvolutionRunService(evolution_repository, run_event_store)
    evolution_stages = EvolutionStageService(evolution_repository, probe_query_repository)
    evolution_launch = EvolutionLaunchService(
        target_repository,
        probe_query_repository,
        evolution_repository,
        jobs,
        evolution_events,
    )
    probe_query = ProbeQueryService(probe_query_repository, target_repository)
    default_workspace_manager = GitWorkspaceManager(
        repos_root=resolved_settings.data_dir / "repos",
        workspaces_root=resolved_settings.data_dir / "workspaces",
        push_enabled=resolved_settings.git_push_enabled,
    )
    workspace_manager = git_workspaces or default_workspace_manager
    candidate_workspace_manager = (
        git_workspaces
        if isinstance(git_workspaces, GitWorkspaceManager)
        else default_workspace_manager
    )
    prepare_service = EvolutionPrepareService(
        evolution_repository,
        RepositoryProbeReader(probe_query_repository),
        workspace_manager,
        evolution_events,
    )
    evolution_candidates = EvolutionCandidateService(
        evolution_repository,
        candidate_workspace_manager,
        events=evolution_events,
        web_base_url=resolved_settings.web_base_url,
    )
    evolution_advance = EvolutionAdvanceService(
        evolution_repository,
        evolution_candidates,
        probe_query_repository,
    )
    evolution_lifecycle = EvolutionJobLifecycle(
        evolution_repository,
        jobs,
        default_workspace_manager,
        before_terminal=sync.release_terminal_job,
    )
    jobs.set_terminal_hook(evolution_lifecycle.on_terminal)

    async def prepare_handler(job: JobRunRecord) -> Mapping[str, Any]:
        """Run the real prepare workflow for one admitted run."""
        return await prepare_service.handle(job)

    async def advance_handler(job: JobRunRecord) -> Mapping[str, Any]:
        """Publish the first pending round through the real candidate boundary."""
        return await evolution_advance.handle(job)

    jobs.register_handler("evolution_prepare", prepare_handler)
    jobs.register_handler("evolution_advance", advance_handler)
    catalogs = CatalogService(target_repository, resolved_git_remote)

    @asynccontextmanager
    async def lifespan(lifespan_app: FastAPI) -> AsyncIterator[None]:
        """Start storage and migrations without turning outages into crashes."""
        phase = "startup"
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
            phase = "job-dispatch"
            await jobs.start_queued()
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
            try:
                await sync.stop_scheduler()
            finally:
                try:
                    await jobs.close()
                finally:
                    try:
                        if resolved_source is not None:
                            await resolved_source.close()
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
    app.state.identity = identity
    app.state.event_bus = event_bus
    app.state.jobs = jobs
    app.state.sync = sync
    app.state.upstream_pull = pull_service
    app.state.run_events = run_event_store
    app.state.evolution_events = evolution_events
    app.state.sessions = sessions
    app.state.problems = problems
    app.state.evolution_targets = evolution_targets
    app.state.evolution_runs = evolution_runs
    app.state.evolution_stages = evolution_stages
    app.state.evolution_candidates = evolution_candidates
    app.state.evolution_advance = evolution_advance
    app.state.evolution_launch = evolution_launch
    app.state.probe_query = probe_query
    app.state.catalogs = catalogs
    app.state.run_event_replay = run_event_store
    app.state.run_topic_authorizer = EvolutionRunTopicAuthorizer(
        evolution_repository,
    )
    app.state.login_rate_limiter = LoginRateLimiter()
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
    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(jobs_router)
    app.include_router(sessions_router)
    app.include_router(problems_router)
    app.include_router(evolution_runs_router)
    app.include_router(probe_router)
    app.include_router(preview_router)
    app.include_router(evolution_targets_router)
    app.include_router(catalogs_router)
    app.include_router(events_router)
    app.include_router(acquisition_router)
    return app
