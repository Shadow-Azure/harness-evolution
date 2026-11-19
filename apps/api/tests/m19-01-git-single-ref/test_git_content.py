"""Per-ref shallow content reads: ref shapes, caching, and failure classes."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from app.third_party_api.git.content import (
    GitContentUnavailable,
    GitProcessResult,
    SubprocessGitContent,
    _run_process,
)

SKILL_BODY = "# Systematic debugging\n\nReproduce before fixing.\n"


def _git(repo: Path, *args: str) -> str:
    """Run one deterministic local git command with a fixed identity."""
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(  # noqa: S603 - fixed local test binary and argv
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
    return result.stdout.strip()


def _seed(tmp_path: Path) -> tuple[Path, str]:
    """Create one repository with a tag, a branch, and a full commit id."""
    repo = tmp_path / "seed"
    (repo / "skills" / "x").mkdir(parents=True)
    (repo / "skills" / "x" / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "initial")
    _git(repo, "tag", "-a", "v1", "-m", "tag")
    _git(repo, "switch", "-q", "-c", "feature")
    (repo / "skills" / "x" / "SKILL.md").write_text(
        "# Branch body\n\nFeature branch.\n",
        encoding="utf-8",
    )
    _git(repo, "commit", "-q", "-am", "branch")
    _git(repo, "switch", "-q", "main")
    return repo, _git(repo, "rev-parse", "HEAD")


async def test_reads_tag_branch_and_full_commit(tmp_path: Path) -> None:
    """One per-(repo, ref) cache serves tags, branches, and a full commit id."""
    repo, commit = _seed(tmp_path)
    content = SubprocessGitContent(cache_root=tmp_path / "cache")

    tagged = await content.read_file(
        repo_url=str(repo),
        sub_dir="skills/x",
        ref="v1",
        file_name="SKILL.md",
    )
    branch = await content.read_file(
        repo_url=str(repo),
        sub_dir="skills/x",
        ref="feature",
        file_name="SKILL.md",
    )
    pinned = await content.read_file(
        repo_url=str(repo),
        sub_dir="skills/x",
        ref=commit,
        file_name="SKILL.md",
    )

    assert tagged == SKILL_BODY
    assert branch == "# Branch body\n\nFeature branch.\n"
    assert pinned == SKILL_BODY


async def test_cold_read_fetches_one_ref_without_mirror(tmp_path: Path) -> None:
    """The first read clones one single branch at depth one with blob filtering."""
    repo, _commit = _seed(tmp_path)
    calls: list[tuple[str, ...]] = []

    async def runner(
        argv: tuple[str, ...],
        cwd: Path | None,
    ) -> GitProcessResult:
        calls.append(argv)
        return await _run_process(argv, cwd)

    content = SubprocessGitContent(cache_root=tmp_path / "cache", runner=runner)
    body = await content.read_file(
        repo_url=str(repo),
        sub_dir="skills/x",
        ref="v1",
        file_name="SKILL.md",
    )

    assert body == SKILL_BODY
    clone = next(argv for argv in calls if "clone" in argv)
    assert "--mirror" not in clone
    assert "--depth" in clone and clone[clone.index("--depth") + 1] == "1"
    assert "--single-branch" in clone
    assert "--filter=blob:none" in clone
    assert "--branch" in clone and clone[clone.index("--branch") + 1] == "v1"
    assert not any("--mirror" in argv for argv in calls)


async def test_existing_cache_fetches_only_that_ref(tmp_path: Path) -> None:
    """A second read refreshes one ref instead of cloning the repository again."""
    repo, _commit = _seed(tmp_path)
    calls: list[tuple[str, ...]] = []

    async def runner(
        argv: tuple[str, ...],
        cwd: Path | None,
    ) -> GitProcessResult:
        calls.append(argv)
        return await _run_process(argv, cwd)

    content = SubprocessGitContent(cache_root=tmp_path / "cache", runner=runner)
    for _ in range(2):
        await content.read_file(
            repo_url=str(repo),
            sub_dir="skills/x",
            ref="v1",
            file_name="SKILL.md",
        )

    assert sum(1 for argv in calls if "clone" in argv) == 1
    fetch_calls = [argv for argv in calls if "fetch" in argv]
    assert fetch_calls
    assert all("--depth" in argv and "--filter=blob:none" in argv for argv in fetch_calls)
    assert any("refs/tags/v1" in argv for argv in fetch_calls)
    assert all(argv[-1].startswith(("refs/heads/", "refs/tags/")) for argv in fetch_calls)


async def test_missing_ref_is_classified_and_leaves_no_cache(tmp_path: Path) -> None:
    """A missing tag fails with a stable reason and no partial cache directory."""
    repo, _commit = _seed(tmp_path)
    content = SubprocessGitContent(cache_root=tmp_path / "cache")

    with pytest.raises(GitContentUnavailable) as raised:
        await content.read_file(
            repo_url=str(repo),
            sub_dir="skills/x",
            ref="v-missing",
            file_name="SKILL.md",
        )

    assert raised.value.reason == "ref_not_found"
    assert not any(path.is_dir() for path in (tmp_path / "cache").glob("*/*"))


async def test_missing_file_is_classified(tmp_path: Path) -> None:
    """A valid ref with no such file returns file_not_found."""
    repo, _commit = _seed(tmp_path)
    content = SubprocessGitContent(cache_root=tmp_path / "cache")

    with pytest.raises(GitContentUnavailable) as raised:
        await content.read_file(
            repo_url=str(repo),
            sub_dir="skills/x",
            ref="v1",
            file_name="MISSING.md",
        )

    assert raised.value.reason == "file_not_found"


async def test_unsafe_ref_and_path_are_rejected(tmp_path: Path) -> None:
    """Option-like refs and traversal paths never reach a git process."""
    content = SubprocessGitContent(cache_root=tmp_path / "cache")

    with pytest.raises(GitContentUnavailable) as bad_ref:
        await content.read_file(
            repo_url="https://example.invalid/repo.git",
            sub_dir="skills/x",
            ref="--upload-pack=x",
            file_name="SKILL.md",
        )
    with pytest.raises(GitContentUnavailable) as bad_path:
        await content.read_file(
            repo_url="https://example.invalid/repo.git",
            sub_dir="../escape",
            ref="v1",
            file_name="SKILL.md",
        )

    assert bad_ref.value.reason == "ref_invalid"
    assert bad_path.value.reason == "path_invalid"
