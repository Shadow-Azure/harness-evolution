"""Claude stdout and visible session history survive cleanup through the backend hook."""

import json
import shutil
from pathlib import Path

import pytest

from app.third_party_api.attribution import claude_backend
from app.third_party_api.attribution.claude_backend import ClaudeBackend


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
    monkeypatch.setattr(claude_backend, "_sandbox", lambda *_: [])
    monkeypatch.setattr(
        claude_backend,
        "_provider_environment",
        lambda _: {"ANTHROPIC_API_KEY": "test-credential-opaque"},
    )
    backend = ClaudeBackend()
    if exit_code:
        with pytest.raises(RuntimeError, match="status 1"):
            await backend.execute(work, "test prompt", "test", 10)
    else:
        assert await backend.execute(work, "test prompt", "test", 10) == 3
    details = backend.execution_details(work)
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
    assert backend.execution_details(work)["transcript"]["status"] == "unavailable"


async def test_attribution_uses_shared_service_binary_and_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import Settings
    from app.third_party_api.attribution.backend import AgentFactory

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
    monkeypatch.setattr(claude_backend, "_sandbox", lambda *_: [])
    backend = AgentFactory.create(
        "claude",
        Settings(ai_agent_claude_bin=str(binary), ai_agent_claude_settings=str(settings_file)),
    )
    work = tmp_path / "attempt"
    work.mkdir()
    assert backend.model_identity("haiku")["model"] == "deployed-model"
    assert await backend.execute(work, "fixture prompt", "haiku", 10) == 9
