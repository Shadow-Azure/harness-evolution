"""Patch source seam: placeholder and minimal-config patches side by side."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.db.models.evolution import EvolutionRunRecord
from app.service.evolution.engine.contracts import ConfigError
from app.service.evolution.git_candidate import CandidateSource, CandidateTrace
from app.service.evolution.patch_source import (
    MinimalConfigPatchSource,
    PatchSource,
    PlaceholderPatchSource,
    default_patch_source_factory,
)
from app.third_party_api.git.workspace import GitWorkspaceManager, Patch

NOW = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)


def _run(
    *,
    workspace_path: Path | None = None,
    eval_config: dict[str, object] | None = None,
    sub_dir: str = "skills/deep-research",
) -> EvolutionRunRecord:
    """Build one run snapshot for patch source selection."""
    return EvolutionRunRecord(
        id="run-m12-03",
        title="deep-research evolution",
        mode="full",
        engine_key="full",
        eval_config=eval_config or {},
        target_config_id="target-m12-03",
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        repo_url="https://example.invalid/repo.git",
        sub_dir=sub_dir,
        repo_path=None,
        base_ref="v2.0.0",
        base_commit="a" * 40,
        branch_name=None,
        workspace_path=str(workspace_path) if workspace_path else None,
        remote_name="origin",
        push_status="pending",
        pushed_at=None,
        push_error=None,
        window_from=None,
        window_to=None,
        models=[],
        status="running",
        blocked_stage=None,
        retry_attempts=0,
        next_retry_at=None,
        eval_status="pending",
        error_stage=None,
        error_message=None,
        error_at=None,
        progress_unit=4,
        stats={},
        created_by=None,
        created_at=NOW,
        finished_at=None,
    )


def _trace(text: str, title: str = "对象行为异常") -> CandidateTrace:
    """Build one trace whose analysis carries the bad-case evidence text."""
    return CandidateTrace(
        cluster_id="C1",
        cluster_title=title,
        probes=("probe-1",),
        bad_cases=("bc-050b-03",),
        analysis=text,
        sources=(
            CandidateSource(
                probe_id="probe-1",
                bad_case_ids=("bc-050b-03",),
                description=text,
            ),
        ),
    )


async def test_placeholder_source_reproduces_the_v1_patch() -> None:
    """The placeholder source keeps the existing V1 patch shape and note."""
    source = PlaceholderPatchSource()

    patch = await source.build(_run(), 1, _trace("未校验快照字段"))

    assert isinstance(source, PatchSource)
    assert patch.file == "skills/deep-research/.harness-evolution/candidate-r1.md"
    assert patch.overwrite is False
    assert any("V1 patch" in line for line in patch.lines)
    assert await source.change_note(_run(), 1, _trace("x")) == (
        "V1 占位 patch；真实文件已写入 isolated workspace"
    )


@pytest.mark.parametrize(
    ("text", "key", "value"),
    [
        ("下游服务响应 timeout 频繁出现", "requestTimeoutSeconds", 30),
        ("调用上游时 retry 次数不足导致失败", "maxRetries", 3),
        ("检索索引读取失败 ENOENT，读取前未校验", "snapshotFieldCheckEnabled", True),
        ("空间权限 forbidden 导致写配置失败", "permissionCheckEnabled", True),
        ("未命中任何已知规则的混合故障描述", "harnessGuardEnabled", True),
    ],
)
async def test_minimal_config_source_maps_bad_case_to_one_key(
    tmp_path: Path,
    text: str,
    key: str,
    value: object,
) -> None:
    """The minimal-config source turns bad-case text into one config key."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    source = MinimalConfigPatchSource()

    patch = await source.build(_run(workspace_path=workspace), 2, _trace(text))

    assert patch.file == "skills/deep-research/config/deep-research.json"
    assert patch.overwrite is True
    document = json.loads("\n".join(patch.lines))
    assert document == {key: value}
    note = await source.change_note(_run(workspace_path=workspace), 2, _trace(text))
    assert key in note
    assert "config/deep-research.json" in note


