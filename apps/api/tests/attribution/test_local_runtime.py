"""SQLite acceptance test for one case, immutable Skill selection, and replay."""

from __future__ import annotations

import io
import json
import os
import runpy
import sys
import zipfile
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, ClassVar

import pytest
from sqlalchemy import insert, select

from app.config import Settings
from app.db.crud.attribution_skill_packages import AttributionSkillPackageRepository
from app.db.crud.attribution_skills import AttributionSkillRepository
from app.db.crud.attributions import AttributionRepository
from app.db.crud.problems import ProblemRepository
from app.db.crud.read_scope import WorkspaceReadScope
from app.db.models.domain import evolution_targets, probe_reports
from app.service.bad_cases.attribution import AttributionReadService
from app.service.evolution.attribution import AttributionRunner
from app.service.evolution.attribution_skill_packages import AttributionSkillPackageService
from app.service.evolution.attribution_skills import AttributionSkillService
from app.service.evolution.engine.contracts import RunBlocked
from app.service.evolution.local_attribution import ENGINE, LocalAttribution, canonical_report
from app.third_party_api.ai_agent import (
    FakeAIAgentProvider,
    SkillRunRequest,
    build_agent_provider,
    factory,
)
from tests.attribution.support import CASE_ID, NOW, OTHER_RUN_ID, Harness, potential_case
from tests.attribution.test_m10_03_runner import load_run
from tests.workspaces.helpers import create_user


class Source:
    async def read_file(self, *, repo_url: str, sub_dir: str, ref: str, file_name: str) -> str:
        return "# Deep research\nAlways inspect the evidence."


class ScriptAgent(FakeAIAgentProvider):
    """Zero-adaptation stub: declares the skill capability and stages no alias."""

    provider_id = "script-test"
    category = "flow"
    verdict = "attributed"
    cause = "流程缺少校验"
    capabilities: ClassVar[frozenset[str]] = frozenset({"analyze", "edit", "skill"})

    def stage_skill(self, work: Path, name: str, files: Mapping[str, bytes]) -> str:
        """Reuse the neutral layout unchanged and return no native prefix."""
        for relative, content in files.items():
            dest = work / "skills" / name / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(content)
        return ""

    async def run_skill(self, request: SkillRunRequest, *, diagnostics: dict[str, Any]) -> int:
        import asyncio

        directory, prompt = request.directory, request.prompt
        skill = next((directory / "skills").iterdir()).name
        assert prompt == (
            f"使用 {skill} skill：读取 skills/{skill}/SKILL.md 并严格遵循其中的全部指令，"  # noqa: RUF001
            "分析本目录的 input_badcase.json 并生成归因报告。"
        )
        assert not (directory / ".claude").exists()
        assert (directory / "session_tree.json").is_file()
        assert (directory / "attribute_source.md").is_file()
        row = json.loads((directory / "input_badcase.json").read_bytes())["bad_cases"][0]
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            f"skills/{skill}/make_probe_report.py",
            "--input-badcase",
            "input_badcase.json",
            "--bad-case-id",
            row["bad_case_id"],
            "--conclusion",
            self.verdict,
            "--evidence-ref",
            "event:main:1",
            "--root-cause",
            self.cause,
            "--proposal-change",
            "复核并如实汇报验证结果",
            *(("--probe_object", row["object"]) if self.verdict != "inconclusive" else ()),
            "--attribute-type",
            self.category,
            "--probe-description",
            self.cause,
            "--probe-analysis",
            f"{self.cause}。依据见输入中的 {row['bad_case_id']}。",
            "--output",
            "probe_report.json",
            cwd=directory,
        )
        assert await proc.wait() == 0
        return 10


