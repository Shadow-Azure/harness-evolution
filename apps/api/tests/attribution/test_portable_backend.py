# ruff: noqa: RUF001
"""A zero-adaptation stub backend completes all four capability faces (#604).

The stub only declares ``capabilities``, implements ``stage_skill`` with an
empty prefix, and reuses the ``claude_cli`` transport. Analyze, edit, health,
and a full Skill case run through it without touching the service layer or
configuration code, which is exactly the onboarding surface the portable
backend issue promises.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.db.crud.attribution_skill_packages import AttributionSkillPackageRepository
from app.db.crud.attribution_skills import AttributionSkillRepository
from app.db.crud.attributions import AttributionRepository
from app.service.evolution.attribution import AttributionRunner
from app.service.evolution.attribution_skill_packages import AttributionSkillPackageService
from app.service.evolution.attribution_skills import AttributionSkillService
from app.service.evolution.local_attribution import ENGINE, LocalAttribution
from app.third_party_api.ai_agent import (
    AgentProviderError,
    AIAgentProvider,
    AnalysisRequest,
    AnalysisResult,
    ClaudeCliResult,
    ClaudeCliRunner,
    EditRequest,
    EditResult,
    ProviderHealth,
    SkillRunRequest,
    StructuredSubmission,
    build_agent_provider,
    factory,
)
from app.third_party_api.ai_agent.claude_cli import AsyncioClaudeCliRunner
from app.third_party_api.ai_agent.contracts import EDIT_PLAN_FILENAME, AgentUsage
from app.third_party_api.ai_agent.edits import EditPlan
from tests.attribution.support import CASE_ID, Harness, potential_case
from tests.attribution.test_m10_03_runner import load_run


class ReviewOutput(BaseModel):
    """Minimal caller schema for the stubbed analysis."""

    title: str


class ScriptedRunner:
    """claude_cli-protocol transport double that writes one submission per call."""

    def __init__(self, payload: dict[str, Any], *, filename: str = "result.json5") -> None:
        self._payload = payload
        self._filename = filename
        self.prompts: list[str] = []

    async def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_seconds: float,
    ) -> ClaudeCliResult:
        """Record the prompt, write the submission literal, and return one result."""
        self.prompts.append(argv[-1])
        submission = cwd / self._filename
        submission.parent.mkdir(parents=True, exist_ok=True)
        submission.write_text(json.dumps(self._payload), encoding="utf-8")
        document = {"type": "result", "is_error": False, "usage": {"input_tokens": 3}}
        return ClaudeCliResult(0, json.dumps(document), "")


class GenericCliBackend(AIAgentProvider):
    """Minimal portable backend: declaration + neutral staging + shared transport."""

    provider_id = "generic-cli"
    capabilities: ClassVar[frozenset[str]] = frozenset({"analyze", "edit", "skill"})

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        runner: ClaudeCliRunner | None = None,
        agent_script: Path | None = None,
    ) -> None:
        super().__init__(settings)
        self._runner = runner if runner is not None else AsyncioClaudeCliRunner()
        self._submission = StructuredSubmission()
        self._agent_script = agent_script

    def stage_skill(self, work: Path, name: str, files: Mapping[str, bytes]) -> str:
        """Reuse the neutral layout unchanged and return no native prefix."""
        staged = work / "skills" / name
        for relative, content in files.items():
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        return ""

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        started = time.monotonic()
        prep = self._submission.prepare(request.task, request.output_model)
        try:
            prompt = f"{request.prompt}\n\n{prep.prompt_addendum}"
            result = await self._runner.run(
                ("generic-agent", "analyze", request.task, prompt),
                cwd=prep.directory,
                env={},
                timeout_seconds=120.0,
            )
            if result.returncode:
                raise AgentProviderError(
                    "generic-cli analysis call failed",
                    retryable=False,
                    provider_id=self.provider_id,
                )
            outcome = self._submission.collect(prep, request.output_model.model_validate)
            validated = outcome.validated
            if not outcome.is_ok or validated is None:
                raise AgentProviderError(
                    "generic-cli analysis submission failed validation",
                    retryable=False,
                    provider_id=self.provider_id,
                )
            return AnalysisResult(
                output=validated.model_dump(mode="json"),
                provider_id=self.provider_id,
                usage=_scripted_usage(result),
                latency_ms=int((time.monotonic() - started) * 1_000),
            )
        finally:
            self._submission.discard(prep)

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        prep = self._submission.prepare(
            "agent.edit",
            EditPlan,
            directory=request.workspace,
            filename=EDIT_PLAN_FILENAME,
        )
        prompt = f"{request.prompt}\n\n{prep.prompt_addendum}"
        result = await self._runner.run(
            ("generic-agent", "edit", prompt),
            cwd=request.workspace,
            env={},
            timeout_seconds=120.0,
        )
        outcome = self._submission.collect(prep, EditPlan.model_validate)
        validated = outcome.validated
        if not outcome.is_ok or not isinstance(validated, EditPlan):
            raise AgentProviderError(
                "generic-cli edit submission failed validation",
                retryable=False,
                provider_id=self.provider_id,
            )
        return EditResult(
            summary=validated.summary,
            provider_id=self.provider_id,
            usage=_scripted_usage(result),
            plan=validated,
        )

    async def run_skill(self, request: SkillRunRequest, *, diagnostics: dict[str, Any]) -> int:
        if self._agent_script is None:
            raise AgentProviderError(
                "generic-cli agent script unavailable",
                retryable=False,
                provider_id=self.provider_id,
            )
        result = await self._runner.run(
            (sys.executable, "-I", str(self._agent_script), request.prompt),
            cwd=request.directory,
            env=dict(os.environ),
            timeout_seconds=request.timeout_seconds,
        )
        if result.cancelled:
            raise TimeoutError("generic-cli skill execution timed out")
        if result.returncode:
            raise RuntimeError(f"generic-cli skill exited with status {result.returncode}")
        usage = json.loads(result.stdout).get("usage", {})
        return int(usage.get("input_tokens", 0)) + int(usage.get("output_tokens", 0))

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            provider_id=self.provider_id,
            healthy=True,
            detail="generic deterministic stub",
            auth="ok",
        )


def _scripted_usage(result: ClaudeCliResult) -> AgentUsage:
    """Return the usage document carried by one scripted CLI result."""
    usage = json.loads(result.stdout).get("usage", {})
    return AgentUsage(
        model="generic-model",
        input_tokens=int(usage.get("input_tokens", 0)),
    )


_AGENT_SCRIPT = """\
import json, pathlib, subprocess, sys
work = pathlib.Path.cwd()
prompt = sys.argv[-1]
skill = next((work / "skills").iterdir())
assert prompt.startswith(f"使用 {skill.name} skill")
assert f"skills/{skill.name}/SKILL.md" in prompt
assert not (work / ".claude").exists()
row = json.loads((work / "input_badcase.json").read_bytes())["bad_cases"][0]
completed = subprocess.run(
    [sys.executable, "-I", str(skill / "make_probe_report.py"),
     "--input-badcase", "input_badcase.json",
     "--bad-case-id", row["bad_case_id"],
     "--conclusion", "attributed",
     "--root-cause", "流程缺少校验",
     "--probe_object", row["object"],
     "--attribute-type", "flow",
     "--probe-description", "流程缺少校验",
     "--probe-analysis", "缺少复核步骤",
     "--output", "probe_report.json"],
    cwd=work, check=False, stdout=subprocess.DEVNULL)
