"""Pure unit-cursor rules for the seven-step evolution workflow."""

import pytest

from app.service.evolution.state import (
    STEP_KEYS,
    StageConflict,
    StepNotReady,
    effective_unit,
    ensure_step_readable,
    legacy_unit,
    next_unit,
    progress_total,
    step_states,
    total_units,
    validate_cursor,
    validate_transition,
)


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        (0, ["active", "pending", "pending", "pending", "pending", "pending", "pending"]),
        (1, ["done", "active", "pending", "pending", "pending", "pending", "pending"]),
        (2, ["done", "done", "active", "pending", "pending", "pending", "pending"]),
        (3, ["done", "done", "done", "active", "pending", "pending", "pending"]),
        (4, ["done", "done", "done", "done", "active", "pending", "pending"]),
        (5, ["done", "done", "done", "done", "done", "active", "pending"]),
        (6, ["done", "done", "done", "done", "done", "active", "pending"]),
        (7, ["done", "done", "done", "done", "done", "done", "active"]),
        (8, ["done", "done", "done", "done", "done", "done", "done"]),
    ],
)
def test_step_states_follow_the_unit_cursor(
    unit: int,
    expected: list[str],
) -> None:
    """Every step maps directly to the persisted unit cursor."""
    states = step_states(unit, 2, "running")

    assert [step.status for step in states] == expected
    assert [step.key for step in states] == list(STEP_KEYS)
    assert [step.index for step in states] == list(range(7))
    assert [step.clickable for step in states] == [status != "pending" for status in expected]


def test_step_titles_match_the_public_workflow() -> None:
    """Titles stay server-owned so the frontend never invents labels."""
    assert [step.title for step in step_states(0, 2, "running")] == [
        "选择范围",
        "Session 关联",
        "潜在 bad case",
        "对象归因",
        "聚类与严重度",
        "迭代优化",
        "测试集终评",
    ]


def test_total_units_and_progress_helpers_follow_cluster_count() -> None:
    """The final cursor is five fixed steps plus M rounds and final review."""
    assert total_units(0) == 6
    assert total_units(2) == 8
    assert next_unit(0, 2) == 1
    assert next_unit(5, 2) == 6


def test_progress_total_hides_iteration_for_cluster_only_runs() -> None:
    """A cluster-only run announces five visible units regardless of clusters."""
    assert progress_total("full", 2) == total_units(2)
    assert progress_total("cluster_only", 0) == 5
    assert progress_total("cluster_only", 2) == 5


@pytest.mark.parametrize("unit", [-1, 9])
def test_validate_cursor_rejects_out_of_range_units(unit: int) -> None:
    """Persisted cursors outside the computed range are conflicts."""
    with pytest.raises(StageConflict) as raised:
        validate_cursor(unit, 2)

    assert raised.value.status_code == 409
    assert raised.value.current == unit
    assert raised.value.target == unit


@pytest.mark.parametrize(("current", "target"), [(3, 3), (3, 2), (3, 5)])
def test_validate_transition_only_accepts_one_forward_unit(
    current: int,
    target: int,
) -> None:
    """Repeated, backward, and multi-unit writes are illegal."""
    with pytest.raises(StageConflict) as raised:
        validate_transition(current, target, 2)

    assert raised.value.status_code == 409
    assert raised.value.current == current
    assert raised.value.target == target


def test_validate_transition_accepts_the_next_unit() -> None:
    """One forward unit is the only valid transition."""
    validate_transition(3, 4, 2)


def test_reading_a_pending_step_raises_not_ready() -> None:
    """A pending step cannot be fetched before the cursor reaches it."""
    with pytest.raises(StepNotReady):
        ensure_step_readable(1, 2, "running", "attribution")

    ensure_step_readable(2, 2, "running", "potential")


def test_range_is_readable_while_preparing() -> None:
    """The first step has a preparation state instead of disappearing."""
    ensure_step_readable(0, 2, "preparing", "range")


def test_blocked_run_exposes_the_first_pending_step_without_moving_the_cursor() -> None:
    """Blocked is derived from status, not from inventing another cursor."""
    states = step_states(5, 2, "blocked")

    assert states[5].status == "active"
    assert states[5].clickable is True
    assert step_states(5, 2, "running") == states


@pytest.mark.parametrize("run_status", ["completed", "failed", "interrupted"])
def test_terminal_runs_have_no_active_step(run_status: str) -> None:
    """Terminal run states never claim that work is still active."""
    states = step_states(3, 2, run_status)

    assert all(step.status != "active" for step in states)


def test_failed_cluster_step_stays_readable() -> None:
    """A strict cluster failure keeps its step fetchable instead of 404ing."""
    states = step_states(4, 0, "failed", error_stage="cluster")

    assert states[4].status == "active"
    assert states[4].clickable is True
    ensure_step_readable(4, 0, "failed", "clusters", error_stage="cluster")
    with pytest.raises(StepNotReady):
        ensure_step_readable(4, 0, "failed", "clusters")


def test_unknown_step_key_is_not_readable() -> None:
    """Only the closed seven-step vocabulary is addressable."""
    with pytest.raises(StepNotReady):
        ensure_step_readable(8, 2, "completed", "unknown")


def test_legacy_cursor_skips_inserted_stages_and_shifts_tail() -> None:
    """A V1 cursor maps onto the same seven-step DTO without rewriting rows."""
    assert legacy_unit(0, 2) == 0
    assert legacy_unit(1, 2) == 1
    assert legacy_unit(2, 2) == 5
    assert legacy_unit(3, 2) == 5
    assert legacy_unit(4, 2) == 5
    assert legacy_unit(5, 2) == 6
    assert legacy_unit(7, 2) == 8
    assert effective_unit(4, 2, attribution_engine="legacy-probe-import") == 5
    assert effective_unit(4, 2, attribution_engine="rule-v1") == 4


def test_cluster_only_hides_only_iteration_and_final() -> None:
    """Cluster-only runs keep every step through clustering readable."""
    for key in ("range", "sessions", "potential", "attribution", "clusters"):
        ensure_step_readable(5, 1, "completed", key, "cluster_only")
    for key in ("iteration", "final"):
        with pytest.raises(StepNotReady):
            ensure_step_readable(5, 1, "completed", key, "cluster_only")
