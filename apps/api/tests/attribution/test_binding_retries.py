"""Bounded target attribution retries, independent trace polling and lease fencing."""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from app.db.crud.binding_batches import BindingClaim, BindingQueue
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.errors import AppError, ErrorCode
from app.service.evolution.binding_worker import BindingWorker
from app.service.evolution.local_attribution import FrozenSkill, LocalAttribution
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
    runtime = Mock(targets=repo, resolve_bound_skill=AsyncMock())
    matcher = AsyncMock()
    worker = BindingWorker(
        queue, AsyncMock(), runtime, AsyncMock(), matcher, AsyncMock(), AsyncMock()
    )
    assert not await worker.analyze(stale)
    runtime.resolve_bound_skill.assert_not_awaited()
    matcher.associated_sessions.assert_not_awaited()
    await queue.fail(stale, "analysis_failed")
    fresh = await queue.claim(60)
    assert fresh is not None and fresh.generation != stale.generation and fresh.failures == 0


async def test_concurrent_skill_pins_keep_one_snapshot_per_generation(
    attribution_harness: Harness,
) -> None:
    repo = EvolutionTargetRepository(attribution_harness.database)
    definition = {"key": "a" * 64, "commit": "b" * 40, "path": "SKILL.md", "revision": "v1"}
    target = await repo.insert({**TARGET, "definition": definition})
    hashes = ["c" * 64, "d" * 64]
    first, other = await asyncio.gather(
        *(
            repo.pin_binding_skill(
                target, skill_key="attribute-badcases", revision=1, content_hash=h
            )
            for h in hashes
        )
    )
    assert first == other
    assert first["hash"] in hashes
    assert first["definition"] == definition
    stored = await repo.get(target.id)
    assert stored is not None and stored.attribution_snapshot == first

    # A new generation can bind the same package. A stale caller still must not write to it.
    replacement = await repo.update(target.id, {**TARGET, "default_ref": "v2"})
    assert replacement.attribution_generation != target.attribution_generation
    with pytest.raises(AppError):
        await repo.pin_binding_skill(
            target, skill_key="attribute-badcases", revision=1, content_hash=first["hash"]
        )
    new_hash = "e" * 64
    new = await repo.pin_binding_skill(
        replacement, skill_key="attribute-badcases", revision=1, content_hash=new_hash
    )
    assert new["hash"] == new_hash


@pytest.mark.parametrize("pinned_before_worker", [False, True])
async def test_recovered_worker_preserves_snapshot_and_skips_reports_from_same_generation(
    attribution_harness: Harness, monkeypatch: pytest.MonkeyPatch, pinned_before_worker: bool
) -> None:
    repo = EvolutionTargetRepository(attribution_harness.database)
    target = await repo.insert(TARGET)
    queue = BindingQueue(attribution_harness.database)
    clock = now_shanghai()
    monkeypatch.setattr("app.db.crud.binding_batches.now_shanghai", lambda: clock)

    runtime = LocalAttribution(
        Mock(attribution_timeout_seconds=60), Mock(), Mock(), attribution_harness.database, Mock()
    )
    latest = FrozenSkill("attribute-badcases", 1, "f" * 64)
    freeze = AsyncMock(return_value=latest)
    monkeypatch.setattr(runtime, "resolve_package", freeze)
    if pinned_before_worker:
        original_claim = queue.claim
        launch_pending = True

        async def claim_during_launch(duration: int) -> BindingClaim | None:
            nonlocal launch_pending
            claim = await original_claim(duration)
            if claim and launch_pending:
                launch_pending = False
                # The worker already leased the target when the wizard wins the first pin.
                freeze.return_value = FrozenSkill("attribute-badcases", 1, "a" * 64)
                await runtime.resolve_for_run(target, target.attribution_package_id)
                freeze.return_value = latest
            return claim

        monkeypatch.setattr(queue, "claim", claim_during_launch)
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
    expected_hash = ("a" if pinned_before_worker else "f") * 64
    assert first.args[0].attribution_skill_content_hash == expected_hash
    assert second.args[0].attribution_skill_content_hash == expected_hash
    assert first.args[0].target_revision == second.args[0].target_revision == "fixed"
    assert reports.latest_reports.await_args.kwargs["generation"] == first.args[0].id
    assert [case.bad_case_id for case in first.args[1]] == [CASE_ID, OTHER_CASE_ID]
    assert [case.bad_case_id for case in second.args[1]] == [OTHER_CASE_ID]
    freeze.assert_awaited_once_with(target.workspace_id, target.attribution_package_id)
    assert not await worker.tick()


