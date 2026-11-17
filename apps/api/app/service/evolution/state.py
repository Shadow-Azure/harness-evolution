"""Pure state rules for the durable seven-step evolution unit cursor."""

from dataclasses import dataclass
from typing import Literal

STEP_KEYS: tuple[str, ...] = (
    "range",
    "sessions",
    "potential",
    "attribution",
    "clusters",
    "iteration",
    "final",
)
STEP_TITLES: tuple[str, ...] = (
    "选择范围",
    "Session 关联",
    "潜在 bad case",
    "对象归因",
    "聚类与严重度",
    "迭代优化",
    "测试集终评",
)
_WORKING_STATUSES = frozenset({"preparing", "running", "blocked"})
_VALID_RUN_STATUSES = _WORKING_STATUSES | frozenset({"completed", "failed", "interrupted"})
_CLUSTER_ONLY_HIDDEN = frozenset({"iteration", "final"})
PREPARE_COMPLETE_UNIT = 5
"""Prepared unit once range through clusters have completed."""


@dataclass(frozen=True, slots=True)
class StepState:
    """One server-owned state item in the seven-step workflow."""

    index: int
    key: str
    title: str
    status: Literal["done", "active", "pending"]
    clickable: bool


class StepNotReady(LookupError):
    """Raised when a requested step has not reached a readable state."""

    def __init__(self, key: str, progress_unit: int) -> None:
        """Describe the unreadable step without inventing a public API error."""
        super().__init__(f"step {key!r} is not ready at unit {progress_unit}")
        self.key = key
        self.progress_unit = progress_unit


class StageConflict(ValueError):
    """Raised when a cursor read or transition violates the workflow."""

    def __init__(
        self,
        *,
        status_code: int,
        current: int,
        target: int,
        reason: str,
    ) -> None:
        """Keep normal exception traceback behavior for async rollback paths."""
        super().__init__(reason)
        self.status_code = status_code
        self.current = current
        self.target = target
        self.reason = reason


def total_units(cluster_count: int) -> int:
    """Return the inclusive final cursor for a run with M clusters."""
    if cluster_count < 0:
        raise StageConflict(
            status_code=409,
            current=cluster_count,
            target=cluster_count,
            reason="cluster count cannot be negative",
        )
    return PREPARE_COMPLETE_UNIT + cluster_count + 1


def _thresholds(cluster_count: int) -> tuple[int, ...]:
    """Map each step key to the first unit at which it is done."""
    total = total_units(cluster_count)
    return (1, 2, 3, 4, 5, total - 1, total)


def is_legacy_run(attribution_engine: str) -> bool:
    """Return whether a run predates the V2 prepare pipeline."""
    return attribution_engine == "legacy-probe-import"


def legacy_unit(progress_unit: int, cluster_count: int) -> int:
    """Project a six-step V1 cursor onto the seven-step workflow.

    V1 stored input=1, clusters=2, attribution=3, severity=4, iteration
    4..4+M, final=5+M. V2 inserts sessions and potential between input and
    clusters, so a V1 run that already clustered skips straight to the
    prepared unit while iteration/final shift by one.

    Args:
        progress_unit: Persisted six-step unit of a legacy run.
        cluster_count: Cluster count behind the legacy cursor.

    Returns:
        The equivalent seven-step unit, bounded by the new total.
    """
    if progress_unit <= 1:
        projected = progress_unit
    elif progress_unit <= 4:
        projected = PREPARE_COMPLETE_UNIT
    else:
        projected = progress_unit + 1
    return min(projected, total_units(cluster_count))


def effective_unit(
    progress_unit: int,
    cluster_count: int,
    *,
    attribution_engine: str,
) -> int:
    """Return the seven-step cursor for either a V2 or a legacy run.

    Args:
        progress_unit: Persisted unit cursor.
        cluster_count: Cluster count behind the run.
        attribution_engine: Persisted attribution engine snapshot.

    Returns:
        The seven-step unit to use for status, progress, and step readability.
    """
    if is_legacy_run(attribution_engine):
        return legacy_unit(progress_unit, cluster_count)
    return progress_unit


