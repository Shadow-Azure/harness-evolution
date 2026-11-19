from __future__ import annotations

import base64
import importlib.util
import json
import stat
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SPEC = importlib.util.spec_from_file_location(
    "install_claude_code",
    ROOT / "deploy" / "install-claude-code.py",
)
assert SPEC is not None and SPEC.loader is not None
install_claude_code = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(install_claude_code)


def encode(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def test_decode_entries_round_trips() -> None:
    decoded = install_claude_code.decode_entries(
        [
            f"CLAUDE_CODE_MODEL {encode('MiniMax-M3.1-Flash[1m]')}",
            f"CLAUDE_CODE_API_KEY {encode('sk-test')}",
            "",
        ]
    )

    assert decoded["CLAUDE_CODE_MODEL"] == "MiniMax-M3.1-Flash[1m]"
    assert decoded["CLAUDE_CODE_API_KEY"] == "sk-test"


def test_decode_entries_rejects_invalid_and_multiline_values() -> None:
    with pytest.raises(ValueError, match="base64"):
        install_claude_code.decode_entries(["CLAUDE_CODE_API_KEY not-base64!"])
    with pytest.raises(ValueError, match="newline"):
        install_claude_code.decode_entries([f"CLAUDE_CODE_API_KEY {encode('a\nb')}"])
    with pytest.raises(ValueError, match="KEY <base64>"):
        install_claude_code.decode_entries(["CLAUDE_CODE_API_KEY"])


def test_version_helpers() -> None:
    assert install_claude_code.normalize_version("2.1.311-1") == "2.1.311"
    assert install_claude_code.normalize_version("v2.1.311") == "2.1.311"
    assert install_claude_code.cli_version("2.1.311 (Claude Code)") == "2.1.311"
    assert install_claude_code.cli_version("not a version") is None


def test_validate_base_url() -> None:
    assert (
        install_claude_code.validate_base_url("https://api.minimax.cn/anthropic")
        == "https://api.minimax.cn/anthropic"
    )
    assert install_claude_code.validate_base_url("") is None
    with pytest.raises(ValueError, match="http"):
        install_claude_code.validate_base_url("ftp://api.example.com")
    with pytest.raises(ValueError, match="credentials"):
        install_claude_code.validate_base_url("https://user:pass@api.example.com")
    with pytest.raises(ValueError, match="whitespace"):
        install_claude_code.validate_base_url("https://api.example.com/a b")


def test_build_settings_official_endpoint_has_no_gateway_env(tmp_path: Path) -> None:
    settings = install_claude_code.build_settings("claude-sonnet-5", None, tmp_path)
    env = settings["env"]

    assert settings["model"] == "claude-sonnet-5"
    assert settings["apiKeyHelper"] == str(tmp_path / ".claude" / "api-key.sh")
    assert env == {"DISABLE_AUTOUPDATER": "1"}
    assert "CLAUDE_CODE_API_KEY" not in json.dumps(settings)


def test_build_settings_minimax_uses_documented_defaults(tmp_path: Path) -> None:
    model = "MiniMax-M3.1-Flash[1m]"
    settings = install_claude_code.build_settings(
        model, "https://api.minimax.cn/anthropic", tmp_path
    )
    env = settings["env"]

    assert env["ANTHROPIC_BASE_URL"] == "https://api.minimax.cn/anthropic"
    assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == model
    assert env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == model
    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == model
    assert env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] == "524288"
    assert env["CLAUDE_CODE_EFFORT_LEVEL"] == "max"
    assert "CLAUDE_CODE_API_KEY" not in json.dumps(settings)


def test_build_settings_generic_gateway_sets_aliases_without_minimax_defaults(
    tmp_path: Path,
) -> None:
    model = "custom-model"
    settings = install_claude_code.build_settings(model, "https://gateway.example.com", tmp_path)
    env = settings["env"]

    assert env["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == model
    assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" not in env
    assert "CLAUDE_CODE_EFFORT_LEVEL" not in env


def test_write_atomic_sets_permissions(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    install_claude_code.write_atomic(path, "{}\n", 0o600)

    assert path.read_text(encoding="utf-8") == "{}\n"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_configure_keeps_key_out_of_settings(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    entries = {
        "CLAUDE_CODE_MODEL": "MiniMax-M3.1-Flash[1m]",
        "CLAUDE_CODE_API_KEY": "sk-secret-value",
        "CLAUDE_CODE_BASE_URL": "https://api.minimax.cn/anthropic",
    }

    settings_path = install_claude_code.configure(entries, home)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert settings["model"] == "MiniMax-M3.1-Flash[1m]"
    assert settings["env"]["ANTHROPIC_BASE_URL"] == "https://api.minimax.cn/anthropic"
    assert "sk-secret-value" not in settings_path.read_text(encoding="utf-8")

    key_path = home / ".claude" / "api-key"
    helper_path = home / ".claude" / "api-key.sh"
    assert key_path.read_text(encoding="utf-8") == "sk-secret-value"
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(settings_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(helper_path.stat().st_mode) == 0o700
    assert str(key_path) in helper_path.read_text(encoding="utf-8")


def test_configure_requires_model_and_key(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    with pytest.raises(ValueError, match="required"):
        install_claude_code.configure({"CLAUDE_CODE_MODEL": "model"}, home)


def test_clean_versions_keeps_newest_and_ignores_incoming(tmp_path: Path) -> None:
    prefix = tmp_path / "claude-code"
    prefix.mkdir()
    for name in ("2.1.1-1", "2.1.2-1", "2.1.3-1", "incoming"):
        (prefix / name).mkdir()

    install_claude_code.clean_versions(prefix, 2)

    assert not (prefix / "2.1.1-1").exists()
    assert (prefix / "2.1.2-1").exists()
    assert (prefix / "2.1.3-1").exists()
    assert (prefix / "incoming").exists()
