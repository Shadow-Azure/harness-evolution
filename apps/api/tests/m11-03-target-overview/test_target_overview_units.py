"""Unit coverage for target-overview parsing, version, and state helpers."""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.db.crud.evolution_targets import EvolutionTargetRecord
from app.db.crud.overview_targets import AttributionLinkRecord, ObjectVersionRecord
from app.errors import AppError
from app.service.evolution.target_content import (
    ResolvedTargetVersion,
    target_content_unresolved,
)
from app.service.overview.target_schemas import TARGET_STATES, TargetState
from app.service.overview.targets import (
    TargetAnalysis,
    TargetCaseEntry,
    TargetOverviewQuery,
    TargetOverviewService,
    _build_version_labels,
    _category,
    _display_version,
    _newest_link_by_case,
    _record_identity,
    _state,
    parse_state_filter,
    parse_target_filter,
    parse_version_filter,
    parse_version_limit,
)
from app.service.overview.window import Window
from app.utils.time import SHANGHAI

TARGET = EvolutionTargetRecord(
    id="target-unit",
    object_type="skill",
    object_name="deep-research",
    repo_url="https://example.invalid/deep-research.git",
    sub_dir="skills/deep-research",
    default_ref="v2.0.0",
    validation_project_id="validation",
    test_project_id="test",
    enabled=True,
    workspace_id="ws-unit",
)
NOW = datetime(2026, 11, 17, 12, 0, tzinfo=SHANGHAI)


def _link(
    case_id: str,
    *,
    version: str,
    conclusion: str,
    category: str | None,
    minute: int,
) -> AttributionLinkRecord:
    """Build one attribution link with a deterministic time."""
    return AttributionLinkRecord(
        bad_case_id=case_id,
        attribution_id=f"probe-{case_id}-{conclusion}",
        object_version=version,
        conclusion=conclusion,
        category=category,
        created_at=NOW.replace(minute=minute),
        updated_at=NOW.replace(minute=minute),
    )


def _entry(case_id: str, state: TargetState) -> TargetCaseEntry:
    """Build the minimal projected entry the property assertions need."""
    return TargetCaseEntry(
        bad_case_id=case_id,
        target=TARGET,
        version="v2.0.0",
        session_id=f"session-{case_id}",
        source="workflow",
        bad_case_type="discovery",
        title=case_id,
        created_at=NOW,
        state=state,
        attribution_id=None,
        category=None,
        attributed_at=None,
    )


def test_parse_target_state_and_version_filters() -> None:
    """Repeated and comma-separated filters dedupe; empty states mean all."""
    assert parse_target_filter(None) == ()
    assert parse_target_filter([" a ", "b,a", ""]) == ("a", "b")
    assert parse_state_filter(None) == frozenset(TARGET_STATES)
    assert parse_state_filter([""]) == frozenset(TARGET_STATES)
    assert parse_state_filter(["attributed,unanalyzed"]) == frozenset(
        {"attributed", "unanalyzed"},
    )
    assert parse_version_filter(["v2.0.0,v1.0.0"]) == ("v2.0.0", "v1.0.0")
    assert parse_version_limit(0) == 0
    assert parse_version_limit(20) == 20

    with pytest.raises(AppError) as invalid_state:
        parse_state_filter(["bogus"])
    assert invalid_state.value.code == "VALIDATION_INVALID"

    with pytest.raises(AppError) as invalid_limit:
        parse_version_limit(7)
    assert invalid_limit.value.code == "VALIDATION_INVALID"

    with pytest.raises(AppError) as too_many_targets:
        parse_target_filter([",".join(f"t{index}" for index in range(51))])
    assert too_many_targets.value.code == "VALIDATION_INVALID"

    with pytest.raises(AppError) as too_many_versions:
        parse_version_filter([",".join(f"v{index}" for index in range(51))])
    assert too_many_versions.value.code == "VALIDATION_INVALID"


def test_version_normalization_groups_one_record_into_one_version() -> None:
    """A ref and a digest from one trigger record are one display version."""
    assert _display_version(None) is None
    assert _display_version("") is None
    assert _display_version("tag:") is None
    assert _display_version("tag:v2.0.0") == "v2.0.0"
    assert _display_version("digest:abc") == "digest:abc"
    assert _record_identity(
        ObjectVersionRecord(object_version="v2.0.0", object_revision="tag:v2.0.0"),
    ) == ("v2.0.0", frozenset({"v2.0.0"}), "v2.0.0", None)
    assert _record_identity(
        ObjectVersionRecord(object_version=None, object_revision="tag:v1.9.0"),
    ) == ("v1.9.0", frozenset({"v1.9.0"}), "v1.9.0", None)
    assert _record_identity(
        ObjectVersionRecord(object_version="unknown", object_revision="digest:abc"),
    ) == ("digest:abc", frozenset({"digest:abc", "abc"}), None, "digest:abc")
    assert (
        _record_identity(
            ObjectVersionRecord(object_version="unknown", object_revision=None),
        )
        is None
    )
    assert _record_identity(
        ObjectVersionRecord(object_version="provider:alpha", object_revision=None),
    ) == ("provider:alpha", frozenset({"provider:alpha"}), None, None)
    versions, labels = _build_version_labels(
        "v2.0.0",
        (
            ObjectVersionRecord(object_version="tag:v2.0.0", object_revision=None),
            ObjectVersionRecord(object_version=None, object_revision="tag:v1.9.0"),
            ObjectVersionRecord(object_version="v2.10.0", object_revision=None),
            ObjectVersionRecord(object_version="unknown", object_revision=None),
        ),
        (),
    )
    assert versions == ("v2.10.0", "v2.0.0", "v1.9.0")
    assert labels["v2.0.0"].ref == "v2.0.0"
    assert labels["v2.0.0"].commit is None


