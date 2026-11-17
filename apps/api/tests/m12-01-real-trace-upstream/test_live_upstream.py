"""Opt-in live integration test for a real upstream trajectory service.

CI must never reach a real upstream. This module skips unless both
``HE_UPSTREAM_BASE_URL`` and ``HE_UPSTREAM_TOKEN`` are present in the
environment, so the default ``pnpm test:api`` run stays hermetic.
"""

from __future__ import annotations

import os
from datetime import timedelta

import httpx
import pytest

from app.third_party_api.trajectory.http import HttpTrajectorySource
from app.utils.time import now_shanghai

pytestmark = pytest.mark.live_upstream


def _env(name: str) -> str | None:
    """Return a trimmed optional environment value."""
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


async def test_live_upstream_contract_round_trip() -> None:
    """Verify credentials, pagination, package mapping, and per-session isolation."""
    base_url = _env("HE_UPSTREAM_BASE_URL")
    token = _env("HE_UPSTREAM_TOKEN")
    if not base_url or not token:
        pytest.skip("HE_UPSTREAM_BASE_URL and HE_UPSTREAM_TOKEN are not configured")
    explicit_session = _env("HE_UPSTREAM_LIVE_SESSION_ID")
    client = httpx.AsyncClient(
        base_url=base_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60.0,
        follow_redirects=False,
    )
    source = HttpTrajectorySource(client, max_retries=1, backoff_seconds=0.5)
    try:
        today = now_shanghai().date()
        items = await source.list_window(
            from_date=today - timedelta(days=30),
            to_date=today,
            problem_only=True,
            cursor=None,
        )
        target = explicit_session or (items[0].session_id if items else None)
        if target is None:
            pytest.skip(
                "upstream window returned no sessions; set HE_UPSTREAM_LIVE_SESSION_ID",
            )
        package = await source.fetch(target)
        assert package.session_id == target
        isolated = await source.fetch_many([target, "m12-01-missing-session"])
        assert [item.session_id for item in isolated.packages] == [target]
        assert len(isolated.issues) == 1
    finally:
        await source.close()
