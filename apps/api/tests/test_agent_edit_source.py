# ruff: noqa: RUF001
"""agent-edit patch source: scratch application, feedback, and resume wiring."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.db.models.evolution import EvolutionRunRecord
from app.service.evolution.engine.contracts import ConfigError
from app.service.evolution.git_candidate import CandidateSource, CandidateTrace
from app.service.evolution.patch_source import AgentEditPatchSource, PatchFeedback
from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.ai_agent.contracts import (
    AgentUsage,
    AnalysisRequest,
    AnalysisResult,
    EditRequest,
    EditResult,
    ProviderHealth,
)
from app.third_party_api.ai_agent.edits import EditPlan

NOW = datetime(2026, 11, 23, 1, 15, tzinfo=UTC)
SUB_DIR = "skills/deep-research"


def _run(workspace: Path) -> EvolutionRunRecord:
    """Build one prepared full run whose workspace is the temporary repository."""
    return EvolutionRunRecord(
        id="run-agent-edit",
        title="deep-research evolution",
        mode="full",
        engine_key="full",
        eval_config={},
        target_config_id="target-agent-edit",
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        repo_url="https://example.invalid/repo.git",
        sub_dir=SUB_DIR,
        repo_path=None,
        base_ref="v2.0.0",
        base_commit="a" * 40,
        branch_name=None,
        workspace_path=str(workspace),
        remote_name="origin",
        push_status="pending",
        pushed_at=None,
        push_error=None,
        window_from=None,
        window_to=None,
        models=[],
        status="running",
        blocked_stage=None,
        retry_attempts=0,
        next_retry_at=None,
        eval_status="pending",
        error_stage=None,
        error_message=None,
        error_at=None,
        progress_unit=4,
        stats={},
        created_by=None,
        created_at=NOW,
        finished_at=None,
    )


def _trace() -> CandidateTrace:
    """Build one trace carrying the goal and representative evidence."""
    return CandidateTrace(
        cluster_id="C1",
        cluster_title="检索索引读取失败",
        probes=("probe-1",),
        bad_cases=("case-1",),
        analysis="读取前未校验快照字段导致越界 ENOENT。",
        sources=(
            CandidateSource(
                probe_id="probe-1",
                bad_case_ids=("case-1",),
                description="索引读取未校验快照字段",
                analysis="同批次带校验的 subagent 未报错，属步骤缺失。",
            ),
        ),
    )


def _workspace(tmp_path: Path) -> Path:
    """Create the target sub-directory with two deterministic files."""
    workspace = tmp_path / "workspace"
    target = workspace / SUB_DIR
    target.mkdir(parents=True)
    (target / "skill.json").write_text('{"timeoutSeconds": 30}\n', encoding="utf-8")
    (target / "SKILL.md").write_text("# Deep Research\n", encoding="utf-8")
    return workspace


def _plan(*edits: Mapping[str, Any], summary: str = "raise the fetch timeout") -> dict[str, Any]:
    """Build one raw plan document for the fake or scripted provider."""
    return {"summary": summary, "edits": list(edits)}


def _replace(file: str, target: str, content: str) -> Mapping[str, Any]:
    """Build one replace edit."""
    return {
        "op": "replace",
        "file": file,
        "target": target,
        "content": content,
        "rationale": "three cases timed out",
    }


def _append(file: str, content: str) -> Mapping[str, Any]:
    """Build one append edit."""
    return {
        "op": "append",
        "file": file,
        "content": content,
        "rationale": "document the new timeout",
    }


class ScriptedProvider(AIAgentProvider):
    """Return a scripted plan per call and record every request it receives."""

    provider_id = "scripted"

    def __init__(self, plans: list[Mapping[str, Any]]) -> None:
        """Bind the ordered plan documents and an empty request log."""
        super().__init__(None)
        self._plans = plans
        self.requests: list[EditRequest] = []

    async def analyze(self, request: AnalysisRequest) -> AnalysisResult:
        """Never used on the edit path."""
        raise NotImplementedError

    async def edit_workspace(self, request: EditRequest) -> EditResult:
        """Record the request and return the next scripted plan."""
        self.requests.append(request)
        index = len(self.requests) - 1
        plan = EditPlan.model_validate(self._plans[min(index, len(self._plans) - 1)])
        return EditResult(
            summary=plan.summary,
            provider_id=self.provider_id,
            usage=AgentUsage(model=self.provider_id),
            session_id=f"session-{index + 1}",
            plan=plan,
        )

    async def health_check(self) -> ProviderHealth:
        """Report a healthy scripted backend."""
        return ProviderHealth(provider_id=self.provider_id, healthy=True)


async def test_agent_edit_applies_a_multi_file_plan_on_a_scratch_mirror(
    tmp_path: Path,
) -> None:
    """Two edits land in one bundle while the real workspace stays untouched."""
    workspace = _workspace(tmp_path)
    provider = ScriptedProvider(
        [
            _plan(
                _replace(
                    f"{SUB_DIR}/skill.json",
                    '"timeoutSeconds": 30',
                    '"timeoutSeconds": 120',
                ),
                _append(f"{SUB_DIR}/SKILL.md", "Fetch timeout is 120 seconds."),
                summary="raise the fetch timeout and document it",
            ),
        ],
    )
    source = AgentEditPatchSource(provider)

    bundle = await source.build_bundle(_run(workspace), 1, _trace())

    assert [patch.file for patch in bundle.files] == [
        f"{SUB_DIR}/SKILL.md",
        f"{SUB_DIR}/skill.json",
    ]
    assert bundle.note == "raise the fetch timeout and document it"
    assert bundle.intent is not None
    assert len(bundle.intent.edits) == 2
    assert {status.status for status in bundle.report} == {"applied"}
    assert bundle.session_id == "session-1"
    by_file = {patch.file: patch for patch in bundle.files}
    assert by_file[f"{SUB_DIR}/skill.json"].lines == ('{"timeoutSeconds": 120}',)
    assert "Fetch timeout is 120 seconds." in by_file[f"{SUB_DIR}/SKILL.md"].lines
    # The repository is read-only during edit: the source commits the new bytes later.
    assert (workspace / SUB_DIR / "skill.json").read_text(
        encoding="utf-8"
    ) == '{"timeoutSeconds": 30}\n'
    assert provider.requests[0].allowed_paths == (f"{SUB_DIR}/**",)


async def test_agent_edit_retries_once_with_feedback_when_no_anchor_matches(
    tmp_path: Path,
) -> None:
    """A plan that cannot apply resumes the session with the concrete reasons."""
    workspace = _workspace(tmp_path)
    provider = ScriptedProvider(
        [
            _plan(_replace(f"{SUB_DIR}/SKILL.md", "missing anchor", "unused")),
            _plan(
                _replace(
                    f"{SUB_DIR}/skill.json",
                    '"timeoutSeconds": 30',
                    '"timeoutSeconds": 120',
                ),
            ),
        ],
    )
    source = AgentEditPatchSource(provider)

    bundle = await source.build_bundle(_run(workspace), 1, _trace())

    assert len(provider.requests) == 2
    first, second = provider.requests
    assert first.session_id is None
    assert second.session_id == "session-1"
    assert second.feedback is not None
    assert "未能全部应用" in second.feedback
    assert "anchor" in second.feedback
    assert [patch.file for patch in bundle.files] == [f"{SUB_DIR}/skill.json"]
    assert bundle.session_id == "session-2"


async def test_agent_edit_injects_rejected_round_feedback_and_buffer(
    tmp_path: Path,
) -> None:
    """A rejected round's delta, reason, buffer, and session reach the request."""
    workspace = _workspace(tmp_path)
    provider = ScriptedProvider(
        [
            _plan(
                _replace(
                    f"{SUB_DIR}/skill.json",
                    '"timeoutSeconds": 30',
                    '"timeoutSeconds": 120',
                ),
            ),
        ],
    )
    feedback = PatchFeedback(
        attempt=2,
        failure_reason="候选分低于基线",
        current_score=82.0,
        candidate_score=70.0,
        rejected_edits=("- 上一轮计划：缩短超时", "    - replace skill.json: 又被拒绝"),
        session_id="session-prior",
    )

    await AgentEditPatchSource(provider).build_bundle(
        _run(workspace),
        2,
        _trace(),
        feedback=feedback,
    )

    request = provider.requests[0]
    assert request.session_id == "session-prior"
    assert request.feedback is not None
    assert "候选分 70.0 对比基线 82.0" in request.feedback
    assert "Δ=-12.0" in request.feedback
    assert "候选分低于基线" in request.feedback
    assert "已被拒绝的编辑" in request.feedback
    assert "又被拒绝" in request.feedback


