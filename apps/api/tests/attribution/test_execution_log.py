"""Claude stdout and visible session history survive cleanup through the backend hook."""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from app.third_party_api.ai_agent import (
    ClaudeCodeProvider,
    SkillRunRequest,
    build_agent_provider,
    claude_skill,
)


@pytest.mark.parametrize("exit_code", [0, 1])
async def test_claude_result_and_visible_turns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    executable = tmp_path / "claude"
    executable.write_text(
        """#!/usr/bin/env python3
import json, os, pathlib, sys
session = sys.argv[sys.argv.index('--session-id')+1]
project = pathlib.Path(os.environ['CLAUDE_CONFIG_DIR']) / 'projects/test'
project.mkdir(parents=True)
events = [
 {'type':'user','message':{'content':sys.argv[-1]}},
 {'type':'assistant','message':{'content':[{'type':'thinking','thinking':'private-reasoning'},
 {'type':'tool_use','id':'t1','name':'Read','input':{'file_path':'input_badcase.json'}}]}},
 {'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':'t1',
 'content':'tool output'}]}}]
(project / (session+'.jsonl')).write_text(chr(10).join(json.dumps(e) for e in events))
print(os.environ['ANTHROPIC_API_KEY'], file=sys.stderr)
print(json.dumps({'result':'visible reply','subtype':'success',
 'usage':{'input_tokens':2,'output_tokens':1}}))
"""
        + f"sys.exit({exit_code})"
    )
    executable.chmod(0o700)
    work = tmp_path / "case"
    work.mkdir()
    monkeypatch.setattr(shutil, "which", lambda _: str(executable))
    monkeypatch.setattr(claude_skill, "_sandbox", lambda *_: [])
    monkeypatch.setattr(
        claude_skill,
        "_provider_environment",
        lambda _: {"ANTHROPIC_API_KEY": "test-credential-opaque"},
    )
    backend = ClaudeCodeProvider()
    details: dict[str, Any] = {}
    request = SkillRunRequest(work, "test prompt", "test", 10)
    if exit_code:
        with pytest.raises(RuntimeError, match="status 1"):
            await backend.run_skill(request, diagnostics=details)
    else:
        assert await backend.run_skill(request, diagnostics=details) == 3
    assert details["exitCode"] == exit_code
    assert details["result"]["result"] == "visible reply"
    turns = details["transcript"]["turns"]
    assert turns[1]["content"][0]["input"] == {"file_path": "input_badcase.json"}
    assert turns[2]["content"][0]["content"][0]["text"] == "tool output"
    serialized = json.dumps(details)
    assert "private-reasoning" not in serialized and "test-credential-opaque" not in serialized
    transcript = next(work.rglob("*.jsonl"))
    external = tmp_path / "external.jsonl"
    transcript.rename(external)
    transcript.symlink_to(external)
    from app.third_party_api.attribution.transcript import read_transcript

    assert read_transcript(work, details["sessionId"])["status"] == "unavailable"


async def test_attribution_uses_shared_service_binary_and_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import Settings

    binary = tmp_path / "shared" / "current" / "bin" / "claude"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        """#!/usr/bin/env python3
import json, os
assert os.environ["ANTHROPIC_BASE_URL"] == "https://gateway.example"
assert os.environ["ANTHROPIC_API_KEY"] == "fixture-key"
assert os.environ["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "deployed-model"
assert os.environ["CLAUDE_CONFIG_DIR"].startswith(os.getcwd() + "/")
assert "UNRELATED_SETTING" not in os.environ
print(json.dumps({"subtype": "success", "usage": {"input_tokens": 9}}))
"""
    )
    binary.chmod(0o700)
    settings_file = tmp_path / "shared" / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "env": {
                    "ANTHROPIC_BASE_URL": "https://gateway.example",
                    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "deployed-model",
                    "UNRELATED_SETTING": "not-for-agent",
                }
            }
        )
    )
    for key in ("ANTHROPIC_BASE_URL", "ANTHROPIC_DEFAULT_HAIKU_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fixture-key")
    monkeypatch.setattr(claude_skill, "_sandbox", lambda *_: [])
    backend = build_agent_provider(
        Settings(ai_agent_claude_bin=str(binary), ai_agent_claude_settings=str(settings_file)),
    )
    work = tmp_path / "attempt"
    work.mkdir()
    assert backend.skill_model_identity("haiku")["model"] == "deployed-model"
    assert (
        await backend.run_skill(
            SkillRunRequest(work, "fixture prompt", "haiku", 10), diagnostics={}
        )
        == 9
    )


