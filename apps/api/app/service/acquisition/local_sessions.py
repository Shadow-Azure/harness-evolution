"""Discover and import development-only Claude Code session payloads."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel
from sqlalchemy.exc import SQLAlchemyError

from app.config import ServicePhase, Settings
from app.db.crud.local_sessions import (
    LocalImportWriteResult,
    list_local_session_keys,
    list_local_source_record_keys,
    write_local_payloads,
)
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.service.acquisition.agent_tree import (
    AgentTreeAggregate,
    assemble_agent_trees,
)
from app.service.acquisition.normalize import (
    NormalizationAggregate,
    ParsedTranscript,
    aggregate_transcripts,
    normalize_transcript,
)
from app.utils.time import as_shanghai

MAX_LOCAL_PAYLOAD_BYTES = 64 * 1024 * 1024
MAX_LOCAL_SOURCE_BYTES = 512 * 1024 * 1024
SESSION_ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SUBAGENT_PREFIX = "agent-"
MAX_AGENT_ID_LENGTH = 64


class LocalSessionSourceError(ValueError):
    """Stable local-session failure that never includes an absolute source path."""


class ClaudeSubagentMeta(BaseModel):
    """Closed metadata schema emitted beside a Claude subagent transcript."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        populate_by_name=True,
    )

    agent_type: str = Field(min_length=1, max_length=64)
    color: str | None = Field(default=None, max_length=64)
    description: str = Field(min_length=1, max_length=4_000)
    model: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=255)
    permission_mode: str | None = Field(default=None, max_length=64)
    plan_mode_required: bool | None = None
    request_non_interactive: bool | None = None
    request_shape: str | None = Field(default=None, max_length=128)
    spawn_depth: int = Field(ge=0)
    task_kind: str | None = Field(default=None, max_length=32)
    team_name: str | None = Field(default=None, max_length=128)
    tool_use_id: str | None = Field(default=None, max_length=128)


@dataclass(frozen=True, slots=True)
class LocalAgentPayload:
    """One raw JSONL payload plus provider and file-derived identity."""

    root_session_id: str
    agent_id: str
    agent_kind: Literal["main", "subagent"]
    content: str
    content_hash: str
    line_count: int
    agent_meta: dict[str, object] | None
    source_updated_at: datetime
    discovered_at: datetime


@dataclass(frozen=True, slots=True)
class LocalSessionCorpus:
    """A validated local source tree represented without source paths."""

    root_sessions: int
    jsonl_files: int
    subagents: int
    payloads: tuple[LocalAgentPayload, ...]
    total_bytes: int


@dataclass(frozen=True, slots=True)
class LocalImportResult:
    """Stable aggregate from one transactional local import."""

    status: Literal["imported"]
    root_sessions: int
    jsonl_files: int
    subagents: int
    payload_rows: int
    inserted_payloads: int
    updated_payloads: int
    unchanged_payloads: int
    inserted_source_records: int
    updated_source_records: int


@dataclass(frozen=True, slots=True)
class LocalVerificationResult:
    """Stable aggregate proving source and database identities agree."""

    status: Literal["verified"]
    root_sessions: int
    jsonl_files: int
    subagents: int
    payload_rows: int
    source_record_rows: int


def _reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate object keys instead of allowing silent overwrite."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise LocalSessionSourceError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_json_object(path: Path, *, label: str) -> dict[str, object]:
    """Read one closed metadata object without exposing source paths."""
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_json_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalSessionSourceError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise LocalSessionSourceError(f"{label} must be a JSON object")
    return value


def _jsonl_lines(content: str, *, label: str) -> list[str]:
    """Split JSONL framing only on LF, preserving Unicode JSON string content."""
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    lines = [line[:-1] if line.endswith("\r") else line for line in lines]
    if not lines or any(not line.strip() for line in lines):
        raise LocalSessionSourceError(f"{label} must contain non-empty JSONL lines")
    return lines


