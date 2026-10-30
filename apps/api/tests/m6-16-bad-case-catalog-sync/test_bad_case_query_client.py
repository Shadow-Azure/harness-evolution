"""Strict parsing, retries, and serialization for the catalog query client."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import pytest

from app.errors import AppError, ErrorCode
from app.third_party_api.bad_case_query.http import HttpBadCaseCatalogSource
from app.third_party_api.bad_case_query.models import BadCasePage


def _item(case_id: int, *, title: str = "case title", **overrides: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "bad_case_id": case_id,
        "bad_case_session_id": "session-1",
        "bad_case_type": "self",
        "object_name": "deep-research",
        "object_type": "skill",
        "object_version": None,
        "bad_case_agent_id": None,
        "bad_case_title": title,
        "bad_case_description": "description",
        "meta_data": None,
        "source": "upstream",
        "created_at": "2026-10-30T10:00:00+08:00",
        "updated_at": "2026-10-30T10:00:00+08:00",
    }
    item.update(overrides)
    return item


def _page(
    items: list[dict[str, Any]], *, total: int | None = None, limit: int = 2
) -> dict[str, Any]:
    return {
        "total": len(items) if total is None else total,
        "offset": 0,
        "limit": limit,
        "items": items,
    }


async def test_fetch_page_maps_title_and_optionals() -> None:
    """The response maps bad_case_title to title and keeps optional timestamps."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=_page(
                [
                    _item(11, meta_data=["tag", 1]),
                    _item(12, title="second"),
                ],
            ),
        )

    source = HttpBadCaseCatalogSource(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://query.test",
        ),
        max_retries=0,
    )
    try:
        page = await source.fetch_page(after_id=10, offset=0, limit=2)
    finally:
        await source.close()

    assert isinstance(page, BadCasePage)
    assert page.total == 2
    assert page.items[0].bad_case_id == 11
    assert page.items[0].title == "case title"
    assert page.items[0].description == "description"
    assert page.items[0].meta_data == ["tag", 1]
    assert page.items[0].created_at is not None
    assert page.items[0].created_at.utcoffset() is not None
    assert page.items[1].title == "second"
    assert seen[0].url.params["bad_case_id"] == "10"
    assert seen[0].url.params["offset"] == "0"
    assert seen[0].url.params["limit"] == "2"


@pytest.mark.asyncio
async def test_fetch_page_allows_missing_timestamps() -> None:
    """Timestamps are optional; absent values stay None instead of failing."""
    missing: dict[str, Any] = _item(1)
    del missing["created_at"]
    del missing["updated_at"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_page([missing], total=1))

    source = HttpBadCaseCatalogSource(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://query.test",
        ),
        max_retries=0,
    )
    try:
        page = await source.fetch_page(after_id=0, offset=0, limit=2)
    finally:
        await source.close()

    assert page.items[0].created_at is None
    assert page.items[0].updated_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        _page([_item(1), _item(2), _item(3)], total=3),
        _page([_item(2), _item(1)], total=2),
        _page([_item(1), _item(1)], total=2),
        _page([_item(1), _item(2)], total=1),
        _page([_item(0)], total=1),
        _page([_item(1)], total=1, limit=3),
    ],
)
async def test_fetch_page_rejects_inconsistent_pages(payload: dict[str, Any]) -> None:
    """Oversized, unsorted, duplicated, or cursor-violating pages are invalid."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    source = HttpBadCaseCatalogSource(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://query.test",
        ),
        max_retries=0,
    )
    try:
        with pytest.raises(AppError) as failure:
            await source.fetch_page(after_id=0, offset=0, limit=2)
    finally:
        await source.close()

    assert failure.value.code is ErrorCode.BAD_CASE_QUERY_INVALID_RESPONSE


@pytest.mark.asyncio
async def test_fetch_page_rejects_missing_required_field() -> None:
    """A missing table-shaped field is a contract violation, not a partial row."""
    broken = _item(1)
    del broken["bad_case_session_id"]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_page([broken], total=1))

    source = HttpBadCaseCatalogSource(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://query.test",
        ),
        max_retries=0,
    )
    try:
        with pytest.raises(AppError) as failure:
            await source.fetch_page(after_id=0, offset=0, limit=2)
    finally:
        await source.close()

    assert failure.value.code is ErrorCode.BAD_CASE_QUERY_INVALID_RESPONSE


@pytest.mark.asyncio
async def test_fetch_page_rejects_naive_timestamp() -> None:
    """A present timestamp must carry a timezone."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_page([_item(1, created_at="2026-10-30T10:00:00")], total=1),
        )

    source = HttpBadCaseCatalogSource(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://query.test",
        ),
        max_retries=0,
    )
    try:
        with pytest.raises(AppError) as failure:
            await source.fetch_page(after_id=0, offset=0, limit=2)
    finally:
        await source.close()

    assert failure.value.code is ErrorCode.BAD_CASE_QUERY_INVALID_RESPONSE


@pytest.mark.asyncio
async def test_fetch_page_maps_unauthorized() -> None:
    """401 and 403 become the stable unauthorized code without leaking the body."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "denied"})

    source = HttpBadCaseCatalogSource(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://query.test",
        ),
        max_retries=0,
    )
    try:
        with pytest.raises(AppError) as failure:
            await source.fetch_page(after_id=0, offset=0, limit=2)
    finally:
        await source.close()

    assert failure.value.code is ErrorCode.BAD_CASE_QUERY_UNAUTHORIZED


@pytest.mark.asyncio
async def test_fetch_page_retries_5xx_then_succeeds() -> None:
    """Transient 5xx responses are retried a bounded number of times."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503)
        return httpx.Response(200, json=_page([_item(1)], total=1))

    source = HttpBadCaseCatalogSource(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://query.test",
        ),
        max_retries=2,
        backoff_seconds=0,
    )
    try:
        page = await source.fetch_page(after_id=0, offset=0, limit=2)
    finally:
        await source.close()

    assert attempts == 3
    assert page.items[0].bad_case_id == 1


@pytest.mark.asyncio
async def test_fetch_page_reports_request_failed_after_retries() -> None:
    """Persistent 5xx responses surface a request-failed code."""
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(500)

    source = HttpBadCaseCatalogSource(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://query.test",
        ),
        max_retries=2,
        backoff_seconds=0,
    )
    try:
        with pytest.raises(AppError) as failure:
            await source.fetch_page(after_id=0, offset=0, limit=2)
    finally:
        await source.close()

    assert attempts == 3
    assert failure.value.code is ErrorCode.BAD_CASE_QUERY_REQUEST_FAILED


@pytest.mark.asyncio
async def test_calls_never_overlap() -> None:
    """The client serializes concurrent page requests."""
    intervals: list[tuple[float, float]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        start = time.monotonic()
        await asyncio.sleep(0.02)
        intervals.append((start, time.monotonic()))
        return httpx.Response(200, json=_page([], total=0))

    source = HttpBadCaseCatalogSource(
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://query.test",
        ),
        max_retries=0,
    )
    try:
        await asyncio.gather(
            source.fetch_page(after_id=0, offset=0, limit=2),
            source.fetch_page(after_id=0, offset=0, limit=2),
        )
    finally:
        await source.close()

    assert len(intervals) == 2
    first, second = sorted(intervals)
    assert first[1] <= second[0]