async def test_agent_edit_rejects_an_out_of_scope_plan_without_writing(
    tmp_path: Path,
) -> None:
    """A plan outside allowed_paths fails closed and leaves repository bytes intact."""
    workspace = _workspace(tmp_path)
    outside = workspace / "other" / "notes.md"
    outside.parent.mkdir()
    outside.write_text("keep me\n", encoding="utf-8")
    provider = ScriptedProvider(
        [_plan(_append("other/notes.md", "leak"))],
    )

    with pytest.raises(ConfigError, match="no applicable change"):
        await AgentEditPatchSource(provider).build_bundle(_run(workspace), 1, _trace())

    assert outside.read_text(encoding="utf-8") == "keep me\n"
    assert (workspace / SUB_DIR / "skill.json").read_text(
        encoding="utf-8"
    ) == '{"timeoutSeconds": 30}\n'


async def test_agent_edit_requires_a_prepared_workspace(tmp_path: Path) -> None:
    """A run without a workspace fails before any provider call."""
    provider = ScriptedProvider([_plan()])
    run = replace(_run(tmp_path / "missing"), workspace_path=None)

    with pytest.raises(ConfigError, match="prepared workspace"):
        await AgentEditPatchSource(provider).build_bundle(run, 1, _trace())
    assert provider.requests == []


def test_patch_feedback_rejects_a_non_positive_attempt() -> None:
    """The retry ordinal is validated before it becomes prompt text."""
    with pytest.raises(ValueError, match="attempt"):
        PatchFeedback(attempt=0)
