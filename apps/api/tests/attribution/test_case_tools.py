"""Input visibility and writer integrity in the Linux attribution tool server."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.third_party_api.ai_agent.attribution_case_tools import CaseTools, ReportFields
from app.third_party_api.attribution import writer_entrypoint


@pytest.fixture
def case(tmp_path: Path) -> Path:
    work = tmp_path / "case"
    skill = work / ".claude/skills/original"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("Use this case.")
    (skill / "references").mkdir()
    (skill / "references/guide.md").write_text("Read these examples.")
    shutil.copyfile(writer_entrypoint.__file__, skill / "make_probe_report.py")
    platform = work / ".platform"
    platform.mkdir()
    source = Path(__file__).resolve().parents[4] / "attribute-badcases/make_probe_report.py"
    shutil.copyfile(source, platform / source.name)
    (work / "input_badcase.json").write_text(
        json.dumps(
            {
                "session_id": "one-session",
                "selected_target": {"name": "reporter", "type": "agent", "version": "v1"},
                "bad_cases": [
                    {
                        "bad_case_id": "case-one",
                        "type": "skill",
                        "object": "reporter",
                        "object_version": "v1",
                        "bad_case_type": "discovery",
                    }
                ],
            }
        )
    )
    return work


def test_only_frozen_evidence_and_selected_skill_are_readable(case: Path) -> None:
    other = case.parent / "another-case.txt"
    other.write_text("another case")
    skill = case / ".claude/skills/original"
    (skill / "other.md").symlink_to(other)
    (case / "traces.json").symlink_to(other)
    # Create a page boundary inside a multibyte UTF-8 character.
    prompt = "x" + "树" * 14_000
    (case / "attribute_source.md").write_text(prompt)
    server = CaseTools(case)
    assert set(server.read_evidence()["files"]) == {
        "skill/SKILL.md",
        "skill/references/guide.md",
        "input_badcase.json",
        "attribute_source.md",
    }
    for denied in (
        "../another-case.txt",
        str(other),
        ".platform/receipt.json",
        "home",
        "skill/other.md",
        "traces.json",
        "skill/make_probe_report.py",
    ):
        with pytest.raises(ValueError, match="unknown evidence"):
            server.read_evidence(denied)
    parts = []
    offset = 0
    while True:
        page = server.read_evidence("attribute_source.md", offset)
        parts.append(page["text"])
        if page["next_offset"] is None:
            break
        assert page["next_offset"] > offset
        offset = page["next_offset"]
    assert len(parts) > 1 and "".join(parts) == prompt
    with pytest.raises(ValueError, match="offset"):
        server.read_evidence("skill/SKILL.md", 1000)
    (skill / "SKILL.md").unlink()
    (skill / "SKILL.md").symlink_to(other)
    with pytest.raises(ValueError, match="unknown evidence"):
        server.read_evidence("skill/SKILL.md")


def test_only_platform_writer_chooses_paths_and_case_identity(case: Path) -> None:
    fields = {
        "probe_object": "reporter",
        "probe_type": "agent",
        "attribute_type": "context",
        "conclusion": "attributed",
        "root_cause": "上游参数已存在，检视规则误报",  # noqa: RUF001
        "probe_description": "--output=just literal analysis",
        "probe_analysis": "说明",
    }
    for key in ("bad_case_id", "output", "input_badcase", "command"):
        with pytest.raises(ValidationError):
            ReportFields.model_validate({**fields, key: "outside"})
    for invalid in (
        {**fields, "conclusion": "maybe"},
        {**fields, "root_cause": "  "},
    ):
        with pytest.raises(ValidationError):
            ReportFields.model_validate(invalid)
    missing_verdict = {key: value for key, value in fields.items() if key != "conclusion"}
    with pytest.raises(ValidationError):
        ReportFields.model_validate(missing_verdict)
    tools = CaseTools(case)
    with pytest.raises(ValueError, match="platform writer rejected"):
        tools.write_probe_report(ReportFields.model_validate({**fields, "probe_object": "other"}))
    assert not (case / "probe_report.json").exists()
    assert tools.write_probe_report(ReportFields.model_validate(fields)) == "probe_report.json"
    output = case / "probe_report.json"
    report = json.loads(output.read_bytes())
    assert report["from_bad_cases"][0]["bad_case_id"] == "case-one"
    assert report["probe_description"] == fields["probe_description"]
    assert report["conclusion"] == fields["conclusion"]
    assert report["root_cause"] == fields["root_cause"]
    assert json.loads((case / ".platform/receipt.json").read_bytes()) == {
        "path": output.name,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    output.unlink()
    other = case.parent / "another-output"
    output.symlink_to(other)
    with pytest.raises(ValueError, match="invalid staged writer"):
        tools.write_probe_report(ReportFields.model_validate(fields))
    assert not other.exists()
