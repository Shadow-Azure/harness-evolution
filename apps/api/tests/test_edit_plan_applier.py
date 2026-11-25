"""EditPlan contract, deterministic applier, and bundle compatibility."""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

from app.db.models.evolution import EvolutionRunRecord
from app.service.evolution.engine.contracts import ConfigError
from app.service.evolution.git_candidate import CandidateTrace
from app.service.evolution.patch_source import (
    DEFAULT_PATCH_SOURCE_MODE,
    PATCH_SOURCE_MODES,
    AgentEditPatchSource,
    MinimalConfigPatchSource,
    PatchBundle,
    PatchSource,
    PlaceholderPatchSource,
    default_patch_source_factory,
)
from app.third_party_api.ai_agent.edits import (
    EDIT_BUDGET,
    MAX_CONTENT_LINES,
    EditOp,
    EditOpName,
    EditPlan,
    EditPlanError,
    EditStatus,
    EditStatusKind,
    apply_edit_plan,
)
from app.third_party_api.ai_agent.fake import FakeAIAgentProvider
from app.third_party_api.git.workspace import Patch

NOW = datetime(2026, 11, 23, 0, 45, tzinfo=UTC)


def _run(
    *,
    workspace_path: Path | None = None,
    eval_config: dict[str, object] | None = None,
) -> EvolutionRunRecord:
    """Build one run snapshot for patch source selection."""
    return EvolutionRunRecord(
        id="run-edit-plan",
        title="deep-research evolution",
        mode="full",
        engine_key="full",
        eval_config=eval_config or {},
        target_config_id="target-edit-plan",
        target_type="skill",
        target_name="deep-research",
        target_version="v2.0.0",
        repo_url="https://example.invalid/repo.git",
        sub_dir="skills/deep-research",
        repo_path=None,
        base_ref="v2.0.0",
        base_commit="a" * 40,
        branch_name=None,
        workspace_path=str(workspace_path) if workspace_path else None,
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


def _trace(text: str) -> CandidateTrace:
    """Build one trace carrying the bad-case evidence text."""
    return CandidateTrace(
        cluster_id="C1",
        cluster_title="对象行为异常",
        probes=("probe-1",),
        bad_cases=("bc-050b-03",),
        analysis=text,
    )


def _write(path: Path, text: str) -> None:
    """Create a parent directory and write exact UTF-8 bytes without newline translation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def _symlinks_supported() -> bool:
    """Probe once whether this host permits creating a symlink at all."""
    try:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "link").symlink_to(Path(tmp) / "missing-target")
    except (NotImplementedError, OSError):
        return False
    return True


_NO_SYMLINK = not _symlinks_supported()


def test_four_ops_apply_to_real_files(tmp_path: Path) -> None:
    """append, insert_after, replace, and delete each produce exact content."""
    workspace = tmp_path / "ws"
    _write(workspace / "notes.md", "a\n")
    _write(workspace / "skill.md", "one\ntwo\nthree")
    _write(workspace / "config.json", '{"timeout": 30}\n')
    _write(workspace / "old.md", "keep\ndrop\nkeep2\n")
    plan = EditPlan(
        summary="four ops",
        edits=(
            EditOp(op="append", file="notes.md", content="b\nc", rationale="append"),
            EditOp(
                op="insert_after",
                file="skill.md",
                target="two",
                content="two-and-a-half",
                rationale="insert",
            ),
            EditOp(
                op="replace",
                file="config.json",
                target='"timeout": 30',
                content='"timeout": 120',
                rationale="replace",
            ),
            EditOp(op="delete", file="old.md", target="drop\n", rationale="delete"),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert (workspace / "notes.md").read_text(encoding="utf-8") == "a\nb\nc\n"
    assert (workspace / "skill.md").read_text(encoding="utf-8") == (
        "one\ntwo\ntwo-and-a-half\nthree"
    )
    assert (workspace / "config.json").read_text(encoding="utf-8") == '{"timeout": 120}\n'
    assert (workspace / "old.md").read_text(encoding="utf-8") == "keep\nkeep2\n"
    assert application.files == ("config.json", "notes.md", "old.md", "skill.md")
    assert [status.status for status in application.report] == ["applied"] * 4
    assert application.applied == application.report
    assert application.skipped == ()


def test_append_normalizes_the_trailing_newline(tmp_path: Path) -> None:
    """Append preserves existing bytes and ends with exactly one newline."""
    workspace = tmp_path / "ws"
    _write(workspace / "empty.md", "")
    _write(workspace / "no-final-newline.md", "no-newline")
    plan = EditPlan(
        summary="append newline handling",
        edits=(
            EditOp(op="append", file="empty.md", content="line1\nline2\n\n", rationale="r"),
            EditOp(op="append", file="no-final-newline.md", content="tail", rationale="r"),
        ),
    )

    apply_edit_plan(plan, workspace=workspace)

    assert (workspace / "empty.md").read_text(encoding="utf-8") == "line1\nline2\n"
    assert (workspace / "no-final-newline.md").read_text(encoding="utf-8") == ("no-newline\ntail\n")


def test_missing_anchor_is_skipped_and_remaining_edits_run(tmp_path: Path) -> None:
    """A missing anchor or file skips that edit without blocking later edits."""
    workspace = tmp_path / "ws"
    _write(workspace / "a.md", "hello\n")
    plan = EditPlan(
        summary="missing anchor",
        edits=(
            EditOp(op="replace", file="a.md", target="absent", content="x", rationale="r"),
            EditOp(op="append", file="missing.md", content="x", rationale="r"),
            EditOp(op="append", file="a.md", content="tail", rationale="r"),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert [status.status for status in application.report] == [
        "skipped_anchor_missing",
        "skipped_anchor_missing",
        "applied",
    ]
    assert len(application.skipped) == 2
    assert "edits[0]" in application.skipped[0].message
    assert "anchor not found" in application.skipped[0].message
    assert "edits[1]" in application.skipped[1].message
    assert "file does not exist" in application.skipped[1].message
    assert (workspace / "a.md").read_text(encoding="utf-8") == "hello\ntail\n"


@pytest.mark.parametrize("op", ["replace", "insert_after", "delete"])
def test_ambiguous_anchor_is_an_error_and_is_never_guessed(
    tmp_path: Path,
    op: EditOpName,
) -> None:
    """An anchor appearing twice is rejected instead of picking an occurrence."""
    workspace = tmp_path / "ws"
    _write(workspace / "dup.md", "x\nx\n")
    plan = EditPlan(
        summary="ambiguous anchor",
        edits=(
            EditOp(
                op=op,
                file="dup.md",
                target="x",
                content=None if op == "delete" else "y",
                rationale="r",
            ),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "error"
    assert "ambiguous (2 occurrences)" in application.report[0].message
    assert application.errors[0] is application.report[0]
    assert (workspace / "dup.md").read_text(encoding="utf-8") == "x\nx\n"


def test_scope_violation_is_an_error_and_in_scope_edits_apply(tmp_path: Path) -> None:
    """allowed_paths narrows the applies; an outside file is an error."""
    workspace = tmp_path / "ws"
    _write(workspace / "README.md", "readme\n")
    _write(workspace / "skills" / "deep" / "SKILL.md", "skill\n")
    outside = EditPlan(
        summary="outside",
        edits=(
            EditOp(op="replace", file="README.md", target="readme", content="x", rationale="r"),
        ),
    )
    inside = EditPlan(
        summary="inside",
        edits=(
            EditOp(
                op="replace",
                file="skills/deep/SKILL.md",
                target="skill",
                content="updated",
                rationale="r",
            ),
        ),
    )

    rejected = apply_edit_plan(
        outside,
        workspace=workspace,
        allowed_paths=("skills/**",),
    )
    accepted = apply_edit_plan(
        inside,
        workspace=workspace,
        allowed_paths=("skills/**",),
    )

    assert rejected.report[0].status == "error"
    assert "allowed_paths" in rejected.report[0].message
    assert (workspace / "README.md").read_text(encoding="utf-8") == "readme\n"
    assert accepted.report[0].status == "applied"
    assert (workspace / "skills" / "deep" / "SKILL.md").read_text(encoding="utf-8") == "updated\n"


@pytest.mark.parametrize(
    ("allowed", "file", "applies"),
    [
        (("skills/**",), "skills/a.md", True),
        (("skills/**",), "skills/deep/b.md", True),
        (("skills/**",), "README.md", False),
        (("**/*.json",), "config/a.json", True),
        (("**/*.json",), "skills/deep/a.json", True),
        (("skills/*",), "skills/deep/a.md", False),
        (("skills/?.md",), "skills/a.md", True),
        (("skills/?.md",), "skills/ab.md", False),
        (("./skills/**",), "skills/a.md", True),
        (("",), "anything/at/all.md", False),
        ((), "anything/at/all.md", False),
        (None, "anything/at/all.md", True),
    ],
)
def test_allowed_paths_use_posix_globs(
    tmp_path: Path,
    allowed: tuple[str, ...] | None,
    file: str,
    applies: bool,
) -> None:
    """Glob scope supports recursive globs, allows nothing when empty, and None widens."""
    workspace = tmp_path / "ws"
    _write(workspace / file, "old\n")
    plan = EditPlan(
        summary="glob",
        edits=(EditOp(op="replace", file=file, target="old", content="new", rationale="r"),),
    )

    application = apply_edit_plan(plan, workspace=workspace, allowed_paths=allowed)

    assert (application.report[0].status == "applied") is applies


def test_allowed_paths_none_means_no_narrowing_and_empty_denies(tmp_path: Path) -> None:
    """The default is an explicit no-narrowing sentinel, not an empty scope."""
    workspace = tmp_path / "ws"
    _write(workspace / "README.md", "readme\n")
    plan = EditPlan(
        summary="scope contract",
        edits=(
            EditOp(op="replace", file="README.md", target="readme", content="x", rationale="r"),
        ),
    )

    defaulted = apply_edit_plan(plan, workspace=workspace)
    assert defaulted.report[0].status == "applied"

    _write(workspace / "README.md", "readme\n")
    denied = apply_edit_plan(plan, workspace=workspace, allowed_paths=())

    assert denied.report[0].status == "error"
    assert "allowed_paths []" in denied.report[0].message
    assert (workspace / "README.md").read_text(encoding="utf-8") == "readme\n"


@pytest.mark.parametrize(
    "file",
    [
        "",
        " a.md",
        "a.md ",
        ".harness-evolution/edits.json5",
        ".Harness-Evolution/edits.json5",
        ".git/config",
        ".GIT/config",
        "skills/.harness-evolution/candidate.md",
        "../escape.md",
        "/absolute.md",
        "C:/escape.md",
        "a\\b.md",
        "a//b.md",
        "./a.md",
        "a/../b.md",
        "a\x00b.md",
    ],
)
def test_unsafe_paths_are_rejected_by_the_model(file: str) -> None:
    """Absolute, traversal, protected, and non-canonical paths never validate."""
    with pytest.raises(ValidationError):
        EditOp(op="append", file=file, content="x", rationale="r")


@pytest.mark.parametrize(
    ("op", "target", "content"),
    [
        ("append", "forbidden-target", "content"),
        ("append", None, ""),
        ("append", None, "   "),
        ("replace", None, "content"),
        ("replace", "target", None),
        ("insert_after", None, "content"),
        ("insert_after", "target", "   "),
        ("delete", None, None),
        ("delete", "target", "forbidden-content"),
    ],
)
def test_op_specific_fields_are_enforced(
    op: EditOpName,
    target: str | None,
    content: str | None,
) -> None:
    """Required and forbidden fields are rejected before any applier runs."""
    with pytest.raises(ValidationError):
        EditOp(op=op, file="a.md", target=target, content=content, rationale="r")


def test_insert_after_accepts_a_unique_multiline_block_anchor(tmp_path: Path) -> None:
    """A unique four-line block anchor validates and applies after its last line."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "l1\nl2\nl3\nl4\nl5\nl6\n")
    plan = EditPlan(
        summary="multiline block",
        edits=(
            EditOp(
                op="insert_after",
                file="doc.md",
                target="l2\nl3\nl4\nl5\n",
                content="NEW",
                rationale="r",
            ),
        ),
    )

    validated = EditPlan.model_validate(plan.model_dump())
    application = apply_edit_plan(validated, workspace=workspace)

    assert application.report[0].status == "applied"
    assert (workspace / "doc.md").read_bytes() == b"l1\nl2\nl3\nl4\nl5\nNEW\nl6\n"


def test_replace_still_applies_a_multiline_anchor(tmp_path: Path) -> None:
    """replace keeps allowing a cross-line target; only insert_after was narrower."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "one\ntwo\nthree\n")
    plan = EditPlan(
        summary="multiline replace",
        edits=(
            EditOp(
                op="replace",
                file="doc.md",
                target="one\ntwo",
                content="ONE",
                rationale="r",
            ),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "applied"
    assert (workspace / "doc.md").read_bytes() == b"ONE\nthree\n"


def test_summary_rationale_and_content_cap_are_enforced() -> None:
    """The plan summary, edit rationale, and one-edit content cap all validate."""
    with pytest.raises(ValidationError):
        EditPlan(
            summary="  ", edits=(EditOp(op="append", file="a.md", content="x", rationale="r"),)
        )
    with pytest.raises(ValidationError):
        EditOp(op="append", file="a.md", content="x", rationale=" ")
    too_long = "\n".join("x" for _ in range(MAX_CONTENT_LINES + 1))
    with pytest.raises(ValidationError, match="lines"):
        EditOp(op="append", file="a.md", content=too_long, rationale="r")
    accepted = EditOp(
        op="append",
        file="a.md",
        content="\n".join("x" for _ in range(MAX_CONTENT_LINES)),
        rationale="r",
    )
    assert accepted.content is not None


def test_later_edit_sees_the_result_of_an_earlier_edit(tmp_path: Path) -> None:
    """Every edit re-reads its file, so a changed anchor is visible immediately."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "alpha\nbeta\n")
    plan = EditPlan(
        summary="sequential",
        edits=(
            EditOp(op="replace", file="doc.md", target="beta", content="gamma", rationale="r"),
            EditOp(op="replace", file="doc.md", target="gamma", content="delta", rationale="r"),
            EditOp(
                op="insert_after",
                file="doc.md",
                target="delta",
                content="after delta",
                rationale="r",
            ),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert [status.status for status in application.report] == ["applied"] * 3
    assert (workspace / "doc.md").read_text(encoding="utf-8") == ("alpha\ndelta\nafter delta\n")


def test_model_rejects_a_plan_above_the_edit_budget() -> None:
    """The Pydantic contract rejects more edits than EDIT_BUDGET."""
    edits = [
        EditOp(op="append", file="a.md", content=f"line-{index}", rationale="r")
        for index in range(EDIT_BUDGET + 1)
    ]
    with pytest.raises(ValidationError, match="edit_budget"):
        EditPlan(summary="too many", edits=tuple(edits))
    accepted = EditPlan(summary="at budget", edits=tuple(edits[:EDIT_BUDGET]))
    assert len(accepted.edits) == EDIT_BUDGET


def test_edit_plan_edits_are_a_deeply_immutable_tuple() -> None:
    """The frozen model holds a tuple, while JSON arrays still validate into it."""
    edit = EditOp(op="append", file="a.md", content="x", rationale="r")
    plan = EditPlan(summary="immutable", edits=(edit,))

    assert isinstance(plan.edits, tuple)
    assert plan.edits == (edit,)
    assert not hasattr(plan.edits, "append")
    assert isinstance(hash(plan), int)

    schema = EditPlan.model_json_schema()
    assert schema["properties"]["edits"]["type"] == "array"

    validated = EditPlan.model_validate(
        {
            "summary": "from json",
            "edits": [{"op": "append", "file": "a.md", "content": "x", "rationale": "r"}],
        },
    )
    assert isinstance(validated.edits, tuple)
    assert validated.edits == (edit,)
    assert isinstance(hash(validated), int)


def test_apply_time_budget_hard_truncates_a_bypassed_plan(tmp_path: Path) -> None:
    """A plan constructed around the model is still hard-truncated at apply time."""
    workspace = tmp_path / "ws"
    _write(workspace / "a.md", "base\n")
    edits = [
        EditOp(op="append", file="a.md", content=f"n{index}", rationale="r")
        for index in range(EDIT_BUDGET + 2)
    ]
    bypassed = EditPlan.model_construct(summary="bypassed", edits=edits)

    application = apply_edit_plan(bypassed, workspace=workspace)

    assert [status.status for status in application.report] == (
        ["applied"] * EDIT_BUDGET + ["error"] * 2
    )
    assert "edit budget exceeded" in application.report[-1].message
    content = (workspace / "a.md").read_text(encoding="utf-8")
    assert f"n{EDIT_BUDGET - 1}\n" in content
    assert f"n{EDIT_BUDGET}\n" not in content


def test_caller_budget_can_tighten_but_never_widen_the_ceiling(tmp_path: Path) -> None:
    """edit_budget tightens below EDIT_BUDGET and is clamped above it."""
    workspace = tmp_path / "ws"
    _write(workspace / "a.md", "base\n")
    three = EditPlan(
        summary="three",
        edits=tuple(
            EditOp(op="append", file="a.md", content=f"n{index}", rationale="r")
            for index in range(3)
        ),
    )

    tightened = apply_edit_plan(three, workspace=workspace, edit_budget=1)

    assert [status.status for status in tightened.report] == ["applied", "error", "error"]

    _write(workspace / "a.md", "base\n")
    wide_edits = [
        EditOp(op="append", file="a.md", content=f"w{index}", rationale="r")
        for index in range(EDIT_BUDGET + 2)
    ]
    widened = EditPlan.model_construct(summary="widened", edits=wide_edits)
    clamped = apply_edit_plan(widened, workspace=workspace, edit_budget=99)

    assert [status.status for status in clamped.report].count("applied") == EDIT_BUDGET

    with pytest.raises(EditPlanError, match="negative"):
        apply_edit_plan(three, workspace=workspace, edit_budget=-1)


def test_replay_is_byte_identical(tmp_path: Path) -> None:
    """The same plan over the same base produces identical files and report."""
    base = "# Doc\n\nalpha\nbeta\n"
    left = tmp_path / "left"
    right = tmp_path / "right"
    _write(left / "doc.md", base)
    _write(right / "doc.md", base)

    def plan() -> EditPlan:
        return EditPlan(
            summary="replay",
            edits=(
                EditOp(op="replace", file="doc.md", target="alpha", content="ALPHA", rationale="r"),
                EditOp(
                    op="insert_after",
                    file="doc.md",
                    target="ALPHA",
                    content="inserted",
                    rationale="r",
                ),
                EditOp(op="delete", file="doc.md", target="beta\n", rationale="r"),
                EditOp(op="append", file="doc.md", content="tail", rationale="r"),
            ),
        )

    left_application = apply_edit_plan(plan(), workspace=left)
    right_application = apply_edit_plan(plan(), workspace=right)

    assert left_application == right_application
    assert (left / "doc.md").read_bytes() == (right / "doc.md").read_bytes()
    assert (left / "doc.md").read_text(encoding="utf-8") == ("# Doc\n\nALPHA\ninserted\ntail\n")


def test_edit_status_rejects_invalid_fields() -> None:
    """An impossible status record fails fast instead of reaching a report."""
    with pytest.raises(ValueError, match="negative"):
        EditStatus(index=-1, op="append", file="a.md", status="applied")
    with pytest.raises(ValueError, match="unknown"):
        EditStatus(
            index=0,
            op="append",
            file="a.md",
            status=cast("EditStatusKind", "unknown"),
        )


def test_directory_target_and_glob_directory_match_are_errors(tmp_path: Path) -> None:
    """A directory is never a writable target even when the glob matches it."""
    workspace = tmp_path / "ws"
    (workspace / "skills").mkdir(parents=True)
    plan = EditPlan(
        summary="directory",
        edits=(EditOp(op="append", file="skills", content="x", rationale="r"),),
    )

    application = apply_edit_plan(
        plan,
        workspace=workspace,
        allowed_paths=("skills/**",),
    )

    assert application.report[0].status == "error"
    assert "regular file" in application.report[0].message


@pytest.mark.skipif(_NO_SYMLINK, reason="symlink creation requires Developer Mode on Windows")
def test_symlink_escape_is_an_error(tmp_path: Path) -> None:
    """A symlink that resolves outside the workspace is rejected before write."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside.md"
    _write(outside, "secret\n")
    (workspace / "link.md").symlink_to(outside)
    plan = EditPlan(
        summary="symlink",
        edits=(
            EditOp(op="replace", file="link.md", target="secret", content="leaked", rationale="r"),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "error"
    assert "escapes the workspace" in application.report[0].message
    assert outside.read_text(encoding="utf-8") == "secret\n"


@pytest.mark.skipif(_NO_SYMLINK, reason="symlink creation requires Developer Mode on Windows")
@pytest.mark.parametrize("protected", [".harness-evolution", ".git"])
def test_symlink_into_a_protected_directory_is_an_error(
    tmp_path: Path,
    protected: str,
) -> None:
    """A workspace-internal symlink cannot smuggle an edit into a protected dir."""
    workspace = tmp_path / "ws"
    protected_dir = workspace / protected
    protected_dir.mkdir(parents=True)
    secret = protected_dir / "secret.md"
    _write(secret, "secret\n")
    (workspace / "link.md").symlink_to(secret)
    plan = EditPlan(
        summary="protected symlink",
        edits=(
            EditOp(op="replace", file="link.md", target="secret", content="leaked", rationale="r"),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "error"
    assert "protected directory" in application.report[0].message
    assert secret.read_text(encoding="utf-8") == "secret\n"


@pytest.mark.skipif(_NO_SYMLINK, reason="symlink creation requires Developer Mode on Windows")
def test_symlink_outside_allowed_paths_is_an_error(tmp_path: Path) -> None:
    """The resolved target, not just the lexical path, must satisfy the scope."""
    workspace = tmp_path / "ws"
    _write(workspace / "README.md", "outside\n")
    _write(workspace / "skills" / "deep" / "SKILL.md", "inside\n")
    (workspace / "skills" / "link.md").symlink_to(workspace / "README.md")
    plan = EditPlan(
        summary="scope symlink",
        edits=(
            EditOp(
                op="replace", file="skills/link.md", target="outside", content="x", rationale="r"
            ),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace, allowed_paths=("skills/**",))

    assert application.report[0].status == "error"
    assert "resolved path is outside allowed_paths" in application.report[0].message
    assert (workspace / "README.md").read_text(encoding="utf-8") == "outside\n"


def test_invalid_utf8_is_an_error(tmp_path: Path) -> None:
    """A non-UTF-8 target fails the edit instead of being rewritten lossily."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "binary.md").write_bytes(b"\xff\xfe")
    plan = EditPlan(
        summary="binary",
        edits=(EditOp(op="append", file="binary.md", content="x", rationale="r"),),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "error"
    assert "UTF-8" in application.report[0].message


def test_bypassed_edit_with_an_unsafe_path_is_an_error(tmp_path: Path) -> None:
    """A bypassed EditOp is re-validated for path safety by the applier."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    raw = EditOp.model_construct(
        op="append",
        file="../escape.md",
        target=None,
        content="x",
        rationale="r",
    )
    plan = EditPlan.model_construct(summary="bypassed", edits=[raw])

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "error"
    assert ".." in application.report[0].message


@pytest.mark.parametrize(
    ("op", "target", "content", "constraint"),
    [
        ("append", None, None, "content is required"),
        ("replace", None, "x", "target is required"),
        ("insert_after", "line", None, "content is required"),
        ("replace", "line", None, "content is required"),
    ],
)
def test_bypassed_edits_with_missing_fields_are_errors(
    tmp_path: Path,
    op: EditOpName,
    target: str | None,
    content: str | None,
    constraint: str,
) -> None:
    """Applying around the model still rejects an incomplete op safely."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "line\n")
    raw = EditOp.model_construct(
        op=op,
        file="doc.md",
        target=target,
        content=content,
        rationale="r",
    )
    plan = EditPlan.model_construct(summary="bypassed", edits=[raw])

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "error"
    assert constraint in application.report[0].message


def test_insert_after_missing_anchor_is_skipped(tmp_path: Path) -> None:
    """A missing insert_after anchor is skipped, not guessed."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "line\n")
    plan = EditPlan(
        summary="missing",
        edits=(
            EditOp(op="insert_after", file="doc.md", target="absent", content="x", rationale="r"),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "skipped_anchor_missing"
    assert "anchor not found" in application.report[0].message


def test_insert_after_last_line_without_newline(tmp_path: Path) -> None:
    """Inserting after a final unterminated line adds the line boundary first."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "one\ntwo")
    plan = EditPlan(
        summary="last line",
        edits=(
            EditOp(op="insert_after", file="doc.md", target="two", content="three", rationale="r"),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "applied"
    assert (workspace / "doc.md").read_text(encoding="utf-8") == "one\ntwo\nthree\n"


@pytest.mark.parametrize(
    ("text", "target", "content", "expected"),
    [
        # A mid-line match inserts after that line's terminator.
        ("alpha beta\ngamma\n", "beta", "x", "alpha beta\nx\ngamma\n"),
        # A line-end match reuses the anchor line's own newline.
        ("one\ntwo\n", "two", "three", "one\ntwo\nthree\n"),
        # A final unterminated line gains its boundary before the insert.
        ("one\ntwo", "two", "three", "one\ntwo\nthree\n"),
        # A mid-line target on the unterminated final line keeps the tail to EOF.
        ("one\ntwo", "tw", "x", "one\ntwo\nx\n"),
        ("alpha\nbeta gamma", "beta", "x", "alpha\nbeta gamma\nx\n"),
        # A target stopping halfway through a CRLF terminator finishes it.
        ("l1\r\nl2\r\n", "l1\r", "NEW", "l1\r\nNEW\r\nl2\r\n"),
        # A target ending with a bare \r keeps its bytes; inserted lines use \n.
        ("a\rb\rc\r", "b\r", "x", "a\rb\rx\nc\r"),
        # A bare-\r anchor keeps its bytes; inserted lines use \n.
        ("a\rb\rc\r", "b", "x", "a\rb\rx\nc\r"),
        # A CRLF anchor line inserts \r\n-terminated content.
        ('x: {"a": 1}\r\ny\r\n', 'x: {"a": 1}', "z", 'x: {"a": 1}\r\nz\r\ny\r\n'),
    ],
)
def test_insert_after_single_line_targets_reproduce_exact_bytes(
    tmp_path: Path,
    text: str,
    target: str,
    content: str,
    expected: str,
) -> None:
    """Single-line anchors keep producing the historical byte-for-byte output."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", text)
    plan = EditPlan(
        summary="single-line bytes",
        edits=(
            EditOp(
                op="insert_after",
                file="doc.md",
                target=target,
                content=content,
                rationale="r",
            ),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "applied"
    assert (workspace / "doc.md").read_bytes() == expected.encode("utf-8")


def test_insert_after_multiline_block_without_trailing_newline(tmp_path: Path) -> None:
    """A block that ends mid-file inserts after its last line's terminator."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "l1\nl2\nl3\n")
    plan = EditPlan(
        summary="block mid-file",
        edits=(
            EditOp(op="insert_after", file="doc.md", target="l1\nl2", content="NEW", rationale="r"),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "applied"
    assert (workspace / "doc.md").read_bytes() == b"l1\nl2\nNEW\nl3\n"


def test_insert_after_target_ending_with_newline_adds_no_blank_line(tmp_path: Path) -> None:
    """A target that ends with its own newline puts the insert right after it."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "l1\nl2\nl3\nl4\n")
    plan = EditPlan(
        summary="terminated anchor",
        edits=(
            EditOp(
                op="insert_after",
                file="doc.md",
                target="l1\nl2\n",
                content="NEW",
                rationale="r",
            ),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "applied"
    assert (workspace / "doc.md").read_bytes() == b"l1\nl2\nNEW\nl3\nl4\n"


def test_insert_after_multiline_block_missing_and_ambiguous(tmp_path: Path) -> None:
    """A multi-line block anchor follows the same 0/2 occurrence contract."""
    workspace = tmp_path / "ws"
    _write(workspace / "missing.md", "l1\nl2\nl3\n")
    _write(workspace / "dup.md", "l1\nl2\nl1\nl2\nl3\n")
    missing = EditPlan(
        summary="missing block",
        edits=(
            EditOp(
                op="insert_after",
                file="missing.md",
                target="l1\nl2\nl4\n",
                content="x",
                rationale="r",
            ),
        ),
    )
    ambiguous = EditPlan(
        summary="ambiguous block",
        edits=(
            EditOp(
                op="insert_after",
                file="dup.md",
                target="l1\nl2\n",
                content="x",
                rationale="r",
            ),
        ),
    )

    missing_application = apply_edit_plan(missing, workspace=workspace)
    ambiguous_application = apply_edit_plan(ambiguous, workspace=workspace)

    assert missing_application.report[0].status == "skipped_anchor_missing"
    assert "anchor not found" in missing_application.report[0].message
    assert ambiguous_application.report[0].status == "error"
    assert "anchor is ambiguous" in ambiguous_application.report[0].message
    assert (workspace / "missing.md").read_bytes() == b"l1\nl2\nl3\n"
    assert (workspace / "dup.md").read_bytes() == b"l1\nl2\nl1\nl2\nl3\n"


def test_insert_after_multiline_block_keeps_crlf_ending(tmp_path: Path) -> None:
    """A multi-line block in a CRLF file inserts CRLF-terminated lines."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "l1\r\nl2\r\nl3\r\nl4\r\nl5\r\n")
    plan = EditPlan(
        summary="crlf block",
        edits=(
            EditOp(
                op="insert_after",
                file="doc.md",
                target="l2\r\nl3\r\nl4\r\n",
                content="NEW1\nNEW2",
                rationale="r",
            ),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "applied"
    assert (workspace / "doc.md").read_bytes() == (
        b"l1\r\nl2\r\nl3\r\nl4\r\nNEW1\r\nNEW2\r\nl5\r\n"
    )


def test_production_shaped_plan_replays_with_every_edit_applied(tmp_path: Path) -> None:
    """A production-shaped 8-edit plan with a block anchor validates and applies."""
    workspace = tmp_path / "ws"
    skill = (
        "# demo skill\n"
        "\n"
        "## 概述\n"
        "把上游轨迹整理成周报。\n"
        "\n"
        "## 步骤\n"
        "### 输入\n"
        "读取 sessions 列表\n"
        "过滤已归档条目\n"
        "\n"
        "### 输出\n"
        "生成 summary.md\n"
        "附带统计表\n"
        "\n"
        "### 验收模板\n"
        "运行 fixtures:check 确认 corpus 有效\n"
        "运行 test:api 确认回归全绿\n"
        "确认 git diff 只含目标文件\n"
        "\n"
        "## 限制\n"
        "不读取生产凭据。\n"
    )
    _write(workspace / "skills" / "demo" / "SKILL.md", skill)
    regression_evidence = "\n".join(f"回归证据第 {index} 行" for index in range(1, 29))
    block_anchor = (
        "### 验收模板\n"
        "运行 fixtures:check 确认 corpus 有效\n"
        "运行 test:api 确认回归全绿\n"
        "确认 git diff 只含目标文件\n"
    )
    raw_plan = {
        "summary": "补齐验收模板回归证据并修正统计口径",
        "edits": [
            {
                "op": "replace",
                "file": "skills/demo/SKILL.md",
                "target": "把上游轨迹整理成周报。",
                "content": "把上游轨迹整理成带异常标注的周报。",
                "rationale": "概述缺异常标注口径",
            },
            {
                "op": "insert_after",
                "file": "skills/demo/SKILL.md",
                "target": block_anchor,
                "content": regression_evidence,
                "rationale": "验收模板缺回归证据",
            },
            {
                "op": "insert_after",
                "file": "skills/demo/SKILL.md",
                "target": "### 输出",
                "content": "输出前先按对象去重。",
                "rationale": "输出缺去重前提",
            },
            {
                "op": "delete",
                "file": "skills/demo/SKILL.md",
                "target": "过滤已归档条目\n",
                "rationale": "该输入步骤已由上游保证",
            },
            {
                "op": "append",
                "file": "skills/demo/SKILL.md",
                "content": "维护备注：本文件为测试合成副本。",  # noqa: RUF001
                "rationale": "标注合成来源",
            },
            {
                "op": "replace",
                "file": "skills/demo/SKILL.md",
                "target": "附带统计表",
                "content": "附带统计表（含错误分级）。",  # noqa: RUF001
                "rationale": "统计缺错误分级",
            },
            {
                "op": "insert_after",
                "file": "skills/demo/SKILL.md",
                "target": "## 限制\n",
                "content": "凭据零感知同样适用于评测网关。",
                "rationale": "限制缺网关侧口径",
            },
            {
                "op": "append",
                "file": "skills/demo/SKILL.md",
                "content": "完。",
                "rationale": "收尾标记",
            },
        ],
    }

    plan = EditPlan.model_validate(raw_plan)
    application = apply_edit_plan(plan, workspace=workspace)

    final = (workspace / "skills" / "demo" / "SKILL.md").read_bytes().decode("utf-8")
    assert [status.status for status in application.report] == ["applied"] * 8
    assert application.files == ("skills/demo/SKILL.md",)
    inserted = plan.edits[1].content
    assert inserted is not None
    assert len(inserted.splitlines()) == 28
    assert f"{block_anchor}{regression_evidence}\n" in final
    assert "### 输出\n输出前先按对象去重。\n生成 summary.md\n" in final
    assert "附带统计表（含错误分级）。\n" in final  # noqa: RUF001
    assert "过滤已归档条目" not in final
    assert "## 限制\n凭据零感知同样适用于评测网关。\n不读取生产凭据。\n" in final
    assert final.endswith("维护备注：本文件为测试合成副本。\n完。\n")  # noqa: RUF001


def test_replace_with_identical_content_is_applied_but_not_changed(tmp_path: Path) -> None:
    """An applied no-op edit is reported applied without claiming a file change."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "same\n")
    plan = EditPlan(
        summary="no-op",
        edits=(EditOp(op="replace", file="doc.md", target="same", content="same", rationale="r"),),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "applied"
    assert application.files == ()


def test_workspace_must_be_absolute_and_existing(tmp_path: Path) -> None:
    """A relative or missing workspace fails before any edit is considered."""
    plan = EditPlan(
        summary="workspace",
        edits=(EditOp(op="append", file="a.md", content="x", rationale="r"),),
    )
    with pytest.raises(EditPlanError, match="absolute"):
        apply_edit_plan(plan, workspace=Path("relative"))
    with pytest.raises(EditPlanError, match="existing directory"):
        apply_edit_plan(plan, workspace=tmp_path / "missing")


def test_bypassed_edit_instance_is_revalidated_before_applying(tmp_path: Path) -> None:
    """An EditOp built with model_construct cannot skip the Pydantic contract."""
    workspace = tmp_path / "ws"
    _write(workspace / "doc.md", "line\n")
    unknown_op = EditOp.model_construct(
        op=cast("EditOpName", "move"),
        file="doc.md",
        target="line",
        content="x",
        rationale="r",
    )
    blank_append = EditOp.model_construct(
        op="append",
        file="doc.md",
        target=None,
        content="",
        rationale="r",
    )
    plan = EditPlan.model_construct(summary="bypassed", edits=[unknown_op, blank_append])

    application = apply_edit_plan(plan, workspace=workspace)

    assert [status.status for status in application.report] == ["error", "error"]
    assert "op" in application.report[0].message
    assert "content" in application.report[1].message
    assert (workspace / "doc.md").read_text(encoding="utf-8") == "line\n"


def test_invalid_bypassed_edit_is_reported_locatably(tmp_path: Path) -> None:
    """A malformed bypassed entry names its index, file, and violated field."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    plan = EditPlan.model_construct(
        summary="malformed",
        edits=[{"op": "append", "file": "a.md", "rationale": ""}],
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert application.report[0].status == "error"
    message = application.report[0].message
    assert "edits[0]" in message
    assert "a.md" in message
    assert "rationale" in message


def test_write_failure_is_recorded_and_later_edits_continue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An atomic-write I/O failure is recorded without blocking later files."""
    workspace = tmp_path / "ws"
    _write(workspace / "a.md", "a\n")
    _write(workspace / "b.md", "b\n")
    real_replace = os.replace
    calls = 0

    def flaky_replace(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(13, "Permission denied")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", flaky_replace)
    plan = EditPlan(
        summary="write failure",
        edits=(
            EditOp(op="append", file="a.md", content="tail", rationale="r"),
            EditOp(op="append", file="b.md", content="tail", rationale="r"),
        ),
    )

    application = apply_edit_plan(plan, workspace=workspace)

    assert [status.status for status in application.report] == ["error", "applied"]
    assert "write failed" in application.report[0].message
    assert "Permission denied" in application.report[0].message
    assert (workspace / "a.md").read_text(encoding="utf-8") == "a\n"
    assert (workspace / "b.md").read_text(encoding="utf-8") == "b\ntail\n"


def test_single_file_bundle_hash_matches_the_patch() -> None:
    """A one-file bundle keeps the legacy Patch.sha256 byte-for-byte."""
    patch = Patch(file="skills/deep-research/SKILL.md", lines=("a", "b"))
    bundle = PatchBundle(files=(patch,), note="one file")

    assert bundle.sha256 == patch.sha256


def test_multi_file_bundle_hash_is_order_independent_and_distinct() -> None:
    """Multi-file hashing sorts paths and never collides with a member hash."""
    first = Patch(file="a.md", lines=("1",))
    second = Patch(file="b.md", lines=("2",))
    forward = PatchBundle(files=(first, second), note="two files")
    reverse = PatchBundle(files=(second, first), note="two files")

    assert forward.files == (first, second)
    assert forward.sha256 == reverse.sha256
    assert forward.sha256 not in {first.sha256, second.sha256}
    assert len(forward.sha256) == 64


def test_bundle_rejects_empty_duplicate_and_blank_inputs() -> None:
    """Invalid bundle shapes fail before a candidate can be created."""
    patch = Patch(file="a.md", lines=("x",))
    with pytest.raises(ValueError, match="must not be empty"):
        PatchBundle(files=(), note="empty")
    with pytest.raises(ValueError, match="must not be blank"):
        PatchBundle(files=(patch,), note=" ")
    with pytest.raises(ValueError, match="must not repeat"):
        PatchBundle(files=(patch, patch), note="duplicate")


def test_bundle_note_is_the_intent_summary() -> None:
    """An intent-bearing bundle uses the EditPlan summary as its note."""
    plan = EditPlan(
        summary="timeout 30s to 120s",
        edits=(
            EditOp(
                op="replace",
                file="config/a.json",
                target='"timeout": 30',
                content='"timeout": 120',
                rationale="r",
            ),
        ),
    )
    patch = Patch(file="config/a.json", lines=("{", "}"), overwrite=True)

    with pytest.raises(ValueError, match=r"intent\.summary"):
        PatchBundle(files=(patch,), note="different", intent=plan)

    bundle = PatchBundle(files=(patch,), note=plan.summary, intent=plan)
    assert bundle.note == plan.summary
    assert bundle.intent is plan


async def test_placeholder_bundle_preserves_legacy_build_and_note() -> None:
    """The default build_bundle wrapper is a pure single-file projection."""
    source = PlaceholderPatchSource()
    run = _run()
    trace = _trace("未校验快照字段")
    legacy_patch = await source.build(run, 1, trace)
    legacy_note = await source.change_note(run, 1, trace)

    bundle = await source.build_bundle(run, 1, trace)

    assert isinstance(source, PatchSource)
    assert bundle.files == (legacy_patch,)
    assert bundle.note == legacy_note
    assert bundle.intent is None
    assert bundle.report == ()
    assert bundle.unified_diff == ""
    assert bundle.sha256 == legacy_patch.sha256


async def test_minimal_config_bundle_preserves_legacy_build_and_note(tmp_path: Path) -> None:
    """The minimal-config source keeps its exact build() output inside a bundle."""
    workspace = tmp_path / "ws"
    _write(workspace / "skills" / "deep-research" / "config" / "deep-research.json", "{}\n")
    source = MinimalConfigPatchSource()
    run = _run(workspace_path=workspace)
    trace = _trace("下游服务响应 timeout 频繁出现")
    legacy_patch = await source.build(run, 2, trace)
    legacy_note = await source.change_note(run, 2, trace)

    bundle = await source.build_bundle(run, 2, trace)

    assert bundle.files == (legacy_patch,)
    assert bundle.note == legacy_note
    assert bundle.intent is None
    assert bundle.report == ()
    assert bundle.sha256 == legacy_patch.sha256
    assert legacy_patch.overwrite is True


def test_agent_edit_mode_requires_and_selects_the_agent_provider() -> None:
    """agent-edit is a real mode that needs a provider and selects its source."""
    assert PATCH_SOURCE_MODES == ("placeholder", "minimal-config", "agent-edit")
    assert DEFAULT_PATCH_SOURCE_MODE == "placeholder"
    with pytest.raises(ConfigError, match="AI agent provider"):
        default_patch_source_factory(_run(eval_config={"patchMode": "agent-edit"}))
    with pytest.raises(ConfigError, match="AI agent provider"):
        default_patch_source_factory(_run(), fallback_mode="agent-edit")
    source = default_patch_source_factory(
        _run(eval_config={"patchMode": "agent-edit"}),
        provider=FakeAIAgentProvider(),
    )
    assert isinstance(source, AgentEditPatchSource)
    assert isinstance(source, PatchSource)
    with pytest.raises(ConfigError, match="unknown patch source mode"):
        default_patch_source_factory(_run(eval_config={"patchMode": "llm"}))


def test_edit_prompt_states_the_same_anchor_contract_as_the_validator() -> None:
    """The model-visible prompt states the cross-line, unique-fragment contract."""
    from app.service.evolution import patch_source

    prompt = patch_source._edit_prompt(_run(), _trace("对象行为异常"), allowed=("skills/**",))

    assert "唯一出现的文本片段" in prompt
    assert "可跨行" in prompt
    assert "末行之后" in prompt
