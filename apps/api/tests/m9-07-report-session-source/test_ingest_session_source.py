"""Optional sessionSource report contract and persistence."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from tests.ingest.helpers import (
    create_ingest_workspace,
    fetch_case,
    ingest_body,
    report,
)

SOURCE = {
    "runtime": "claude-code",
    "sessionUrlTemplate": "https://trace.internal/api/sessions/{sessionId}?sig=short",
}


async def test_session_source_is_persisted_with_camel_case_keys(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """The optional source is stored verbatim for later root selection."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Source Persist")

    response = await report(client, workspace, ingest_body(sessionSource=SOURCE))

    assert response.status_code == 201
    row = await fetch_case(app.state.database, "BC-HC-021")
    assert row is not None
    assert row["session_source"] == SOURCE


async def test_omitting_session_source_stays_backward_compatible(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """A report without the new field keeps the previous null behavior."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Source Absent")

    response = await report(client, workspace, ingest_body())

    assert response.status_code == 201
    row = await fetch_case(app.state.database, "BC-HC-021")
    assert row is not None
    assert row["session_source"] is None


async def test_re_report_without_source_replaces_it_with_null(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    """An upsert replaces every upstream field, including an omitted source."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Source Replace")
    first = await report(client, workspace, ingest_body(sessionSource=SOURCE))
    assert first.status_code == 201

    second = await report(client, workspace, ingest_body(title="重报"))

    assert second.status_code == 200
    row = await fetch_case(app.state.database, "BC-HC-021")
    assert row is not None
    assert row["session_source"] is None


@pytest.mark.parametrize(
    "source",
    [
        pytest.param({"runtime": "claude-code"}, id="missing-template"),
        pytest.param(
            {
                "runtime": "claude-code",
                "sessionUrlTemplate": "https://x.test/{sessionId}/{sessionId}",
            },
            id="duplicate-placeholder",
        ),
        pytest.param(
            {"runtime": "claude-code", "sessionUrlTemplate": "https://x.test/no-placeholder"},
            id="no-placeholder",
        ),
        pytest.param(
            {"runtime": "claude-code", "sessionUrlTemplate": "ftp://x.test/{sessionId}"},
            id="bad-scheme",
        ),
        pytest.param(
            {
                "runtime": "claude-code",
                "sessionUrlTemplate": "https://x.test/" + "a" * 2050 + "/{sessionId}",
            },
            id="too-long",
        ),
        pytest.param(
            {
                "runtime": "claude-code",
                "sessionUrlTemplate": "https://user:pass@x.test/{sessionId}",
            },
            id="embedded-credentials",
        ),
        pytest.param(
            {"runtime": "claude-code", "sessionUrlTemplate": "https://x.test/{sessionId}#frag"},
            id="fragment",
        ),
        pytest.param(
            {
                "runtime": "claude-code",
                "sessionUrlTemplate": "https://x.test/{sessionId}",
                "headers": {"authorization": "secret"},
            },
            id="extra-headers",
        ),
        pytest.param(
            {"runtime": "Claude Code", "sessionUrlTemplate": "https://x.test/{sessionId}"},
            id="invalid-runtime",
        ),
    ],
)
async def test_invalid_session_source_is_422(
    ingest_client: tuple[FastAPI, httpx.AsyncClient],
    source: dict[str, object],
) -> None:
    """Template and runtime violations reject the report before persistence."""
    app, client = ingest_client
    workspace = await create_ingest_workspace(app, client, name="Source Invalid")

    response = await report(client, workspace, ingest_body(sessionSource=source))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_INVALID"
    assert await fetch_case(app.state.database, "BC-HC-021") is None