def validate_cursor(progress_unit: int, cluster_count: int) -> None:
    """Reject a persisted cursor outside the run's computed range."""
    total = total_units(cluster_count)
    if progress_unit < 0 or progress_unit > total:
        raise StageConflict(
            status_code=409,
            current=progress_unit,
            target=progress_unit,
            reason=f"progress unit must be between 0 and {total}",
        )


def next_unit(progress_unit: int, cluster_count: int) -> int:
    """Return the sole legal next cursor after validating the current one."""
    validate_cursor(progress_unit, cluster_count)
    target = progress_unit + 1
    if target > total_units(cluster_count):
        raise StageConflict(
            status_code=409,
            current=progress_unit,
            target=target,
            reason="run is already at its final unit",
        )
    return target


def validate_transition(
    progress_unit: int,
    target: int,
    cluster_count: int,
) -> None:
    """Require exactly one forward unit for every cursor write."""
    validate_cursor(progress_unit, cluster_count)
    total = total_units(cluster_count)
    if target < 0 or target > total:
        raise StageConflict(
            status_code=409,
            current=progress_unit,
            target=target,
            reason=f"target unit must be between 0 and {total}",
        )
    if target != progress_unit + 1:
        raise StageConflict(
            status_code=409,
            current=progress_unit,
            target=target,
            reason="progress may advance by exactly one unit",
        )


def step_states(
    progress_unit: int,
    cluster_count: int,
    run_status: str,
    *,
    attribution_engine: str = "rule-v1",
) -> list[StepState]:
    """Derive all seven public step states from one persisted cursor."""
    validate_cursor(progress_unit, cluster_count)
    if run_status not in _VALID_RUN_STATUSES:
        raise ValueError(f"unknown run status: {run_status}")
    unit = effective_unit(
        progress_unit,
        cluster_count,
        attribution_engine=attribution_engine,
    )

    active_assigned = False
    states: list[StepState] = []
    for index, (key, title, threshold) in enumerate(
        zip(STEP_KEYS, STEP_TITLES, _thresholds(cluster_count), strict=True),
    ):
        if unit >= threshold:
            status: Literal["done", "active", "pending"] = "done"
        elif run_status in _WORKING_STATUSES and not active_assigned:
            status = "active"
            active_assigned = True
        else:
            status = "pending"
        states.append(
            StepState(
                index=index,
                key=key,
                title=title,
                status=status,
                clickable=status != "pending",
            ),
        )
    return states


def ensure_step_readable(
    progress_unit: int,
    cluster_count: int,
    run_status: str,
    key: str,
    mode: str = "full",
    *,
    attribution_engine: str = "rule-v1",
) -> None:
    """Raise unless the requested step is readable for this run.

    Cluster-only runs never run iteration or a terminal evaluation, so
    05 §4.12 fixes those two steps at 404 regardless of the cursor.

    Args:
        progress_unit: Persisted unit cursor behind the seven step states.
        cluster_count: Number of clusters behind the run's cursor range.
        run_status: Persisted run status feeding the active-step rule.
        key: Requested step key inside the closed seven-key vocabulary.
        mode: Persisted run mode; `cluster_only` hides iteration and final.
        attribution_engine: Persisted engine snapshot selecting legacy cursor
            projection.
    """
    if key not in STEP_KEYS:
        raise StepNotReady(key, progress_unit)
    if mode == "cluster_only" and key in _CLUSTER_ONLY_HIDDEN:
        raise StepNotReady(key, progress_unit)
    state = step_states(
        progress_unit,
        cluster_count,
        run_status,
        attribution_engine=attribution_engine,
    )[STEP_KEYS.index(key)]
    if state.status == "pending":
        raise StepNotReady(key, progress_unit)
