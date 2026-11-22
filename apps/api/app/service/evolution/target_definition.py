"""Freeze the Git definition selected by a workspace target configuration."""

import asyncio
from pathlib import Path, PurePosixPath
from typing import Protocol

from app.service.evolution.attribution_inputs import disk_id, file_digest, publish_directory
from app.service.evolution.target_content import TARGET_FILE_NAMES, target_content_unresolved
from app.third_party_api.git.content import GitContentUnavailable
from app.utils.definition import definition_file_hash
from app.utils.redaction import redact_text


class VersionedFileSource(Protocol):
    async def read_versioned_file(
        self, *, repo_url: str, sub_dir: str, ref: str, file_name: str
    ) -> tuple[str, str]: ...


class TargetDefinitions:
    def __init__(self, source: VersionedFileSource, root: Path):
        self.source = source
        self.root = root

    async def freeze(
        self, workspace: str, kind: str, repo: str, subdir: str, ref: str
    ) -> dict[str, str]:
        for name in TARGET_FILE_NAMES[kind]:
            try:
                commit, body = await self.source.read_versioned_file(
                    repo_url=repo, sub_dir=subdir, ref=ref, file_name=name
                )
            except GitContentUnavailable as exc:
                if exc.reason == "file_not_found":
                    continue
                raise target_content_unresolved(object_type=kind, reason=exc.reason) from exc
            digest = definition_file_hash(body)
            if digest is None:
                raise target_content_unresolved(object_type=kind, reason="empty_definition_body")
            key = file_digest(body)
            directory = self.root / disk_id(workspace) / "attribute_source" / key
            await asyncio.to_thread(publish_directory, directory, {"definition.md": body})
            if await asyncio.to_thread((directory / "definition.md").read_bytes) != body.encode():
                raise ValueError("stored target definition checksum mismatch")
            return {
                "commit": commit,
                "path": str(PurePosixPath(subdir) / name),
                "revision": f"digest:{digest}",
                "key": key,
                "preview": redact_text(body)[:500],
            }
        raise target_content_unresolved(object_type=kind, reason="file_not_found")
