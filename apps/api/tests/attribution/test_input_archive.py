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


async def test_runtime_reads_the_commit_that_launch_resolved(
    tmp_path: Path,
    attribution_harness: Harness,
) -> None:
    """Moving branch tips cannot change attribution inputs or collide in the local source cache."""
    first_commit, second_commit = "a" * 40, "b" * 40
    bodies = {first_commit: "first body", second_commit: "updated body"}
    source = Mock()
    source.read_file = AsyncMock(side_effect=lambda **kwargs: bodies[kwargs["ref"]])
    service = LocalAttribution(
        Mock(attribution_package_dir=tmp_path), Mock(), Mock(), attribution_harness.database, source
    )
    first = replace(case_input(), selected_version="main", source_commit=first_commit)
    second = replace(first, source_commit=second_commit, run_id="another-batch")
    assert await service._target_prompt(first) == bodies[first_commit]
    assert await service._target_prompt(second) == bodies[second_commit]
    assert await service._target_prompt(first) == bodies[first_commit]
    assert [call.kwargs["ref"] for call in source.read_file.await_args_list] == [
        first_commit,
        second_commit,
    ]
    assert first.definition_key != second.definition_key


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


async def test_target_source_failure_never_caches_partial_or_moved_content(
    tmp_path: Path,
    attribution_harness: Harness,
) -> None:
    """An unavailable commit is retryable; agent.md fallback still verifies the selected digest."""
    from app.third_party_api.git.content import GitContentUnavailable
    from app.utils.definition import definition_file_hash

    source = Mock()
    service = LocalAttribution(
        Mock(attribution_package_dir=tmp_path), Mock(), Mock(), attribution_harness.database, source
    )
    body = "# Agent\nUse the fixed input."
    item = replace(
        case_input(),
        probe_type="agent",
        repo_url="upstream",
        sub_dir="agents/example",
        selected_version="main",
        source_commit="f" * 40,
        object_version=f"digest:{definition_file_hash(body)}",
    )
    source.read_file = AsyncMock(side_effect=GitContentUnavailable())
    with pytest.raises(GitContentUnavailable, match="content_unavailable"):
        await service._target_prompt(item)
    source.read_file = AsyncMock(side_effect=GitContentUnavailable("file_not_found"))
    with pytest.raises(ValueError, match="unavailable"):
        await service._target_prompt(item)
    source.read_file = AsyncMock(return_value="# Agent\nDifferent definition.")
    with pytest.raises(ValueError, match="changed since launch"):
        await service._target_prompt(item)
    source.read_file = AsyncMock(side_effect=[GitContentUnavailable("file_not_found"), body])
    assert await service._target_prompt(item) == body
    assert [call.kwargs["file_name"] for call in source.read_file.await_args_list] == [
        "AGENT.md",
        "agent.md",
    ]
    assert {call.kwargs["ref"] for call in source.read_file.await_args_list} == {item.source_commit}


@pytest.mark.parametrize("change", ["skill", "target_commit", "prompt", "input"])
def test_retry_refuses_mixed_batch_identity_and_partial_inputs(tmp_path: Path, change: str) -> None:
    """A retried case cannot run from another Skill/commit or a partially restored source file."""
    item = replace(case_input(), source_commit="a" * 40)
    archive = CaseInputArchive(tmp_path, item)
    data = {
        "session_tree.json": "{}",
        "trace_coverage.json": "{}",
        "traces.json": "{}",
        "input_badcase.json": '{"case":"one"}',
        "attribute_source.md": "fixed definition",
    }
    archive.publish(data)
    if change == "skill":
        archive = CaseInputArchive(tmp_path, replace(item, attribution_skill_content_hash="b" * 64))
    elif change == "target_commit":
        archive = CaseInputArchive(tmp_path, replace(item, source_commit="b" * 40))
    elif change == "prompt":
        next(archive.sources.glob("*/attribute_source.md")).write_text("partial")
    else:
        (archive.case_path / "input_badcase.json").write_text("partial")
    with pytest.raises(ValueError, match=r"identity mismatch|checksum mismatch"):
        archive.load()
