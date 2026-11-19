"""Target content resolver: tag -> normalized body hash, cache, and errors."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from app.errors import AppError, ErrorCode
from app.service.evolution.target_content import (
    ResolvedTargetVersion,
    TargetContentResolver,
)
from app.third_party_api.git.content import SubprocessGitContent
from app.utils.definition import definition_hash

SKILL_BODY = "# Systematic debugging\n\nReproduce before fixing.\n"
AGENT_BODY = "# Reviewer\n\nCheck the evidence trail.\n"
KNOWLEDGE_BODY = "# Runbook\n\nRestart the worker.\n"
ROOT_BODY = "# Root skill\n\nRoot body.\n"
DOT_BODY = "# Dot skill\n\nDot body.\n"
PLAIN_BODY = "# Plain skill\n\nPlain body.\n"


def _git(repo: Path, *args: str) -> None:
    """Run one deterministic local git command with a fixed identity."""
    git = shutil.which("git")
    assert git is not None
    subprocess.run(  # noqa: S603 - argv is fixed and the binary is repository tooling
        (
            git,
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            *args,
        ),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _commit_fixture(repo: Path) -> None:
    """Create one commit with a Skill, an Agent, and a tag."""
    (repo / "skills" / "systematic-debugging").mkdir(parents=True)
    (repo / "agents" / "reviewer").mkdir(parents=True)
    (repo / "skills" / "systematic-debugging" / "SKILL.md").write_text(
        SKILL_BODY,
        encoding="utf-8",
    )
    (repo / "agents" / "reviewer" / "AGENT.md").write_text(
        AGENT_BODY,
        encoding="utf-8",
    )
    (repo / "SKILL.md").write_text(ROOT_BODY, encoding="utf-8")
    (repo / ".claude" / "skills" / "dot").mkdir(parents=True)
    (repo / ".claude" / "skills" / "dot" / "SKILL.md").write_text(
        DOT_BODY,
        encoding="utf-8",
    )
    (repo / "claude" / "skills" / "dot").mkdir(parents=True)
    (repo / "claude" / "skills" / "dot" / "SKILL.md").write_text(
        PLAIN_BODY,
        encoding="utf-8",
    )
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "fixture")
    _git(repo, "tag", "v1.0.0")


class CountingContent:
    """Count content reads so the resolver cache can be asserted."""

    def __init__(self, inner: SubprocessGitContent) -> None:
        """Wrap one real git content source."""
        self._inner = inner
        self.calls: list[tuple[str, str, str, str]] = []

    async def read_file(
        self,
        *,
        repo_url: str,
        sub_dir: str,
        ref: str,
        file_name: str,
    ) -> str:
        """Delegate and record one read."""
        self.calls.append((repo_url, sub_dir, ref, file_name))
        return await self._inner.read_file(
            repo_url=repo_url,
            sub_dir=sub_dir,
            ref=ref,
            file_name=file_name,
        )


class FakeKnowledgeContent:
    """Return a configured document body or nothing."""

    def __init__(self, documents: dict[str, str]) -> None:
        """Bind revision-keyed document bodies."""
        self._documents = documents
        self.calls: list[tuple[str, str, str]] = []

    async def read_document(
        self,
        *,
        repo_url: str,
        sub_dir: str,
        revision: str,
    ) -> str | None:
        """Return one document body and record the read."""
        self.calls.append((repo_url, sub_dir, revision))
        return self._documents.get(revision)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Create a local git repository carrying Skill and Agent definitions."""
    path = tmp_path / "source"
    path.mkdir()
    _commit_fixture(path)
    return path


def _resolver(
    tmp_path: Path,
    *,
    knowledge: FakeKnowledgeContent | None = None,
) -> tuple[TargetContentResolver, CountingContent]:
    """Bind a resolver over a real local git source and an optional document source."""
    counting = CountingContent(
        SubprocessGitContent(cache_root=tmp_path / "content-cache"),
    )
    return (
        TargetContentResolver(counting, knowledge=knowledge),
        counting,
    )


