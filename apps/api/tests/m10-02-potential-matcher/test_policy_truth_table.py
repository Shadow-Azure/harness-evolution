"""Pure truth table for the shared potential policy and trigger comparison."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Literal

import pytest

from app.errors import AppError, ErrorCode
from app.service.evolution.potential import (
    PotentialPolicy,
    ResolvedPolicy,
    TriggerPoint,
    compare_triggers,
    evaluate_hit,
    resolve_policy,
    resolve_window,
)
from app.utils.time import SHANGHAI

EARLY = datetime(2026, 11, 17, 9, 0, tzinfo=SHANGHAI)
LATE = datetime(2026, 11, 17, 10, 0, tzinfo=SHANGHAI)


def policy(**overrides: object) -> ResolvedPolicy:
    """Build one already-resolved custom policy for the truth table."""
    values: dict[str, object] = {
        "preset": "custom",
        "include_self_report": False,
        "include_after_object": False,
        "same_object_only": False,
    }
    values.update(overrides)
    return ResolvedPolicy(**values)  # type: ignore[arg-type]


def default_policy() -> ResolvedPolicy:
    """Return the documented default policy: both rules, no object filter."""
    return ResolvedPolicy(
        preset="default",
        include_self_report=True,
        include_after_object=True,
        same_object_only=False,
    )


def _invalid_policy(payload: PotentialPolicy | None) -> AppError:
    """Resolve a policy and return the expected stable 422 error."""
    with pytest.raises(AppError) as raised:
        resolve_policy(payload)
    error = raised.value
    assert error.status_code == 422
    assert error.code is ErrorCode.POLICY_INVALID
    return error


def test_absent_and_explicit_default_policy_enable_both_rules() -> None:
    """Omitted policy and preset=default are the same documented default."""
    for candidate in (None, PotentialPolicy(), PotentialPolicy(preset="default")):
        resolved = resolve_policy(candidate)
        assert resolved.preset == "default"
        assert resolved.include_self_report is True
        assert resolved.include_after_object is True
        assert resolved.same_object_only is False


@pytest.mark.parametrize(
    "switches",
    [
        {"include_self_report": True},
        {"include_after_object": False},
        {"same_object_only": True},
        {
            "include_self_report": True,
            "include_after_object": True,
            "same_object_only": True,
        },
    ],
)
def test_default_policy_rejects_any_rule_switch(switches: dict[str, object]) -> None:
    """A default preset must not smuggle custom switches."""
    _invalid_policy(PotentialPolicy(preset="default", **switches))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "switches",
    [
        {"include_after_object": True, "same_object_only": False},
        {"include_self_report": True, "same_object_only": False},
        {"include_self_report": True, "include_after_object": True},
    ],
)
def test_custom_policy_requires_all_three_switches(switches: dict[str, object]) -> None:
    """A custom preset must state every switch explicitly."""
    _invalid_policy(PotentialPolicy(preset="custom", **switches))  # type: ignore[arg-type]


def test_custom_policy_requires_at_least_one_rule() -> None:
    """A custom policy with both rules off cannot select anything."""
    _invalid_policy(
        PotentialPolicy(
            preset="custom",
            include_self_report=False,
            include_after_object=False,
            same_object_only=True,
        ),
    )


@pytest.mark.parametrize(
    ("include_self", "include_after", "same_object"),
    [
        (True, False, False),
        (False, True, False),
        (True, True, True),
        (False, True, True),
    ],
)
def test_custom_policy_snapshot_keeps_requested_switches(
    include_self: bool,
    include_after: bool,
    same_object: bool,
) -> None:
    """Every legal custom combination resolves without rewriting its switches."""
    resolved = resolve_policy(
        PotentialPolicy(
            preset="custom",
            include_self_report=include_self,
            include_after_object=include_after,
            same_object_only=same_object,
        ),
    )
    assert resolved.preset == "custom"
    assert resolved.include_self_report is include_self
    assert resolved.include_after_object is include_after
    assert resolved.same_object_only is same_object


@pytest.mark.parametrize(
    (
        "selected",
        "self_match",
        "after_match",
        "order_state",
        "same_object",
        "hit_reason",
        "included",
    ),
    [
        # Default policy: self and after union.
        (default_policy, True, False, "comparable", True, "self_report", True),
        (default_policy, True, True, "comparable", True, "both", True),
        (default_policy, False, True, "comparable", False, "after_object", True),
        (default_policy, False, False, "comparable", False, "policy_excluded", False),
        (default_policy, False, False, "unknown", False, "order_unknown", False),
        (default_policy, True, False, "unknown", True, "self_report", True),
        (default_policy, True, True, "unknown", True, "self_report", True),
        # Custom policy: only enabled rules can match.
        (
            lambda: policy(include_self_report=True),
            True,
            True,
            "comparable",
            True,
            "self_report",
            True,
        ),
        (
            lambda: policy(include_self_report=True),
            False,
            True,
            "comparable",
            False,
            "policy_excluded",
            False,
        ),
        (
            lambda: policy(include_after_object=True),
            True,
            True,
            "comparable",
            True,
            "after_object",
            True,
        ),
        (
            lambda: policy(include_after_object=True),
            True,
            False,
            "comparable",
            True,
            "policy_excluded",
            False,
        ),
        (
            lambda: policy(include_self_report=True, include_after_object=True),
            True,
            True,
            "comparable",
            True,
            "both",
            True,
        ),
        # sameObjectOnly filters the union even when the rule matched.
        (
            lambda: policy(include_after_object=True, same_object_only=True),
            False,
            True,
            "comparable",
            False,
            "policy_excluded",
            False,
        ),
        (
            lambda: policy(include_after_object=True, same_object_only=True),
            False,
            True,
            "comparable",
            True,
            "after_object",
            True,
        ),
        # Unknown order only becomes a reason when the after rule is enabled.
        (
            lambda: policy(include_after_object=True),
            False,
            False,
            "unknown",
            False,
            "order_unknown",
            False,
        ),
        (
            lambda: policy(include_self_report=True),
            False,
            False,
            "unknown",
            False,
            "policy_excluded",
            False,
        ),
        (
            lambda: policy(include_self_report=True),
            True,
            False,
            "unknown",
            True,
            "self_report",
            True,
        ),
    ],
)
def test_hit_reason_truth_table(
    selected: Callable[[], ResolvedPolicy],
    self_match: bool,
    after_match: bool,
    order_state: Literal["comparable", "unknown"],
    same_object: bool,
    hit_reason: Literal[
        "self_report",
        "after_object",
        "both",
        "policy_excluded",
        "order_unknown",
    ],
    included: bool,
) -> None:
    """The closed reason set follows rule priority, object filter, and order state."""
    resolved = selected()
    verdict = evaluate_hit(
        self_match=self_match,
        after_match=after_match,
        order_state=order_state,
        same_object=same_object,
        policy=resolved,
    )
    assert verdict.hit_reason == hit_reason
    assert verdict.included is included


def point(
    *,
    at: datetime | None = None,
    tree_index: int | None = None,
    event_index: int | None = None,
) -> TriggerPoint:
    """Build one comparable/degenerate trigger point."""
    return TriggerPoint(
        agent_id="agent",
        event_index=event_index,
        triggered_at=at,
        tree_index=tree_index,
    )


def test_compare_prefers_wall_clock_and_is_strict() -> None:
    """Wall-clock comparison requires a strictly later case trigger."""
    later = compare_triggers(point(at=LATE), point(at=EARLY))
    assert later.state == "comparable"
    assert later.after is True

    equal = compare_triggers(point(at=LATE), point(at=LATE))
    assert equal.state == "comparable"
    assert equal.after is False

    earlier = compare_triggers(point(at=EARLY), point(at=LATE))
    assert earlier.state == "comparable"
    assert earlier.after is False


def test_compare_falls_back_to_tree_and_event_order() -> None:
    """A missing timestamp on either side uses the documented coordinates."""
    case = point(at=None, tree_index=2, event_index=3)
    target = point(at=EARLY, tree_index=1, event_index=9)
    verdict = compare_triggers(case, target)
    assert verdict.state == "comparable"
    assert verdict.after is True

    same_agent = compare_triggers(
        point(at=None, tree_index=1, event_index=2),
        point(at=None, tree_index=1, event_index=3),
    )
    assert same_agent.state == "comparable"
    assert same_agent.after is False


def test_compare_requires_both_sides_to_be_comparable() -> None:
    """A missing anchor or fully missing coordinates is unknown, never 'after'."""
    unknown = compare_triggers(None, point(at=EARLY, tree_index=1, event_index=1))
    assert unknown.state == "unknown"
    assert unknown.after is False

    no_coordinates = compare_triggers(
        point(at=None, tree_index=None, event_index=None),
        point(at=None, tree_index=1, event_index=1),
    )
    assert no_coordinates.state == "unknown"
    assert no_coordinates.after is False


def test_window_defaults_to_the_last_ninety_local_days() -> None:
    """No boundaries means a 90-day inclusive window ending today."""
    start, end = resolve_window(None, None, today=date(2026, 11, 17))

    assert start == date(2026, 8, 20)
    assert end == date(2026, 11, 17)


def test_window_anchors_a_single_supplied_boundary() -> None:
    """One boundary is completed to a 90-day inclusive window."""
    assert resolve_window(date(2026, 11, 1), None, today=date(2026, 11, 17)) == (
        date(2026, 11, 1),
        date(2026, 11, 17),
    )
    assert resolve_window(None, date(2026, 11, 17), today=date(2027, 1, 1)) == (
        date(2026, 8, 20),
        date(2026, 11, 17),
    )


def test_window_rejects_dates_outside_the_supported_range() -> None:
    """A boundary that would overflow the half-open end predicate is a 422."""
    with pytest.raises(AppError) as raised:
        resolve_window(None, date(9999, 12, 31), today=date(2026, 11, 17))

    assert raised.value.code is ErrorCode.WINDOW_INVALID


def test_resolved_policy_snapshot_uses_camel_case() -> None:
    """The shared snapshot is ready for a future run's policy column."""
    resolved = resolve_policy(
        PotentialPolicy(
            preset="custom",
            include_self_report=True,
            include_after_object=False,
            same_object_only=True,
        ),
    )

    assert resolved.snapshot() == {
        "preset": "custom",
        "includeSelfReport": True,
        "includeAfterObject": False,
        "sameObjectOnly": True,
    }
