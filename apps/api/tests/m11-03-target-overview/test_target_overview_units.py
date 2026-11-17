"""Unit coverage for target-overview parsing, version, and state helpers."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.db.crud.evolution_targets import EvolutionTargetRecord
from app.db.crud.overview_targets import AttributionLinkRecord, ObjectVersionRecord
from app.errors import AppError
from app.service.overview.target_schemas import TARGET_STATES, TargetState
from app.service.overview.targets import (
    TargetAnalysis,
    TargetCaseEntry,
    _category,
    _display_version,
    _event_version,
    _newest_link_by_case,
    _ordered_versions,
    _state,
    parse_state_filter,
    parse_target_filter,
    parse_version_filter,
    parse_version_limit,
)
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


def test_version_normalization_dedupes_tag_and_revision_forms() -> None:
    """Display versions strip tag prefixes and prefer the persisted version field."""
    assert _display_version(None) is None
    assert _display_version("") is None
    assert _display_version("tag:") is None
    assert _display_version("tag:v2.0.0") == "v2.0.0"
    assert _display_version("digest:abc") == "digest:abc"
    assert (
        _event_version(
            ObjectVersionRecord(object_version="v2.0.0", object_revision="tag:v2.0.0"),
        )
        == "v2.0.0"
    )
    assert (
        _event_version(
            ObjectVersionRecord(object_version=None, object_revision="tag:v1.9.0"),
        )
        == "v1.9.0"
    )
    assert (
        _event_version(
            ObjectVersionRecord(object_version="unknown", object_revision="digest:abc"),
        )
        == "digest:abc"
    )
    assert (
        _event_version(
            ObjectVersionRecord(object_version="unknown", object_revision=None),
        )
        is None
    )
    versions = _ordered_versions(
        "v2.0.0",
        (
            ObjectVersionRecord(object_version="tag:v2.0.0", object_revision=None),
            ObjectVersionRecord(object_version=None, object_revision="tag:v1.9.0"),
            ObjectVersionRecord(object_version="v2.10.0", object_revision=None),
            ObjectVersionRecord(object_version="unknown", object_revision=None),
        ),
    )
    assert versions == ("v2.10.0", "v2.0.0", "v1.9.0")


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
    newest = _newest_link_by_case(links, "v2.0.0")
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
