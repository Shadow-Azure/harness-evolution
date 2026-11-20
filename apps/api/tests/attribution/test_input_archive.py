"""Concurrent publication, immutable retries and versioned Session coverage."""

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.service.evolution import local_attribution
from app.service.evolution.attribution import AttributionInput
from app.service.evolution.attribution_inputs import CaseInputArchive, disk_id
from app.service.evolution.local_attribution import LocalAttribution
from tests.attribution.support import CASE_ID, SESSION_ID, Harness


def case_input() -> AttributionInput:
    return AttributionInput(
        bad_case_id=CASE_ID,
        run_id="batch-1",
        session_id=SESSION_ID,
        workspace_id="ws-default",
        probe_type="skill",
        probe_object="example",
        object_version="r1",
        policy_version="v1",
        attribution_engine="local-agent-skill-v1",
        bad_case_type="self",
        title="Case",
        description="",
        hit_reason="self_report",
        order_state="unknown",
        attribution_skill_content_hash="a" * 64,
        attribution_skill_key="example-skill",
    )


async def test_retry_keeps_old_evidence_and_new_batch_sees_trace_backfill(
    tmp_path: Path,
    attribution_harness: Harness,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.db.crud.sessions import SessionRepository

    item = case_input()
    service = LocalAttribution(
        Mock(attribution_package_dir=tmp_path), Mock(), Mock(), attribution_harness.database, Mock()
    )
    read_tree = AsyncMock(wraps=SessionRepository(attribution_harness.database).tree_snapshot)
    monkeypatch.setattr(service.sessions, "tree_snapshot", read_tree)
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(local_attribution, "list_root_payloads", fetch)
    monkeypatch.setattr(service, "_target_prompt", AsyncMock(return_value="Bearer abc123"))
    prepare = service.prepare_inputs([SESSION_ID, SESSION_ID])
    first, second = await asyncio.gather(prepare(item), prepare(item))
    assert first.local_input == second.local_input
    assert read_tree.await_count == fetch.await_count == 1
    assert first.local_input["attribute_source.md"] == "Bearer <redacted>"
    coverage = json.loads(first.local_input["trace_coverage.json"])
    assert coverage["status"] == "normalized_events_only" and coverage["missing_agent_ids"]
    archive = CaseInputArchive(service.root(item.workspace_id), item)
    archive.publish(first.local_input)
    agent = coverage["missing_agent_ids"][0]
    fetch.return_value = [SimpleNamespace(agent_id=agent, payload='{"token":"private"}')]
    retry = await service.prepare_inputs([SESSION_ID])(item)
    assert read_tree.await_count == fetch.await_count == 1
    assert retry.local_input_hash == first.local_input_hash
    other = replace(item, run_id="batch-2")
    updated = await service.prepare_inputs([SESSION_ID])(other)
    assert updated.local_input_hash != first.local_input_hash
    updated_coverage = json.loads(updated.local_input["trace_coverage.json"])
    assert updated_coverage["available_agent_ids"] == [agent]
    assert updated_coverage["missing_agent_ids"] == coverage["missing_agent_ids"][1:]
    assert updated_coverage["status"] == (
        "partial" if updated_coverage["missing_agent_ids"] else "available"
    )
    assert "private" not in updated.local_input["traces.json"]
    CaseInputArchive(service.root(item.workspace_id), other).publish(updated.local_input)
    assert len(list(archive.sessions.iterdir())) == 2
    assert archive.load() == first.local_input


def test_shared_snapshot_and_safe_path_under_concurrent_writes(tmp_path: Path) -> None:
    item = replace(case_input(), session_id="../session", bad_case_id="../case")
    data = {
        "session_tree.json": "{}",
        "traces.json": "{}",
        "trace_coverage.json": "{}",
        "attribute_source.md": "prompt",
        "input_badcase.json": "{}",
    }
    first = CaseInputArchive(tmp_path, item)
    second = CaseInputArchive(tmp_path, replace(item, bad_case_id="second"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all(
            x == data
            for x in pool.map(lambda archive: archive.publish(data), [first, second, first, second])
        )
    assert first.case_path.name == disk_id("../case") and first.case_path.name.startswith("~")
    assert len(list(first.sessions.iterdir())) == len(list(first.sources.iterdir())) == 1
    with pytest.raises(ValueError, match="different attribution inputs"):
        first.publish({**data, "input_badcase.json": '{"changed":true}'})
    assert first.load() == data
    (next(first.sessions.iterdir()) / "traces.json").write_text("changed")
    with pytest.raises(ValueError, match="evidence checksum"):
        first.load()
