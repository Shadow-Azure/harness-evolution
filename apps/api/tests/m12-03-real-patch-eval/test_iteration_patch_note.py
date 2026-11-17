"""Iteration step must tolerate the patch note persisted by m12-03 sources.

The real-process smoke (reports/2026-11-18-m12-03-smoke) hit a 500 on
``GET /runs/{id}/steps/iteration`` for any run published with the
minimal-config patch source: ``round.patch`` stores the change note under
``note``, but ``StepRoundPatch`` was still the V1 placeholder shape and
``extra="forbid"`` rejected the extra key. This pins the response contract.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.service.evolution.stages import StepRoundPatch


def test_patch_roundtrip_accepts_note_from_minimal_config_source() -> None:
    """The persisted minimal-config patch shape validates with its note."""
    step = StepRoundPatch.model_validate(
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
    assert step.file.endswith("synthetic-review.json")
    assert step.note is not None
    assert step.note.startswith("最小配置变更")


def test_patch_roundtrip_keeps_v1_placeholder_shape_valid() -> None:
    """Legacy rounds without a note stay valid and render note=None."""
    step = StepRoundPatch.model_validate(
        {
            "file": "skills/deep-research/.harness-evolution/candidate-r1.md",
            "lines": ["V1 占位说明"],
        },
    )
    assert step.note is None


def test_patch_roundtrip_still_rejects_unknown_keys() -> None:
    """The response contract stays closed for genuinely unknown keys."""
    with pytest.raises(ValidationError):
        StepRoundPatch.model_validate({"file": "x", "lines": [], "secretExtra": 1})
