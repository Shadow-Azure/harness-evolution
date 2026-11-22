from __future__ import annotations

import base64
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
AI_AGENT_VALUES = {
    "AI_AGENT_PROVIDER": "claude-code",
    "HE_AI_AGENT_CLAUDE_BIN": "/opt/harness/.local/bin/claude",
    "HE_PATCH_SOURCE_MODE": "minimal-config",
}
SPEC = importlib.util.spec_from_file_location(
    "inject_config",
    ROOT / "deploy" / "inject-config.py",
)
assert SPEC is not None and SPEC.loader is not None
inject_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inject_config)


def encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def write_ai_agent_env(target: Path) -> None:
    """Seed the env file with stale AI Agent values plus a stable data-dir key."""
    target.write_text(
        "HE_DATA_DIR=/var/lib/harness-evolution/data\n"
        "AI_AGENT_PROVIDER=fake\n"
        "HE_AI_AGENT_CLAUDE_BIN=/usr/local/bin/claude\n"
        "HE_PATCH_SOURCE_MODE=placeholder\n",
        encoding="utf-8",
    )


@pytest.fixture
def target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".env"
    path.write_text(
        "HE_DATA_DIR=/var/lib/harness-evolution/data\nHE_GIT_PROXY=http://127.0.0.1:10808\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(inject_config, "TARGET", str(path))
    return path


def test_rewrite_replaces_and_appends(target: Path) -> None:
    inject_config.rewrite_env({"HE_GIT_PROXY": "http://127.0.0.1:10809", "HE_EVAL_MODE": "fake"})

    text = target.read_text(encoding="utf-8")
    assert "HE_GIT_PROXY=http://127.0.0.1:10809" in text
    assert "HE_EVAL_MODE=fake" in text
    assert text.count("HE_GIT_PROXY=") == 1


def test_rewrite_removes_unset_key(target: Path) -> None:
    inject_config.rewrite_env({"HE_EVAL_MODE": "fake"}, {"HE_GIT_PROXY"})

    text = target.read_text(encoding="utf-8")
    assert "HE_GIT_PROXY" not in text
    assert "HE_EVAL_MODE=fake" in text


def test_rewrite_writes_all_ai_agent_keys(target: Path) -> None:
    inject_config.rewrite_env(dict(AI_AGENT_VALUES))

    text = target.read_text(encoding="utf-8")
    for key, value in AI_AGENT_VALUES.items():
        assert f"{key}={value}" in text
    assert text.count("AI_AGENT_PROVIDER=") == 1
    assert "HE_DATA_DIR=/var/lib/harness-evolution/data" in text


def test_rewrite_unsets_all_ai_agent_keys(target: Path) -> None:
    write_ai_agent_env(target)
    inject_config.rewrite_env({}, set(AI_AGENT_VALUES))

    text = target.read_text(encoding="utf-8")
    for key in AI_AGENT_VALUES:
        assert key not in text
    assert "HE_DATA_DIR=/var/lib/harness-evolution/data" in text


def test_rewrite_partially_updates_ai_agent_keys(target: Path) -> None:
    write_ai_agent_env(target)
    inject_config.rewrite_env(
        {"AI_AGENT_PROVIDER": "fake"},
        {"HE_AI_AGENT_CLAUDE_BIN", "HE_PATCH_SOURCE_MODE"},
    )

    text = target.read_text(encoding="utf-8")
    assert text.count("AI_AGENT_PROVIDER=") == 1
    assert "AI_AGENT_PROVIDER=fake" in text
    assert "HE_AI_AGENT_CLAUDE_BIN" not in text
    assert "HE_PATCH_SOURCE_MODE" not in text
    assert "HE_DATA_DIR=/var/lib/harness-evolution/data" in text


def test_main_backs_up_and_unsets(target: Path, tmp_path: Path) -> None:
    backup = tmp_path / "env.bak"
    stdin = f"HE_EVAL_MODE {encode('http')}\n"
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("sys.stdin", _Stdin(stdin))
        assert inject_config.main(["--backup", str(backup), "--unset", "HE_GIT_PROXY"]) == 0

    assert backup.exists()
    text = target.read_text(encoding="utf-8")
    assert "HE_GIT_PROXY" not in text
    assert "HE_EVAL_MODE=http" in text


def test_main_keeps_file_when_nothing_to_do(
    target: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("sys.stdin", _Stdin(""))
        assert inject_config.main([]) == 0

    assert target.read_text(encoding="utf-8").count("HE_GIT_PROXY=") == 1
    assert "无可用配置" in capsys.readouterr().out


def test_workflow_wires_ai_agent_secrets() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"- name: 注入部署配置.*?(?=\n\s*- name: |\Z)", workflow, re.S)
    assert match is not None, "deploy.yml 缺少配置注入步骤"
    step = match.group(0)
    for key in AI_AGENT_VALUES:
        assert re.search(rf"secrets\.{key}\b", step), f"{key} 未从 Secrets 读取"
        assert re.search(rf'ENTRIES\+=\("{key}\s', step), f"{key} 未追加到 ENTRIES"
        assert re.search(rf"UNSET_ARGS=.*--unset\s+{key}\b", step), f"{key} 缺少 --unset 分支"


class _Stdin:
    def __init__(self, value: str) -> None:
        self._value = value

    def read(self) -> str:
        return self._value
