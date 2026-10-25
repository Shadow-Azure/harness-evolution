"""Root-atomic, idempotent replay from raw payloads to canonical tree rows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from app.config import Settings
from app.db.base import Database
from app.db.crud.acquisition_replay import (
    PendingPayload,
    RootPayload,
    count_payloads,
    create_sync_run,
    finish_sync_run,
    list_missing_payload_sources,
    list_pending_payloads,
    list_root_payloads,
    replace_normalized_root,
)
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.service.acquisition.agent_tree import assemble_agent_trees
from app.service.acquisition.local_sessions import (
    import_local_sessions,
    scan_local_sessions,
)
from app.service.acquisition.normalize import (
    CURRENT_PARSER_VERSION,
    ParsedIssue,
    ParsedTranscript,
    normalize_transcript,
)
from app.utils.ids import new_id
from app.utils.time import now_shanghai


@dataclass(frozen=True, slots=True)
class ReplayResult:
    """Privacy-safe counts from one pending-payload replay batch."""

    status: str
    sync_run_id: str
    root_sessions: int
    payloads: int
    imported: int
    skipped: int
    failed: int
    errors: int


@dataclass(frozen=True, slots=True)
class LocalReplayResult:
    """Aggregate-only result for importing and replaying local payloads."""

    status: str
    sync_run_id: str
    root_sessions: int
    jsonl_files: int
    subagents: int
    payloads: int
    imported: int
    skipped: int
    failed: int
    errors: int


def _normalize_payload(payload: RootPayload) -> ParsedTranscript:
    """Normalize one stored payload without retaining message detail."""
    return normalize_transcript(
        payload.payload,
        root_session_id=payload.root_session_id,
        agent_id=payload.agent_id,
        agent_kind=cast(Literal["main", "subagent"], payload.agent_kind),
        agent_meta=payload.agent_meta,
    )


def _issue_record(
    root_session_id: str,
    agent_id: str,
    code: str,
    message: str,
) -> dict[str, object]:
    """Build one stable storage issue for a failed root boundary."""
    return ParsedIssue(
        session_id=root_session_id,
        agent_id=agent_id,
        line_no=0,
        code=code,
        message=message,
    ).as_sync_error()


async def replay_pending_payloads(
    database: Database,
    *,
    parser_version: int = CURRENT_PARSER_VERSION,
    on_progress: Callable[[int, int], Awaitable[None]] | None = None,
    sync_run_id: str | None = None,
) -> ReplayResult:
    """Replay every pending root atomically and return aggregate-only counts."""
    pending = await list_pending_payloads(database, parser_version)
    total_payloads = await count_payloads(database)
    started_at = now_shanghai()
    resolved_sync_run_id = sync_run_id or new_id()
    await create_sync_run(
        database,
        sync_run_id=resolved_sync_run_id,
        source_type=pending[0].source_type if pending else "script",
        started_at=started_at,
        records_total=total_payloads,
    )

    grouped: dict[str, list[PendingPayload]] = {}
    for payload in pending:
        grouped.setdefault(payload.root_session_id, []).append(payload)

    missing_sources = await list_missing_payload_sources(database)
    missing_by_root: dict[str, list[str]] = {}
    for source in missing_sources:
        missing_by_root.setdefault(source.root_session_id, []).append(source.agent_id)

    imported = 0
    failed = 0
    errors: list[dict[str, object]] = [
        _issue_record(
            source.root_session_id,
            source.agent_id,
            "MISSING_PAYLOAD_SOURCE",
            "Source payload no longer exists",
        )
        for source in missing_sources
    ]
    rebuilt_roots = 0
    processed_candidates = 0
    progress_callback = on_progress

    async def notify_progress(
        root_session_id: str,
        agent_id: str,
        done: int,
    ) -> None:
        nonlocal progress_callback
        if progress_callback is None:
            return
        try:
            await progress_callback(done, len(pending))
        except Exception:
            errors.append(
                _issue_record(
                    root_session_id,
                    agent_id,
                    "SYNC_PROGRESS_FAILED",
                    "Replay progress notification failed",
                ),
            )
            progress_callback = None

    for root_session_id in sorted(grouped):
        root_pending = tuple(grouped[root_session_id])
        if root_session_id in missing_by_root:
            failed += len(root_pending)
            processed_candidates += len(root_pending)
            await notify_progress(
                root_session_id,
                root_pending[0].agent_id,
                processed_candidates,
            )
            continue
        try:
            payloads = await list_root_payloads(database, root_session_id)
            parsed = tuple(_normalize_payload(payload) for payload in payloads)
            assembled = assemble_agent_trees(parsed)
            root_issues = [_issue.as_sync_error() for _issue in assembled.issues]
            if not assembled.trees:
                if not root_issues:
                    root_issues.append(
                        _issue_record(
                            root_session_id,
                            root_pending[0].agent_id,
                            "ROOT_ASSEMBLY_FAILED",
                            "Root session could not be assembled",
                        ),
                    )
                errors.extend(root_issues)
                failed += len(root_pending)
                processed_candidates += len(root_pending)
                await notify_progress(
                    root_session_id,
                    root_pending[0].agent_id,
                    processed_candidates,
                )
                continue
            if len(assembled.trees) != 1:
                errors.append(
                    _issue_record(
                        root_session_id,
                        root_pending[0].agent_id,
                        "ROOT_ASSEMBLY_AMBIGUOUS",
                        "Root replay produced an ambiguous session identity",
                    ),
                )
                failed += len(root_pending)
                processed_candidates += len(root_pending)
                await notify_progress(
                    root_session_id,
                    root_pending[0].agent_id,
                    processed_candidates,
                )
                continue
            await replace_normalized_root(
                database,
                tree=assembled.trees[0],
                payloads=payloads,
                pending_agent_ids=frozenset(payload.agent_id for payload in root_pending),
                parser_version=parser_version,
                sync_run_id=resolved_sync_run_id,
                completed_at=now_shanghai(),
            )
        except Exception:
            errors.append(
                _issue_record(
                    root_session_id,
                    root_pending[0].agent_id,
                    "ROOT_REPLAY_FAILED",
                    "Root session replay failed",
                ),
            )
            failed += len(root_pending)
            processed_candidates += len(root_pending)
            await notify_progress(
                root_session_id,
                root_pending[0].agent_id,
                processed_candidates,
            )
            continue
        errors.extend(root_issues)
        imported += len(root_pending)
        processed_candidates += len(root_pending)
        rebuilt_roots += 1
        await notify_progress(
            root_session_id,
            root_pending[0].agent_id,
            processed_candidates,
        )

    skipped = max(0, total_payloads - len(pending))
    await finish_sync_run(
        database,
        sync_run_id=resolved_sync_run_id,
        finished_at=now_shanghai(),
        records_done=imported + skipped + failed,
        imported=imported,
        skipped=skipped,
        errors=errors,
    )
    return ReplayResult(
        status="completed",
        sync_run_id=resolved_sync_run_id,
        root_sessions=rebuilt_roots,
        payloads=total_payloads,
        imported=imported,
        skipped=skipped,
        failed=failed,
        errors=len(errors),
    )


async def replay_local_payloads(
    settings: Settings,
    source_root: Path,
) -> LocalReplayResult:
    """Import current local files, replay pending roots, and emit safe aggregates."""
    imported_files = await import_local_sessions(settings, source_root)
    corpus = scan_local_sessions(source_root)
    database = create_database(settings)
    await database.start()
    try:
        await upgrade_database(database)
        result = await replay_pending_payloads(database)
    finally:
        await database.dispose()
    return LocalReplayResult(
        status=result.status,
        sync_run_id=result.sync_run_id,
        root_sessions=result.root_sessions,
        jsonl_files=imported_files.jsonl_files,
        subagents=corpus.subagents,
        payloads=result.payloads,
        imported=result.imported,
        skipped=result.skipped,
        failed=result.failed,
        errors=result.errors,
    )
