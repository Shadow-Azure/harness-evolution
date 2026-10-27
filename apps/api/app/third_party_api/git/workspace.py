"""Isolated git workspaces for candidate creation and publication."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

from app.db.models.evolution import EvolutionRunRecord
from app.utils.redaction import sanitize_message

GitStage = Literal[
    "workspace",
    "clone",
    "reference",
    "subdirectory",
    "patch",
    "commit",
    "push",
]


class GitOperationError(RuntimeError):
    """A sanitized git failure carrying a stage and retry classification."""

    def __init__(
        self,
        message: str,
        *,
        stage: GitStage,
        retryable: bool = False,
    ) -> None:
        """Store safe diagnostics without retaining raw process output."""
        super().__init__(message)
        self.stage = stage
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class GitProcessResult:
    """Captured output from one argument-array git process."""

    returncode: int
    stdout: str
    stderr: str


type GitRunner = Callable[[tuple[str, ...], Path | None], Awaitable[GitProcessResult]]


@dataclass(frozen=True, slots=True)
class PreparedWorkspace:
    """Paths and immutable refs created for one evolution run."""

    repo_path: Path
    path: Path
    ref: str
    base_commit: str
    branch: str


@dataclass(frozen=True, slots=True)
class Patch:
    """One deterministic patch applied inside an isolated workspace."""

    file: str
    lines: tuple[str, ...]

    @property
    def sha256(self) -> str:
        """Return the stable digest recorded in candidate trailers."""
        body = "\n".join(self.lines)
        return hashlib.sha256(
            f"{self.file}\0{body}".encode(),
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidateWorkspace:
    """A committed candidate branch ready to push."""

    workspace_path: Path
    run_branch: str
    local_branch: str
    ref: str
    commit: str
    message: str


class GitWorkspaceManager:
    """Own repository caches, isolated workspaces, and candidate refs."""

    _RUN_BRANCH = re.compile(r"^evo/\d{8}-.+$")
    _TRANSIENT_MARKERS = (
        "could not resolve host",
        "connection timed out",
        "connection reset",
        "failed to connect",
        "operation timed out",
        "remote end hung up",
        "temporarily unavailable",
        "timed out",
    )

    def __init__(
        self,
        *,
        repos_root: Path,
        workspaces_root: Path,
        runner: GitRunner | None = None,
        timeout_seconds: float = 60.0,
        push_enabled: bool = True,
    ) -> None:
        """Bind roots and the sanitized process seam."""
        self.repos_root = repos_root
        self.workspaces_root = workspaces_root
        self._runner = runner or _run_process
        self._timeout_seconds = timeout_seconds
        self._push_enabled = push_enabled

    async def prepare(self, run: EvolutionRunRecord) -> PreparedWorkspace:
        """Clone a cache and create the uniquely named run branch."""
        self.repos_root.mkdir(parents=True, exist_ok=True)
        self.workspaces_root.mkdir(parents=True, exist_ok=True)
        repo_path = self.repos_root / _safe_component(run.target_config_id or run.id)
        workspace_path = self.workspaces_root / _safe_component(run.id)
        ref = run.target_version
        branch = f"evo/{run.created_at:%Y%m%d}-{run.id}"

        if not repo_path.exists():
            await self._git_checked(
                None,
                ("git", "clone", "--mirror", "--no-hardlinks", "--", run.repo_url, str(repo_path)),
                stage="clone",
                failure="repository cache clone failed",
            )
        else:
            await self._git_checked(
                repo_path,
                ("git", "remote", "update", "--prune"),
                stage="clone",
                failure="repository cache refresh failed",
                retryable=True,
            )

        resolved_ref = await self._git_checked(
            repo_path,
            ("git", "rev-parse", "--verify", f"{ref}^{{commit}}"),
            stage="reference",
            failure="target reference is invalid",
        )
        base_commit = resolved_ref.stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40}", base_commit):
            raise GitOperationError(
                "target reference did not resolve to a commit",
                stage="reference",
            )

        sub_dir = _normalize_sub_dir(run.sub_dir)
        if sub_dir != ".":
            object_type = await self._git_checked(
                repo_path,
                ("git", "cat-file", "-t", f"{base_commit}:{sub_dir}"),
                stage="subdirectory",
                failure="target subdirectory is missing",
            )
            if object_type.stdout.strip() != "tree":
                raise GitOperationError(
                    "target subdirectory is not a directory",
                    stage="subdirectory",
                )

        if workspace_path.exists():
            await self._reuse_or_reject(workspace_path, branch, run.repo_url)
        else:
            try:
                await self._git_checked(
                    None,
                    ("git", "clone", "--no-checkout", "--", str(repo_path), str(workspace_path)),
                    stage="workspace",
                    failure="workspace clone failed",
                )
            except Exception:
                shutil.rmtree(workspace_path, ignore_errors=True)
                raise
            await self._git_checked(
                workspace_path,
                ("git", "remote", "set-url", run.remote_name, run.repo_url),
                stage="workspace",
                failure="workspace remote setup failed",
            )
            local_branch = await self._optional_ref(
                workspace_path,
                ("git", "rev-parse", "--verify", f"refs/heads/{branch}"),
            )
            if local_branch is None:
                remote_branch = await self.remote_ref_commit(
                    workspace_path,
                    run.remote_name,
                    branch,
                )
                if remote_branch is None:
                    await self._git_checked(
                        workspace_path,
                        ("git", "switch", "-c", branch, base_commit),
                        stage="workspace",
                        failure="run branch creation failed",
                    )
                else:
                    await self._git_checked(
                        workspace_path,
                        ("git", "switch", "-c", branch, "--track", f"{run.remote_name}/{branch}"),
                        stage="workspace",
                        failure="existing run branch could not be resumed",
                    )
            else:
                await self._git_checked(
                    workspace_path,
                    ("git", "switch", branch),
                    stage="workspace",
                    failure="existing local run branch could not be resumed",
                )

        self.validate_for_push(
            PreparedWorkspace(
                repo_path=repo_path,
                path=workspace_path,
                ref=ref,
                base_commit=base_commit,
                branch=branch,
            ),
            run,
        )
        cleanliness = await self._git_checked(
            workspace_path,
            ("git", "status", "--porcelain"),
            stage="workspace",
            failure="workspace status check failed",
        )
        if cleanliness.stdout.strip():
            raise GitOperationError(
                "workspace is not clean after preparation",
                stage="workspace",
            )
        if self._push_enabled:
            await self._push_run_branch(workspace_path, branch)
        return PreparedWorkspace(
            repo_path=repo_path,
            path=workspace_path,
            ref=ref,
            base_commit=base_commit,
            branch=branch,
        )

    async def create_candidate(
        self,
        prepared: PreparedWorkspace,
        *,
        run_branch: str,
        candidate_ref: str,
        patch: Patch,
        message: str,
    ) -> CandidateWorkspace:
        """Create one candidate commit from the clean, current run branch."""
        await self._require_clean(prepared.path)
        await self._git_checked(
            prepared.path,
            ("git", "switch", run_branch),
            stage="workspace",
            failure="run branch could not be selected",
        )
        if not re.fullmatch(rf"{re.escape(run_branch)}/candidate/r[1-9]\d*", candidate_ref):
            raise GitOperationError("candidate ref does not match the run", stage="workspace")
        local_branch = candidate_local_branch(candidate_ref)
        existing_candidate = await self._optional_ref(
            prepared.path,
            ("git", "rev-parse", "--verify", f"refs/heads/{local_branch}"),
        )
        if existing_candidate is not None:
            await self._git_checked(
                prepared.path,
                ("git", "branch", "-D", local_branch),
                stage="workspace",
                failure="stale local candidate branch could not be removed",
            )
        await self._git_checked(
            prepared.path,
            ("git", "switch", "-c", local_branch, run_branch),
            stage="workspace",
            failure="candidate branch creation failed",
        )
        self._write_patch(prepared.path, patch)
        await self._git_checked(
            prepared.path,
            ("git", "add", "--", patch.file),
            stage="patch",
            failure="candidate patch could not be staged",
        )
        await self._git_checked(
            prepared.path,
            (
                "git",
                "-c",
                "user.name=Harness Evolution",
                "-c",
                "user.email=harness-evolution@localhost",
                "commit",
                "-m",
                message,
            ),
            stage="commit",
            failure="candidate commit failed",
        )
        commit = (
            await self._git_checked(
                prepared.path,
                ("git", "rev-parse", "HEAD"),
                stage="commit",
                failure="candidate commit could not be resolved",
            )
        ).stdout.strip()
        return CandidateWorkspace(
            workspace_path=prepared.path,
            run_branch=run_branch,
            local_branch=local_branch,
            ref=candidate_ref,
            commit=commit,
            message=message,
        )

    async def push_candidate(
        self,
        candidate: CandidateWorkspace,
        *,
        expected_remote_commit: str | None,
    ) -> None:
        """Push an initial candidate or replace its own prior commit with a lease."""
        remote = await self.remote_tag_commit(
            candidate.workspace_path,
            "origin",
            candidate.ref,
        )
        if expected_remote_commit is None:
            if remote is not None and remote != candidate.commit:
                raise GitOperationError(
                    "candidate reference already exists",
                    stage="push",
                )
            if remote == candidate.commit:
                return
            args: tuple[str, ...] = (
                "git",
                "push",
                "origin",
                f"{candidate.commit}:refs/tags/{candidate.ref}",
            )
        else:
            if remote != expected_remote_commit:
                raise GitOperationError(
                    "candidate reference lease no longer matches",
                    stage="push",
                )
            args = (
                "git",
                "push",
                f"--force-with-lease=refs/tags/{candidate.ref}:{expected_remote_commit}",
                "origin",
                f"{candidate.commit}:refs/tags/{candidate.ref}",
            )
        await self._push_checked(candidate.workspace_path, args)

    async def accept_candidate(
        self,
        candidate: CandidateWorkspace,
        *,
        run_branch: str,
        message: str,
    ) -> CandidateWorkspace:
        """Amend accepted metadata, publish the candidate, and fast-forward run."""
        await self._git_checked(
            candidate.workspace_path,
            (
                "git",
                "-c",
                "user.name=Harness Evolution",
                "-c",
                "user.email=harness-evolution@localhost",
                "commit",
                "--amend",
                "-m",
                message,
            ),
            stage="commit",
            failure="accepted candidate amend failed",
        )
        final_commit = (
            await self._git_checked(
                candidate.workspace_path,
                ("git", "rev-parse", "HEAD"),
                stage="commit",
                failure="accepted candidate commit could not be resolved",
            )
        ).stdout.strip()
        final_candidate = CandidateWorkspace(
            workspace_path=candidate.workspace_path,
            run_branch=run_branch,
            local_branch=candidate.local_branch,
            ref=candidate.ref,
            commit=final_commit,
            message=message,
        )
        await self.push_candidate(
            final_candidate,
            expected_remote_commit=candidate.commit,
        )
        await self._git_checked(
            candidate.workspace_path,
            ("git", "switch", run_branch),
            stage="workspace",
            failure="run branch could not be selected after acceptance",
        )
        await self._git_checked(
            candidate.workspace_path,
            ("git", "merge", "--ff-only", final_commit),
            stage="workspace",
            failure="run branch is not a fast-forward",
        )
        await self._push_run_branch(candidate.workspace_path, run_branch)
        await self._delete_remote_tag(candidate.workspace_path, candidate.ref)
        await self._git_checked(
            candidate.workspace_path,
            ("git", "branch", "-D", candidate.local_branch),
            stage="workspace",
            failure="accepted local candidate branch could not be removed",
        )
        return final_candidate

    async def reject_candidate(
        self,
        candidate: CandidateWorkspace,
        *,
        run_branch: str,
    ) -> None:
        """Delete rejected candidate refs without changing the run branch."""
        await self._git_checked(
            candidate.workspace_path,
            ("git", "switch", run_branch),
            stage="workspace",
            failure="run branch could not be selected after rejection",
        )
        await self._delete_remote_tag(candidate.workspace_path, candidate.ref)
        await self._git_checked(
            candidate.workspace_path,
            ("git", "branch", "-D", candidate.local_branch),
            stage="workspace",
            failure="rejected local candidate branch could not be removed",
        )

    async def remote_ref_commit(
        self,
        workspace_path: Path,
        remote: str,
        ref: str,
    ) -> str | None:
        """Resolve one remote branch without fetching unrelated objects."""
        result = await self._git(
            workspace_path,
            ("git", "ls-remote", "--heads", remote, f"refs/heads/{ref}"),
            stage="push",
        )
        if result.returncode != 0:
            raise self._error_from_result(
                result,
                stage="push",
                failure="remote reference lookup failed",
            )
        for line in result.stdout.splitlines():
            commit, separator, found = line.partition("\t")
            if separator and found == f"refs/heads/{ref}":
                return commit
        return None

    async def remote_tag_commit(
        self,
        workspace_path: Path,
        remote: str,
        ref: str,
    ) -> str | None:
        """Resolve one candidate tag without treating it as a branch."""
        result = await self._git(
            workspace_path,
            ("git", "ls-remote", "--tags", remote, f"refs/tags/{ref}"),
            stage="push",
        )
        if result.returncode != 0:
            raise self._error_from_result(
                result,
                stage="push",
                failure="remote candidate lookup failed",
            )
        for line in result.stdout.splitlines():
            commit, separator, found = line.partition("\t")
            if separator and found == f"refs/tags/{ref}":
                return commit
        return None

    def validate_for_push(
        self,
        prepared: PreparedWorkspace,
        run: EvolutionRunRecord,
    ) -> None:
        """Reject unsafe branch names and invalid baseline snapshots."""
        if not self._RUN_BRANCH.fullmatch(prepared.branch) or prepared.branch in {"main", "master"}:
            raise GitOperationError("run branch name is unsafe", stage="workspace")
        if not re.fullmatch(r"[0-9a-f]{40}", prepared.base_commit):
            raise GitOperationError("base commit is invalid", stage="reference")
        if prepared.branch != f"evo/{run.created_at:%Y%m%d}-{run.id}":
            raise GitOperationError("run branch does not match the run", stage="workspace")

    def cleanup_workspaces(
        self,
        *,
        active_run_ids: set[str],
        keep: int = 20,
    ) -> tuple[Path, ...]:
        """Delete only inactive workspaces beyond the newest retention window."""
        if keep < 0:
            raise ValueError("workspace retention cannot be negative")
        if not self.workspaces_root.exists():
            return ()
        candidates = sorted(
            (
                path
                for path in self.workspaces_root.iterdir()
                if path.is_dir() and path.name not in active_run_ids
            ),
            key=lambda path: (path.stat().st_mtime, path.name),
            reverse=True,
        )
        removable = candidates[keep:]
        for path in removable:
            path.resolve().relative_to(self.workspaces_root.resolve())
            shutil.rmtree(path)
        return tuple(removable)

    async def _push_run_branch(self, workspace_path: Path, branch: str) -> None:
        """Publish only a fast-forward run branch and never force it."""
        remote_commit = await self.remote_ref_commit(workspace_path, "origin", branch)
        head = (
            await self._git_checked(
                workspace_path,
                ("git", "rev-parse", "HEAD"),
                stage="push",
                failure="run branch commit could not be resolved",
            )
        ).stdout.strip()
        if remote_commit is not None and remote_commit != head:
            ancestor = await self._git(
                workspace_path,
                ("git", "merge-base", "--is-ancestor", remote_commit, head),
                stage="push",
            )
            if ancestor.returncode != 0:
                raise GitOperationError(
                    "run branch update is not a fast-forward",
                    stage="push",
                )
        await self._push_checked(
            workspace_path,
            ("git", "push", "origin", f"{head}:refs/heads/{branch}"),
        )

    async def _delete_remote_tag(self, workspace_path: Path, ref: str) -> None:
        """Delete a transient candidate tag, treating absence as success."""
        if await self.remote_tag_commit(workspace_path, "origin", ref) is None:
            return
        await self._push_checked(
            workspace_path,
            ("git", "push", "origin", f":refs/tags/{ref}"),
        )

    async def _reuse_or_reject(
        self,
        workspace_path: Path,
        branch: str,
        expected_repo_url: str,
    ) -> None:
        """Resume an existing safe run workspace without resetting its branch."""
        if not (workspace_path / ".git").is_dir():
            raise GitOperationError("workspace path exists without git metadata", stage="workspace")
        current_url = await self._git(
            workspace_path,
            ("git", "remote", "get-url", "origin"),
            stage="workspace",
        )
        if current_url.returncode != 0 or current_url.stdout.strip() != expected_repo_url:
            raise GitOperationError("workspace remote does not match the run", stage="workspace")
        current_branch = await self._git(
            workspace_path,
            ("git", "branch", "--show-current"),
            stage="workspace",
        )
        if current_branch.stdout.strip() != branch:
            await self._git_checked(
                workspace_path,
                ("git", "switch", branch),
                stage="workspace",
                failure="existing run workspace cannot switch branches",
            )
        await self._require_clean(workspace_path)

    async def _require_clean(self, workspace_path: Path) -> None:
        """Require no tracked or untracked file before ref-changing operations."""
        result = await self._git_checked(
            workspace_path,
            ("git", "status", "--porcelain", "--untracked-files=all"),
            stage="workspace",
            failure="workspace status check failed",
        )
        if result.stdout.strip():
            raise GitOperationError("workspace is not clean", stage="workspace")

    async def _optional_ref(self, cwd: Path, argv: tuple[str, ...]) -> str | None:
        """Return a ref only when it resolves, without treating absence as failure."""
        result = await self._git(cwd, argv, stage="workspace")
        return result.stdout.strip() if result.returncode == 0 else None

    async def _push_checked(self, cwd: Path, argv: tuple[str, ...]) -> None:
        """Run one push and retain both failure classification and retryability."""
        result = await self._git(cwd, argv, stage="push")
        if result.returncode != 0:
            raise self._error_from_result(
                result,
                stage="push",
                failure="git push failed",
            )

    async def _git_checked(
        self,
        cwd: Path | None,
        argv: tuple[str, ...],
        *,
        stage: GitStage,
        failure: str,
        retryable: bool = False,
    ) -> GitProcessResult:
        """Run git and replace raw diagnostics with a stable safe error."""
        result = await self._git(cwd, argv, stage=stage)
        if result.returncode != 0:
            raise self._error_from_result(
                result,
                stage=stage,
                failure=failure,
                retryable=retryable,
            )
        return result

    async def _git(
        self,
        cwd: Path | None,
        argv: tuple[str, ...],
        *,
        stage: GitStage,
    ) -> GitProcessResult:
        """Invoke the process seam with one bounded timeout."""
        try:
            return await asyncio.wait_for(
                self._runner(argv, cwd),
                timeout=self._timeout_seconds,
            )
        except (TimeoutError, OSError, RuntimeError):
            raise GitOperationError(
                f"{stage} operation failed",
                stage=stage,
                retryable=True,
            ) from None

    def _error_from_result(
        self,
        result: GitProcessResult,
        *,
        stage: GitStage,
        failure: str,
        retryable: bool = False,
    ) -> GitOperationError:
        """Classify transient transport failures without exposing command output."""
        diagnostic = sanitize_message(result.stderr, limit=500).lower()
        is_retryable = retryable or any(marker in diagnostic for marker in self._TRANSIENT_MARKERS)
        return GitOperationError(failure, stage=stage, retryable=is_retryable)

    @staticmethod
    def _write_patch(workspace_path: Path, patch: Patch) -> None:
        """Write a bounded repository-relative patch without path traversal."""
        relative = PurePosixPath(patch.file)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise GitOperationError("patch path is unsafe", stage="patch")
        destination = workspace_path.joinpath(*relative.parts)
        try:
            destination.parent.resolve().relative_to(workspace_path.resolve())
        except ValueError:
            raise GitOperationError("patch path escapes the workspace", stage="patch") from None
        destination.parent.mkdir(parents=True, exist_ok=True)
        existing = destination.read_text(encoding="utf-8") if destination.exists() else ""
        separator = "\n" if existing and not existing.endswith("\n") else ""
        destination.write_text(
            existing + separator + "\n".join(patch.lines) + "\n",
            encoding="utf-8",
        )


async def retry_push(
    push: Callable[[], Awaitable[None]],
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_retry: Callable[[int, GitOperationError], Awaitable[None]] | None = None,
    interval_seconds: float = 5.0,
    attempts: int = 3,
) -> int:
    """Retry a transient push immediately and return its successful attempt count."""
    for attempt in range(1, attempts + 1):
        try:
            await push()
            return attempt
        except GitOperationError as exc:
            if not exc.retryable or attempt == attempts:
                raise
            if on_retry is not None:
                await on_retry(attempt, exc)
            await sleep(interval_seconds)
    raise AssertionError("push retry loop exhausted without a result")


async def _run_process(
    argv: Sequence[str],
    cwd: Path | None,
) -> GitProcessResult:
    """Execute git through a sanitized argument array with prompts disabled."""
    environment = dict(os.environ)
    environment.update(
        {
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
        },
    )
    process = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd) if cwd is not None else None,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=environment,
        start_new_session=sys.platform != "win32",
    )
    stdout, stderr = await process.communicate()
    return GitProcessResult(
        returncode=process.returncode or 0,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
    )


def _safe_component(value: str) -> str:
    """Reduce one database identifier to a safe single path component."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    if not cleaned:
        raise GitOperationError("workspace identifier is empty", stage="workspace")
    return cleaned


def _normalize_sub_dir(value: str) -> str:
    """Normalize and validate a repository-relative target directory."""
    normalized = PurePosixPath((value or ".").strip()).as_posix()
    if normalized.startswith("/") or ".." in PurePosixPath(normalized).parts:
        raise GitOperationError("target subdirectory is unsafe", stage="subdirectory")
    return normalized or "."


def candidate_local_branch(candidate_ref: str) -> str:
    """Map a remote candidate tag to a legal, non-conflicting local work branch."""
    digest = hashlib.sha256(candidate_ref.encode()).hexdigest()[:16]
    return f"harness-candidate/{digest}"
