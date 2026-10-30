"""Scheduled bad-case root-session trajectory backfill."""

from __future__ import annotations

import hashlib
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.config import Settings
from app.db.base import Database
from app.db.crud.bad_case_sync import BadCaseRootSyncRepository
from app.db.crud.local_sessions import write_local_payloads
from app.db.models.jobs import JobRunRecord
from app.errors import AppError, ErrorCode
from app.service.acquisition.local_sessions import LocalAgentPayload
from app.service.acquisition.replay import replay_pending_payloads
from app.third_party_api.session_query.models import (
    SessionQuerySource,
    SessionTrajectory,
)
from app.utils.ids import new_id
from app.utils.time import now_shanghai


@dataclass(frozen=True, slots=True)
class BadCaseRootSyncResult:
    """Aggregate-only outcome of one bounded root-sync batch."""

    roots_considered: int
    roots_synced: int
    roots_failed: int
    roots_skipped: int
    agents_fetched: int
    payloads_inserted: int
    payloads_updated: int
    replayed: int
    skipped: int


def _retry_delay(attempts: int) -> timedelta:
    """Return the documented 1m/5m/15m/1h retry ladder."""
    if attempts <= 1:
        return timedelta(minutes=1)
    if attempts == 2:
        return timedelta(minutes=5)
    if attempts == 3:
        return timedelta(minutes=15)
    return timedelta(hours=1)


def _stable_error(exc: Exception) -> str:
    """Keep only a stable code in the durable status row."""
    if isinstance(exc, AppError):
        return exc.code.value
    return ErrorCode.BAD_CASE_SYNC_FAILED.value


