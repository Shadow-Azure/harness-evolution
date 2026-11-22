"""Structured submission channel: JSON5 tolerance, salvage fallback, terminal states."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import json_repair
import pytest
from pydantic import BaseModel, Field

from app.third_party_api.ai_agent.submission import (
    SUBMISSION_TOOLS,
    StructuredSubmission,
    SubmissionOutcome,
    SubmissionPrep,
)


class ScoreOutput(BaseModel):
    """Minimal caller schema for the confidence-scoring task."""

    confidence: float = Field(ge=0, le=1, description="between zero and one")
    summary: str


class DraftCluster(BaseModel):
    """Nested element proving alias and collection validation come from Pydantic."""

    title: str
    from_drafts: list[str] = Field(alias="from", min_length=1)
    severity: int = Field(ge=0, le=10)


class ReviewOutput(BaseModel):
    """Nested caller schema for the review task."""

    clusters: list[DraftCluster]
    overall: float


def prepare(
    root: Path,
    schema: type[BaseModel] = ScoreOutput,
) -> tuple[StructuredSubmission, SubmissionPrep]:
    """Build one ready-to-write submission under the caller's root."""
    channel = StructuredSubmission(root=root)
    return channel, channel.prepare("cluster.score", schema)


def _repair_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every json-repair attempt made through the submission module."""
    repairs: list[str] = []
    real_loads = json_repair.loads

    def spy(text: str, *args: Any, **kwargs: Any) -> Any:
        repairs.append(text)
        return real_loads(text, *args, **kwargs)

    monkeypatch.setattr(json_repair, "loads", spy)
    return repairs


@pytest.mark.parametrize(
    ("literal", "expected"),
    [
        (
            '// reviewer note\n{"confidence": 0.5, "summary": "line comment"}',
            {"confidence": 0.5, "summary": "line comment"},
        ),
        (
            '{confidence: 0.5, /* inline */ summary: "block comment"}',
            {"confidence": 0.5, "summary": "block comment"},
        ),
        (
            '{confidence: 0.5, summary: "trailing comma",}',
            {"confidence": 0.5, "summary": "trailing comma"},
        ),
        (
            "{'confidence': 0.5, 'summary': 'single quotes'}",
            {"confidence": 0.5, "summary": "single quotes"},
        ),
        (
            '{confidence: 0.5, summary: "bare keys"}',
            {"confidence": 0.5, "summary": "bare keys"},
        ),
    ],
    ids=["line-comment", "block-comment", "trailing-comma", "single-quotes", "bare-keys"],
)
def test_json5_tolerance_matrix(
    tmp_path: Path,
    literal: str,
    expected: dict[str, object],
) -> None:
    """Every lenient JSON5 feature the prompt advertises is actually accepted."""
    channel, prep = prepare(tmp_path)
    prep.result_path.write_text(literal, encoding="utf-8")

    outcome = channel.collect(prep, ScoreOutput.model_validate)

    assert outcome.status == "ok"
    assert outcome.is_ok is True
    assert outcome.payload == expected
    validated = outcome.validated
    assert isinstance(validated, ScoreOutput)
    assert validated.confidence == 0.5
    assert outcome.parse_error is None
    assert outcome.validation_error is None
    assert channel.feedback_prompt(outcome) == ""


def test_json_repair_salvages_only_after_strict_json_and_json5_fail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing closing brace is repaired only because the first two tiers reject it."""
    repairs = _repair_spy(monkeypatch)
    channel, prep = prepare(tmp_path)
    literal = '{"confidence": 0.7, "summary": "salvaged"'
    prep.result_path.write_text(literal, encoding="utf-8")

    outcome = channel.collect(prep, ScoreOutput.model_validate)

    assert repairs == [literal]
    assert outcome.status == "ok"
    assert outcome.payload == {"confidence": 0.7, "summary": "salvaged"}
    validated = outcome.validated
    assert isinstance(validated, ScoreOutput)
    assert validated.summary == "salvaged"


