"""FastAPI application composition root."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.events import router as events_router
from app.api.health import router as health_router
from app.api.jobs import router as jobs_router
from app.api.sessions import router as sessions_router
from app.api.users import router as users_router
from app.config import Settings
from app.db.base import Database
from app.db.crud.jobs import JobRepository
from app.db.crud.run_events import SqlRunEventStore
from app.db.crud.sessions import SessionRepository
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.errors import register_exception_handlers
from app.middleware.auth import AuthMiddleware
from app.middleware.rate_limit import LoginRateLimiter, LoginRateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.service.events import EventBus, ShapeRunTopicAuthorizer
from app.service.identity.service import IdentityService
from app.service.jobs import JobRunner
from app.service.sessions.service import SessionService

logger = logging.getLogger(__name__)


def create_default_app() -> FastAPI:
    """Build the environment-configured application for uvicorn's factory mode."""
    return create_app(Settings())


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
) -> FastAPI:
    """Compose middleware, exception handling, and routes."""
    resolved_settings = settings or Settings()
    resolved_database = database or create_database(resolved_settings)
    identity = IdentityService(resolved_settings, resolved_database)
    event_bus = EventBus(queue_capacity=resolved_settings.sse_queue_capacity)
    run_event_store = SqlRunEventStore(resolved_database)
    jobs = JobRunner(JobRepository(resolved_database), event_bus, run_event_store)
    sessions = SessionService(SessionRepository(resolved_database))

    @asynccontextmanager
    async def lifespan(lifespan_app: FastAPI) -> AsyncIterator[None]:
        """Start storage and migrations without turning outages into crashes."""
        phase = "startup"
        try:
            await resolved_database.start()
            phase = "migration"
            await upgrade_database(resolved_database)
            phase = "identity-seed"
            await identity.seed_admin_if_empty()
            phase = "job-recovery"
            await jobs.start()
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
            await jobs.close()
            await event_bus.close()
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
    app.state.run_events = run_event_store
    app.state.sessions = sessions
    app.state.run_event_replay = run_event_store
    app.state.run_topic_authorizer = ShapeRunTopicAuthorizer()
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
    app.include_router(events_router)
    return app
