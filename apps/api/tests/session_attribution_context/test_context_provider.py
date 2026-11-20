"""Shared Session attribution context, coordinates, bounds, and stable hashes."""

from __future__ import annotations

from collections.abc import Sequence

from app.db.crud.attributions import BadCaseEvidenceRecord, KnowledgeEvidenceRecord
from app.db.crud.potential import AgentNodeRecord, ObjectEventRecord, ObjectType
from app.service.evolution.attribution_context import AttributionContextProvider
from tests.attribution.support import (
    CASE_ID,
    KNOWLEDGE_DOCUMENT_ID,
    KNOWLEDGE_REVISION,
    LATER,
    NOW,
    OTHER_CASE_ID,
    SESSION_ID,
    TARGET_NAME,
    TARGET_VERSION,
    potential_case,
)


class FakeContextStore:
    """Count batched reads while returning one deterministic Session tree."""

    def __init__(self, *, empty: bool = False) -> None:
        """Configure whether normalized trace facts are unavailable."""
        self.empty = empty
        self.agent_calls = 0
        self.event_calls = 0

    async def list_agents(self, session_ids: Sequence[str]) -> tuple[AgentNodeRecord, ...]:
        """Return one root and one reporting child in a single batch."""
        self.agent_calls += 1
        assert session_ids == (SESSION_ID,)
        if self.empty:
            return ()
        return (
            AgentNodeRecord(
                id="agent-m10-03-main",
                root_session_id=SESSION_ID,
                parent_agent_id=None,
                kind="main",
                tool_use_id=None,
                tree_index=0,
            ),
            AgentNodeRecord(
                id="agent-m10-03-child",
                root_session_id=SESSION_ID,
                parent_agent_id="agent-m10-03-main",
                kind="subagent",
                tool_use_id="tool-1",
                tree_index=1,
            ),
        )

    async def list_object_events(
        self,
        session_ids: Sequence[str],
        *,
        object_type: ObjectType,
        object_name: str,
    ) -> tuple[ObjectEventRecord, ...]:
        """Return two exact occurrences and one non-matching revision."""
        self.event_calls += 1
        assert session_ids == (SESSION_ID,)
        assert object_type == "skill"
        assert object_name == TARGET_NAME
        if self.empty:
            return ()
        return (
            ObjectEventRecord(
                session_id=SESSION_ID,
                agent_id="agent-m10-03-main",
                event_index=0,
                tree_index=0,
                object_version=TARGET_VERSION,
                definition_hash=None,
                document_revision=None,
                object_revision="tag:v2.0.0",
                triggered_at=NOW,
            ),
            ObjectEventRecord(
                session_id=SESSION_ID,
                agent_id="agent-m10-03-child",
                event_index=2,
                tree_index=1,
                object_version=TARGET_VERSION,
                definition_hash=None,
                document_revision=None,
                object_revision="tag:v2.0.0",
                triggered_at=LATER,
            ),
            ObjectEventRecord(
                session_id=SESSION_ID,
                agent_id="agent-m10-03-main",
                event_index=3,
                tree_index=0,
                object_version="v1.0.0",
                definition_hash=None,
                document_revision=None,
                object_revision="tag:v1.0.0",
                triggered_at=LATER,
            ),
        )


def _evidence(case_id: str) -> BadCaseEvidenceRecord:
    """Build one redacted Badcase summary used by the provider."""
    return BadCaseEvidenceRecord(
        bad_case_id=case_id,
        session_id=SESSION_ID,
        bad_case_type="self",
        title=f"case {case_id}",
        description="description",
        metadata={},
    )


async def test_one_bundle_serves_multiple_badcases_without_n_plus_one() -> None:
    """Two Badcases share one bundle while retaining distinct report coordinates."""
    store = FakeContextStore()
    provider = AttributionContextProvider(store)
    first = potential_case(CASE_ID)
    second = potential_case(OTHER_CASE_ID)
    contexts = await provider.prepare(
        target_type="skill",
        target_name=TARGET_NAME,
        target_version=TARGET_VERSION,
        candidates=(first, second),
        bad_cases={CASE_ID: _evidence(CASE_ID), OTHER_CASE_ID: _evidence(OTHER_CASE_ID)},
        knowledge={
            SESSION_ID: (
                KnowledgeEvidenceRecord(
                    session_id=SESSION_ID,
                    document_id=KNOWLEDGE_DOCUMENT_ID,
                    document_revision=KNOWLEDGE_REVISION,
                    source_path="knowledge/readme.md",
                    retrieval_kind="read",
                ),
            ),
        },
        historical_probe_ids={SESSION_ID: ("probe-old-1",)},
    )

    assert store.agent_calls == 1
    assert store.event_calls == 1
    assert contexts[CASE_ID].bundle is contexts[OTHER_CASE_ID].bundle
    assert len(contexts[CASE_ID].bundle.object_occurrences) == 2
    assert contexts[CASE_ID].report_ref == "event:agent-m10-03-main:1"
    assert contexts[CASE_ID].report_ref in {
        point.ref for point in contexts[CASE_ID].bundle.evidence_points
    }
    assert contexts[CASE_ID].path_agent_refs == ("agent:agent-m10-03-main",)
    assert contexts[CASE_ID].snapshot_hash == contexts[OTHER_CASE_ID].snapshot_hash
    assert "raw_messages_omitted" in contexts[CASE_ID].bundle.redactions
    assert contexts[CASE_ID].bundle.historical_probe_ids == ("probe-old-1",)


async def test_bundle_hash_is_stable_across_candidate_order() -> None:
    """Input order cannot change the shared snapshot identity."""
    provider = AttributionContextProvider(FakeContextStore())
    inputs = {
        "target_type": "skill",
        "target_name": TARGET_NAME,
        "target_version": TARGET_VERSION,
        "bad_cases": {CASE_ID: _evidence(CASE_ID), OTHER_CASE_ID: _evidence(OTHER_CASE_ID)},
        "knowledge": {},
        "historical_probe_ids": {},
    }
    first = await provider.prepare(
        candidates=(potential_case(CASE_ID), potential_case(OTHER_CASE_ID)),
        **inputs,  # type: ignore[arg-type]
    )
    second = await provider.prepare(
        candidates=(potential_case(OTHER_CASE_ID), potential_case(CASE_ID)),
        **inputs,  # type: ignore[arg-type]
    )
    assert first[CASE_ID].snapshot_hash == second[CASE_ID].snapshot_hash


async def test_missing_trace_is_explicit_and_never_fabricated() -> None:
    """Missing normalized trace yields warnings and no invented coordinates."""
    provider = AttributionContextProvider(FakeContextStore(empty=True))
    contexts = await provider.prepare(
        target_type="skill",
        target_name=TARGET_NAME,
        target_version=TARGET_VERSION,
        candidates=(potential_case(CASE_ID),),
        bad_cases={CASE_ID: _evidence(CASE_ID)},
        knowledge={},
        historical_probe_ids={},
    )
    context = contexts[CASE_ID]
    assert context.bundle.agent_nodes == ()
    assert context.bundle.object_occurrences == ()
    assert context.report_ref is None
    assert set(context.bundle.warnings) >= {
        "SELECTED_OBJECT_OCCURRENCE_MISSING",
        "BADCASE_REPORT_NODE_MISSING",
    }
