"""Pure unit-cursor rules for the six-step evolution workflow."""

import pytest

from app.service.evolution.state import (
    STEP_KEYS,
    StageConflict,
    StepNotReady,
    ensure_step_readable,
    next_unit,
    step_states,
    total_units,
    validate_cursor,
    validate_transition,
)


@pytest.mark.parametrize(
    ("unit", "expected"),
    [
        (0, ["active", "pending", "pending", "pending", "pending", "pending"]),
        (1, ["done", "active", "pending", "pending", "pending", "pending"]),
        (2, ["done", "done", "active", "pending", "pending", "pending"]),
        (3, ["done", "done", "done", "active", "pending", "pending"]),
        (4, ["done", "done", "done", "done", "active", "pending"]),
        (5, ["done", "done", "done", "done", "active", "pending"]),
        (6, ["done", "done", "done", "done", "done", "active"]),
        (7, ["done", "done", "done", "done", "done", "done"]),
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
    assert [step.index for step in states] == list(range(6))
    assert [step.clickable for step in states] == [status != "pending" for status in expected]


def test_step_titles_match_the_public_workflow() -> None:
    """Titles stay server-owned so the frontend never invents labels."""
    assert [step.title for step in step_states(0, 2, "running")] == [
        "筛选输入",
        "问题聚类",
        "归因确认",
        "严重程度排序",
        "迭代优化",
        "测试集终评",
    ]


def test_total_units_and_progress_helpers_follow_cluster_count() -> None:
    """The final cursor is four fixed steps plus M rounds and final review."""
    assert total_units(0) == 5
    assert total_units(2) == 7
    assert next_unit(0, 2) == 1
    assert next_unit(4, 2) == 5


@pytest.mark.parametrize("unit", [-1, 8])
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

    ensure_step_readable(2, 2, "running", "attribution")


def test_input_is_readable_while_preparing() -> None:
    """The first step has a preparation state instead of disappearing."""
    ensure_step_readable(0, 2, "preparing", "input")


def test_blocked_run_exposes_the_first_pending_step_without_moving_the_cursor() -> None:
    """Blocked is derived from status, not from inventing another cursor."""
    states = step_states(4, 2, "blocked")

    assert states[4].status == "active"
    assert states[4].clickable is True
    assert step_states(4, 2, "running") == states


@pytest.mark.parametrize("run_status", ["completed", "failed", "interrupted"])
def test_terminal_runs_have_no_active_step(run_status: str) -> None:
    """Terminal run states never claim that work is still active."""
    states = step_states(3, 2, run_status)

    assert all(step.status != "active" for step in states)


def test_unknown_step_key_is_not_readable() -> None:
    """Only the closed six-step vocabulary is addressable."""
    with pytest.raises(StepNotReady):
        ensure_step_readable(7, 2, "completed", "unknown")
