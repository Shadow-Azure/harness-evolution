"""Bounded target attribution retries, independent trace polling and lease fencing."""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from app.db.crud.binding_batches import BindingQueue
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.service.evolution.binding_worker import BindingWorker
from app.service.evolution.targets import EvolutionTargetService
from app.utils.time import now_shanghai
from tests.attribution.support import CASE_ID, OTHER_CASE_ID, Harness, potential_case

TARGET = dict(
    object_type="skill",
    object_name="retry-target",
    repo_url="https://example.test/skills.git",
    sub_dir="skills/retry",
    default_ref="v1",
    validation_project_id="validate",
    test_project_id="test",
    enabled=True,
)


async def test_worker_stops_after_backoff_and_save_resumes_same_generation(
    attribution_harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = EvolutionTargetRepository(attribution_harness.database)
    target = await repo.insert(TARGET)
    service = EvolutionTargetService(repo, Mock())
    queue = BindingQueue(attribution_harness.database)
    runtime = Mock()
    runtime.settings.attribution_timeout_seconds = 60
    worker = BindingWorker(queue, Mock(), runtime, Mock(), Mock(), Mock(), Mock())
    analyze = AsyncMock(side_effect=ValueError("untrusted model output"))
    monkeypatch.setattr(worker, "analyze", analyze)
    clock = now_shanghai()
    monkeypatch.setattr("app.db.crud.binding_batches.now_shanghai", lambda: clock)
    for attempt, delay in enumerate([30, 60, 0], start=1):
        assert await worker.tick()
        configured = next(item for item in (await service.list()).items if item.id == target.id)
        assert configured.attribution_failure is not None
        assert configured.attribution_failure.model_dump() == {
            "attempts": attempt,
            "reason": "invalid_input_or_report",
            "will_retry": bool(delay),
        }
        if delay:
            clock += timedelta(seconds=delay - 1)
            assert not await worker.tick()
            clock += timedelta(seconds=1)
    clock += timedelta(days=1)
    assert not await worker.tick()
    assert analyze.await_count == 3

    original_generation = analyze.await_args_list[-1].args[0].generation
    await repo.update(target.id, TARGET)
    analyze.side_effect = [True, True, True, True, False]
    for _ in range(5):
        assert await worker.tick()
        updated = await repo.get(target.id)
        assert updated is not None and updated.attribution_failures == 0
        assert updated.attribution_error is None
        clock += timedelta(seconds=30)
    assert not await worker.tick()
    assert analyze.await_args_list[-1].args[0].generation == original_generation


async def test_expired_and_superseded_claims_cannot_overwrite_new_attempt(
    attribution_harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = EvolutionTargetRepository(attribution_harness.database)
    target = await repo.insert(TARGET)
    queue = BindingQueue(attribution_harness.database)
    clock = now_shanghai()
    monkeypatch.setattr("app.db.crud.binding_batches.now_shanghai", lambda: clock)
    interrupted = await queue.claim(60)
    assert interrupted is not None
    clock += timedelta(seconds=61)
    assert await queue.claim(60) is None
    row = await repo.get(target.id)
    assert row is not None and row.attribution_error == "worker_interrupted"
    assert row.attribution_failures == 1
    clock += timedelta(seconds=30)
    live = await queue.claim(60)
    assert live is not None and live.owner != interrupted.owner
    await queue.complete(interrupted, waiting_for_traces=False)
    await queue.fail(live, "analysis_failed")
    row = await repo.get(target.id)
    assert row is not None and row.attribution_failures == 2
    clock += timedelta(seconds=60)
    stale = await queue.claim(60)
    assert stale is not None
    await repo.update(target.id, {**TARGET, "default_ref": "v2"})
    await queue.fail(stale, "analysis_failed")
    fresh = await queue.claim(60)
    assert fresh is not None and fresh.generation != stale.generation and fresh.failures == 0


async def test_recovered_worker_preserves_snapshot_and_skips_reports_from_same_generation(
    attribution_harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = EvolutionTargetRepository(attribution_harness.database)
    await repo.insert(TARGET)
    queue = BindingQueue(attribution_harness.database)
    clock = now_shanghai()
    monkeypatch.setattr("app.db.crud.binding_batches.now_shanghai", lambda: clock)
    runtime = Mock(
        targets=repo,
        resolve_package=AsyncMock(
            return_value=Mock(
                skill_key="example",
                revision=1,
                content_hash="fixed",
            )
        ),
    )
    runtime.settings.attribution_timeout_seconds = 60
    resolver = AsyncMock()
    resolver.resolve.return_value = Mock(target_version="v1", target_revision="fixed")
    matcher = AsyncMock()
    matcher.associated_sessions.return_value = Mock(pending=0)
    matcher.potential_cases.return_value = Mock(
        cases=(potential_case(), potential_case(OTHER_CASE_ID))
    )
    reports = AsyncMock()
    reports.latest_reports.side_effect = [{}, {CASE_ID: ("report-id", "example", "attributed")}]
    runner = AsyncMock()
    runner.run.side_effect = [ValueError("invalid report"), None]
    worker = BindingWorker(queue, AsyncMock(), runtime, resolver, matcher, reports, runner)

    assert await worker.tick()
    clock += timedelta(seconds=30)
    assert await worker.tick()
    first, second = runner.run.await_args_list
    assert first.args[0].id == second.args[0].id
    assert reports.latest_reports.await_args.kwargs["generation"] == first.args[0].id
    assert [case.bad_case_id for case in first.args[1]] == [CASE_ID, OTHER_CASE_ID]
    assert [case.bad_case_id for case in second.args[1]] == [OTHER_CASE_ID]
    runtime.resolve_package.assert_awaited_once()
    assert not await worker.tick()