@pytest.mark.parametrize(
    ("category", "verdict", "cause"),
    [("flow", "attributed", "目标流程缺少校验")]
    if os.environ.get("HE_TEST_LIVE_ATTRIBUTION") == "1"
    else [
        ("flow", "attributed", "目标流程缺少校验"),
        ("context", "attributed", "目标丢失输入上下文"),
        ("error", "non_target", "评分环境过期。修改目标只能改善汇报"),
        ("error", "inconclusive", "已观测到错误。缺少判断归属的轨迹"),
    ],
)
async def test_local_skill_report_to_sqlite(
    category: str,
    verdict: str,
    cause: str,
    attribution_harness: Harness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use a real CLI only when explicitly enabled for a synthetic acceptance run."""
    db = attribution_harness.database
    monkeypatch.setattr(ScriptAgent, "category", category)
    monkeypatch.setattr(ScriptAgent, "verdict", verdict)
    monkeypatch.setattr(ScriptAgent, "cause", cause)
    use_claude = os.environ.get("HE_TEST_LIVE_ATTRIBUTION") == "1"
    monkeypatch.setitem(factory._REGISTRY, ScriptAgent.provider_id, ScriptAgent)
    settings = Settings(
        attribution_package_dir=tmp_path / "attribute",
        ai_agent_provider="claude-code" if use_claude else ScriptAgent.provider_id,
        attribution_timeout_seconds=150,
    )
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
        Source(),
        build_agent_provider(settings),
    )
    run = await load_run(db)
    default = await service.resolve(run.workspace_id, "")
    assert default.skill_key == "attribute-badcases"
    zipout = io.BytesIO()
    with zipfile.ZipFile(zipout, "w") as archive:
        archive.writestr(
            "SKILL.md",
            "---\nname: acceptance-skill\ndescription: Attribution acceptance case\n---\n"
            "Read input_badcase.json. Treat the reported object as the actual target. "
            "Classify this synthetic case as flow. Use python3 "
            "skills/acceptance-skill/make_probe_report.py "
            "to write probe_report.json in the working directory. Stop after success.",
        )
    user_id = await create_user(db, username="acceptance")
    package = await packages.upload(
        workspace_id=run.workspace_id,
        uploader_id=user_id,
        uploader_name="admin",
        archive_name="acceptance.zip",
        archive=zipout.getvalue(),
    )
    async with db.transaction() as session:
        await session.execute(
            insert(evolution_targets).values(
                id="acceptance-target",
                workspace_id=run.workspace_id,
                object_type="skill",
                object_name=run.target_name,
                repo_url=run.repo_url,
                sub_dir=run.sub_dir,
                default_ref=run.target_version,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    bound = await service.bind(run.workspace_id, "acceptance-target", "default-attribute-badcases")
    assert bound.id == "default-attribute-badcases" and bound.source == "target"
    assert (
        await service.resolve(run.workspace_id, "acceptance-target")
    ).skill_key == default.skill_key
    assert (await packages.detail(run.workspace_id, "default-attribute-badcases")).targets == [
        run.target_name
    ]
    await service.bind(run.workspace_id, "acceptance-target", package.id)
    selected = await service.resolve(run.workspace_id, "acceptance-target")
    assert selected.skill_key == "acceptance-skill"
    assert (await packages.detail(run.workspace_id, package.id)).targets == [run.target_name]
    await service.bind(run.workspace_id, "acceptance-target", "default-attribute-badcases")
    await packages.delete(run.workspace_id, package.id)
    assert (await service.resolve(run.workspace_id, "")).content_hash == default.content_hash
    if os.environ.get("HE_TEST_PLATFORM_SKILL") == "1":
        selected = default
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
        engine_factory=service.engine,
        skill_resolver=service,
        prepare_input=service.prepare_input,
    )
    if not use_claude:

        async def timeout(*args: object, **kwargs: object) -> int:
            raise TimeoutError

        with monkeypatch.context() as simulated_failure:
            simulated_failure.setattr(ScriptAgent, "run_skill", timeout)
            with pytest.raises(RunBlocked):
                await runner.run(run, [potential_case()], True)
        output = service.root(run.workspace_id) / "attribute_output" / run.id / CASE_ID
        failure = json.loads((output / "attribute_log.json").read_bytes())
        assert (failure["stage"], failure["status"]) == ("agent", "timeout")
        assert not (output / "probe_report.json").exists()
    summary = await runner.run(run, [potential_case()], True)
    assert summary.created == 1
    linked = await store.linked_probe_ids(run.id)
    async with db.session() as session:
        persisted = (
            (
                await session.execute(
                    select(probe_reports).where(probe_reports.c.probe_id == linked[CASE_ID])
                )
            )
            .mappings()
            .one()
        )
    artifact = (
        service.root(run.workspace_id) / "attribute_output" / run.id / CASE_ID / "probe_report.json"
    )
    audit = json.loads(artifact.with_name("attribute_log.json").read_bytes())
    assert audit["status"] == "report_validated" and audit["badcaseId"] == CASE_ID
    assert audit["prompt"].startswith(
        f"使用 {selected.skill_key} skill：读取 skills/"  # noqa: RUF001
    )
    assert audit["prompt"].endswith("并生成归因报告。")
    assert (service.root(run.workspace_id) / audit["inputManifest"]).is_file()
    history = artifact.parent / "logs" / audit["attempt"] / "attribute_log.json"
    assert json.loads(history.read_bytes()) == audit
    assert not (artifact.parent / audit["attempt"]).exists()
    assert audit["agent"] == settings.ai_agent_provider
    if not use_claude:
        assert audit["model"] == {"selection": "provider-default"}
        assert len(list(artifact.parent.glob("logs/*/attribute_log.json"))) == 2
        assert failure["attempt"] != audit["attempt"]
    assert persisted["report_payload"]["sourceReport"] == json.loads(artifact.read_bytes())
    source = persisted["report_payload"]["sourceReport"]
    assert source["selected_target"]["name"] == run.target_name
    assert (
        persisted["conclusion"] == source["conclusion"] == persisted["report_payload"]["conclusion"]
    )
    if not use_claude:
        assert source["conclusion"] == verdict
        assert source["root_cause"] == cause
        assert source["proposal"]["change"]
        assert source["evidence_references"] == ["event:main:1"]
        assert any(
            e["reference"] == "event:main:1" for e in persisted["report_payload"]["evidence"]
        )
        assert persisted["attribute_type"] == (category if verdict == "attributed" else None)
    assert bool(await store.list_clusterable_probes(run.id)) == (
        source["conclusion"] == "attributed"
    )
    detail = await AttributionReadService(store, ProblemRepository(db)).detail(
        CASE_ID, linked[CASE_ID], WorkspaceReadScope.for_workspace(run.workspace_id)
    )
    assert detail.conclusion == source["conclusion"]
    assert detail.report is not None and detail.report.source_report == source
    tampered = persisted["report_payload"]["sourceReport"].copy()
    tampered["probe_id"] = "wrong-session"

    original = tampered["from_bad_cases"][0]
    input_text = json.dumps(
        {
            "session_id": run.id,
            "selected_target": source["selected_target"],
            "bad_cases": [original],
        }
    )
    with pytest.raises(ValueError, match="canonical"):
        canonical_report(packages.writer_path, input_text, tampered, artifact.parent)
    assert json.loads(artifact.read_bytes())["probe_id"] != "wrong-session"
    assert persisted["execution_manifest"]["modelConfigFingerprint"] != "none"
    replay = await runner.run(replace(run, id=OTHER_RUN_ID), [potential_case()], True)
    assert replay.reused == 1
    assert await store.list_clusterable_probes(OTHER_RUN_ID) == await store.list_clusterable_probes(
        run.id
    )


@pytest.mark.parametrize(
    "args",
    [[], ["--conclusion", "maybe"], ["--conclusion", "attributed", "--attribute-type", "unknown"]],
    ids=["missing-verdict", "invalid-verdict", "unclassified-positive"],
)
def test_writer_rejects_invalid_verdicts(tmp_path: Path, args: list[str]) -> None:
    """A missing or malformed verdict can never yield a new report."""
    writer = Settings().attribution_default_skill_path.with_name("make_probe_report.py")
    data = tmp_path / "input_badcase.json"
    output = tmp_path / "probe_report.json"
    data.write_text(
        json.dumps(
            {
                "session_id": "session",
                "selected_target": {"name": "target", "type": "skill", "version": "v1"},
                "bad_cases": [{"bad_case_id": "case"}],
            }
        )
    )
    main = runpy.run_path(str(writer))["main"]
    argv = [
        "--input-badcase",
        str(data),
        "--bad-case-id",
        "case",
        "--root-cause",
        "Unknown",
        "--attribute-type",
        "error",
        "--probe-description",
        "Finding",
        "--probe-analysis",
        "Trace",
        "--output",
        str(output),
        *args,
    ]
    try:
        code = main(argv)
    except SystemExit as exc:
        code = exc.code
    assert code == 2
    assert not output.exists()


def test_handwritten_report_has_no_writer_receipt(tmp_path: Path) -> None:
    (tmp_path / "probe_report.json").write_text("{}")
    with pytest.raises(ValueError, match="did not invoke"):
        LocalAttribution._read_emission(tmp_path)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("skill", "skill"),
        ("agent", "agent"),
        ("agents", "agent"),
        ("knowledge", "knowledge"),
    ],
)
def test_writer_target_type_preserves_reported_source(kind: str, expected: str) -> None:
    writer = Settings().attribution_default_skill_path.with_name("make_probe_report.py")
    report = runpy.run_path(str(writer))["build_report"](
        session_id="root",
        selected_target={"name": "target", "type": "skill", "version": "v1"},
        conclusion="non_target",
        root_cause="upstream owner",
        evidence_references=[],
        bad_case={"bad_case_id": "case", "type": "skill", "object": "reporter"},
        probe_object="owner",
        object_version="v1",
        attribute_type="flow",
        probe_description="test",
        probe_analysis="test",
        probe_type=kind,
        detail_description=None,
        proposal=None,
    )
    assert report["probe_type"] == expected
    assert report["from_bad_cases"][0]["type"] == "skill"


def test_frozen_plural_writer_is_validated_before_normalization(tmp_path: Path) -> None:
    original = json.dumps({"bad_cases": [{"bad_case_id": "case"}]})
    draft = {
        "probe_id": "immutable-id",
        "probe_type": "agents",
        "probe_object": "owner",
        "object_version": "v1",
        "attribute_type": "flow",
        "probe_description": "test",
        "probe_analysis": "test",
        "from_bad_cases": [{"bad_case_id": "case", "type": "skill"}],
    }
    writer = tmp_path / "frozen.py"
    writer.write_text(
        "import pathlib,sys\npathlib.Path(sys.argv[-1]).write_text(" + repr(json.dumps(draft)) + ")"
    )
    with pytest.raises(ValueError, match="provenance"):
        canonical_report(
            writer, original, {**draft, "probe_id": "tampered"}, tmp_path, explicit_conclusion=False
        )
    report = canonical_report(writer, original, draft, tmp_path, explicit_conclusion=False)
    assert (
        json.loads((tmp_path / "probe_report.json").read_bytes())
        == report
        == {**draft, "probe_type": "agent"}
    )


async def test_historical_inline_binding_can_freeze_and_recover_its_exact_revision(
    attribution_harness: Harness,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Freeze the prior registry instructions and platform writer for an upgraded target."""
    from app.errors import AppError
    from app.service.evolution.attribution_skills import AttributionSkillCreate

    db = attribution_harness.database
    monkeypatch.setitem(factory._REGISTRY, ScriptAgent.provider_id, ScriptAgent)
    settings = Settings(attribution_package_dir=tmp_path, ai_agent_provider=ScriptAgent.provider_id)
    repo = AttributionSkillRepository(db)
    registry = AttributionSkillService(repo)
    packages = AttributionSkillPackageService(
        AttributionSkillPackageRepository(db), tmp_path, settings.attribution_default_skill_path
    )
    runtime = LocalAttribution(
        settings, packages, registry, db, Source(), build_agent_provider(settings)
    )
    workspace = "ws-default"
    target_id = "existing-inline-target"
    revision = await registry.create(
        workspace,
        AttributionSkillCreate(
            skill_key="inline-analysis",
            display_name="Old inline Skill",
            content={"instructions": "Inspect the saved trace and cite its evidence.", "tools": []},
        ),
    )
    run = await load_run(db)
    async with db.transaction() as session:
        await session.execute(
            insert(evolution_targets).values(
                id=target_id,
                workspace_id=workspace,
                object_type="skill",
                object_name=run.target_name,
                repo_url=run.repo_url,
                sub_dir=run.sub_dir,
                default_ref=run.target_version,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    await repo.bind(workspace_id=workspace, revision_id=revision.id, target_id=target_id)
    selected = await runtime.effective(workspace, target_id)
    assert selected.id == revision.id and selected.executor_type == "local_agent"
    frozen = await runtime.resolve(workspace, target_id)
    path = runtime.root(workspace) / "attribute_skill/snapshots" / frozen.content_hash
    assert "cite its evidence" in (path / "skill/SKILL.md").read_text()
    assert (path / "skill/make_probe_report.py").read_bytes() == packages.writer_path.read_bytes()
    saved = await runtime.resolve_snapshot(
        workspace, frozen.skill_key, frozen.revision, frozen.content_hash
    )
    assert saved.content["name"] == revision.skill_key
    with pytest.raises(ValueError, match="identity mismatch"):
        await runtime.resolve_snapshot(
            workspace, frozen.skill_key, frozen.revision + 1, frozen.content_hash
        )
    with pytest.raises(AppError):
        await runtime.resolve(workspace, "missing-target")
    with pytest.raises(AppError):
        await runtime.effective(workspace, "missing-target")
    stale = await runtime.resolve_snapshot(
        workspace, revision.skill_key, revision.revision, revision.content_hash
    )
    assert stale.content["instructions"] == selected.content["instructions"]


def test_canonical_report_retains_detail_and_proposal_for_verified_input(tmp_path: Path) -> None:
    """Keep optional fields and preserve the last valid report when validation fails."""
    writer = Settings().attribution_default_skill_path.with_name("make_probe_report.py")
    row = {"bad_case_id": "case", "type": "skill", "object": "reporter"}
    target = {"name": "target", "type": "skill", "version": "v1"}
    original = json.dumps({"session_id": "session", "selected_target": target, "bad_cases": [row]})
    report = runpy.run_path(str(writer))["build_report"](
        session_id="session",
        selected_target=target,
        conclusion="non_target",
        root_cause="Missing input from upstream",
        evidence_references=["event:agent:1"],
        bad_case=row,
        probe_type="agent",
        probe_object="owner",
        object_version="main",
        attribute_type="context",
        probe_description="Missing input",
        probe_analysis="No input appeared in the trace.",
        detail_description="Test evidence",
        proposal={"change": "Pass the input."},
    )
    assert canonical_report(writer, original, report, tmp_path) == report
    for invalid, reason in (
        ({"conclusion": None}, "report field conclusion"),
        ({"selected_target": {"name": "another"}}, "canonical"),
        ({"probe_type": None}, "probe_type"),
        ({"probe_object": ""}, "report field"),
        ({"from_bad_cases": []}, "provenance"),
        ({"proposal": {"omitted_field": "not in the input contract"}}, "proposal field"),
    ):
        with pytest.raises(ValueError, match=reason):
            canonical_report(writer, original, {**report, **invalid}, tmp_path)
        assert json.loads((tmp_path / "probe_report.json").read_bytes()) == report
