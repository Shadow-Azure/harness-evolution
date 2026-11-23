from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ASKPASS = ROOT / "deploy" / "git-askpass.sh"
TOKEN = "s3cr3t-token-value"  # noqa: S105 - test-only PAT value


def run_askpass(prompt: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    base_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HE_GIT_PUSH_TOKEN": TOKEN,
    }
    base_env.update(env)
    return subprocess.run(  # noqa: S603 - fixed local script and argv
        [str(ASKPASS), prompt],
        capture_output=True,
        check=False,
        env=base_env,
        text=True,
    )


def test_username_prompt_uses_default() -> None:
    result = run_askpass("Username for 'https://github.com': ", {})

    assert result.returncode == 0
    assert result.stdout == "x-access-token\n"
    assert result.stderr == ""


def test_username_prompt_honors_override() -> None:
    result = run_askpass("Username for 'https://gitlab.com': ", {"HE_GIT_PUSH_USERNAME": "oauth2"})

    assert result.returncode == 0
    assert result.stdout == "oauth2\n"
    assert result.stderr == ""


def test_password_prompt_prints_token() -> None:
    result = run_askpass("Password for 'https://x-access-token@github.com': ", {})

    assert result.returncode == 0
    assert result.stdout == TOKEN + "\n"
    assert result.stderr == ""
    assert TOKEN not in result.stderr


def test_unknown_prompt_fails_without_leaking_token() -> None:
    result = run_askpass("Passphrase for key: ", {})

    assert result.returncode != 0
    assert result.stdout == ""
    assert TOKEN not in result.stderr


def test_missing_prompt_fails() -> None:
    base_env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HE_GIT_PUSH_TOKEN": TOKEN,
    }
    result = subprocess.run(  # noqa: S603 - fixed local script and argv
        [str(ASKPASS)],
        capture_output=True,
        check=False,
        env=base_env,
        text=True,
    )

    assert result.returncode != 0
    assert result.stdout == ""
