"""Fetch upstream packages, store raw payloads, and enqueue replay."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.base import Database
from app.db.crud.local_sessions import write_local_payloads
from app.db.crud.sync_errors import append_sync_error_records
from app.db.models.jobs import JobRunRecord
from app.service.acquisition.replay import replay_pending_payloads
from app.service.acquisition.upstream import package_to_payloads
from app.service.jobs import JobRunner
from app.third_party_api.trajectory.models import UpstreamItemIssue
from app.third_party_api.trajectory.source import TrajectorySource
from app.utils.time import now_shanghai


class PullWindow(BaseModel):
    """Date window accepted by the upstream enumeration endpoint."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_date: date = Field(alias="from")
    to_date: date = Field(alias="to")
    problem_only: bool = Field(default=True, alias="problemOnly")
    cursor: str | None = None

    @model_validator(mode="after")
    def validate_window(self) -> PullWindow:
        """Require an ordered bounded window."""
        if self.to_date < self.from_date:
            raise ValueError("window end must not precede start")
        return self


class PullJobPayload(BaseModel):
    """Durable selector stored on one queued pull job."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    session_ids: (
        list[
            Annotated[
                str,
                Field(
                    min_length=1,
                    max_length=36,
                    pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
                ),
            ]
        ]
        | None
    ) = Field(default=None, alias="sessionIds")
    window: PullWindow | None = None

    @model_validator(mode="after")
    def exactly_one_selector(self) -> PullJobPayload:
        """Require exactly one non-empty selector."""
        selected = int(self.session_ids is not None) + int(self.window is not None)
        if selected != 1:
            raise ValueError("exactly one of sessionIds or window is required")
        if self.session_ids is not None:
            if not self.session_ids or any(not item for item in self.session_ids):
                raise ValueError("sessionIds must be a non-empty list")
            if len(self.session_ids) != len(set(self.session_ids)):
                raise ValueError("sessionIds must be unique")
        return self


class UpstreamPullService:
    """Execute pull jobs through the same raw-payload and replay pipeline."""

    def __init__(
        self,
        database: Database,
        jobs: JobRunner,
        source: TrajectorySource | None,
    ) -> None:
        """Bind the lifespan-owned source and durable execution services."""
        self._database = database
        self._jobs = jobs
        self._source = source

    @property
    def available(self) -> bool:
        """Return whether an upstream source is configured."""
        return self._source is not None

    async def handle(self, job: JobRunRecord) -> Mapping[str, Any]:
        """Fetch selected sessions, upsert raw payloads, then replay pending roots."""
        source = self._source
        if source is None:
            raise RuntimeError("upstream source is unavailable")
        payload = PullJobPayload.model_validate(job.payload)
        await self._jobs.update_progress(
            job.id,
            0.1,
            unit="sessions",
            stage_label="fetching",
        )
        if payload.session_ids is not None:
            session_ids = list(payload.session_ids)
        else:
            window = payload.window
            if window is None:
                raise ValueError("pull window is missing")
            enumerated = await source.list_window(
                from_date=window.from_date,
                to_date=window.to_date,
                problem_only=window.problem_only,
                cursor=window.cursor,
            )
            session_ids = [item.session_id for item in enumerated]
        fetched = await source.fetch_many(session_ids)
        await self._jobs.update_progress(
            job.id,
            0.45,
            unit="sessions",
            total=len(session_ids),
            stage_label="storing",
        )
        payloads = tuple(
            raw
            for package in fetched.packages
            for raw in package_to_payloads(package, discovered_at=now_shanghai())
        )
        written = await write_local_payloads(
            self._database,
            payloads,
            source_type="http_api",
        )

        async def replay_progress(done: int, total: int) -> None:
            ratio = done / max(total, 1)
            await self._jobs.update_progress(
                job.id,
                0.5 + ratio * 0.5,
                unit="payloads",
                total=total,
                stage_label="normalizing",
            )

        replay = await replay_pending_payloads(
            self._database,
            on_progress=replay_progress,
            sync_run_id=job.id,
            source_type="http_api",
        )
        issues: tuple[UpstreamItemIssue, ...] = fetched.issues
        await append_sync_error_records(
            self._database,
            replay.sync_run_id,
            [
                {
                    "sessionId": issue.session_id,
                    "lineNo": 0,
                    "code": issue.code,
                    "message": issue.message,
                }
                for issue in issues
            ],
        )
        return {
            "sessionsRequested": len(session_ids),
            "sessionsFetched": len(fetched.packages),
            "payloadsInserted": written.inserted_payloads,
            "payloadsUpdated": written.updated_payloads,
            "payloadsUnchanged": written.unchanged_payloads,
            "upstreamIssues": len(issues),
            "syncRunId": replay.sync_run_id,
            "replayed": replay.imported,
            "skipped": replay.skipped,
            "failed": replay.failed,
        }
