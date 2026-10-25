"""Convert validated upstream packages into shared raw-payload records."""

from __future__ import annotations

import hashlib
from datetime import datetime

from app.service.acquisition.local_sessions import LocalAgentPayload
from app.third_party_api.trajectory.models import TrajectoryPackage, TrajectoryTranscript
from app.utils.time import as_shanghai, now_shanghai


def _transcript_payload(
    package: TrajectoryPackage,
    transcript: TrajectoryTranscript,
    *,
    discovered_at: datetime,
) -> LocalAgentPayload:
    content = "\n".join(transcript.lines)
    encoded = content.encode("utf-8")
    source_updated_at = (
        as_shanghai(package.metadata.ended_at) if package.metadata is not None else discovered_at
    ).replace(microsecond=0)
    metadata: dict[str, object] | None
    if transcript.kind == "main":
        agent_id = package.session_id
        metadata = None
    else:
        if transcript.agent_id is None:
            raise ValueError("subagent transcript identity is missing")
        agent_id = transcript.agent_id
        metadata = {
            key: value
            for key, value in {
                "agentType": transcript.agent_type,
                "parentToolUseId": transcript.parent_tool_use_id,
            }.items()
            if value is not None
        }
    return LocalAgentPayload(
        root_session_id=package.session_id,
        agent_id=agent_id,
        agent_kind=transcript.kind,
        content=content,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        line_count=len(transcript.lines),
        agent_meta=metadata,
        source_updated_at=source_updated_at,
        discovered_at=discovered_at,
    )


def package_to_payloads(
    package: TrajectoryPackage,
    *,
    discovered_at: datetime | None = None,
) -> tuple[LocalAgentPayload, ...]:
    """Map main/child identities while preserving raw JSONL line order."""
    timestamp = as_shanghai(discovered_at or now_shanghai())
    return tuple(
        _transcript_payload(package, transcript, discovered_at=timestamp)
        for transcript in package.transcripts
    )