async def test_skill_and_agent_tags_resolve_to_normalized_body_hash(
    tmp_path: Path,
    repo: Path,
) -> None:
    """Tag content is normalized exactly like the parser before hashing."""
    resolver, _ = _resolver(tmp_path)

    skill = await resolver.resolve(
        object_type="skill",
        repo_url=str(repo),
        sub_dir="skills/systematic-debugging",
        version="v1.0.0",
    )
    agent = await resolver.resolve(
        object_type="agent",
        repo_url=str(repo),
        sub_dir="agents/reviewer",
        version="v1.0.0",
    )

    assert skill == ResolvedTargetVersion(
        "v1.0.0",
        f"digest:{definition_hash(SKILL_BODY)}",
    )
    assert agent == ResolvedTargetVersion(
        "v1.0.0",
        f"digest:{definition_hash(AGENT_BODY)}",
    )


async def test_resolution_is_cached_per_repo_subdir_and_ref(
    tmp_path: Path,
    repo: Path,
) -> None:
    """A repeated resolution reuses the body hash without another content read."""
    resolver, counting = _resolver(tmp_path)

    first = await resolver.resolve(
        object_type="skill",
        repo_url=str(repo),
        sub_dir="skills/systematic-debugging",
        version="v1.0.0",
    )
    second = await resolver.resolve(
        object_type="skill",
        repo_url=str(repo),
        sub_dir="skills/systematic-debugging",
        version="v1.0.0",
    )

    assert first == second
    assert len(counting.calls) == 1


async def test_dot_directories_and_repo_root_are_preserved(
    tmp_path: Path,
    repo: Path,
) -> None:
    """A leading dot is part of the path; '.' means the repository root."""
    resolver, _ = _resolver(tmp_path)

    dot = await resolver.resolve(
        object_type="skill",
        repo_url=str(repo),
        sub_dir=".claude/skills/dot",
        version="v1.0.0",
    )
    root = await resolver.resolve(
        object_type="skill",
        repo_url=str(repo),
        sub_dir=".",
        version="v1.0.0",
    )
    plain = await resolver.resolve(
        object_type="skill",
        repo_url=str(repo),
        sub_dir="claude/skills/dot",
        version="v1.0.0",
    )

    assert dot.target_revision == f"digest:{definition_hash(DOT_BODY)}"
    assert root.target_revision == f"digest:{definition_hash(ROOT_BODY)}"
    assert plain.target_revision == f"digest:{definition_hash(PLAIN_BODY)}"
    assert dot.target_revision != plain.target_revision


async def test_absolute_and_parent_paths_are_rejected(
    tmp_path: Path,
    repo: Path,
) -> None:
    """Path traversal and absolute subdirectories never reach git."""
    resolver, _ = _resolver(tmp_path)

    for sub_dir in ("/absolute", "../escape", "skills/../../escape"):
        with pytest.raises(AppError) as error:
            await resolver.resolve(
                object_type="skill",
                repo_url=str(repo),
                sub_dir=sub_dir,
                version="v1.0.0",
            )
        assert error.value.code is ErrorCode.TARGET_CONTENT_UNRESOLVED
        assert error.value.details["reason"] == "path_invalid"


async def test_concurrent_resolutions_share_one_mirror(
    tmp_path: Path,
    repo: Path,
) -> None:
    """Concurrent overview reads must not race create/delete the mirror cache."""
    resolver, _ = _resolver(tmp_path)

    first, second = await asyncio.gather(
        resolver.resolve(
            object_type="skill",
            repo_url=str(repo),
            sub_dir="skills/systematic-debugging",
            version="v1.0.0",
        ),
        resolver.resolve(
            object_type="skill",
            repo_url=str(repo),
            sub_dir="skills/systematic-debugging",
            version="v1.0.0",
        ),
    )

    assert first == second
    assert first.target_revision == f"digest:{definition_hash(SKILL_BODY)}"


