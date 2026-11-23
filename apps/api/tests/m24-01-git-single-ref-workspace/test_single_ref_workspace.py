"""Run-workspace single-ref caches, recovery, push targets, and observability."""

from __future__ import annotations

import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.db.models.evolution import EvolutionRunRecord
from app.db.models.jobs import JobRunRecord
from app.third_party_api.git.observability import (
    GitOperationCollector,
    GitOperationRecord,
    emit_git_operation,
    fallback_reason_for,
    git_operation_scope,
    is_proxy_traffic,
    target_host_for,
)
from app.third_party_api.git.proxy import (
    GitProcessResult as ProxyProcessResult,
)
from app.third_party_api.git.proxy import (
    GitProxyController,
    ProxyAwareGitRunner,
)
from app.third_party_api.git.workspace import (
    GitOperationError,
    GitWorkspaceManager,
    Patch,
)
from app.third_party_api.git.workspace import (
    GitProcessResult as WorkspaceProcessResult,
)

NOW = datetime(2026, 11, 20, 9, 30, tzinfo=UTC)
PROXY = "http://127.0.0.1:10808"


def _git(cwd: Path, *args: str) -> str:
    """Run one deterministic local git command and return stdout."""
    result = subprocess.run(
        ("git", *args),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _seed_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """Create a bare remote with a tagged main commit and a divergent branch."""
    bare = tmp_path / "remote.git"
    seed = tmp_path / "seed"
    _git(tmp_path, "init", "--bare", str(bare))
    _git(tmp_path, "clone", str(bare), str(seed))
    _git(seed, "config", "user.name", "Test User")
    _git(seed, "config", "user.email", "test@example.invalid")
    target = seed / "skills" / "deep-research"
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("# Tagged\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "tagged target")
    tagged = _git(seed, "rev-parse", "HEAD")
    _git(seed, "tag", "v2.0.0")
    _git(seed, "switch", "-c", "feature")
    (target / "SKILL.md").write_text("# Feature\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "feature target")
    feature = _git(seed, "rev-parse", "HEAD")
    _git(seed, "push", "origin", "HEAD:refs/heads/main", "--tags")
    _git(seed, "switch", "main")
    _git(seed, "push", "origin", "feature:refs/heads/feature")
    return bare, tagged, feature


def _run(
    repo_url: str,
    version: str,
    *,
    run_id: str = "run-single",
    target_id: str = "target-single",
) -> EvolutionRunRecord:
    """Build one run snapshot for real local git operations."""
    return EvolutionRunRecord(
        id=run_id,
        title="deep-research evolution",
        mode="full",
        engine_key="full",
        eval_config={"gateway": "fake"},
        target_config_id=target_id,
        target_type="skill",
        target_name="deep-research",
        target_version=version,
        repo_url=repo_url,
        sub_dir="skills/deep-research",
        repo_path=None,
        base_ref=version,
        base_commit=None,
        branch_name=None,
        workspace_path=None,
        remote_name="origin",
        push_status="pending",
        pushed_at=None,
        push_error=None,
        window_from=None,
        window_to=None,
        models=[],
        status="preparing",
        blocked_stage=None,
        retry_attempts=0,
        next_retry_at=None,
        eval_status="pending",
        error_stage=None,
        error_message=None,
        error_at=None,
        progress_unit=0,
        stats={},
        created_by=None,
        created_at=NOW,
        finished_at=None,
    )


class RecordingRunner:
    """Delegate to real git while recording every argv array."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    async def __call__(
        self,
        argv: tuple[str, ...],
        cwd: Path | None,
    ) -> WorkspaceProcessResult:
        self.calls.append(argv)
        from app.third_party_api.git.workspace import _run_process

        return await _run_process(argv, cwd)


class FailingFetchRunner:
    """Fail only network fetches after a real cache was built."""

    def __init__(self, stderr: str) -> None:
        self.stderr = stderr
        self.fail = False
        self.calls: list[tuple[str, ...]] = []

    async def __call__(
        self,
        argv: tuple[str, ...],
        cwd: Path | None,
    ) -> WorkspaceProcessResult:
        self.calls.append(argv)
        if self.fail and len(argv) > 1 and argv[1] == "fetch":
            return WorkspaceProcessResult(returncode=128, stdout="", stderr=self.stderr)
        from app.third_party_api.git.workspace import _run_process

        return await _run_process(argv, cwd)


async def test_each_ref_type_fetches_only_the_target_ref(tmp_path: Path) -> None:
    """Tag, branch, and full commit caches never run --mirror or fetch other refs."""
    bare, tagged, feature = _seed_repo(tmp_path)
    runner = RecordingRunner()
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        runner=runner,
        push_enabled=False,
    )

    tag = await manager.prepare(_run(str(bare), "v2.0.0", run_id="run-tag"))
    branch = await manager.prepare(_run(str(bare), "feature", run_id="run-branch"))
    commit = await manager.prepare(_run(str(bare), feature, run_id="run-commit"))

    assert tag.base_commit == tagged
    assert branch.base_commit == feature
    assert commit.base_commit == feature
    assert (tag.path / "skills" / "deep-research" / "SKILL.md").read_text() == "# Tagged\n"
    assert (branch.path / "skills" / "deep-research" / "SKILL.md").read_text() == "# Feature\n"
    assert tag.repo_path.parent == tmp_path / "repos" / "target-single"
    assert branch.repo_path != tag.repo_path
    assert all("--mirror" not in argv for argv in runner.calls)

    fetches = [argv for argv in runner.calls if len(argv) > 1 and argv[1] == "fetch"]
    assert any(argv[-1] == "v2.0.0" for argv in fetches)
    assert any(argv[-1] == "feature" for argv in fetches)
    assert any("--depth" in argv and argv[-1] == feature and "origin" in argv for argv in fetches)


async def test_cache_hits_and_ref_refresh_preserve_complete_objects(tmp_path: Path) -> None:
    """A branch cache is reused, refreshed, and kept when a later fetch is transient."""
    bare, _tagged, _feature = _seed_repo(tmp_path)
    seed = tmp_path / "seed"
    runner = FailingFetchRunner("fatal: unable to access: Could not resolve host: example.invalid")
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        runner=runner,
        push_enabled=False,
    )

    first = await manager.prepare(_run(str(bare), "feature", run_id="run-cache-1"))
    assert first.cache_hit is False
    assert first.base_commit is not None

    target = seed / "skills" / "deep-research"
    _git(seed, "switch", "feature")
    (target / "SKILL.md").write_text("# Refreshed\n", encoding="utf-8")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "refresh feature")
    refreshed = _git(seed, "rev-parse", "HEAD")
    _git(seed, "push", "origin", "feature:refs/heads/feature")

    second = await manager.prepare(_run(str(bare), "feature", run_id="run-cache-2"))
    assert second.cache_hit is True
    assert second.base_commit == refreshed
    assert (second.path / "skills" / "deep-research" / "SKILL.md").read_text() == "# Refreshed\n"

    runner.fail = True
    with pytest.raises(GitOperationError, match="target reference fetch failed") as failure:
        await manager.prepare(_run(str(bare), "feature", run_id="run-cache-3"))
    assert failure.value.retryable is True
    cache_path = second.repo_path
    assert cache_path.is_dir()
    assert _git(cache_path, "rev-parse", "refs/heads/harness-target") == refreshed


async def test_missing_ref_removes_cold_cache(tmp_path: Path) -> None:
    """A missing target ref fails as a reference error without leaving an empty cache."""
    bare, _tagged, _feature = _seed_repo(tmp_path)
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        push_enabled=False,
    )

    with pytest.raises(GitOperationError, match="reference") as failure:
        await manager.prepare(_run(str(bare), "missing-ref"))

    assert failure.value.stage == "reference"
    target_root = tmp_path / "repos" / "target-single"
    assert not target_root.exists() or not any(target_root.iterdir())


async def test_prepare_resumes_remote_run_branch_in_a_new_workspace(tmp_path: Path) -> None:
    """A new workspace fetches an existing run branch before tracking or pushing it."""
    bare, _tagged, _feature = _seed_repo(tmp_path)
    runner = RecordingRunner()
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        runner=runner,
    )
    run = _run(str(bare), "v2.0.0")

    prepared = await manager.prepare(run)
    (prepared.path / "skills" / "deep-research" / "EVOLUTION.md").write_text(
        "resumed\n",
        encoding="utf-8",
    )
    _git(prepared.path, "add", ".")
    _git(
        prepared.path,
        "-c",
        "user.name=Test User",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        f"resume\n\nHarness-Run-Id: {run.id}",
    )
    remote_tip = _git(prepared.path, "rev-parse", "HEAD")
    _git(prepared.path, "push", "origin", f"HEAD:refs/heads/{prepared.branch}")
    shutil.rmtree(prepared.path)

    resumed = await manager.prepare(run)

    assert resumed.path.is_dir()
    assert resumed.cache_hit is True
    assert _git(resumed.path, "branch", "--show-current") == prepared.branch
    assert _git(resumed.path, "rev-parse", "HEAD") == remote_tip
    assert _git(bare, "rev-parse", prepared.branch) == remote_tip
    assert any(
        f"+refs/heads/{prepared.branch}:refs/remotes/origin/{prepared.branch}" in argv
        for argv in runner.calls
    )


async def test_push_url_routes_all_remote_mutations_to_the_fork(tmp_path: Path) -> None:
    """A configured push URL keeps fetches on origin and every write on the fork."""
    bare, _tagged, _feature = _seed_repo(tmp_path)
    fork = tmp_path / "fork.git"
    _git(tmp_path, "init", "--bare", str(fork))
    origin_refs = set(_git(bare, "for-each-ref", "--format=%(refname)").splitlines())
    manager = GitWorkspaceManager(
        repos_root=tmp_path / "repos",
        workspaces_root=tmp_path / "workspaces",
        push_url=str(fork),
    )
    run = _run(str(bare), "v2.0.0")

    prepared = await manager.prepare(run)
    assert _git(fork, "rev-parse", prepared.branch) == prepared.base_commit
    assert prepared.branch not in _git(bare, "for-each-ref", "--format=%(refname)")

    candidate = await manager.create_candidate(
        prepared,
        run_branch=prepared.branch,
        candidate_ref=f"{prepared.branch}/candidate/r1",
        patch=Patch(file="skills/deep-research/EVOLUTION.md", lines=("candidate",)),
        message=f"candidate\n\nHarness-Run-Id: {run.id}",
    )
    await manager.push_candidate(candidate, expected_remote_commit=None)
    assert _git(fork, "rev-parse", f"refs/tags/{candidate.ref}") == candidate.commit
    remote_tag = subprocess.run(
        ("git", "ls-remote", "--tags", str(bare), f"refs/tags/{candidate.ref}"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert remote_tag == ""

    accepted_message = (
        f"accepted\n\nHarness-Run-Id: {run.id}\n"
        f"Harness-Evaluated-Commit: {candidate.commit}\n"
        "Harness-Verdict: accepted improved"
    )
    accepted = await manager.accept_candidate(
        candidate,
        run_branch=prepared.branch,
        message=accepted_message,
    )
    assert _git(fork, "rev-parse", prepared.branch) == accepted.commit
    fork_tag = subprocess.run(
        ("git", "ls-remote", "--tags", str(fork), f"refs/tags/{candidate.ref}"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert fork_tag == ""
    assert set(_git(bare, "for-each-ref", "--format=%(refname)").splitlines()) == origin_refs


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("https://github.com/owner/fork.git", "https://github.com/owner/fork.git"),
        ("ssh://git@github.com/owner/fork.git", "ssh://git@github.com/owner/fork.git"),
        ("git@github.com:owner/fork.git", "git@github.com:owner/fork.git"),
    ],
)
def test_git_push_url_config_accepts_credential_free_remotes(
    value: str | None,
    expected: str | None,
) -> None:
    """Only credential-free HTTP(S)/SSH push remotes are configured."""
    settings = Settings(jwt_secret=SecretStr("test-secret"), git_push_url=value)
    assert settings.git_push_url == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://user:secret@github.com/owner/fork.git",
        "https://github.com/owner/fork.git?token=1",
        "ftp://github.com/owner/fork.git",
        "/tmp/local-fork.git",
        "git@github.com:owner/fork.git extra",
    ],
)
def test_git_push_url_config_rejects_unsafe_values(value: str) -> None:
    """Embedded credentials, unsupported schemes, and local paths are rejected."""
    with pytest.raises(ValidationError):
        Settings(jwt_secret=SecretStr("test-secret"), git_push_url=value)


def test_git_push_url_environment_variable_is_documented(monkeypatch: pytest.MonkeyPatch) -> None:
    """HE_GIT_PUSH_URL reaches the manager through the composition root."""
    monkeypatch.setenv("HE_GIT_PUSH_URL", "https://github.com/owner/fork.git")
    monkeypatch.setenv("HE_JWT_SECRET", "test-signing-secret")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.git_push_url == "https://github.com/owner/fork.git"


async def test_runner_records_proxy_operations_without_leaking_urls(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A proxy fallback records viaProxy=false, its reason, and only the host."""
    responses = [
        ProxyProcessResult(returncode=0, stdout="", stderr=""),
        ProxyProcessResult(
            returncode=128,
            stdout="",
            stderr=(
                "fatal: unable to access 'https://user:secret@github.com/o/r.git/': "
                "Failed to connect to 127.0.0.1 port 10808"
            ),
        ),
        ProxyProcessResult(returncode=0, stdout="", stderr=""),
    ]

    async def spawn(
        _argv: tuple[str, ...],
        _cwd: Path | None,
        _environment: dict[str, str],
    ) -> ProxyProcessResult:
        return responses.pop(0)

    runner = ProxyAwareGitRunner(
        GitProxyController(PROXY, probe=_healthy_probe),
        spawn=spawn,
    )
    with (
        caplog.at_level("INFO"),
        git_operation_scope(
            run_id="run-observe",
            job_id="job-observe",
            stage="prepare",
            target_host="github.com",
        ) as collector,
    ):
        await runner.run(("git", "fetch", "https://user:secret@github.com/o/r.git"), None)
        await runner.run(("git", "push", "origin", "HEAD:refs/heads/evo/1"), None)

    records = collector.records
    assert [record.operation for record in records] == ["fetch", "push"]
    assert records[0].via_proxy is True
    assert records[1].via_proxy is False
    assert records[1].fallback_reason == "proxy_connect"
    payload, truncated = collector.bounded()
    assert truncated is False
    assert payload[0]["targetHost"] == "github.com"
    assert payload[1]["targetHost"] == "github.com"
    serialized = str(payload)
    assert "secret" not in serialized
    assert "https://" not in serialized
    operation_logs = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "git.proxy.operation"
    ]
    assert len(operation_logs) == 2
    assert getattr(operation_logs[0], "runId", None) == "run-observe"
    assert getattr(operation_logs[0], "jobId", None) == "job-observe"
    assert getattr(operation_logs[0], "stage", None) == "prepare"


async def test_probe_log_is_separate_from_run_traffic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A health probe logs operation=probe with no run id and adds no run record."""
    controller = GitProxyController(PROXY, probe=_healthy_probe)
    with (
        caplog.at_level("INFO"),
        git_operation_scope(run_id="run-probe", job_id="job-probe", stage="prepare") as collector,
    ):
        assert await controller.probe_once() is True

    assert collector.records == ()
    probes = [
        record
        for record in caplog.records
        if getattr(record, "event", None) == "git.proxy.operation"
        and getattr(record, "operation", None) == "probe"
    ]
    assert len(probes) == 1
    assert getattr(probes[0], "runId", None) is None
    assert getattr(probes[0], "exitCode", None) == 0


def test_target_host_extraction_keeps_only_the_host() -> None:
    """Observability never retains a remote URL, credential, or local path."""
    assert target_host_for(("git", "fetch", "https://user:secret@github.com/o/r.git")) == (
        "github.com"
    )
    assert target_host_for(("git", "fetch", "git@github.com:owner/repo.git")) == "github.com"
    assert target_host_for(("git", "fetch", "/tmp/repo/repo.git")) is None
    assert fallback_reason_for("The requested URL returned error: 407") == "407"
    assert fallback_reason_for("fatal: Proxy CONNECT aborted") == "tunnel"
    assert fallback_reason_for("fatal: operation timed out") == "timeout"
    assert fallback_reason_for("fatal: unable to access: Failed to connect") == "proxy_connect"
    assert (
        is_proxy_traffic(("git", "clone", "--no-checkout", "--", "/tmp/cache", "/tmp/ws")) is False
    )
    assert is_proxy_traffic(("git", "clone", "https://github.com/o/r.git", "/tmp/ws")) is True
    assert is_proxy_traffic(("git", "fetch", "origin")) is True


def test_operation_collector_bounds_the_event_list() -> None:
    """The event list is capped and marked truncated, without secrets."""
    collector = GitOperationCollector(run_id="run-bound")
    for index in range(25):
        collector.add(
            GitOperationRecord(
                operation="fetch",
                via_proxy=True,
                proxy_state_before="closed",
                proxy_state_after="closed",
                fallback_reason=None,
                duration_ms=index,
                exit_code=0,
                target_host="github.com",
            ),
        )

    payload, truncated = collector.bounded()

    assert len(payload) == 20
    assert truncated is True
    assert collector.proxy_state == "closed"
    assert all(item["targetHost"] == "github.com" for item in payload)


async def test_workspace_prepared_event_carries_observability() -> None:
    """The prepare service projects cache and proxy facts into the durable event."""
    from app.service.evolution.prepare import EvolutionPrepareService
    from app.third_party_api.git.workspace import PreparedWorkspace

    recorded: list[dict[str, object]] = []

    class FakeEvents:
        async def record(self, run_id: str, event_type: str, **kwargs: object) -> object:
            recorded.append(
                {
                    "run_id": run_id,
                    "event_type": event_type,
                    **kwargs,
                },
            )
            return object()

    class FakeWorkspaces:
        async def prepare(self, run: EvolutionRunRecord) -> PreparedWorkspace:
            emit_git_operation(
                GitOperationRecord(
                    operation="fetch",
                    via_proxy=True,
                    proxy_state_before="closed",
                    proxy_state_after="closed",
                    fallback_reason=None,
                    duration_ms=12,
                    exit_code=0,
                    target_host="github.com",
                ),
            )
            return PreparedWorkspace(
                repo_path=Path("/tmp/cache"),
                path=Path("/tmp/workspace"),
                ref=run.target_version,
                base_commit="a" * 40,
                branch=f"evo/20261120-{run.id}",
                cache_hit=True,
                clone_seconds=1.2345,
            )

    service = EvolutionPrepareService(
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        object(),  # type: ignore[arg-type]
        FakeWorkspaces(),
        FakeEvents(),
    )
    run = _run("https://github.com/owner/repo.git", "v2.0.0", run_id="run-event")
    job = replace_job(run.id)

    await service._prepare_workspace(run, job)

    assert len(recorded) == 1
    payload = recorded[0]["payload"]
    assert isinstance(payload, dict)
    assert payload["ref"] == "v2.0.0"
    assert payload["cacheHit"] is True
    assert payload["cloneSeconds"] == 1.234
    assert payload["proxyState"] == "closed"
    assert payload["gitOperationsTruncated"] is False
    operations = payload["gitOperations"]
    assert isinstance(operations, list)
    assert operations[0]["operation"] == "fetch"
    assert operations[0]["viaProxy"] is True


def replace_job(run_id: str) -> JobRunRecord:
    """Build one prepare job row for the event projection test."""
    return JobRunRecord(
        id="job-event",
        kind="evolution_prepare",
        ref_id=run_id,
        status="running",
        progress=0.0,
        executor="test",
        external_job_id=None,
        attempt=1,
        payload={"runId": run_id},
        result=None,
        error=None,
        created_by=None,
        created_at=NOW,
        started_at=NOW,
        finished_at=None,
        updated_at=NOW,
    )


async def _healthy_probe() -> bool:
    return True
