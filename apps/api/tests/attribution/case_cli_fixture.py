"""Offline Claude stand-in for the sandbox Skill and the case-scoped stdio tools."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters


async def _write_sandbox_report(args: list[str]) -> None:
    assert os.environ["TEST_FIXTURE_BWRAP"] == "1"
    assert args[args.index("--permission-mode") + 1] == "bypassPermissions"
    assert "--allow-dangerously-skip-permissions" in args and "--bare" in args
    assert "--mcp-config" not in args
    work = Path.cwd()
    skill = next((work / ".claude/skills").iterdir())
    assert (skill / "SKILL.md").is_file() and args[-1].startswith(
        f"/{skill.name} 使用 {skill.name} skill"
    )
    row = json.loads((work / "input_badcase.json").read_bytes())["bad_cases"][0]
    writer = await asyncio.create_subprocess_exec(
        sys.executable,
        str(skill / "make_probe_report.py"),
        "--input-badcase",
        "input_badcase.json",
        "--bad-case-id",
        row["bad_case_id"],
        "--conclusion",
        "attributed",
        "--root-cause",
        "fixture root cause",
        "--probe_object",
        row["object"],
        "--probe_type",
        row["type"],
        "--attribute-type",
        "flow",
        "--probe-description",
        "fixture observation",
        "--probe-analysis",
        "fixture evidence",
        "--output",
        "probe_report.json",
        stdout=asyncio.subprocess.DEVNULL,
    )
    assert await writer.wait() == 0


async def _write_case_tool_report(args: list[str]) -> None:
    assert "--restricted" in args and "bypassPermissions" not in args
    assert "--allow-dangerously-skip-permissions" not in args and "--disable-slash-commands" in args
    assert args[args.index("--tools") + 1] == ""
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert args[args.index("--allowed-tools") + 1].split(",") == [
        "mcp__attribution__read_evidence",
        "mcp__attribution__write_probe_report",
    ]
    config = json.loads(args[args.index("--mcp-config") + 1])["mcpServers"]
    assert set(config) == {"attribution"} and "--strict-mcp-config" in args
    spec = config["attribution"]
    assert spec["args"][0] == "-I"
    work = Path(spec["args"][-1])
    assert Path.cwd() == work / "home"
    skill = next((work / ".claude/skills").iterdir())
    guide = await asyncio.to_thread(
        Path(args[args.index("--append-system-prompt-file") + 1]).read_text
    )
    assert (skill / "SKILL.md").read_text() in guide
    assert args[-1].startswith(f"/{skill.name} 使用 {skill.name} skill")
    async with Client(StdioServerParameters(command=spec["command"], args=spec["args"])) as client:
        assert {tool.name for tool in (await client.list_tools()).tools} == {
            "read_evidence",
            "write_probe_report",
        }
        evidence = await client.call_tool("read_evidence", {"path": "input_badcase.json"})
        assert not evidence.is_error and evidence.structured_content
        row = json.loads(evidence.structured_content["text"])["bad_cases"][0]
        result = await client.call_tool(
            "write_probe_report",
            {
                "report": {
                    "probe_object": row["object"],
                    "probe_type": row["type"],
                    "attribute_type": "flow",
                    "conclusion": "attributed",
                    "root_cause": "fixture root cause",
                    "probe_description": "fixture observation",
                    "probe_analysis": "fixture evidence",
                }
            },
        )
        assert not result.is_error, result.content


async def main(args: list[str]) -> int:
    if args == ["--version"]:
        print("offline-fixture")
        return 0
    if "--mcp-config" in args:
        await _write_case_tool_report(args)
    elif "bypassPermissions" in args:
        await _write_sandbox_report(args)
    else:
        return 1  # The wizard fixture uses the deterministic clustering fallback.
    print(json.dumps({"subtype": "success", "result": "report submitted", "usage": {}}))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