async def test_branch_and_commit_refs_resolve_to_the_same_body_hash(
    tmp_path: Path,
    repo: Path,
) -> None:
    """A branch and the commit it points at are both valid content sources."""
    resolver, _ = _resolver(tmp_path)
    git = shutil.which("git")
    assert git is not None
    commit = (
        await asyncio.to_thread(
            subprocess.run,
            (git, "-C", str(repo), "rev-parse", "HEAD"),
            check=True,
            capture_output=True,
            text=True,
        )
    ).stdout.strip()

    branch = await resolver.resolve(
        object_type="skill",
        repo_url=str(repo),
        sub_dir="skills/systematic-debugging",
        version="main",
    )
    by_commit = await resolver.resolve(
        object_type="skill",
        repo_url=str(repo),
        sub_dir="skills/systematic-debugging",
        version=commit,
    )

    assert branch.target_version == "main"
    assert by_commit.target_version == commit
    assert branch.target_revision == by_commit.target_revision
    assert branch.target_revision == f"digest:{definition_hash(SKILL_BODY)}"


async def test_missing_ref_returns_ref_not_found(
    tmp_path: Path,
    repo: Path,
) -> None:
    """A branch or commit absent from the repository never falls back to a tag."""
    resolver, _ = _resolver(tmp_path)

    with pytest.raises(AppError) as error:
        await resolver.resolve(
            object_type="skill",
            repo_url=str(repo),
            sub_dir="skills/systematic-debugging",
            version="feature/does-not-exist",
        )

    assert error.value.code is ErrorCode.TARGET_CONTENT_UNRESOLVED
    assert error.value.status_code == 422
    assert error.value.details["reason"] == "ref_not_found"


async def test_prefixed_revisions_never_read_content(tmp_path: Path) -> None:
    """Digest/tag/provider inputs keep their documented identity semantics."""
    resolver, counting = _resolver(tmp_path)

    for value in ("digest:" + "a" * 64, "tag:v1.0.0", "provider:2026.11"):
        resolved = await resolver.resolve(
            object_type="skill",
            repo_url="https://example.invalid/repo.git",
            sub_dir="skills/example",
            version=value,
        )
        assert resolved == ResolvedTargetVersion(value, value)

    assert counting.calls == []


async def test_knowledge_document_content_becomes_a_body_hash(tmp_path: Path) -> None:
    """A bare knowledge revision is read and normalized into a digest revision."""
    knowledge = FakeKnowledgeContent({"2026.11": KNOWLEDGE_BODY})
    resolver, _ = _resolver(tmp_path, knowledge=knowledge)

    resolved = await resolver.resolve(
        object_type="knowledge",
        repo_url="knowledge://provider",
        sub_dir="runbooks",
        version="2026.11",
    )

    assert resolved == ResolvedTargetVersion(
        "2026.11",
        f"digest:{definition_hash(KNOWLEDGE_BODY)}",
    )
    assert knowledge.calls == [("knowledge://provider", "runbooks", "2026.11")]


async def test_missing_content_returns_target_content_unresolved(
    tmp_path: Path,
    repo: Path,
) -> None:
    """A missing file or document is a stable 422, never a tag fallback."""
    resolver, _ = _resolver(tmp_path)

    with pytest.raises(AppError) as missing:
        await resolver.resolve(
            object_type="skill",
            repo_url=str(repo),
            sub_dir="skills/missing",
            version="v1.0.0",
        )
    assert missing.value.code is ErrorCode.TARGET_CONTENT_UNRESOLVED
    assert missing.value.status_code == 422

    with pytest.raises(AppError) as no_source:
        await resolver.resolve(
            object_type="knowledge",
            repo_url="knowledge://provider",
            sub_dir="runbooks",
            version="2026.11",
        )
    assert no_source.value.code is ErrorCode.TARGET_CONTENT_UNRESOLVED
    assert no_source.value.details["reason"] == "knowledge_content_source_unavailable"


async def test_unknown_object_type_is_unresolved(tmp_path: Path) -> None:
    """An unsupported object type never guesses a definition file."""
    resolver, _ = _resolver(tmp_path)

    with pytest.raises(AppError) as error:
        await resolver.resolve(
            object_type="workflow",
            repo_url="https://example.invalid/repo.git",
            sub_dir="workflows/example",
            version="v1.0.0",
        )
    assert error.value.code is ErrorCode.TARGET_CONTENT_UNRESOLVED
    assert error.value.details["reason"] == "unsupported_object_type"