async def test_minimal_config_source_merges_existing_config(
    tmp_path: Path,
) -> None:
    """An existing config file keeps its keys and gains only the new one."""
    workspace = tmp_path / "ws"
    target_dir = workspace / "skills" / "deep-research" / "config"
    target_dir.mkdir(parents=True)
    (target_dir / "deep-research.json").write_text(
        json.dumps({"maxRetries": 2}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    source = MinimalConfigPatchSource()

    patch = await source.build(
        _run(workspace_path=workspace),
        1,
        _trace("检索索引读取失败"),
    )

    document = json.loads("\n".join(patch.lines))
    assert document == {"maxRetries": 2, "snapshotFieldCheckEnabled": True}


async def test_minimal_config_source_sanitizes_target_names(tmp_path: Path) -> None:
    """Target names cannot escape the workspace through the config path."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    source = MinimalConfigPatchSource()

    patch = await source.build(
        replace(_run(workspace_path=workspace), target_name="../../escape"),
        1,
        _trace("混合故障"),
    )

    relative = Path(patch.file)
    assert not relative.is_absolute()
    assert ".." not in relative.parts
    assert patch.file.endswith("config/-.json") or patch.file.count("/") >= 2


async def test_minimal_config_source_rejects_corrupt_existing_config(
    tmp_path: Path,
) -> None:
    """A broken existing config fails the patch stage instead of being clobbered."""
    workspace = tmp_path / "ws"
    target_dir = workspace / "skills" / "deep-research" / "config"
    target_dir.mkdir(parents=True)
    (target_dir / "deep-research.json").write_text("{not json", encoding="utf-8")
    source = MinimalConfigPatchSource()

    with pytest.raises(ConfigError, match="config"):
        await source.build(
            _run(workspace_path=workspace),
            1,
            _trace("检索索引读取失败"),
        )


def test_factory_selects_source_from_run_snapshot_or_fallback() -> None:
    """Run snapshot mode wins; env fallback applies when the snapshot omits it."""
    minimal = default_patch_source_factory(
        _run(eval_config={"patchMode": "minimal-config"}),
        fallback_mode="placeholder",
    )
    fallback = default_patch_source_factory(_run(), fallback_mode="placeholder")
    default = default_patch_source_factory(_run())

    assert isinstance(minimal, MinimalConfigPatchSource)
    assert isinstance(fallback, PlaceholderPatchSource)
    assert isinstance(default, PlaceholderPatchSource)


def test_factory_rejects_unknown_modes_explicitly() -> None:
    """Unknown patch modes fail loudly instead of silently degrading."""
    with pytest.raises(ConfigError, match="patch"):
        default_patch_source_factory(
            _run(eval_config={"patchMode": "llm"}),
            fallback_mode="placeholder",
        )
    with pytest.raises(ConfigError, match="patch"):
        default_patch_source_factory(_run(), fallback_mode="llm")


def test_settings_patch_source_mode_validates_choices() -> None:
    """The env-backed fallback only accepts the registered source modes."""
    settings = Settings(jwt_secret=SecretStr("m12-03-secret"), patch_source_mode="minimal-config")
    assert settings.patch_source_mode == "minimal-config"
    with pytest.raises(Exception):
        Settings(jwt_secret=SecretStr("m12-03-secret"), patch_source_mode="llm")


def test_write_patch_overwrite_replaces_file_content(tmp_path: Path) -> None:
    """Overwrite patches replace content; the default append behavior is intact."""
    target = tmp_path / "config" / "app.json"
    target.parent.mkdir()
    target.write_text('{"keep": 1}\n', encoding="utf-8")

    GitWorkspaceManager._write_patch(
        tmp_path,
        Patch(file="config/app.json", lines=('{"keep": 1,', '  "new": 2}'), overwrite=True),
    )
    assert json.loads(target.read_text(encoding="utf-8")) == {"keep": 1, "new": 2}

    GitWorkspaceManager._write_patch(
        tmp_path,
        Patch(file="config/append.md", lines=("appended",)),
    )
    assert (tmp_path / "config" / "append.md").read_text(encoding="utf-8") == "appended\n"