def test_standard_json_and_json5_never_reach_the_repair_tier(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strict JSON and JSON5 success must short-circuit before the salvage tier."""
    repairs = _repair_spy(monkeypatch)
    channel, strict_prep = prepare(tmp_path)
    strict_prep.result_path.write_text(
        '{"confidence": 0.5, "summary": "strict"}',
        encoding="utf-8",
    )
    assert channel.collect(strict_prep, ScoreOutput.model_validate).is_ok
    assert repairs == []

    json5_prep = channel.prepare("cluster.score", ScoreOutput)
    json5_prep.result_path.write_text(
        "{confidence: 0.5, summary: 'json5',}",
        encoding="utf-8",
    )
    assert channel.collect(json5_prep, ScoreOutput.model_validate).is_ok
    assert repairs == []


def test_invalid_state_preserves_field_and_constraint_text(tmp_path: Path) -> None:
    """A schema violation lands ``invalid`` with locatable Pydantic error text."""
    channel, prep = prepare(tmp_path)
    prep.result_path.write_text(
        '{"confidence": 2.0, "summary": "too high"}',
        encoding="utf-8",
    )

    outcome = channel.collect(prep, ScoreOutput.model_validate)

    assert outcome.status == "invalid"
    assert outcome.is_ok is False
    assert outcome.payload == {"confidence": 2.0, "summary": "too high"}
    assert outcome.validated is None
    assert outcome.validation_error is not None
    assert "1 validation error for ScoreOutput" in outcome.validation_error
    assert "confidence" in outcome.validation_error
    assert "less than or equal to 1" in outcome.validation_error

    feedback = channel.feedback_prompt(outcome)
    assert "confidence" in feedback
    assert "less than or equal to 1" in feedback
    assert "./result.json5" in feedback
    assert "重新写入" in feedback


def test_missing_state_when_no_result_file_exists(tmp_path: Path) -> None:
    """An absent result file is a terminal ``missing``, never an exception."""
    channel, prep = prepare(tmp_path)

    outcome = channel.collect(prep, ScoreOutput.model_validate)

    assert outcome.status == "missing"
    assert outcome.is_ok is False
    assert outcome.payload is None
    assert outcome.validated is None
    assert outcome.parse_error is not None
    assert "result.json5" in outcome.parse_error

    feedback = channel.feedback_prompt(outcome)
    assert "result.json5" in feedback
    assert "不存在" in feedback
    assert "./result.json5" in feedback


def test_any_validator_exception_becomes_validation_error(tmp_path: Path) -> None:
    """A non-Pydantic validator failure is folded instead of escaping ``collect``."""
    channel, prep = prepare(tmp_path)
    prep.result_path.write_text('{"confidence": 0.5, "summary": "ok"}', encoding="utf-8")

    def reject(payload: Mapping[str, Any]) -> BaseModel:
        raise RuntimeError("from keys must partition the input drafts")

    outcome = channel.collect(prep, reject)

    assert outcome.status == "invalid"
    assert outcome.validation_error is not None
    assert "from keys must partition the input drafts" in outcome.validation_error
    assert "partition" in channel.feedback_prompt(outcome)


@pytest.mark.parametrize(
    ("raw", "expected_status"),
    [
        ("", "invalid"),
        ("not json at all", "invalid"),
        ("[1,2,3]", "invalid"),
        (b'{"confidence": 0.5, "summary": "\xff"}', "missing"),
    ],
    ids=["empty", "garbage", "array", "invalid-utf8"],
)
def test_malformed_input_never_raises(
    tmp_path: Path,
    raw: str | bytes,
    expected_status: Literal["ok", "invalid", "missing"],
) -> None:
    """Empty, garbage, non-object, and undecodable inputs stay terminal data."""
    channel, prep = prepare(tmp_path)
    prep.result_path.write_bytes(raw.encode("utf-8") if isinstance(raw, str) else raw)

    outcome = channel.collect(prep, ScoreOutput.model_validate)

    assert outcome.status == expected_status
    assert outcome.status in {"invalid", "missing"}
    assert outcome.parse_error is not None
    assert channel.feedback_prompt(outcome) != ""


def test_prepare_mints_unique_one_shot_directories(tmp_path: Path) -> None:
    """Two preparations never share a directory; schema is derived and valid JSON."""
    channel = StructuredSubmission(root=tmp_path)
    first = channel.prepare("cluster.review", ReviewOutput)
    second = channel.prepare("cluster.review", ReviewOutput)
    escaped = channel.prepare("../escape", ReviewOutput)

    assert first.directory != second.directory
    assert first.directory.is_dir()
    assert second.directory.is_dir()
    assert escaped.directory.parent == tmp_path
    assert first.result_path == first.directory / "result.json5"
    assert first.schema_path == first.directory / "schema.json"
    assert first.schema_path.exists()
    assert second.schema_path.exists()
    assert not first.result_path.exists()

    schema = json.loads(first.schema_path.read_text(encoding="utf-8"))
    assert schema["title"] == "ReviewOutput"
    assert "clusters" in schema["properties"]
    assert "from" in schema["$defs"]["DraftCluster"]["properties"]

    assert first.allowed_tools == ("Write(./result.json5)",)
    assert first.allowed_tools == SUBMISSION_TOOLS


def test_prompt_addendum_points_at_result_and_schema(tmp_path: Path) -> None:
    """The instruction fragment names both the literal file and the schema."""
    _, prep = prepare(tmp_path)

    assert "./result.json5" in prep.prompt_addendum
    assert "schema.json" in prep.prompt_addendum
    assert "JSON5" in prep.prompt_addendum


def test_default_root_is_a_disposable_temp_directory() -> None:
    """Without a caller root every call still mints its own disposable directory."""
    channel = StructuredSubmission()

    first = channel.prepare("cluster.score", ScoreOutput)
    second = channel.prepare("cluster.score", ScoreOutput)

    assert first.directory != second.directory
    assert first.directory.is_dir()
    assert second.directory.is_dir()
    assert first.directory.name.startswith("he-ai-submission-")


def test_prepare_rejects_blank_key_and_non_pydantic_schema(tmp_path: Path) -> None:
    """Caller mistakes fail before any task directory is created."""
    channel = StructuredSubmission(root=tmp_path)

    with pytest.raises(ValueError, match="task_key"):
        channel.prepare("   ", ScoreOutput)
    with pytest.raises(ValueError, match="Pydantic"):
        channel.prepare("cluster.score", dict)  # type: ignore[arg-type]


def test_round_trip_with_nested_model_proves_pydantic_is_authority(tmp_path: Path) -> None:
    """``model_validate`` performs alias resolution and nested collection validation."""
    channel, prep = prepare(tmp_path, ReviewOutput)
    prep.result_path.write_text(
        """
        {
          // one merged cluster
          clusters: [
            {title: 'Timeout', 'from': ['D1', 'D2'], severity: 7,},
          ],
          overall: 7.5,
        }
        """,
        encoding="utf-8",
    )

    outcome = channel.collect(prep, ReviewOutput.model_validate)

    assert outcome.status == "ok"
    validated = outcome.validated
    assert isinstance(validated, ReviewOutput)
    assert validated.overall == 7.5
    assert validated.clusters[0].from_drafts == ["D1", "D2"]
    assert validated.clusters[0].severity == 7


def test_outcomes_are_frozen_value_objects() -> None:
    """An outcome cannot be mutated after a caller has branched on its status."""
    outcome = SubmissionOutcome(status="missing", parse_error="no file")

    with pytest.raises(AttributeError):
        outcome.status = "ok"  # type: ignore[misc]
    assert outcome.is_ok is False