def _read_payload(path: Path, *, label: str) -> tuple[str, str, int, int]:
    """Return raw text, digest, non-empty line count, and byte size."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise LocalSessionSourceError(f"{label} could not be read") from exc
    if not data:
        raise LocalSessionSourceError(f"{label} is empty")
    if len(data) > MAX_LOCAL_PAYLOAD_BYTES:
        raise LocalSessionSourceError(f"{label} exceeds the per-file size limit")
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LocalSessionSourceError(f"{label} is not UTF-8") from exc
    lines = _jsonl_lines(content, label=label)
    return content, hashlib.sha256(data).hexdigest(), len(lines), len(data)


def _jsonl_objects(path: Path, *, label: str) -> tuple[list[dict[str, object]], str]:
    """Parse all JSONL objects while preserving raw text for storage."""
    content, _digest, _count, _size = _read_payload(path, label=label)
    values: list[dict[str, object]] = []
    for line in _jsonl_lines(content, label=label):
        try:
            value = json.loads(line, object_pairs_hook=_reject_duplicate_json_keys)
        except (json.JSONDecodeError, LocalSessionSourceError) as exc:
            raise LocalSessionSourceError(f"{label} is not valid JSONL") from exc
        if not isinstance(value, dict):
            raise LocalSessionSourceError(f"{label} JSONL lines must be objects")
        values.append(value)
    return values, content


def _source_updated_at(path: Path) -> datetime:
    """Use the provider write time as the payload update timestamp."""
    try:
        modified = path.stat().st_mtime
    except OSError as exc:
        raise LocalSessionSourceError("local session timestamp could not be read") from exc
    return as_shanghai(datetime.fromtimestamp(modified, tz=UTC)).replace(microsecond=0)


def _validate_root_payload(
    path: Path,
    session_id: str,
    *,
    discovered_at: datetime,
) -> LocalAgentPayload:
    """Validate root transcript identity and build its main-agent payload."""
    values, content = _jsonl_objects(path, label="root transcript")
    declared = [value["sessionId"] for value in values if "sessionId" in value]
    if not declared:
        raise LocalSessionSourceError("root transcript does not declare sessionId")
    if any(value != session_id for value in declared):
        raise LocalSessionSourceError(
            "root transcript session id does not match filename",
        )
    data = content.encode("utf-8")
    return LocalAgentPayload(
        root_session_id=session_id,
        agent_id=session_id,
        agent_kind="main",
        content=content,
        content_hash=hashlib.sha256(data).hexdigest(),
        line_count=len(_jsonl_lines(content, label="root transcript")),
        agent_meta=None,
        source_updated_at=_source_updated_at(path),
        discovered_at=discovered_at,
    )


def _validate_subagent_pair(
    payload_path: Path,
    meta_path: Path,
    *,
    root_session_id: str,
    discovered_at: datetime,
) -> LocalAgentPayload:
    """Cross-check subagent JSONL identity, filename, and closed metadata."""
    expected_agent_id = payload_path.name.removeprefix(SUBAGENT_PREFIX).removesuffix(".jsonl")
    if not expected_agent_id:
        raise LocalSessionSourceError("subagent filename is missing an agent id")
    if len(expected_agent_id) > MAX_AGENT_ID_LENGTH:
        raise LocalSessionSourceError(
            f"subagent agent id exceeds {MAX_AGENT_ID_LENGTH} characters",
        )
    values, content = _jsonl_objects(payload_path, label="subagent transcript")
    for value in values:
        if value.get("sessionId") != root_session_id:
            raise LocalSessionSourceError("subagent session id does not match root directory")
        if value.get("agentId") != expected_agent_id:
            raise LocalSessionSourceError("subagent agent id does not match filename")
    raw_meta = _read_json_object(meta_path, label="subagent metadata")
    try:
        meta = ClaudeSubagentMeta.model_validate(raw_meta)
    except ValidationError as exc:
        raise LocalSessionSourceError("subagent metadata does not match the closed schema") from exc
    data = content.encode("utf-8")
    return LocalAgentPayload(
        root_session_id=root_session_id,
        agent_id=expected_agent_id,
        agent_kind="subagent",
        content=content,
        content_hash=hashlib.sha256(data).hexdigest(),
        line_count=len(_jsonl_lines(content, label="subagent transcript")),
        agent_meta=meta.model_dump(by_alias=True, exclude_none=True),
        source_updated_at=_source_updated_at(payload_path),
        discovered_at=discovered_at,
    )


def _ensure_unique(values: Iterable[object], label: str) -> None:
    seen: set[object] = set()
    for value in values:
        if value in seen:
            raise LocalSessionSourceError(f"duplicate {label}")
        seen.add(value)


def scan_local_sessions(source_root: Path) -> LocalSessionCorpus:
    """Discover a bounded Claude session tree without retaining source paths."""
    if source_root.is_symlink():
        raise LocalSessionSourceError("session source must not be a symlink")
    if not source_root.is_dir():
        raise LocalSessionSourceError("session source directory is missing")
    try:
        entries = list(source_root.iterdir())
    except OSError as exc:
        raise LocalSessionSourceError("session source directory could not be read") from exc
    try:
        tree_entries = list(source_root.rglob("*"))
    except OSError as exc:
        raise LocalSessionSourceError("session source could not be scanned") from exc
    if any(entry.is_symlink() for entry in tree_entries):
        raise LocalSessionSourceError("session source must not contain symlink entries")

    root_files = sorted(entry for entry in entries if entry.is_file() and entry.suffix == ".jsonl")
    if not root_files:
        raise LocalSessionSourceError("session source contains no root transcripts")

    root_ids = [path.stem for path in root_files]
    for session_id in root_ids:
        if not SESSION_ID_PATTERN.fullmatch(session_id):
            raise LocalSessionSourceError("root transcript filename is not a session id")
    _ensure_unique(root_ids, "root session id")

    payloads: list[LocalAgentPayload] = []
    subagent_count = 0
    total_bytes = 0
    discovered_at = as_shanghai(datetime.now(UTC))
    for root_file in root_files:
        root_payload = _validate_root_payload(
            root_file,
            root_file.stem,
            discovered_at=discovered_at,
        )
        payloads.append(root_payload)
        total_bytes += len(root_payload.content.encode("utf-8"))
        root_directory = source_root / root_file.stem
        if not root_directory.exists():
            continue
        subagents_directory = root_directory / "subagents"
        if not subagents_directory.exists():
            continue
        try:
            subagent_entries = sorted(subagents_directory.iterdir())
        except OSError as exc:
            raise LocalSessionSourceError(
                "subagent directory could not be read",
            ) from exc
        jsonl_paths = [
            entry for entry in subagent_entries if entry.is_file() and entry.name.endswith(".jsonl")
        ]
        meta_paths = [
            entry
            for entry in subagent_entries
            if entry.is_file() and entry.name.endswith(".meta.json")
        ]
        if len(jsonl_paths) != len(meta_paths):
            raise LocalSessionSourceError("subagent transcript and metadata counts differ")
        expected_meta = {
            payload: payload.with_name(payload.name.removesuffix(".jsonl") + ".meta.json")
            for payload in jsonl_paths
        }
        if set(meta_paths) != set(expected_meta.values()):
            raise LocalSessionSourceError("subagent transcript and metadata files do not pair")
        for payload_path in jsonl_paths:
            if not payload_path.name.startswith(SUBAGENT_PREFIX):
                raise LocalSessionSourceError("subagent transcript filename is invalid")
            payload = _validate_subagent_pair(
                payload_path,
                expected_meta[payload_path],
                root_session_id=root_file.stem,
                discovered_at=discovered_at,
            )
            payloads.append(payload)
            subagent_count += 1
            total_bytes += len(payload.content.encode("utf-8"))

    _ensure_unique(
        ((payload.root_session_id, payload.agent_id) for payload in payloads),
        "payload identity",
    )
    if total_bytes > MAX_LOCAL_SOURCE_BYTES:
        raise LocalSessionSourceError("session source exceeds the total size limit")
    payloads.sort(
        key=lambda payload: (
            payload.root_session_id,
            payload.agent_kind != "main",
            payload.agent_id,
        ),
    )
    return LocalSessionCorpus(
        root_sessions=len(root_ids),
        jsonl_files=len(root_files) + subagent_count,
        subagents=subagent_count,
        payloads=tuple(payloads),
        total_bytes=total_bytes,
    )


def _ensure_local_environment(settings: Settings) -> None:
    """Reject production and live targets before scanning or connecting."""
    if settings.production:
        raise LocalSessionSourceError("local session import refuses production")
    if settings.phase is ServicePhase.LIVE:
        raise LocalSessionSourceError("local session import refuses live")


async def import_local_sessions(
    settings: Settings,
    source_root: Path,
) -> LocalImportResult:
    """Validate all source bytes and import them in one database transaction."""
    _ensure_local_environment(settings)
    corpus = scan_local_sessions(source_root)
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        writes: LocalImportWriteResult = await write_local_payloads(database, corpus.payloads)
        return LocalImportResult(
            status="imported",
            root_sessions=corpus.root_sessions,
            jsonl_files=corpus.jsonl_files,
            subagents=corpus.subagents,
            payload_rows=len(corpus.payloads),
            inserted_payloads=writes.inserted_payloads,
            updated_payloads=writes.updated_payloads,
            unchanged_payloads=writes.unchanged_payloads,
            inserted_source_records=writes.inserted_source_records,
            updated_source_records=writes.updated_source_records,
        )
    finally:
        await database.dispose()


async def verify_local_sessions(
    settings: Settings,
    source_root: Path,
) -> LocalVerificationResult:
    """Prove that every validated source identity exists in the database."""
    _ensure_local_environment(settings)
    corpus = scan_local_sessions(source_root)
    database = create_database(settings)
    await database.start()
    try:
        try:
            payload_keys = await list_local_session_keys(database)
            source_keys = await list_local_source_record_keys(database)
        except SQLAlchemyError as exc:
            raise LocalSessionSourceError(
                "local session database is not initialized",
            ) from exc
        expected_keys = {(payload.root_session_id, payload.agent_id) for payload in corpus.payloads}
        if missing := expected_keys - payload_keys:
            raise LocalSessionSourceError(
                f"payload identities missing from database: {len(missing)}",
            )
        if missing := expected_keys - source_keys:
            raise LocalSessionSourceError(
                f"source-record identities missing from database: {len(missing)}",
            )
        return LocalVerificationResult(
            status="verified",
            root_sessions=corpus.root_sessions,
            jsonl_files=corpus.jsonl_files,
            subagents=corpus.subagents,
            payload_rows=len(expected_keys),
            source_record_rows=len(expected_keys),
        )
    finally:
        await database.dispose()


def normalize_local_sessions(
    settings: Settings,
    source_root: Path,
) -> NormalizationAggregate:
    """Parse every local payload and return aggregate-only statistics."""
    return aggregate_transcripts(normalize_local_transcripts(settings, source_root))


def normalize_local_transcripts(
    settings: Settings,
    source_root: Path,
) -> tuple[ParsedTranscript, ...]:
    """Parse every local payload without writing or retaining source paths."""
    _ensure_local_environment(settings)
    corpus = scan_local_sessions(source_root)
    return tuple(
        normalize_transcript(
            payload.content,
            root_session_id=payload.root_session_id,
            agent_id=payload.agent_id,
            agent_kind=payload.agent_kind,
            agent_meta=payload.agent_meta,
        )
        for payload in corpus.payloads
    )


def assemble_local_sessions(
    settings: Settings,
    source_root: Path,
) -> AgentTreeAggregate:
    """Assemble local trees and return stable aggregate-only verification."""
    return assemble_agent_trees(
        normalize_local_transcripts(settings, source_root),
    ).aggregate
