"""Case-scoped stdio tools for Claude attribution on Linux without bubblewrap."""

from __future__ import annotations

import codecs
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer
from pydantic import BaseModel, ConfigDict

_EVIDENCE = (
    "input_badcase.json",
    "session_tree.json",
    "traces.json",
    "trace_coverage.json",
    "attribute_source.md",
)
_PAGE_BYTES = 16_384


class ReportFields(BaseModel):
    """Analysis fields accepted by the platform writer. Paths and case ID belong to the server."""

    model_config = ConfigDict(extra="forbid", strict=True)
    conclusion: Literal["attributed", "non_target", "inconclusive"]
    root_cause: str
    evidence_references: list[str] = []
    probe_object: str | None = None
    probe_type: Literal["skill", "agent", "knowledge"] | None = None
    object_version: str | None = None
    attribute_type: Literal["prompt", "model", "error", "flow", "context", "unknown"]
    probe_description: str
    probe_analysis: str
    detail_description: str | None = None
    proposal_target_skill: str | None = None
    proposal_target_location: str | None = None
    proposal_change: str | None = None
    proposal_expected_behavior: str | None = None
    proposal_evaluation_plan: str | None = None


class CaseTools:
    """Expose only staged evidence, bound Skill text and the frozen platform writer."""

    def __init__(self, directory: Path) -> None:
        self.work = directory.resolve(strict=True)
        skills = self.work / ".claude/skills"
        (self.skill,) = skills.iterdir()
        if self.skill.resolve(strict=True) != self.skill or not self.skill.is_dir():
            raise ValueError("invalid staged Skill")
        self.files = {name: self.work / name for name in _EVIDENCE}
        self.files.update(
            (f"skill/{path.relative_to(self.skill)}", path)
            for path in self.skill.rglob("*")
            if path.name != "make_probe_report.py" and not path.is_symlink() and path.is_file()
        )
        self.files = {
            name: path
            for name, path in self.files.items()
            if path.is_file() and path.resolve() == path
        }

    def read_evidence(self, path: str = "", offset: int = 0) -> dict[str, Any]:
        """List files with no path, or read a UTF-8 page, continuing at the returned next_offset."""
        if not path:
            return {"files": sorted(self.files)}
        source = self.files.get(path)
        if source is None or source.resolve() != source or offset < 0:
            raise ValueError("unknown evidence file or invalid offset")
        with source.open("rb") as reader:
            size = os.fstat(reader.fileno()).st_size
            if offset > size:
                raise ValueError("offset exceeds file size")
            reader.seek(offset)
            block = reader.read(_PAGE_BYTES)
        decoder = codecs.getincrementaldecoder("utf-8")()
        end = offset + len(block)
        content = decoder.decode(block, final=end == size)
        cursor = end - len(decoder.getstate()[0])
        return {"text": content, "next_offset": cursor if cursor < size else None}

    def write_probe_report(self, report: ReportFields) -> str:
        """Call make_probe_report.py for this case and write probe_report.json with its receipt."""
        input_path = self.files["input_badcase.json"]
        writer = self.skill / "make_probe_report.py"
        output = self.work / "probe_report.json"
        protected = (
            input_path,
            writer,
            output,
            self.work / ".platform/make_probe_report.py",
            self.work / ".platform/receipt.json",
        )
        if any(path.resolve() != path for path in protected):
            raise ValueError("invalid staged writer or report path")
        (case,) = json.loads(input_path.read_bytes())["bad_cases"]
        args = [
            sys.executable,
            "-I",
            str(writer),
            f"--input-badcase={input_path}",
            f"--bad-case-id={case['bad_case_id']}",
            f"--conclusion={report.conclusion}",
            f"--root-cause={report.root_cause}",
            f"--output={output}",
            *(f"--evidence-ref={reference}" for reference in report.evidence_references),
        ]
        if report.probe_object is not None:
            args.append(f"--probe_object={report.probe_object}")
        if report.probe_type is not None:
            args.append(f"--probe_type={report.probe_type}")
        if report.object_version is not None:
            args.append(f"--object-version={report.object_version}")
        args.extend(
            (
                f"--attribute-type={report.attribute_type}",
                f"--probe-description={report.probe_description}",
                f"--probe-analysis={report.probe_analysis}",
            ),
        )
        if report.detail_description is not None:
            args.append(f"--detail-description={report.detail_description}")
        for name, flag in (
            ("proposal_target_skill", "--proposal-target-skill"),
            ("proposal_target_location", "--proposal-target-location"),
            ("proposal_change", "--proposal-change"),
            ("proposal_expected_behavior", "--proposal-expected-behavior"),
            ("proposal_evaluation_plan", "--proposal-evaluation-plan"),
        ):
            value = getattr(report, name)
            if value is not None:
                args.append(f"{flag}={value}")
        result = subprocess.run(  # noqa: S603 - the verified shim and both paths are platform-owned.
            args,
            cwd=self.work,
            env={"PATH": os.defpath},
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=20,
            text=True,
            check=False,
        )
        if result.returncode:
            raise ValueError(f"platform writer rejected the report: {result.stderr.strip()[:512]}")
        return "probe_report.json"


def create_server(directory: Path) -> MCPServer[Any]:
    tools = CaseTools(directory)
    server: MCPServer[Any] = MCPServer("attribution", log_level="WARNING")
    server.tool()(tools.read_evidence)
    server.tool()(tools.write_probe_report)
    return server


if __name__ == "__main__":
    create_server(Path(sys.argv[1])).run(transport="stdio")