class BadCaseRootSyncService:
    """Walk bad_cases roots, write raw payloads, and update durable state."""

    def __init__(
        self,
        database: Database,
        repository: BadCaseRootSyncRepository,
        source: SessionQuerySource | None,
        *,
        batch_size: int = 20,
        time_budget_seconds: float = 600.0,
        max_agents: int = 200,
        max_depth: int = 10,
        lease_seconds: int = 900,
        clock: Callable[[], datetime] = now_shanghai,
    ) -> None:
        """Bind storage, the query source, and bounded-batch policy."""
        self._database = database
        self._repository = repository
        self._source = source
        self._batch_size = max(1, batch_size)
        self._time_budget_seconds = max(0.0, time_budget_seconds)
        self._max_agents = max(1, max_agents)
        self._max_depth = max(0, max_depth)
        self._lease_seconds = max(1, lease_seconds)
        self._clock = clock

    @classmethod
    def from_settings(
        cls,
        database: Database,
        repository: BadCaseRootSyncRepository,
        source: SessionQuerySource | None,
        settings: Settings,
    ) -> BadCaseRootSyncService:
        """Build the service from environment-backed bounds."""
        return cls(
            database,
            repository,
            source,
            batch_size=settings.bad_case_sync_batch_size,
            time_budget_seconds=settings.bad_case_sync_time_budget_seconds,
            max_agents=settings.bad_case_sync_max_agents,
            max_depth=settings.bad_case_sync_max_depth,
            lease_seconds=settings.bad_case_sync_lease_seconds,
        )

    async def handle(self, job: JobRunRecord) -> Mapping[str, Any]:
        """Run one job through JobRunner and expose camel-case result counts."""
        result = await self.run(owner=job.id, sync_run_id=job.id)
        return {
            "rootsConsidered": result.roots_considered,
            "rootsSynced": result.roots_synced,
            "rootsFailed": result.roots_failed,
            "rootsSkipped": result.roots_skipped,
            "agentsFetched": result.agents_fetched,
            "payloadsInserted": result.payloads_inserted,
            "payloadsUpdated": result.payloads_updated,
            "replayed": result.replayed,
            "skipped": result.skipped,
        }

    async def run(
        self,
        *,
        owner: str,
        now: datetime | None = None,
        sync_run_id: str | None = None,
    ) -> BadCaseRootSyncResult:
        """Process one bounded batch; never raise for a single root's failure."""
        started_at = now or self._clock()
        deadline = time.monotonic() + self._time_budget_seconds
        candidates = await self._repository.list_candidates(
            started_at,
            limit=self._batch_size,
        )
        roots_synced = 0
        roots_failed = 0
        roots_skipped = 0
        agents_fetched = 0
        inserted = 0
        updated = 0
        wrote_payloads = False

        for index, root_session_id in enumerate(candidates):
            if time.monotonic() >= deadline:
                roots_skipped += len(candidates) - index
                break
            claimed = await self._repository.claim(
                root_session_id,
                owner=owner,
                lease_seconds=self._lease_seconds,
                now=started_at,
            )
            if not claimed:
                roots_skipped += 1
                continue

            root_now = now or self._clock()
            try:
                payloads = await self._sync_root(root_session_id, root_now)
                written = await write_local_payloads(
                    self._database,
                    tuple(payloads),
                    source_type="http_api",
                )
                inserted += written.inserted_payloads
                updated += written.updated_payloads
                wrote_payloads = wrote_payloads or bool(payloads)
                agents_fetched += len(payloads)
                await self._repository.mark_synced(
                    root_session_id,
                    agent_count=len(payloads),
                    now=root_now,
                )
                roots_synced += 1
            except Exception as exc:
                attempts = await self._attempts(root_session_id)
                retry_at = root_now + _retry_delay(attempts)
                await self._repository.mark_failed(
                    root_session_id,
                    error=_stable_error(exc),
                    next_retry_at=retry_at,
                    now=root_now,
                    agent_count=0,
                )
                roots_failed += 1

        replay = (
            await replay_pending_payloads(
                self._database,
                source_type="http_api",
                sync_run_id=sync_run_id or new_id(),
            )
            if wrote_payloads
            else None
        )
        return BadCaseRootSyncResult(
            roots_considered=len(candidates),
            roots_synced=roots_synced,
            roots_failed=roots_failed,
            roots_skipped=roots_skipped,
            agents_fetched=agents_fetched,
            payloads_inserted=inserted,
            payloads_updated=updated,
            replayed=replay.imported if replay is not None else 0,
            skipped=replay.skipped if replay is not None else 0,
        )

    async def _attempts(self, root_session_id: str) -> int:
        row = await self._repository.get(root_session_id)
        return row.attempts if row is not None else 1

    async def _sync_root(
        self,
        root_session_id: str,
        now: datetime,
    ) -> list[LocalAgentPayload]:
        source = self._source
        if source is None:
            raise AppError(
                status_code=503,
                code=ErrorCode.SESSION_QUERY_UNAVAILABLE,
                message="session query service is not configured",
            )
        queue: deque[tuple[str, str | None, int]] = deque([(root_session_id, None, 0)])
        visited: set[str] = {root_session_id}
        payloads: list[LocalAgentPayload] = []
        while queue:
            session_id, parent_id, depth = queue.popleft()
            if depth > self._max_depth or len(payloads) >= self._max_agents:
                raise AppError(
                    status_code=502,
                    code=ErrorCode.TRAVERSAL_LIMIT_EXCEEDED,
                    message="session traversal exceeded its configured limit",
                )
            trajectory = await source.fetch_trajectory(session_id)
            payloads.append(
                _payload(
                    root_session_id=root_session_id,
                    session_id=session_id,
                    parent_id=parent_id,
                    trajectory=trajectory,
                    now=now,
                ),
            )
            children = await source.list_children(session_id)
            for child in children:
                if not child or child in visited:
                    continue
                if depth + 1 > self._max_depth:
                    raise AppError(
                        status_code=502,
                        code=ErrorCode.TRAVERSAL_LIMIT_EXCEEDED,
                        message="session traversal exceeded its configured depth",
                    )
                visited.add(child)
                queue.append((child, session_id, depth + 1))
        return payloads


def _payload(
    *,
    root_session_id: str,
    session_id: str,
    parent_id: str | None,
    trajectory: SessionTrajectory,
    now: datetime,
) -> LocalAgentPayload:
    encoded = trajectory.content.encode("utf-8")
    return LocalAgentPayload(
        root_session_id=root_session_id,
        agent_id=session_id,
        agent_kind="main" if session_id == root_session_id else "subagent",
        content=trajectory.content,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        line_count=trajectory.line_count,
        agent_meta=None if session_id == root_session_id else {"parentAgentId": parent_id},
        source_updated_at=now,
        discovered_at=now,
    )