async def test_shared_provider_keeps_concurrent_skill_sessions_separate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from app.config import Settings

    executable = tmp_path / "claude"
    executable.write_text(
        """#!/usr/bin/env python3
import json, pathlib, sys, time
name = pathlib.Path.cwd().name
assert sys.argv[-1] == name
time.sleep(0.05)
print(json.dumps({"subtype": "success", "result": name, "usage": {"output_tokens": len(name)}}))
"""
    )
    executable.chmod(0o700)
    monkeypatch.setattr(claude_skill, "_sandbox", lambda *_: [])
    provider = ClaudeCodeProvider(
        Settings(ai_agent_claude_bin=str(executable)), settings_path=tmp_path / "settings"
    )

    async def invoke(name: str) -> tuple[int, dict[str, Any]]:
        work = tmp_path / name
        work.mkdir()
        details: dict[str, Any] = {}
        count = await provider.run_skill(
            SkillRunRequest(work, name, "fixture", 10), diagnostics=details
        )
        return count, details

    (left_count, left), (right_count, right) = await asyncio.gather(
        invoke("first"), invoke("second")
    )
    assert (left_count, right_count) == (5, 6)
    assert (left["result"]["result"], right["result"]["result"]) == ("first", "second")
    assert left["sessionId"] != right["sessionId"]


@pytest.mark.parametrize("caller_cancelled", [False, True], ids=["timeout", "cancel"])
async def test_skill_keeps_private_diagnostics_when_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caller_cancelled: bool
) -> None:
    import asyncio
    from unittest.mock import AsyncMock

    from app.config import Settings
    from app.third_party_api.ai_agent.claude_cli import ClaudeCliCancelled, ClaudeCliResult

    binary = tmp_path / "claude"
    binary.touch(mode=0o700)
    work = tmp_path / "case"
    work.mkdir()
    runner = AsyncMock()
    stopped = ClaudeCliResult(-9, "", "interrupted", cancelled=True, stderr_truncated=True)
    if caller_cancelled:
        runner.run.side_effect = ClaudeCliCancelled(stopped)
    else:
        runner.run.return_value = stopped
    monkeypatch.setattr(claude_skill, "_sandbox", lambda *_: ["sandbox"])
    provider = ClaudeCodeProvider(
        Settings(ai_agent_claude_bin=str(binary)),
        runner=runner,
        settings_path=tmp_path / "settings",
    )
    details: dict[str, Any] = {}
    with pytest.raises(asyncio.CancelledError if caller_cancelled else TimeoutError):
        await provider.run_skill(
            SkillRunRequest(work, "/test input_badcase.json", "model", 3), diagnostics=details
        )
    argv = runner.run.await_args.args[0]
    assert argv == [
        "sandbox",
        str(binary),
        "-p",
        "--output-format",
        "json",
        "--bare",
        "--session-id",
        details["sessionId"],
        "--permission-mode",
        "bypassPermissions",
        "--allow-dangerously-skip-permissions",
        "--model",
        "model",
        "/test input_badcase.json",
    ]
    assert (details["exitCode"], details["stderrTail"], details["stderrTruncated"]) == (
        -9,
        "interrupted",
        True,
    )
