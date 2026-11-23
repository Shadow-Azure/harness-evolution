"""Production runtime contracts for a deployed CLI, private transcripts and report receipts."""

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

from app.config import Settings
from app.service.evolution.local_attribution import LocalAttribution
from app.third_party_api.attribution import claude_backend, writer_entrypoint
from app.third_party_api.attribution.backend import AgentFactory, ModelFactory
from app.third_party_api.attribution.transcript import read_transcript


def test_deployment_factory_accepts_compatible_plugins() -> None:
    model = ModelFactory.create("app.third_party_api.attribution.backend:NativeModel")
    assert model.resolve("deployed-model") == "deployed-model"
    with pytest.raises(ValueError, match="invalid attribution model"):
        model.resolve(" ")
    with pytest.raises(ValueError, match="incompatible"):
        AgentFactory.create("app.third_party_api.attribution.backend:NativeModel")
    with pytest.raises(ValueError, match="unknown attribution provider"):
        AgentFactory.create("invalid")


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_sandbox_uses_case_directory_and_installed_binary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    binary = str(tmp_path / "shared" / "claude")
    work = tmp_path / "attempt"
    if platform == "linux":
        monkeypatch.setattr(claude_backend.shutil, "which", lambda _: None)
        with pytest.raises(RuntimeError, match="bubblewrap"):
            claude_backend._sandbox(work, binary)
        monkeypatch.setattr(claude_backend.shutil, "which", lambda _: "/usr/bin/bwrap")
    argv = claude_backend._sandbox(work, binary)
    if platform == "darwin":
        assert argv[0] == "/usr/bin/sandbox-exec"
        assert f"WORK={work}" in argv and f"CLAUDE={binary}" in argv
    else:
        assert argv[0] == "/usr/bin/bwrap"
        assert argv[argv.index("--bind") + 1 :][:2] == [str(work), str(work)]
        assert argv[-3:] == ["--chdir", str(work), "--"]
        assert binary in argv and "--die-with-parent" in argv


@pytest.mark.parametrize(
    ("payload", "exitcode", "error"),
    [
        ("not json", 1, "exited with status"),
        ("[]", 0, "invalid Claude result"),
        ('{"subtype":"error"}', 0, "did not complete"),
    ],
)
async def test_failed_cli_envelopes_never_publish_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str, exitcode: int, error: str
) -> None:
    binary = tmp_path / "stub"
    binary.write_text(f"#!/usr/bin/env python3\nprint({payload!r})\nraise SystemExit({exitcode})\n")
    binary.chmod(0o700)
    monkeypatch.setattr(claude_backend, "_sandbox", lambda *_: [])
    settings = Settings(
        ai_agent_claude_bin=str(binary), ai_agent_claude_settings=str(tmp_path / "none")
    )
    work = tmp_path / "attempt"
    work.mkdir()
    backend = AgentFactory.create("claude", settings)
    with pytest.raises((RuntimeError, ValueError), match=error):
        await backend.execute(work, "fixture", "haiku", 10)
    assert backend.execution_details(work)["exitCode"] == exitcode
    binary.unlink()
    with pytest.raises(RuntimeError, match="executable unavailable"):
        await backend.execute(work, "fixture", "haiku", 10)


def test_truncated_or_incomplete_transcript_retains_visible_turns(tmp_path: Path) -> None:
    session = str(uuid4())
    projects = tmp_path / "home/.claude/projects"
    folder = projects / "case"
    folder.mkdir(parents=True)
    (projects / "manifest.txt").write_text("skip")
    (projects / "prior-project").mkdir()
    assert read_transcript(tmp_path, session)["status"] == "unavailable"
    text = {"type": "assistant", "message": {"content": [None, {"type": "text", "text": "result"}]}}
    (folder / f"{session}.jsonl").write_text(
        "\n".join(
            [
                json.dumps(text),
                '{"type":"user","message":{"content":null}}',
                '{"type":"meta"}',
                '{"type":',
            ]
        )
    )
    transcript = read_transcript(tmp_path, session)
    assert transcript["status"] == "partial"
    assert transcript["turns"] == [
        {"role": "assistant", "timestamp": None, "content": [{"type": "text", "text": "result"}]}
    ]


@pytest.mark.parametrize("mode", ["valid", "writer_error", "missing", "oversize", "other_name"])
def test_only_successful_writer_output_can_be_collected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    wrapper = tmp_path / ".claude/skills/attr/make_probe_report.py"
    script = tmp_path / ".platform/make_probe_report.py"
    script.parent.mkdir()
    report = tmp_path / ("other.json" if mode == "other_name" else "probe_report.json")
    if mode != "missing":
        report.write_text("x" * 2_000_001 if mode == "oversize" else '{"probe_id":"fixture"}')
    script.write_text(
        f"import sys\nprint({str(report)!r})\nsys.exit({int(mode == 'writer_error')})\n"
    )
    monkeypatch.setattr(writer_entrypoint, "__file__", str(wrapper))
    monkeypatch.setattr(sys, "argv", [str(wrapper)])
    status = writer_entrypoint.main()
    if mode != "valid":
        assert status == (1 if mode == "writer_error" else 2)
        assert not (script.parent / "receipt.json").exists()
        return
    assert status == 0
    assert LocalAttribution._read_emission(tmp_path) == {"probe_id": "fixture"}
    report.write_text('{"probe_id":"changed"}')
    with pytest.raises(ValueError, match="modified"):
        LocalAttribution._read_emission(tmp_path)
    report.unlink()
    with pytest.raises(ValueError, match="invalid platform report output"):
        LocalAttribution._read_emission(tmp_path)