def test_ref_and_digest_merge_into_one_version_with_run_commit() -> None:
    """Same-record ref+digest is one canonical version labelled by its ref."""
    from app.db.crud.overview_targets import TargetRunVersionRecord

    digest = "digest:" + "8e54" * 16
    versions, labels = _build_version_labels(
        "main",
        (
            ObjectVersionRecord(object_version="main", object_revision=digest),
            ObjectVersionRecord(object_version=None, object_revision="digest:" + "ab" * 32),
        ),
        (
            TargetRunVersionRecord(
                target_version="main",
                target_revision=digest,
                base_commit="580c97cf8ca7901d4dc2f8d0ff8a8f7e0f0f0f0f",
                created_at=NOW,
            ),
        ),
    )
    assert versions == (digest, "digest:" + "ab" * 32)
    assert labels[digest].ref == "main"
    assert labels[digest].display == "main"
    assert labels[digest].commit == "580c97c"
    assert labels[digest].aliases == frozenset({"main", digest, digest[7:]})
    assert labels["digest:" + "ab" * 32].ref is None


def test_digest_only_default_ref_merges_through_run_evidence() -> None:
    """A digest-only event joins the default ref when a run maps the two."""
    from app.db.crud.overview_targets import TargetRunVersionRecord

    main_digest = "digest:" + "8e54" * 16
    old_digest = "digest:" + "580c" * 16
    versions, labels = _build_version_labels(
        "main",
        (
            ObjectVersionRecord(object_version=None, object_revision=main_digest),
            ObjectVersionRecord(object_version=None, object_revision=old_digest),
        ),
        (
            TargetRunVersionRecord(
                target_version="main",
                target_revision=main_digest,
                base_commit="10e97a33f68559e7f6b5d612e8b6a03b15e83465",
                created_at=NOW,
            ),
            TargetRunVersionRecord(
                target_version="v6.4.1",
                target_revision=old_digest,
                base_commit="10e97a33f68559e7f6b5d612e8b6a03b15e83465",
                created_at=NOW,
            ),
        ),
    )
    assert versions == (old_digest, main_digest)
    assert "main" not in versions
    assert labels[main_digest].ref == "main"
    assert labels[main_digest].commit == "10e97a3"
    assert "main" in labels[main_digest].aliases
    assert labels[old_digest].ref == "v6.4.1"


def test_bound_snapshot_merges_a_ref_only_group_and_keeps_other_digests() -> None:
    current = "digest:" + "a" * 64
    historic = "digest:" + "b" * 64
    observed = (
        ObjectVersionRecord("tag:main", None),
        ObjectVersionRecord("main", historic),
        ObjectVersionRecord(None, current),
    )
    versions, labels = _build_version_labels("main", observed, (), bound_revision=current)
    assert set(versions) == {current, historic}
    assert labels[current].digest == current
    assert labels[historic].digest == historic


def test_newest_link_state_and_category_projection() -> None:
    """The newest matching link owns the state and only attributed rows get a category."""
    links = (
        _link(
            "case-a",
            version="tag:v2.0.0",
            conclusion="attributed",
            category="error",
            minute=2,
        ),
        _link(
            "case-a",
            version="v2.0.0",
            conclusion="non_target",
            category=None,
            minute=1,
        ),
        _link(
            "case-b",
            version="v1.9.0",
            conclusion="non_target",
            category=None,
            minute=3,
        ),
    )
    newest = _newest_link_by_case(links, frozenset({"v2.0.0"}))
    assert set(newest) == {"case-a"}
    assert newest["case-a"].conclusion == "attributed"
    assert _state(newest["case-a"]) == "attributed"
    assert _category(newest["case-a"]) == "error"
    assert _state(None) == "unanalyzed"
    assert (
        _state(_link("case-b", version="v2.0.0", conclusion="non_target", category=None, minute=4))
        == "nonTarget"
    )
    assert _category(None) is None
    assert (
        _category(
            _link("case-c", version="v2.0.0", conclusion="attributed", category="other", minute=5),
        )
        is None
    )


