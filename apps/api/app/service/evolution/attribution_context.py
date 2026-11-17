"""Bounded, redacted Session context bundles for per-Badcase attribution."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.db.crud.attributions import BadCaseEvidenceRecord, KnowledgeEvidenceRecord
from app.db.crud.potential import AgentNodeRecord, ObjectEventRecord, ObjectType
from app.service.evolution.attribution_contracts import canonical_json_hash
from app.service.evolution.potential import PotentialCase, resolve_target_revision

MAX_AGENT_NODES = 512
MAX_OBJECT_OCCURRENCES = 256
CONTEXT_SCHEMA_VERSION = "attribution-context/v1"


class AttributionContextStore(Protocol):
    """Normalized Session facts required to build shared context bundles."""

    async def list_agents(self, session_ids: Sequence[str]) -> tuple[AgentNodeRecord, ...]:
        """Return Agent tree nodes for all requested Sessions in one batched read."""
        ...

    async def list_object_events(
        self,
        session_ids: Sequence[str],
        *,
        object_type: ObjectType,
        object_name: str,
    ) -> tuple[ObjectEventRecord, ...]:
        """Return every selected-object occurrence for the requested Sessions."""
        ...


@dataclass(frozen=True, slots=True)
class ContextAgentNode:
    """One non-content Agent tree node addressable by evidence references."""

    ref: str
    agent_id: str
    parent_agent_id: str | None
    kind: str
    tree_index: int


@dataclass(frozen=True, slots=True)
class ContextObjectOccurrence:
    """One exact selected-object occurrence inside the Session tree."""

    ref: str
    agent_id: str
    event_index: int
    tree_index: int
    object_version: str | None
    object_revision: str | None
    triggered_at: datetime | None


@dataclass(frozen=True, slots=True)
class ContextBadCase:
    """One Session Badcase and its report anchor/path projection."""

    bad_case_id: str
    report_ref: str | None
    report_agent_id: str | None
    report_event_index: int | None
    path_agent_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextEvidencePoint:
    """One verifiable event coordinate referenced by a target or Badcase."""

    ref: str
    kind: str
    agent_id: str
    event_index: int


@dataclass(frozen=True, slots=True)
class AttributionContextBundle:
    """Shared immutable Session context; raw messages and credentials are omitted."""

    session_id: str
    target_type: str
    target_name: str
    target_revision: str
    agent_nodes: tuple[ContextAgentNode, ...]
    object_occurrences: tuple[ContextObjectOccurrence, ...]
    bad_cases: tuple[ContextBadCase, ...]
    evidence_points: tuple[ContextEvidencePoint, ...]
    knowledge_evidence: tuple[Mapping[str, object], ...]
    historical_probe_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    redactions: tuple[str, ...] = ("raw_messages_omitted", "credentials_omitted")
    schema_version: str = CONTEXT_SCHEMA_VERSION

    @property
    def snapshot_hash(self) -> str:
        """Return the stable hash of the bounded redacted bundle."""
        return canonical_json_hash(self.to_payload())

    def to_payload(self) -> Mapping[str, object]:
        """Return the canonical JSON-compatible bundle payload."""
        return {
            "schemaVersion": self.schema_version,
            "sessionId": self.session_id,
            "target": {
                "objectType": self.target_type,
                "objectName": self.target_name,
                "objectRevision": self.target_revision,
            },
            "agentNodes": [
                {
                    "ref": item.ref,
                    "agentId": item.agent_id,
                    "parentAgentId": item.parent_agent_id,
                    "kind": item.kind,
                    "treeIndex": item.tree_index,
                }
                for item in self.agent_nodes
            ],
            "objectOccurrences": [
                {
                    "ref": item.ref,
                    "agentId": item.agent_id,
                    "eventIndex": item.event_index,
                    "treeIndex": item.tree_index,
                    "objectVersion": item.object_version,
                    "objectRevision": item.object_revision,
                    "triggeredAt": (
                        item.triggered_at.isoformat() if item.triggered_at is not None else None
                    ),
                }
                for item in self.object_occurrences
            ],
            "badCases": [
                {
                    "badCaseId": item.bad_case_id,
                    "reportRef": item.report_ref,
                    "reportAgentId": item.report_agent_id,
                    "reportEventIndex": item.report_event_index,
                    "pathAgentRefs": list(item.path_agent_refs),
                }
                for item in self.bad_cases
            ],
            "evidencePoints": [
                {
                    "ref": item.ref,
                    "kind": item.kind,
                    "agentId": item.agent_id,
                    "eventIndex": item.event_index,
                }
                for item in self.evidence_points
            ],
            "knowledgeEvidence": [dict(item) for item in self.knowledge_evidence],
            "historicalProbeIds": list(self.historical_probe_ids),
            "sourceVersions": {
                "normalizedTrace": "domain-v1",
                "contextSchema": self.schema_version,
            },
            "warnings": list(self.warnings),
            "redactions": list(self.redactions),
        }


@dataclass(frozen=True, slots=True)
class AttributionCaseContext:
    """Per-Badcase projection that references one shared Session bundle."""

    bad_case_id: str
    bundle: AttributionContextBundle
    report_ref: str | None
    path_agent_refs: tuple[str, ...]

    @property
    def snapshot_hash(self) -> str:
        """Return the shared bundle identity used in the execution manifest."""
        return self.bundle.snapshot_hash


class AttributionContextProvider:
    """Build each Session bundle once, then project it for every candidate."""

    def __init__(self, store: AttributionContextStore) -> None:
        """Bind the provider to normalized Session reads."""
        self._store = store

    async def prepare(
        self,
        *,
        target_type: ObjectType,
        target_name: str,
        target_version: str,
        candidates: Sequence[PotentialCase],
        bad_cases: Mapping[str, BadCaseEvidenceRecord],
        knowledge: Mapping[str, tuple[KnowledgeEvidenceRecord, ...]],
        historical_probe_ids: Mapping[str, tuple[str, ...]],
    ) -> dict[str, AttributionCaseContext]:
        """Batch-read facts and return one projection per candidate Badcase."""
        session_ids = tuple(sorted({item.session_id for item in candidates}))
        if not session_ids:
            return {}
        agents = await self._store.list_agents(session_ids)
        events = await self._store.list_object_events(
            session_ids,
            object_type=target_type,
            object_name=target_name,
        )
        agents_by_session: dict[str, list[AgentNodeRecord]] = defaultdict(list)
        for agent in agents:
            agents_by_session[agent.root_session_id].append(agent)
        events_by_session: dict[str, list[ObjectEventRecord]] = defaultdict(list)
        for event in events:
            if _matches_revision(event, target_version):
                events_by_session[event.session_id].append(event)
        cases_by_session: dict[str, list[PotentialCase]] = defaultdict(list)
        for candidate in candidates:
            cases_by_session[candidate.session_id].append(candidate)

        projections: dict[str, AttributionCaseContext] = {}
        target_revision = resolve_target_revision(target_version)[1]
        for session_id in session_ids:
            bundle = _bundle(
                session_id=session_id,
                target_type=target_type,
                target_name=target_name,
                target_revision=target_revision,
                agents=agents_by_session.get(session_id, []),
                occurrences=events_by_session.get(session_id, []),
                candidates=cases_by_session.get(session_id, []),
                bad_cases=bad_cases,
                knowledge=knowledge.get(session_id, ()),
                historical_probe_ids=historical_probe_ids.get(session_id, ()),
            )
            by_id = {case.bad_case_id: case for case in bundle.bad_cases}
            for candidate in cases_by_session.get(session_id, []):
                context_case = by_id[candidate.bad_case_id]
                projections[candidate.bad_case_id] = AttributionCaseContext(
                    bad_case_id=candidate.bad_case_id,
                    bundle=bundle,
                    report_ref=context_case.report_ref,
                    path_agent_refs=context_case.path_agent_refs,
                )
        return projections


def _matches_revision(event: ObjectEventRecord, target_version: str) -> bool:
    """Keep the same exact version/revision identity selected by the matcher."""
    version, revision = resolve_target_revision(target_version)
    return event.object_revision == revision or event.object_version in {version, target_version}


def _bundle(
    *,
    session_id: str,
    target_type: str,
    target_name: str,
    target_revision: str,
    agents: Sequence[AgentNodeRecord],
    occurrences: Sequence[ObjectEventRecord],
    candidates: Sequence[PotentialCase],
    bad_cases: Mapping[str, BadCaseEvidenceRecord],
    knowledge: Sequence[KnowledgeEvidenceRecord],
    historical_probe_ids: Sequence[str],
) -> AttributionContextBundle:
    """Build one bounded bundle and validate every local evidence coordinate."""
    ordered_agents = sorted(agents, key=lambda item: (item.tree_index, item.id))
    ordered_occurrences = sorted(
        occurrences,
        key=lambda item: (item.tree_index, item.event_index, item.agent_id),
    )
    warnings: list[str] = []
    if len(ordered_agents) > MAX_AGENT_NODES:
        warnings.append("AGENT_TREE_TRUNCATED")
    if len(ordered_occurrences) > MAX_OBJECT_OCCURRENCES:
        warnings.append("OBJECT_OCCURRENCES_TRUNCATED")
    ordered_agents = ordered_agents[:MAX_AGENT_NODES]
    ordered_occurrences = ordered_occurrences[:MAX_OBJECT_OCCURRENCES]
    known_agents = {item.id for item in ordered_agents}
    parent = {item.id: item.parent_agent_id for item in ordered_agents}
    nodes = tuple(
        ContextAgentNode(
            ref=f"agent:{item.id}",
            agent_id=item.id,
            parent_agent_id=(
                item.parent_agent_id if item.parent_agent_id in known_agents else None
            ),
            kind=item.kind,
            tree_index=item.tree_index,
        )
        for item in ordered_agents
    )
    occurrence_rows = tuple(
        ContextObjectOccurrence(
            ref=f"event:{item.agent_id}:{item.event_index}",
            agent_id=item.agent_id,
            event_index=item.event_index,
            tree_index=item.tree_index,
            object_version=item.object_version,
            object_revision=item.object_revision,
            triggered_at=item.triggered_at,
        )
        for item in ordered_occurrences
        if item.agent_id in known_agents
    )
    if not occurrence_rows:
        warnings.append("SELECTED_OBJECT_OCCURRENCE_MISSING")

    case_rows: list[ContextBadCase] = []
    evidence_points: dict[str, ContextEvidencePoint] = {
        item.ref: ContextEvidencePoint(
            ref=item.ref,
            kind="selected_object",
            agent_id=item.agent_id,
            event_index=item.event_index,
        )
        for item in occurrence_rows
    }
    first_object_agent = occurrence_rows[0].agent_id if occurrence_rows else None
    for candidate in sorted(candidates, key=lambda item: item.bad_case_id):
        evidence = bad_cases.get(candidate.bad_case_id)
        report_agent = (
            candidate.case_trigger.agent_id if candidate.case_trigger is not None else None
        )
        report_event = (
            candidate.case_trigger.event_index if candidate.case_trigger is not None else None
        )
        if report_agent not in known_agents:
            report_agent = None
            report_event = None
            warnings.append("BADCASE_REPORT_NODE_MISSING")
        if evidence is None:
            warnings.append("BADCASE_EVIDENCE_MISSING")
        path = _tree_path(first_object_agent, report_agent, parent)
        if first_object_agent and report_agent and not path:
            warnings.append("AGENT_RELATION_DEGRADED")
        case_rows.append(
            ContextBadCase(
                bad_case_id=candidate.bad_case_id,
                report_ref=(
                    f"event:{report_agent}:{report_event}"
                    if report_agent is not None and report_event is not None
                    else (f"agent:{report_agent}" if report_agent is not None else None)
                ),
                report_agent_id=report_agent,
                report_event_index=report_event,
                path_agent_refs=tuple(f"agent:{agent_id}" for agent_id in path),
            ),
        )
        if report_agent is not None and report_event is not None:
            ref = f"event:{report_agent}:{report_event}"
            evidence_points[ref] = ContextEvidencePoint(
                ref=ref,
                kind="badcase_report",
                agent_id=report_agent,
                event_index=report_event,
            )
    knowledge_rows = tuple(
        {
            "documentId": item.document_id,
            "documentRevision": item.document_revision,
            "sourcePath": item.source_path,
            "retrievalKind": item.retrieval_kind,
        }
        for item in sorted(
            knowledge,
            key=lambda value: (
                value.document_id or "",
                value.document_revision or "",
                value.source_path or "",
            ),
        )
    )
    return AttributionContextBundle(
        session_id=session_id,
        target_type=target_type,
        target_name=target_name,
        target_revision=target_revision,
        agent_nodes=nodes,
        object_occurrences=occurrence_rows,
        bad_cases=tuple(case_rows),
        evidence_points=tuple(evidence_points[key] for key in sorted(evidence_points)),
        knowledge_evidence=knowledge_rows,
        historical_probe_ids=tuple(sorted(set(historical_probe_ids))),
        warnings=tuple(sorted(set(warnings))),
    )


def _tree_path(
    start: str | None,
    end: str | None,
    parent: Mapping[str, str | None],
) -> tuple[str, ...]:
    """Return the deterministic tree path between two known Agent nodes."""
    if start is None or end is None:
        return ()
    start_chain = _ancestors(start, parent)
    end_chain = _ancestors(end, parent)
    end_positions = {agent_id: index for index, agent_id in enumerate(end_chain)}
    for start_index, agent_id in enumerate(start_chain):
        end_index = end_positions.get(agent_id)
        if end_index is None:
            continue
        return tuple(start_chain[: start_index + 1] + list(reversed(end_chain[:end_index])))
    return ()


def _ancestors(node: str, parent: Mapping[str, str | None]) -> list[str]:
    """Walk a bounded parent chain without accepting cycles."""
    result: list[str] = []
    seen: set[str] = set()
    current: str | None = node
    while current is not None and current in parent and current not in seen:
        result.append(current)
        seen.add(current)
        current = parent[current]
    return result
