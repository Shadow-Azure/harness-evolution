"""SQLite acceptance test for one case, immutable Skill selection, and replay."""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import insert, select

from app.config import Settings
from app.db.crud.attribution_skill_packages import AttributionSkillPackageRepository
from app.db.crud.attribution_skills import AttributionSkillRepository
from app.db.crud.attributions import AttributionRepository
from app.db.models.domain import evolution_targets, probe_reports
from app.service.evolution.attribution import AttributionRunner
from app.service.evolution.attribution_skill_packages import AttributionSkillPackageService
from app.service.evolution.attribution_skills import AttributionSkillService
from app.service.evolution.local_attribution import ENGINE, LocalAttribution, canonical_report
from app.third_party_api.attribution.backend import AgentBackend, AgentFactory
from tests.attribution.support import CASE_ID, NOW, OTHER_RUN_ID, Harness, potential_case
from tests.attribution.test_m10_03_runner import load_run
from tests.workspaces.helpers import create_user


class Source:
    async def read_file(self, *, repo_url: str, sub_dir: str, ref: str, file_name: str) -> str:
        return "# Deep research\nAlways inspect the evidence."


class ScriptAgent(AgentBackend):
    category = "flow"

    async def execute(self, directory: Path, prompt: str, model: str, timeout_seconds: int) -> int:
        import asyncio

        assert prompt == "/acceptance-skill input_badcase.json，请分析并生成归因报告"  # noqa: RUF001
        assert (directory / "session_tree.json").is_file()
        assert (directory / "attribute_source.md").is_file()
        row = json.loads((directory / "input_badcase.json").read_bytes())["bad_cases"][0]
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            ".claude/skills/acceptance-skill/make_probe_report.py",
            "--input-badcase",
            "input_badcase.json",
            "--bad-case-id",
            row["bad_case_id"],
            "--probe_object",
            row["object"],
            "--attribute-type",
            self.category,
            "--probe-description",
            "流程缺少校验",
            "--probe-analysis",
            "缺少复核步骤",
            "--output",
            "probe_report.json",
            cwd=directory,
        )
        assert await proc.wait() == 0
        return 10


@pytest.mark.parametrize(
    "category",
    ["flow"] if os.environ.get("HE_TEST_LIVE_ATTRIBUTION") == "1" else ["flow", "context"],
)
async def test_local_skill_report_to_sqlite(
    category: str, attribution_harness: Harness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Use a real CLI only when explicitly enabled for a synthetic acceptance run."""
    db = attribution_harness.database
    monkeypatch.setattr(ScriptAgent, "category", category)
    use_claude = os.environ.get("HE_TEST_LIVE_ATTRIBUTION") == "1"
    monkeypatch.setitem(AgentFactory.providers, "test", ScriptAgent)
    settings = Settings(
        attribution_package_dir=tmp_path / "attribute",
        attribution_agent="claude" if use_claude else "test",
        attribution_timeout_seconds=150,
    )
    packages = AttributionSkillPackageService(
        AttributionSkillPackageRepository(db),
        settings.attribution_package_dir,
        settings.attribution_default_skill_path,
    )
    service = LocalAttribution(
        settings, packages, AttributionSkillService(AttributionSkillRepository(db)), db, Source()
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
            ".claude/skills/acceptance-skill/make_probe_report.py "
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
    await packages.activate(run.workspace_id, package.id, user_id)
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
    await service.registry.unbind(run.workspace_id, target_id="acceptance-target")
    assert (await service.effective(run.workspace_id, "acceptance-target")).source == "workspace"
    await service.bind(run.workspace_id, "acceptance-target", package.id)
    selected = await service.resolve(run.workspace_id, "acceptance-target")
    assert selected.skill_key == "acceptance-skill"
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
    assert persisted["report_payload"]["sourceReport"] == json.loads(artifact.read_bytes())
    if selected != default:
        assert persisted["attribute_type"] == category
    tampered = persisted["report_payload"]["sourceReport"].copy()
    tampered["probe_id"] = "wrong-session"

    original = tampered["from_bad_cases"][0]
    input_text = json.dumps({"session_id": run.id, "bad_cases": [original]})
    with pytest.raises(ValueError, match="canonical"):
        canonical_report(packages.writer_path, input_text, tampered, artifact.parent)
    assert json.loads(artifact.read_bytes())["probe_id"] != "wrong-session"
    assert persisted["execution_manifest"]["modelConfigFingerprint"] != "none"
    replay = await runner.run(replace(run, id=OTHER_RUN_ID), [potential_case()], True)
    assert replay.reused == 1


def test_handwritten_report_has_no_writer_receipt(tmp_path: Path) -> None:
    (tmp_path / "probe_report.json").write_text("{}")
    with pytest.raises(ValueError, match="did not invoke"):
        LocalAttribution._read_emission(tmp_path)
