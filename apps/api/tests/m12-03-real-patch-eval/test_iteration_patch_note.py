"""Iteration step must project stored patch notes without a closed-model 500.

The real-process smoke (reports/2026-11-18-m12-03-smoke) and the 2026-11-23
production run both hit a 500 on ``GET /runs/{id}/steps/iteration``: the
durable ``round.patch`` dictionary carries fields the read DTO does not expose,
and ``extra="forbid"`` rejected them. The read path now projects the stored
bundle first; this pins the note and legacy-shape behavior.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.service.evolution.stages import StepRoundPatch, _round_patch


def test_patch_projection_accepts_note_from_minimal_config_source() -> None:
    """The persisted minimal-config patch shape projects with its note."""
    step = _round_patch(
        {
            "file": "skills/synthetic-review/config/synthetic-review.json",
            "lines": [
                "{",
                '  "requestTimeoutSeconds": 60,',
                '  "snapshotFieldCheckEnabled": true',
                "}",
            ],
            "note": "最小配置变更：启用 snapshotFieldCheckEnabled（小参数级修复）",
        },
    )
    assert step is not None
    assert step.files[0].file.endswith("synthetic-review.json")
    assert step.files[0].overwrite is False
    assert step.note is not None
    assert step.note.startswith("最小配置变更")


def test_patch_projection_keeps_v1_placeholder_shape_valid() -> None:
    """Legacy rounds without a note stay valid and project note=None."""
    step = _round_patch(
        {
            "file": "skills/deep-research/.harness-evolution/candidate-r1.md",
            "lines": ["V1 占位说明"],
        },
    )
    assert step is not None
    assert step.files[0].model_dump() == {
        "file": "skills/deep-research/.harness-evolution/candidate-r1.md",
        "lines": ["V1 占位说明"],
        "overwrite": False,
    }
    assert step.note is None


def test_patch_projection_ignores_writer_only_fields() -> None:
    """Writer-only keys such as intent/report never reach the read DTO."""
    step = _round_patch(
        {
            "files": [{"file": "SKILL.md", "lines": ["+ new"], "overwrite": False}],
            "note": "多文件修复",
            "intent": {"summary": "多文件修复", "edits": []},
            "report": [],
        },
    )
    assert step is not None
    assert step.files[0].file == "SKILL.md"
    assert step.note == "多文件修复"


def test_patch_dto_still_rejects_unknown_client_keys() -> None:
    """The response contract stays closed even though storage input is projected."""
    with pytest.raises(ValidationError):
        StepRoundPatch.model_validate({"files": [], "secretExtra": 1})
