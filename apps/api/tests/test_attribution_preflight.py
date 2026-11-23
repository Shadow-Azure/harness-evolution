"""Offline coverage for Skill readiness and the release gate before migrations."""

import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.config import Settings
from app.third_party_api.ai_agent import build_agent_provider, claude_skill
from app.third_party_api.ai_agent.base import SKILL_UNSUPPORTED
from app.third_party_api.ai_agent.preflight import main


def test_provider_capability_skips_unneeded_linux_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    lookup = Mock(side_effect=AssertionError("unexpected sandbox lookup"))
    monkeypatch.setattr(claude_skill, "shutil", SimpleNamespace(which=lookup))
    monkeypatch.setattr(claude_skill, "sys", SimpleNamespace(platform="linux"))
    assert (
        build_agent_provider(Settings(ai_agent_provider="fake")).skill_preflight_error()
        == SKILL_UNSUPPORTED
    )
    monkeypatch.setattr(claude_skill, "sys", SimpleNamespace(platform="darwin"))
    assert (
        build_agent_provider(Settings(ai_agent_provider="claude-code")).skill_preflight_error()
        is None
    )
    lookup.assert_not_called()


def test_invalid_preflight_settings_do_not_disclose_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AI_AGENT_PROVIDER", "sensitive-invalid-fixture")
    assert main() == 1
    assert (
        capsys.readouterr().err.strip()
        == "attribution.preflight error_code=ATTRIBUTION_CONFIG_INVALID"
    )


def _script(path: Path, source: str) -> None:
    path.write_text(source)
    path.chmod(0o755)


@pytest.mark.parametrize(
    ("provider", "bwrap_exit", "expected"),
    [
        (None, None, "ATTRIBUTION_BWRAP_MISSING"),
        ("claude-code", 1, "ATTRIBUTION_BWRAP_UNUSABLE"),
        ("claude-code", 0, "ready=True"),
        ("fake", None, "cache_only=True"),
    ],
)
def test_release_checks_candidate_before_switch_or_migration(
    tmp_path: Path, provider: str | None, bwrap_exit: int | None, expected: str
) -> None:
    root = Path(__file__).resolve().parents[3]
    shared = tmp_path / "shared"
    tools = tmp_path / "commands"
    venv = shared / "venv/bin"
    config = shared / "config"
    release = tmp_path / "releases/candidate"
    api = release / "api"
    previous = tmp_path / "releases/previous"
    for folder in (tools, venv, config, api, previous):
        folder.mkdir(parents=True)
    current = tmp_path / "current"
    current.symlink_to(previous, target_is_directory=True)
    (api / "app").symlink_to(root / "apps/api/app", target_is_directory=True)
    (api / "alembic.ini").write_text("[alembic]\n")
    (api / "release-assets").mkdir()
    (api / "release-assets/SKILL.md").write_text("# Synthetic Skill\n")
    (config / "attribution-assets.list").write_text("SKILL.md\n")
    script = tmp_path / "release.sh"
    script.write_text(
        (root / "deploy/release.sh").read_text().replace("/opt/harness", str(tmp_path))
    )
    for name in ("bash", "basename", "sed", "tail", "readlink", "cp", "rm"):
        system_binary = shutil.which(name)
        assert system_binary is not None
        (tools / name).symlink_to(system_binary)
    _script(tools / "systemctl", '#!/bin/sh\n[ "$1" = show ] && echo he-preflight-test\n')
    if bwrap_exit is not None:
        _script(tools / "bwrap", f"#!/bin/sh\nexit {bwrap_exit}\n")
    _script(venv / "pip", "#!/bin/sh\nexit 0\n")
    reached_migration = tmp_path / "migration-invoked"
    _script(venv / "alembic", f"#!/bin/sh\n: > {shlex.quote(str(reached_migration))}\nexit 77\n")
    # Run the actual candidate command and PATH lookup on Linux and macOS test hosts.
    _script(
        venv / "python",
        f"#!{sys.executable}\n"
        + """
import os, runpy, sys
from types import SimpleNamespace
sys.path.insert(0, os.getcwd())
from app.third_party_api.ai_agent import claude_skill
claude_skill.sys = SimpleNamespace(platform="linux")
assert sys.argv[1:] == ["-m", "app.third_party_api.ai_agent.preflight"]
runpy.run_module(sys.argv[2], run_name="__main__")
""",
    )
    env_file = shared / ".env"
    env_file.write_text(
        "HE_DATA_DIR=/var/lib/he-preflight-test\nHE_JWT_SECRET=fixture-signing-secret\nHE_DB_URL=sqlite:///fixture\n"
        + (f"AI_AGENT_PROVIDER={provider}\n" if provider else "")
    )
    backup = shared / ".env.bak.candidate"
    backup.write_text("previous-release-environment\n")
    result = subprocess.run(  # noqa: S603 - isolated copy of the release script and fixture commands.
        [str(tools / "bash"), str(script), str(release)],
        cwd=tmp_path,
        env={"PATH": str(tools), "LC_ALL": "C"},
        capture_output=True,
        text=True,
        timeout=25,
    )
    output = result.stdout + result.stderr
    assert expected in output, output
    assert "fixture-signing-secret" not in output
    blocked = expected.startswith("ATTRIBUTION_")
    assert result.returncode == (1 if blocked else 77), output
    assert reached_migration.exists() is not blocked
    assert current.resolve() == previous
    assert env_file.read_text() == "previous-release-environment\n"