print(json.dumps({"usage": {"input_tokens": 4, "output_tokens": 6}}))
sys.exit(completed.returncode)
"""

_EDIT_PLAN_PAYLOAD = {
    "summary": "fetch 超时 30s 提高到 120s",
    "edits": [
        {
            "op": "replace",
            "file": "config/app.json",
            "target": '"timeout": 30',
            "content": '"timeout": 120',
            "rationale": "三条 case 均为 30s 超时，同一根因",
        }
    ],
}


class _Source:
    async def read_file(self, *, repo_url: str, sub_dir: str, ref: str, file_name: str) -> str:
        return "# Deep research\nAlways inspect the evidence."


async def test_generic_backend_completes_analyze_edit_and_health(tmp_path: Path) -> None:
    """analyze / edit / health run on one scripted claude_cli transport double."""
    backend = GenericCliBackend(
        runner=ScriptedRunner({"title": "共同根因"}),
    )

    analysis = await backend.analyze(
        AnalysisRequest(task="cluster.review", prompt="review", output_model=ReviewOutput)
    )
    assert analysis.output == {"title": "共同根因"}
    assert analysis.provider_id == "generic-cli"
    assert analysis.usage.input_tokens == 3

    edit_backend = GenericCliBackend(
        runner=ScriptedRunner(_EDIT_PLAN_PAYLOAD, filename=EDIT_PLAN_FILENAME),
    )
    edit = await edit_backend.edit_workspace(
        EditRequest(
            workspace=_ensure(tmp_path / "workspace"),
            prompt="修复超时",
        ),
    )
    assert edit.summary == "fetch 超时 30s 提高到 120s"
    assert edit.plan is not None and edit.plan.edits[0].op == "replace"

    health = await backend.health_check()
    assert health.healthy is True and health.auth == "ok"


def test_factory_assembles_the_generic_backend_through_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Registration plus the generic config entry is the whole onboarding surface."""
    monkeypatch.setitem(factory._REGISTRY, "generic-cli", GenericCliBackend)
    settings = Settings(ai_agent_provider="generic-cli")

    backend = build_agent_provider(settings)

    assert isinstance(backend, GenericCliBackend)
    assert backend.capabilities == frozenset({"analyze", "edit", "skill"})
    assert backend.supports_skills is True


