"""Deterministic target version resolver shared by HTTP-level test fixtures."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Literal

from app.service.evolution.target_content import ResolvedTargetVersion


class FakeTargetVersionResolver:
    """Resolve every bare version without content I/O.

    The default keeps the legacy ``tag:`` identity so preview and launch
    fixtures can focus on route semantics. Tests that exercise the body-hash
    path pass ``revision="digest"``.
    """

    def __init__(
        self,
        *,
        revision: Literal["tag", "digest"] = "tag",
        revisions: Mapping[str, str] | None = None,
    ) -> None:
        """Choose the identity form, with per-version overrides for fixtures."""
        self._revision = revision
        self._revisions = dict(revisions or {})
        self.calls: list[tuple[str, str, str, str]] = []

    async def resolve(
        self,
        *,
        object_type: str,
        repo_url: str,
        sub_dir: str,
        version: str,
    ) -> ResolvedTargetVersion:
        """Return a stable revision so fixtures never touch a real repository."""
        self.calls.append((object_type, repo_url, sub_dir, version))
        if version.startswith(("tag:", "digest:", "provider:")):
            return ResolvedTargetVersion(version, version)
        if version in self._revisions:
            return ResolvedTargetVersion(version, self._revisions[version])
        if self._revision == "tag":
            return ResolvedTargetVersion(version, f"tag:{version}")
        digest = hashlib.sha256(version.encode("utf-8")).hexdigest()
        return ResolvedTargetVersion(version, f"digest:{digest}")


class FakeDefinitionSource:
    body = "# Deep research\nAlways inspect the evidence."

    async def read_versioned_file(
        self, *, repo_url: str, sub_dir: str, ref: str, file_name: str
    ) -> tuple[str, str]:
        return "a" * 40, self.body
