from __future__ import annotations

import base64
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location(
    "inject_config",
    ROOT / "deploy" / "inject-config.py",
)
assert SPEC is not None and SPEC.loader is not None
inject_config = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inject_config)


def encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


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


class _Stdin:
    def __init__(self, value: str) -> None:
        self._value = value

    def read(self) -> str:
        return self._value