async def test_generic_backend_runs_a_full_skill_case_without_service_changes(
    attribution_harness: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One registered stub executes the frozen attribution case end to end."""
    db = attribution_harness.database
    agent_script = tmp_path / "generic-agent.py"
    agent_script.write_text(_AGENT_SCRIPT, encoding="utf-8")
    monkeypatch.setitem(factory._REGISTRY, "generic-cli", GenericCliBackend)
    settings = Settings(
        attribution_package_dir=tmp_path / "attribute",
        ai_agent_provider="generic-cli",
        attribution_timeout_seconds=150,
    )
    backend = build_agent_provider(settings)
    assert isinstance(backend, GenericCliBackend)
    backend._agent_script = agent_script
    packages = AttributionSkillPackageService(
        AttributionSkillPackageRepository(db),
        settings.attribution_package_dir,
        settings.attribution_default_skill_path,
    )
    service = LocalAttribution(
        settings,
        packages,
        AttributionSkillService(AttributionSkillRepository(db)),
        db,
        _Source(),
        backend,
    )
    run = await load_run(db)
    selected = await service.resolve(run.workspace_id, "")
    assert selected.skill_key == "attribute-badcases"
    run = replace(
        run,
        attribution_engine=ENGINE,
        attribution_skill_key=selected.skill_key,
        attribution_skill_revision=selected.revision,
        attribution_skill_content_hash=selected.content_hash,
    )
    store = AttributionRepository(db)
    runner = AttributionRunner(
        store,
        skill_resolver=service,
        engine_factory=service.engine,
        prepare_input=service.prepare_input,
    )
    summary = await runner.run(run, [potential_case()], True)
    assert summary.created == 1

    artifact = (
        service.root(run.workspace_id) / "attribute_output" / run.id / CASE_ID / "probe_report.json"
    )
    assert artifact.is_file()
    audit = json.loads(artifact.with_name("attribute_log.json").read_bytes())
    assert audit["agent"] == "generic-cli"
    assert audit["prompt"].startswith("使用 attribute-badcases skill：读取 skills/")
    assert audit["status"] == "report_validated"


def _ensure(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return directory
