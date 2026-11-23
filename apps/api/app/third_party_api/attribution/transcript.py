"""Extract visible turns from the main session in the disposable Claude home."""

import json
import os
import stat
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID

_LIMIT = 8 * 1024 * 1024


@contextmanager
def _directory(name: str | Path, parent: int | None = None) -> Iterator[int]:
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        yield fd
    finally:
        os.close(fd)


def _session_bytes(work: Path, session_id: str) -> bytes | None:
    """Read only a regular, private session file; never follow agent-created links."""
    filename = f"{UUID(session_id)}.jsonl"
    with ExitStack() as stack:
        parent = stack.enter_context(_directory(work))
        for name in ("home", ".claude", "projects"):
            parent = stack.enter_context(_directory(name, parent))
        with os.scandir(parent) as projects:
            for project in projects:
                if not project.is_dir(follow_symlinks=False):
                    continue
                with _directory(project.name, parent) as directory:
                    try:
                        fd = os.open(
                            filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
                        )
                    except FileNotFoundError:
                        continue
                    with os.fdopen(fd, "rb") as source:
                        metadata = os.fstat(fd)
                        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
                            return source.read(_LIMIT + 1)
    return None


def _visible(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return []
    visible = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            visible.append({"type": kind, "text": block.get("text")})
        elif kind == "tool_use":
            visible.append({key: block.get(key) for key in ("type", "id", "name", "input")})
        elif kind == "tool_result":
            visible.append(
                {
                    "type": kind,
                    "toolUseId": block.get("tool_use_id"),
                    "isError": block.get("is_error", False),
                    "content": _visible(block.get("content")),
                }
            )
    return visible


def read_transcript(work: Path, session_id: str) -> dict[str, Any]:
    try:
        raw = _session_bytes(work, session_id)
    except (ValueError, OSError):
        raw = None
    if raw is None:
        return {"status": "unavailable", "turns": []}
    partial = len(raw) > _LIMIT
    turns = []
    for line in raw[:_LIMIT].splitlines():
        try:
            record = json.loads(line)
        except (ValueError, RecursionError):
            partial = True
            continue
        if not isinstance(record, dict) or record.get("type") not in ("user", "assistant"):
            continue
        message = record.get("message")
        if isinstance(message, dict) and (content := _visible(message.get("content"))):
            turns.append(
                {"role": record["type"], "timestamp": record.get("timestamp"), "content": content}
            )
    return {"status": "partial" if partial else "available", "turns": turns}
