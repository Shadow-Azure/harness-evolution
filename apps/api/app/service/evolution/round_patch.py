"""Restore durable round patch dictionaries into the shared bundle type.

The candidate writer persists a bundle as ``files[] / note / diff / intent /
report`` plus the legacy single-file keys when the bundle has one file. ``diff``
is the candidate commit's real unified diff, written after the commit succeeds;
older rows simply lack it and readers fall back to a neutral preview. Readers
must go through this module instead of validating the raw dictionary with a
closed model: the stored shape is the writer's concern, while each read surface
projects only the fields it exposes.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from app.service.evolution.patch_source import PLACEHOLDER_PATCH_NOTE, PatchBundle
from app.third_party_api.ai_agent.edits import EditPlan, EditStatus, EditStatusKind
from app.third_party_api.git.workspace import Patch


def stored_bundle(raw: object) -> PatchBundle | None:
    """Rebuild a persisted bundle, including the legacy single-file shape.

    A dictionary that carries a valid ``files`` list wins; otherwise the
    top-level ``file``/``lines`` pair is read as one legacy file. The result is
    ``None`` when no usable file entry remains, so a malformed row degrades to
    "no patch preview" instead of raising during a read.
    """
    if not isinstance(raw, Mapping):
        return None
    note = raw.get("note")
    if not isinstance(note, str) or not note.strip():
        note = PLACEHOLDER_PATCH_NOTE
    intent = _stored_intent(raw.get("intent"))
    report = _stored_report(raw.get("report"))
    diff = raw.get("diff")
    unified_diff = diff if isinstance(diff, str) else ""
    files: list[Patch] = []
    raw_files = raw.get("files")
    if isinstance(raw_files, list):
        for item in raw_files:
            patch = _stored_patch_file(item)
            if patch is not None:
                files.append(patch)
    if not files:
        legacy = _stored_patch_file(raw)
        if legacy is not None:
            files.append(legacy)
    if not files:
        return None
    try:
        return PatchBundle(
            files=tuple(files),
            note=note,
            intent=intent,
            report=report,
            unified_diff=unified_diff,
        )
    except ValueError:
        return None


def _stored_patch_file(raw: object) -> Patch | None:
    """Rebuild one Patch from a stored mapping, rejecting malformed entries."""
    if not isinstance(raw, Mapping):
        return None
    file = raw.get("file")
    lines = raw.get("lines")
    if not isinstance(file, str) or not file:
        return None
    if not isinstance(lines, (list, tuple)):
        return None
    overwrite = raw.get("overwrite", False)
    return Patch(
        file=file,
        lines=tuple(line for line in lines if isinstance(line, str)),
        overwrite=bool(overwrite),
    )


def _stored_intent(raw: object) -> EditPlan | None:
    """Rebuild the persisted EditPlan when it is present and valid."""
    if not isinstance(raw, Mapping):
        return None
    try:
        return EditPlan.model_validate(dict(raw))
    except ValueError:
        return None


def _stored_report(raw: object) -> tuple[EditStatus, ...]:
    """Rebuild the persisted per-edit report when it is present and valid."""
    if not isinstance(raw, list):
        return ()
    statuses: list[EditStatus] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        try:
            statuses.append(
                EditStatus(
                    index=int(item["index"]),
                    op=str(item["op"]),
                    file=str(item["file"]),
                    status=cast("EditStatusKind", str(item["status"])),
                    message=str(item.get("message", "")),
                ),
            )
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(statuses)