def test_target_analysis_properties_count_every_state() -> None:
    """The object counters always partition potential and used the documented sort key."""
    entries = (
        _entry("case-1", "attributed"),
        _entry("case-2", "nonTarget"),
        _entry("case-3", "unanalyzed"),
    )
    analysis = TargetAnalysis(
        target=TARGET,
        versions=("v2.0.0",),
        session_ids=frozenset({"session-a", "session-b"}),
        entries=entries,
        version_sessions={"v2.0.0": frozenset({"session-a", "session-b"})},
    )
    assert analysis.sessions == 2
    assert analysis.potential == 3
    assert analysis.attributed == 1
    assert analysis.non_target == 1
    assert analysis.unanalyzed == 1
    assert analysis.evolvable == 2
    assert analysis.potential == analysis.attributed + analysis.non_target + analysis.unanalyzed


async def test_trend_skips_attribution_created_outside_the_window() -> None:
    """Analyzed rows bucket by attribution createdAt; out-of-window rows are excluded."""
    service = TargetOverviewService(
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
    )
    attributed = _entry("case-late-attribution", "attributed")
    attributed = TargetCaseEntry(
        bad_case_id=attributed.bad_case_id,
        target=attributed.target,
        version=attributed.version,
        session_id=attributed.session_id,
        source=attributed.source,
        bad_case_type=attributed.bad_case_type,
        title=attributed.title,
        created_at=attributed.created_at,
        state=attributed.state,
        attribution_id="probe-late",
        category="error",
        attributed_at=datetime(2026, 12, 5, 12, 0, tzinfo=SHANGHAI),
    )
    unanalyzed = _entry("case-unanalyzed", "unanalyzed")
    analysis = TargetAnalysis(
        target=TARGET,
        versions=("v2.0.0",),
        session_ids=frozenset({attributed.session_id, unanalyzed.session_id}),
        entries=(attributed, unanalyzed),
        version_sessions={
            "v2.0.0": frozenset({attributed.session_id, unanalyzed.session_id}),
        },
    )

    async def fake_analyses(
        workspace_id: str,
        window: Window,
        target_ids: tuple[str, ...],
    ) -> tuple[TargetAnalysis, ...]:
        del workspace_id, window, target_ids
        return (analysis,)

    service._analyses = fake_analyses  # type: ignore[method-assign]
    response = await service.trend(
        "ws-unit",
        TargetOverviewQuery(
            window=Window(start=date(2026, 11, 1), end=date(2026, 11, 30), grain="day"),
        ),
    )
    assert sum(bucket.attributed for bucket in response.buckets) == 0
    assert sum(bucket.unanalyzed for bucket in response.buckets) == 1
    assert response.meta.bucket_policy == (
        "attributed and nonTarget rows bucket by attribution createdAt; "
        "unanalyzed rows bucket by badCase createdAt"
    )


class _SlowResolver:
    """Never finish before the overview timeout and count invocations."""

    def __init__(self) -> None:
        """Start with no calls."""
        self.calls = 0

    async def resolve(
        self,
        *,
        object_type: str,
        repo_url: str,
        sub_dir: str,
        version: str,
    ) -> ResolvedTargetVersion:
        """Sleep past the short test timeout."""
        del object_type, repo_url, sub_dir, version
        self.calls += 1
        await asyncio.sleep(10)
        raise AssertionError("slow resolver should have been cancelled")


class _UnresolvedResolver:
    """Raise the stable content-unresolved error for every version."""

    async def resolve(
        self,
        *,
        object_type: str,
        repo_url: str,
        sub_dir: str,
        version: str,
    ) -> ResolvedTargetVersion:
        """Report a missing target content file."""
        del repo_url, sub_dir, version
        raise target_content_unresolved(
            object_type=object_type,
            reason="file_not_found",
        )


async def test_overview_skips_content_unresolved_versions_without_tag_fallback() -> None:
    """An unresolved target version produces no matcher call and no tag guess."""
    service = TargetOverviewService(
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        _UnresolvedResolver(),
    )
    target = cast(
        Any,
        SimpleNamespace(
            object_type="skill",
            object_name="deep-research",
            repo_url="https://example.invalid/repo.git",
            sub_dir="skills/deep-research",
        ),
    )

    evaluated = await service._evaluate(
        target,
        "v2.0.0",
        workspace_id="ws-unit",
        window_start=datetime(2026, 11, 1),
        window_end=datetime(2026, 12, 1),
    )

    assert evaluated is None


async def test_overview_times_out_slow_resolution_and_caches_the_failure() -> None:
    """A slow repository is skipped promptly and the failure is cached."""
    resolver = _SlowResolver()
    service = TargetOverviewService(
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        resolver,
        resolve_timeout_seconds=0.01,
    )
    target = cast(
        Any,
        SimpleNamespace(
            object_type="skill",
            object_name="deep-research",
            repo_url="https://example.invalid/slow.git",
            sub_dir="skills/deep-research",
        ),
    )

    first = await service._evaluate(
        target,
        "v2.0.0",
        workspace_id="ws-unit",
        window_start=datetime(2026, 11, 1),
        window_end=datetime(2026, 12, 1),
    )
    second = await service._evaluate(
        target,
        "v2.0.0",
        workspace_id="ws-unit",
        window_start=datetime(2026, 11, 1),
        window_end=datetime(2026, 12, 1),
    )

    assert first is None
    assert second is None
    assert resolver.calls == 1
