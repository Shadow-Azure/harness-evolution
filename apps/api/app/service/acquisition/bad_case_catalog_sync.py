"""Cursor-based synchronization of upstream bad cases into the local table."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import Settings
from app.db.crud.bad_case_catalog_sync import (
    BadCaseCatalogSyncRepository,
    CatalogCaseRow,
)
from app.db.models.jobs import JobRunRecord
from app.errors import AppError, ErrorCode
from app.third_party_api.bad_case_query.models import (
    BadCaseCatalogSource,
    BadCaseItem,
)
from app.utils.time import now_shanghai

logger = logging.getLogger(__name__)

KIND = "bad_case_catalog_sync"

_SOURCE_OBJECT_NAMES = {
    "code_reivew": "code-review",
    "code_review": "code-review",
}


@dataclass(frozen=True, slots=True)
class CatalogSyncResult:
    """Aggregate outcome of one bounded catalog-sync run."""

    pages: int
    inserted: int
    updated: int
    last_bad_case_id: int
    pending: int
    exhausted: bool


def _stable_error(exc: Exception) -> str:
    """Keep only a stable code in the durable status row."""
    if isinstance(exc, AppError):
        return exc.code.value
    return ErrorCode.BAD_CASE_CATALOG_SYNC_FAILED.value


def _object_name(item: BadCaseItem) -> str:
    """Return the explicit name, the code-review alias, or a source fallback."""
    if item.object_name:
        return item.object_name
    source = item.source or ""
    return _SOURCE_OBJECT_NAMES.get(source, source or "unknown")


def _row(item: BadCaseItem, fallback: datetime) -> CatalogCaseRow:
    """Map one upstream item to local column names, defaulting timestamps."""
    return CatalogCaseRow(
        bad_case_id=item.bad_case_id,
        bad_case_session_id=item.bad_case_session_id,
        bad_case_type=item.bad_case_type,
        object_name=_object_name(item),
        object_type=item.object_type or "skill",
        object_version=item.object_version,
        bad_case_agent_id=item.bad_case_agent_id,
        title=item.title,
        description=item.description,
        meta_data=item.meta_data,
        source=item.source,
        created_at=item.created_at or fallback,
        updated_at=item.updated_at or fallback,
    )


class BadCaseCatalogSyncService:
    """Page through the upstream catalog and commit one page per transaction."""

    def __init__(
        self,
        repository: BadCaseCatalogSyncRepository,
        source: BadCaseCatalogSource | None,
        *,
        page_size: int = 200,
        max_pages: int = 100,
        time_budget_seconds: float = 300.0,
        clock: Callable[[], datetime] = now_shanghai,
    ) -> None:
        """Bind storage, the read source, and bounded-run policy."""
        self._repository = repository
        self._source = source
        self._page_size = max(1, min(page_size, 200))
        self._max_pages = max(1, max_pages)
        self._time_budget_seconds = max(0.0, time_budget_seconds)
        self._clock = clock

    @classmethod
    def from_settings(
        cls,
        repository: BadCaseCatalogSyncRepository,
        source: BadCaseCatalogSource | None,
        settings: Settings,
    ) -> BadCaseCatalogSyncService:
        """Build the service from environment-backed bounds."""
        return cls(
            repository,
            source,
            page_size=settings.bad_case_catalog_sync_page_size,
            max_pages=settings.bad_case_catalog_sync_max_pages,
            time_budget_seconds=settings.bad_case_catalog_sync_time_budget_seconds,
        )

    async def handle(self, job: JobRunRecord) -> Mapping[str, Any]:
        """Run one job through JobRunner and expose camel-case result counts."""
        result = await self.run(owner=job.id)
        return {
            "pages": result.pages,
            "inserted": result.inserted,
            "updated": result.updated,
            "lastBadCaseId": result.last_bad_case_id,
            "pending": result.pending,
            "exhausted": result.exhausted,
        }

    async def run(self, *, owner: str) -> CatalogSyncResult:
        """Process pages until exhaustion or a configured run bound."""
        started_at = self._clock()
        state = await self._repository.get_state()
        if state is None:
            state = await self._repository.initialize(started_at)
        if self._source is None:
            await self._repository.mark_failed(
                ErrorCode.BAD_CASE_QUERY_UNAVAILABLE.value,
                started_at,
            )
            raise AppError(
                status_code=503,
                code=ErrorCode.BAD_CASE_QUERY_UNAVAILABLE,
                message="bad-case query service is not configured",
            )

        await self._repository.mark_running(started_at)
        cursor = state.last_bad_case_id
        pending = state.pending_count
        pages = 0
        inserted = 0
        updated = 0
        exhausted = False
        deadline = time.monotonic() + self._time_budget_seconds
        logger.debug(
            "catalog sync started",
            extra={"owner": owner, "cursor": cursor},
        )

        try:
            while pages < self._max_pages and time.monotonic() < deadline:
                page = await self._source.fetch_page(
                    after_id=cursor,
                    offset=0,
                    limit=self._page_size,
                )
                if not page.items:
                    pending = 0
                    exhausted = True
                    break
                max_id = page.items[-1].bad_case_id
                if max_id <= cursor:
                    raise AppError(
                        status_code=502,
                        code=ErrorCode.BAD_CASE_QUERY_INVALID_RESPONSE,
                        message="page cursor did not advance",
                    )
                page_now = self._clock()
                remaining = max(page.total - len(page.items), 0)
                counts = await self._repository.commit_page(
                    [_row(item, page_now) for item in page.items],
                    last_bad_case_id=max_id,
                    pending_count=remaining,
                    now=page_now,
                )
                pages += 1
                inserted += counts.inserted
                updated += counts.updated
                cursor = max_id
                pending = remaining
                if len(page.items) >= page.total:
                    exhausted = True
                    break
            await self._repository.mark_idle(self._clock(), pending=pending)
        except Exception as exc:
            await self._repository.mark_failed(
                _stable_error(exc),
                self._clock(),
            )
            raise

        return CatalogSyncResult(
            pages=pages,
            inserted=inserted,
            updated=updated,
            last_bad_case_id=cursor,
            pending=pending,
            exhausted=exhausted,
        )
