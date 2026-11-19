"""Resolve a selected target version into the normalized body-hash revision.

The wizard stores a tag (or a knowledge document revision) as the version a
human selected. Session association and cache keys need the *content* identity:
``sha256(normalize_definition_body(body))`` computed with the same normalizer the
trace parser uses. This module owns that resolution and its bounded cache.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Literal, Protocol

from app.errors import AppError, ErrorCode
from app.third_party_api.git.content import GitContentUnavailable
from app.utils.definition import definition_file_hash, definition_hash

TargetObjectType = Literal["skill", "agent", "knowledge"]

TARGET_FILE_NAMES: dict[str, tuple[str, ...]] = {
    "skill": ("SKILL.md",),
    "agent": ("AGENT.md", "agent.md"),
}
"""Repository-relative definition files; agent.md is accepted for mixed-case repos."""


DEFAULT_CACHE_SIZE = 256
"""Bounded in-process cache of resolved digests."""

DEFAULT_TIMEOUT_SECONDS = 20.0
"""Upper bound for one content read, independent of the git process timeout."""


@dataclass(frozen=True, slots=True)
class ResolvedTargetVersion:
    """The user-facing version and the body-hash revision derived from it."""

    target_version: str
    target_revision: str


class TargetContentSource(Protocol):
    """Read-only git content seam used for skill and agent definitions."""

    async def read_file(
        self,
        *,
        repo_url: str,
        sub_dir: str,
        ref: str,
        file_name: str,
    ) -> str:
        """Return one file body at ``ref`` or raise a classified failure."""


class KnowledgeContentSource(Protocol):
    """Read-only document seam used for bare knowledge revisions."""

    async def read_document(
        self,
        *,
        repo_url: str,
        sub_dir: str,
        revision: str,
    ) -> str | None:
        """Return the document body for one revision, or ``None`` when absent."""


class TargetVersionResolver(Protocol):
    """Resolve one selected version into its persisted revision identity."""

    async def resolve(
        self,
        *,
        object_type: str,
        repo_url: str,
        sub_dir: str,
        version: str,
    ) -> ResolvedTargetVersion:
        """Return the version and the body-hash revision for a target."""
        ...


def target_content_unresolved(
    *,
    object_type: str,
    reason: str,
) -> AppError:
    """Return the stable 422 for target content that cannot be read as-is."""
    return AppError(
        status_code=422,
        code=ErrorCode.TARGET_CONTENT_UNRESOLVED,
        message="target content could not be resolved to a body hash",
        details={"targetType": object_type, "reason": reason},
    )


def prefixed_revision(value: str) -> bool:
    """Return whether a value already carries a normalized revision prefix."""
    return value.startswith(("tag:", "digest:", "provider:"))


def _unsafe_ref(value: str) -> bool:
    """Reject a git ref that could be parsed as an option or spans lines."""
    return value.startswith("-") or any(
        character.isspace() or ord(character) < 0x20 for character in value
    )


class TargetContentResolver:
    """Resolve skill/agent/knowledge targets through cached content reads."""

    def __init__(
        self,
        content: TargetContentSource,
        *,
        knowledge: KnowledgeContentSource | None = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Bind the content seams, cache bound, and read timeout."""
        if cache_size < 0:
            raise ValueError("cache_size cannot be negative")
        self._content = content
        self._knowledge = knowledge
        self._cache_size = cache_size
        self._timeout_seconds = timeout_seconds
        self._cache: OrderedDict[tuple[str, str, str, str], ResolvedTargetVersion] = OrderedDict()

    async def resolve(
        self,
        *,
        object_type: str,
        repo_url: str,
        sub_dir: str,
        version: str,
    ) -> ResolvedTargetVersion:
        """Resolve one target version, using content only for bare versions.

        A value already carrying ``tag:`` / ``digest:`` / ``provider:`` keeps
        its documented revision semantics and is never re-read. Bare skill and
        agent tags are content sources; a bare knowledge revision is read
        through the configured document seam.
        """
        value = version.strip()
        if not value:
            raise AppError(
                status_code=422,
                code=ErrorCode.VALIDATION_INVALID,
                message="target version is required",
            )
        if prefixed_revision(value):
            return ResolvedTargetVersion(value, value)
        key = (object_type, repo_url, sub_dir, value)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached
        resolved = await self._resolve_content(
            object_type=object_type,
            repo_url=repo_url,
            sub_dir=sub_dir,
            version=value,
        )
        self._remember(key, resolved)
        return resolved

    async def _resolve_content(
        self,
        *,
        object_type: str,
        repo_url: str,
        sub_dir: str,
        version: str,
    ) -> ResolvedTargetVersion:
        """Read the configured content and derive its normalized digest."""
        if object_type == "knowledge":
            if self._knowledge is None:
                raise target_content_unresolved(
                    object_type=object_type,
                    reason="knowledge_content_source_unavailable",
                )
            content = await self._bounded(
                self._knowledge.read_document(
                    repo_url=repo_url,
                    sub_dir=sub_dir,
                    revision=version,
                ),
                object_type=object_type,
            )
            if content is None:
                raise target_content_unresolved(
                    object_type=object_type,
                    reason="content_not_found",
                )
            digest = definition_hash(content)
            if digest is None:
                raise target_content_unresolved(
                    object_type=object_type,
                    reason="empty_definition_body",
                )
            return ResolvedTargetVersion(version, f"digest:{digest}")

        file_names = TARGET_FILE_NAMES.get(object_type)
        if not file_names:
            raise target_content_unresolved(
                object_type=object_type,
                reason="unsupported_object_type",
            )
        if _unsafe_ref(version):
            raise target_content_unresolved(
                object_type=object_type,
                reason="ref_invalid",
            )
        content: str | None = None
        for file_name in file_names:
            try:
                content = await self._bounded(
                    self._content.read_file(
                        repo_url=repo_url,
                        sub_dir=sub_dir,
                        ref=version,
                        file_name=file_name,
                    ),
                    object_type=object_type,
                )
                break
            except AppError as error:
                # Only try the next casing for a genuinely missing file.
                if (
                    len(file_names) > 1
                    and file_name != file_names[-1]
                    and error.details.get("reason") == "file_not_found"
                ):
                    continue
                raise
        if content is None:
            raise target_content_unresolved(
                object_type=object_type,
                reason="content_not_found",
            )
        # Skill/Agent files carry YAML frontmatter that the trace never sees.
        digest = definition_file_hash(content)
        if digest is None:
            raise target_content_unresolved(
                object_type=object_type,
                reason="empty_definition_body",
            )
        return ResolvedTargetVersion(version, f"digest:{digest}")

    async def _bounded(
        self,
        operation: Awaitable[str | None],
        *,
        object_type: str,
    ) -> str | None:
        """Await one content read under a timeout and stable failure mapping."""
        try:
            return await asyncio.wait_for(operation, timeout=self._timeout_seconds)
        except TimeoutError:
            raise target_content_unresolved(
                object_type=object_type,
                reason="content_timeout",
            ) from None
        except AppError:
            raise
        except GitContentUnavailable as error:
            raise target_content_unresolved(
                object_type=object_type,
                reason=error.reason,
            ) from None
        except (OSError, RuntimeError):
            raise target_content_unresolved(
                object_type=object_type,
                reason="content_unavailable",
            ) from None
        except Exception:
            raise target_content_unresolved(
                object_type=object_type,
                reason="content_read_failed",
            ) from None

    def _remember(
        self,
        key: tuple[str, str, str, str],
        resolved: ResolvedTargetVersion,
    ) -> None:
        """Store one successful resolution inside the bounded cache."""
        if self._cache_size == 0:
            return
        self._cache[key] = resolved
        self._cache.move_to_end(key)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)

    def clear_cache(self) -> None:
        """Drop every cached resolution; used by tests and configuration changes."""
        self._cache.clear()


def resolve_legacy_target_version(value: str) -> ResolvedTargetVersion:
    """Resolve a prefixed digest/tag/provider value without a content read.

    Historical runs and tests that predate the content resolver keep their
    stored identity: a prefixed value is used as-is, and a bare value is treated
    as a git tag revision. New launches must call
    :class:`TargetContentResolver` instead so skill/agent tags become body hashes.
    """
    normalized = value.strip()
    if prefixed_revision(normalized):
        return ResolvedTargetVersion(normalized, normalized)
    return ResolvedTargetVersion(normalized, f"tag:{normalized}")
