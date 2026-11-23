from __future__ import annotations

import base64
import importlib.util
import io
import json
import stat
import subprocess
from pathlib import Path
from typing import Any

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
    with pytest.raises(ValueError, match="https"):
        install_claude_code.validate_base_url("http://api.example.com")
    assert install_claude_code.validate_base_url("http://127.0.0.1:8080") == "http://127.0.0.1:8080"


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
    onboarding_path = home / ".claude.json"
    assert key_path.read_text(encoding="utf-8") == "sk-secret-value"
    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(settings_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(helper_path.stat().st_mode) == 0o700
    assert stat.S_IMODE(onboarding_path.stat().st_mode) == 0o600
    assert json.loads(onboarding_path.read_text(encoding="utf-8"))["hasCompletedOnboarding"] is True
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


def test_clean_versions_keeps_protected_older_version(tmp_path: Path) -> None:
    prefix = tmp_path / "claude-code"
    prefix.mkdir()
    for name in ("2.1.1-1", "2.1.2-1", "2.1.3-1"):
        (prefix / name).mkdir()

    install_claude_code.clean_versions(prefix, 2, protected=prefix / "2.1.1-1")

    assert (prefix / "2.1.1-1").exists()
    assert (prefix / "2.1.3-1").exists()
    assert not (prefix / "2.1.2-1").exists()


def test_configure_requires_base_url_for_minimax(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    with pytest.raises(ValueError, match="MiniMax models require"):
        install_claude_code.configure(
            {
                "CLAUDE_CODE_MODEL": "MiniMax-M3.1-Flash[1m]",
                "CLAUDE_CODE_API_KEY": "sk-test",
            },
            home,
        )


def test_configure_preserves_existing_claude_json(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text('{"existing": 1}\n', encoding="utf-8")

    install_claude_code.configure(
        {
            "CLAUDE_CODE_MODEL": "claude-sonnet-5",
            "CLAUDE_CODE_API_KEY": "sk-test",
        },
        home,
    )

    data = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    assert data == {"existing": 1, "hasCompletedOnboarding": True}


def test_build_shared_settings_has_no_credential(tmp_path: Path) -> None:
    settings = install_claude_code.build_shared_settings(
        "MiniMax-M3.1-Flash[1m]",
        "https://api.minimax.cn/anthropic",
    )

    assert settings["model"] == "MiniMax-M3.1-Flash[1m]"
    assert "apiKeyHelper" not in settings
    assert settings["env"]["ANTHROPIC_BASE_URL"] == "https://api.minimax.cn/anthropic"
    assert settings["env"]["CLAUDE_CODE_EFFORT_LEVEL"] == "max"


def test_configure_shared_writes_service_readable_settings(tmp_path: Path) -> None:
    prefix = tmp_path / "claude-code"
    path = install_claude_code.configure_shared(
        {
            "CLAUDE_CODE_MODEL": "MiniMax-M3.1-Flash[1m]",
            "CLAUDE_CODE_API_KEY": "sk-secret-value",
            "CLAUDE_CODE_BASE_URL": "https://api.minimax.cn/anthropic",
        },
        prefix,
    )

    assert path == prefix / "config" / "settings.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o644
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o755
    text = path.read_text(encoding="utf-8")
    assert "sk-secret-value" not in text
    assert "apiKeyHelper" not in text
    assert json.loads(text)["model"] == "MiniMax-M3.1-Flash[1m]"


def test_configure_shared_requires_model_and_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="required"):
        install_claude_code.configure_shared({"CLAUDE_CODE_MODEL": "model"}, tmp_path)


def test_switch_current_is_a_relative_atomic_link(tmp_path: Path) -> None:
    prefix = tmp_path / "claude-code"
    binary = prefix / "2.1.323-1" / "usr" / "bin" / "claude"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    current = install_claude_code.switch_current(binary, prefix)

    assert current.is_symlink()
    assert current.readlink().as_posix() == "2.1.323-1"
    assert (current / "usr" / "bin" / "claude").resolve() == binary


def test_preflight_accepts_service_readable_assets(tmp_path: Path) -> None:
    prefix, binary, settings = seed_shared_assets(tmp_path)

    install_claude_code.preflight_shared_access(binary, settings, prefix)


def test_preflight_rejects_unreadable_settings(tmp_path: Path) -> None:
    prefix, binary, settings = seed_shared_assets(tmp_path)
    settings.chmod(0o600)

    with pytest.raises(RuntimeError, match="not readable"):
        install_claude_code.preflight_shared_access(binary, settings, prefix)


def test_preflight_rejects_non_executable_binary(tmp_path: Path) -> None:
    prefix, binary, settings = seed_shared_assets(tmp_path)
    binary.chmod(0o644)

    with pytest.raises(RuntimeError, match="not executable"):
        install_claude_code.preflight_shared_access(binary, settings, prefix)


def test_write_atomic_does_not_chmod_an_existing_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(mode=0o755)
    home.chmod(0o755)

    install_claude_code.write_atomic(home / ".claude.json", "{}\n", 0o600)

    assert stat.S_IMODE(home.stat().st_mode) == 0o755


def seed_shared_assets(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a prefix whose whole chain is service-readable."""
    prefix = tmp_path / "claude-code"
    binary = prefix / "2.1.323-1" / "usr" / "bin" / "claude"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755)
    settings = prefix / "config" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{}\n", encoding="utf-8")
    settings.chmod(0o644)
    for directory in (
        tmp_path,
        prefix,
        prefix / "2.1.323-1",
        prefix / "2.1.323-1" / "usr",
        prefix / "2.1.323-1" / "usr" / "bin",
        prefix / "config",
    ):
        directory.chmod(0o755)
    return prefix, binary, settings


def test_preflight_rejects_untraversable_version_chain(tmp_path: Path) -> None:
    prefix, binary, settings = seed_shared_assets(tmp_path)
    for relative in ("2.1.323-1", "2.1.323-1/usr", "2.1.323-1/usr/bin"):
        directory = prefix / relative
        directory.chmod(0o700)

        with pytest.raises(RuntimeError, match="not traversable") as error:
            install_claude_code.preflight_shared_access(binary, settings, prefix)

        assert str(directory) in str(error.value)
        directory.chmod(0o755)


def test_repair_service_access_fixes_an_existing_version_directory(tmp_path: Path) -> None:
    prefix, binary, settings = seed_shared_assets(tmp_path)
    version = prefix / "2.1.323-1"
    for directory in (version, version / "usr", version / "usr" / "bin"):
        directory.chmod(0o700)

    install_claude_code.repair_service_access(binary, prefix)

    for directory in (prefix, version, version / "usr", version / "usr" / "bin"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o755
    assert stat.S_IMODE(binary.stat().st_mode) == 0o755
    install_claude_code.preflight_shared_access(binary, settings, prefix)


def test_install_from_deb_repairs_an_existing_version_directory(tmp_path: Path) -> None:
    prefix, binary, _ = seed_shared_assets(tmp_path)
    (prefix / "2.1.323-1").chmod(0o700)

    installed = install_claude_code.install_from_deb(
        tmp_path / "missing.deb", "2.1.323-1", prefix, tmp_path
    )

    assert installed == binary
    assert stat.S_IMODE((prefix / "2.1.323-1").stat().st_mode) == 0o755


def test_install_from_deb_sets_service_traversable_version_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prefix = tmp_path / "claude-code"
    home = tmp_path / "home"
    home.mkdir()
    deb = tmp_path / "claude-code.deb"
    deb.write_bytes(b"")
    real_run = subprocess.run

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[0] == "dpkg-deb":
            staging = Path(command[3])
            extracted = staging / "usr/bin/claude"
            extracted.parent.mkdir(parents=True)
            extracted.write_text("#!/bin/sh\necho '2.1.323 (Claude Code)'\n", encoding="utf-8")
            extracted.chmod(0o755)
            return subprocess.CompletedProcess(command, 0, "", "")
        return real_run(command, **kwargs)

    monkeypatch.setattr(install_claude_code.subprocess, "run", fake_run)

    binary = install_claude_code.install_from_deb(deb, "2.1.323-1", prefix, home)

    version = prefix / "2.1.323-1"
    assert binary == version / "usr" / "bin" / "claude"
    for directory in (version, version / "usr", version / "usr" / "bin"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o755


def test_main_configure_only_repairs_the_existing_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    prefix = tmp_path / "claude-code"
    version = prefix / "2.1.323-1"
    binary = version / "usr" / "bin" / "claude"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\necho '2.1.323 (Claude Code)'\n", encoding="utf-8")
    binary.chmod(0o755)
    for directory in (prefix, version, version / "usr", version / "usr" / "bin"):
        directory.chmod(0o755)
    version.chmod(0o700)
    launcher = home / ".local" / "bin" / "claude"
    launcher.parent.mkdir(parents=True)
    launcher.symlink_to(binary)

    entries = "\n".join(
        [
            f"CLAUDE_CODE_MODEL {encode('claude-sonnet-5')}",
            f"CLAUDE_CODE_API_KEY {encode('sk-test')}",
        ]
    )
    monkeypatch.setattr(install_claude_code.sys, "stdin", io.StringIO(entries))

    exit_code = install_claude_code.main(
        ["--version", "2.1.323-1", "--prefix", str(prefix), "--home", str(home)]
    )

    assert exit_code == 0
    assert stat.S_IMODE(version.stat().st_mode) == 0o755
