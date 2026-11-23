"""V2 report round trips and execution-manifest cache invalidation."""

from __future__ import annotations

from datetime import datetime

from app.service.evolution.attribution_contracts import (
    AttributionAnalysis,
    AttributionExecutionManifest,
    AttributionReportV2,
    AttributionSkillRevision,
    AttributionTargetRef,
    default_execution_manifest,
)
from app.utils.time import SHANGHAI

NOW = datetime(2026, 11, 17, 12, 0, tzinfo=SHANGHAI)


def manifest() -> AttributionExecutionManifest:
    """Build one deterministic platform-default execution manifest."""
    return default_execution_manifest(
        workspace_id="ws-default",
        bad_case_id="bc-m12-07",
        target_type="skill",
        target_name="deep-research",
        target_version="tag:v2.0.0",
        policy_version="v1",
        engine="rule-v1",
        session_id="97000000-0000-4000-8000-000000000001",
        hit_reason="self_report",
        order_state="comparable",
        object_trigger_at=NOW,
        case_trigger_at=NOW,
    )


def test_report_v2_round_trips_camel_case_json() -> None:
    """Stored JSON can be validated and emitted through the public convention."""
    report = AttributionReportV2(
        target=AttributionTargetRef(
            object_type="skill",
            object_name="deep-research",
            object_version="tag:v2.0.0",
        ),
        conclusion="inconclusive",
        analysis=AttributionAnalysis(summary="evidence missing", reasoning="no anchor"),
        warnings=["ATTRIBUTION_EVIDENCE_INSUFFICIENT"],
    )

    payload = report.model_dump(mode="json", by_alias=True)
    restored = AttributionReportV2.model_validate(payload)

    assert restored == report
    assert payload["schemaVersion"] == "probe-report/v2"
    assert payload["conclusion"] == "inconclusive"


def test_manifest_hash_changes_for_every_semantic_cache_dimension() -> None:
    """Skill, model, context, and output schema inputs cannot share a cache row."""
    base = manifest()
    changed_skill = base.model_copy(
        update={
            "skill": AttributionSkillRevision(
                key=base.skill.key,
                revision="builtin-v2",
                content_hash="d" * 64,
            ),
        },
    )
    changed_model = base.model_copy(update={"model_config_fingerprint": "model-config-v2"})
    changed_context = base.model_copy(update={"context_snapshot_hash": "e" * 64})
    changed_schema = base.model_copy(update={"output_schema_version": "probe-report/v3"})

    hashes = {
        base.content_hash,
        changed_skill.content_hash,
        changed_model.content_hash,
        changed_context.content_hash,
        changed_schema.content_hash,
    }

    assert len(hashes) == 5