async def test_shutdown_releases_binding_without_spending_an_attempt(
    attribution_harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = EvolutionTargetRepository(attribution_harness.database)
    target = await repo.insert(TARGET)
    runtime = Mock()
    runtime.settings.attribution_timeout_seconds = 60
    queue = BindingQueue(attribution_harness.database)
    worker = BindingWorker(queue, Mock(), runtime, Mock(), Mock(), Mock(), Mock())
    entered = asyncio.Event()

    async def holding(_claim: BindingClaim) -> bool:
        entered.set()
        await asyncio.Event().wait()
        return False

    monkeypatch.setattr(worker, "analyze", holding)
    task = asyncio.create_task(worker.tick())
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    released = await repo.get(target.id)
    assert released is not None and released.attribution_will_retry
    assert released.attribution_failures == 0 and released.attribution_error is None
    next_claim = await queue.claim(60)
    assert next_claim is not None and next_claim.generation == target.attribution_generation


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (
            AppError(
                code=ErrorCode.TARGET_CONTENT_UNRESOLVED, message="git temporarily unavailable"
            ),
            "target_unavailable",
        ),
        (TimeoutError("remote timeout"), "analysis_failed"),
    ],
)
async def test_target_and_executor_failures_have_distinct_retry_reasons(
    attribution_harness: Harness, monkeypatch: pytest.MonkeyPatch, failure: Exception, reason: str
) -> None:
    repo = EvolutionTargetRepository(attribution_harness.database)
    target = await repo.insert(TARGET)
    queue = BindingQueue(attribution_harness.database)
    worker = BindingWorker(
        queue,
        Mock(),
        Mock(settings=Mock(attribution_timeout_seconds=60)),
        Mock(),
        Mock(),
        Mock(),
        Mock(),
    )
    monkeypatch.setattr(worker, "analyze", AsyncMock(side_effect=failure))
    assert await worker.tick()
    readback = await repo.get(target.id)
    assert readback is not None and readback.attribution_generation == target.attribution_generation
    assert readback.attribution_error == reason
    assert readback.attribution_failures == 1 and readback.attribution_will_retry
    assert not await worker.tick()


async def test_binding_polls_missing_session_without_reanalyzing_completed_cases(
    attribution_harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = EvolutionTargetRepository(attribution_harness.database)
    target = await repo.insert(TARGET)
    queue = BindingQueue(attribution_harness.database)
    runtime = LocalAttribution(
        Mock(attribution_timeout_seconds=60), Mock(), Mock(), attribution_harness.database, Mock()
    )
    freeze = AsyncMock(return_value=FrozenSkill("attribute-badcases", 1, "f" * 64))
    monkeypatch.setattr(runtime, "resolve_package", freeze)
    resolver = AsyncMock()
    resolver.resolve.return_value = Mock(target_version="v1", target_revision="fixed")
    matcher, reports, acquisition, runner = (AsyncMock() for _ in range(4))
    matcher.associated_sessions.return_value = Mock(pending=1)
    matcher.potential_cases.return_value = Mock(cases=(potential_case(),))
    reports.latest_reports.return_value = {CASE_ID: ("report", "bound", "attributed")}
    worker = BindingWorker(queue, acquisition, runtime, resolver, matcher, reports, runner)
    assert await worker.tick()
    acquisition.trigger.assert_awaited_once_with("target_binding")
    runner.run.assert_not_awaited()
    current = await repo.get(target.id)
    assert (
        current is not None and current.attribution_will_retry and current.attribution_failures == 0
    )
    assert (
        current.attribution_snapshot is not None
        and current.attribution_snapshot["hash"] == "f" * 64
    )
