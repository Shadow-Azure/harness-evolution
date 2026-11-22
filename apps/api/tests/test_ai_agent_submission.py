"""Structured submission channel: JSON5 tolerance, salvage fallback, terminal states."""

# ruff: noqa: RUF001

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any, Literal

import json_repair
import pytest
from pydantic import BaseModel, Field, ValidationError

from app.third_party_api.ai_agent import (
    RESULT_FILENAME,
    SCHEMA_FILENAME,
    SUBMISSION_TOOLS,
    EditPlan,
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


class ManyValuesOutput(BaseModel):
    """Schema that emits one independent violation block per list element."""

    values: list[Annotated[int, Field(ge=0, le=1)]]


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


@pytest.mark.parametrize(
    ("literal", "expected_tier"),
    [
        ('{"confidence": 0.5, "summary": "strict"}', "strict"),
        ('// note\n{confidence: 0.5, summary: "json5"}', "json5"),
        ('{"confidence": 0.5, "summary": "salvaged"', "repair"),
        (None, None),
    ],
    ids=["strict", "json5", "repair", "missing"],
)
def test_parsed_by_records_the_tier_that_produced_the_document(
    tmp_path: Path,
    literal: str | None,
    expected_tier: Literal["strict", "json5", "repair"] | None,
) -> None:
    """Layer-5 provenance names the successful tier and stays ``None`` when none ran."""
    channel, prep = prepare(tmp_path)
    if literal is not None:
        prep.result_path.write_text(literal, encoding="utf-8")

    outcome = channel.collect(prep, ScoreOutput.model_validate)

    assert outcome.status == ("missing" if literal is None else "ok")
    assert outcome.parsed_by == expected_tier


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
    assert outcome.parsed_by == "repair"
    assert outcome.payload == {"confidence": 0.7, "summary": "salvaged"}
    validated = outcome.validated
    assert isinstance(validated, ScoreOutput)
    assert validated.summary == "salvaged"


def test_repair_log_is_bounded_and_only_populated_by_the_repair_tier(tmp_path: Path) -> None:
    """Salvage actions stay auditable while never growing the outcome without bound."""
    channel, prep = prepare(tmp_path)
    prep.result_path.write_text(
        '{confidence: 0.5, summary: "ok", a: , b: , c: , d: , e: }',
        encoding="utf-8",
    )

    outcome = channel.collect(prep, ScoreOutput.model_validate)

    assert outcome.status == "ok"
    assert outcome.parsed_by == "repair"
    assert 0 < len(outcome.repair_log) <= 5
    assert all(entry and isinstance(entry, str) for entry in outcome.repair_log)
    assert all(len(entry) <= 500 for entry in outcome.repair_log)

    strict_prep = channel.prepare("cluster.score", ScoreOutput)
    strict_prep.result_path.write_text(
        '{"confidence": 0.5, "summary": "strict"}',
        encoding="utf-8",
    )
    strict_outcome = channel.collect(strict_prep, ScoreOutput.model_validate)
    assert strict_outcome.parsed_by == "strict"
    assert strict_outcome.repair_log == ()


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


def test_non_mapping_top_level_is_invalid_and_skips_the_validator(tmp_path: Path) -> None:
    """A list top level never reaches the caller validator, whichever tier saw it."""
    channel, prep = prepare(tmp_path)
    calls: list[Mapping[str, Any]] = []

    def spy_validate(payload: Mapping[str, Any]) -> BaseModel:
        calls.append(payload)
        return ScoreOutput.model_validate(payload)

    prep.result_path.write_text('[{"confidence": 0.5, "summary": "wrapped"}]', encoding="utf-8")
    strict_outcome = channel.collect(prep, spy_validate)

    assert strict_outcome.status == "invalid"
    assert strict_outcome.payload is None
    assert strict_outcome.parsed_by == "strict"
    assert calls == []

    prep.result_path.write_text('[{"confidence": 0.5, "summary": "wrapped"},]', encoding="utf-8")
    json5_outcome = channel.collect(prep, spy_validate)

    assert json5_outcome.status == "invalid"
    assert json5_outcome.parsed_by == "json5"
    assert "不是 JSON 对象" in (json5_outcome.parse_error or "")
    assert calls == []


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
    assert outcome.parsed_by == "strict"

    feedback = channel.feedback_prompt(outcome)
    assert "confidence" in feedback
    assert "less than or equal to 1" in feedback
    assert "./result.json5" in feedback
    assert "重新写入" in feedback


def test_validation_error_truncates_at_line_boundaries(tmp_path: Path) -> None:
    """A long error keeps complete lines instead of cutting an entry mid-line."""
    channel, prep = prepare(tmp_path, ManyValuesOutput)
    payload = {"values": [9] * 200}
    prep.result_path.write_text(json.dumps(payload), encoding="utf-8")

    outcome = channel.collect(prep, ManyValuesOutput.model_validate)

    assert outcome.status == "invalid"
    assert outcome.validation_error is not None
    bounded = outcome.validation_error.splitlines()
    marker = re.fullmatch(r"…（还有 (\d+) 行未展示）", bounded[-1])
    assert marker is not None
    hidden = int(marker.group(1))
    body = bounded[:-1]

    with pytest.raises(ValidationError) as excinfo:
        ManyValuesOutput.model_validate(payload)
    full_lines = str(excinfo.value).strip().splitlines()

    assert body == full_lines[: len(body)]
    assert hidden == len(full_lines) - len(body)
    assert hidden > 0
    assert any("less than or equal to 1" in line for line in body)


def test_single_oversized_error_line_hits_the_character_ceiling(tmp_path: Path) -> None:
    """One pathological line still respects the hard 4000-character backstop."""
    channel, prep = prepare(tmp_path)
    prep.result_path.write_text('{"confidence": 0.5, "summary": "ok"}', encoding="utf-8")

    def reject(payload: Mapping[str, Any]) -> BaseModel:
        raise RuntimeError("x" * 5_000)

    outcome = channel.collect(prep, reject)

    assert outcome.validation_error is not None
    assert outcome.validation_error.endswith("…（还有 1 行未展示）")
    assert len(outcome.validation_error) == 4_000 + len("…（还有 1 行未展示）")


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
    assert outcome.parsed_by is None
    assert outcome.repair_log == ()

    feedback = channel.feedback_prompt(outcome)
    assert "result.json5" in feedback
    assert "不存在" in feedback
    assert "./result.json5" in feedback


def test_feedback_prompt_leaks_no_absolute_path_and_no_duplicated_prefix(tmp_path: Path) -> None:
    """The retry text names the bare file, never the temp directory, and repeats no prefix."""
    channel, prep = prepare(tmp_path)
    outcome = channel.collect(prep, ScoreOutput.model_validate)

    feedback = channel.feedback_prompt(outcome)

    assert str(prep.directory) not in feedback
    assert str(prep.result_path) not in feedback
    assert "/tmp" not in feedback  # noqa: S108 - asserting absence, not using a temp dir
    assert "/var/folders" not in feedback
    assert feedback.count("不存在或不可读") == 1
    assert not feedback.startswith(f"{RESULT_FILENAME} 不存在或不可读：{RESULT_FILENAME}")


def test_oversized_result_is_rejected_before_reading(tmp_path: Path) -> None:
    """A result file above the 1 MiB ceiling is ``invalid`` without ever being read."""
    channel, prep = prepare(tmp_path)
    prep.result_path.write_bytes(b"{" + b" " * (1024 * 1024) + b"}")

    outcome = channel.collect(prep, ScoreOutput.model_validate)

    assert outcome.status == "invalid"
    assert outcome.payload is None
    assert outcome.parse_error is not None
    assert "1 MiB" in outcome.parse_error
    assert str(1024 * 1024) in outcome.parse_error
    assert outcome.parsed_by is None


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
        (b'{"confidence": 0.5, "summary": "\xff"}', "invalid"),
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


def test_invalid_utf8_is_invalid_not_missing(tmp_path: Path) -> None:
    """Undecodable bytes mean "wrote something unusable", not "did not submit"."""
    channel, prep = prepare(tmp_path)
    prep.result_path.write_bytes(b'{"confidence": 0.5, "summary": "\xff"}')

    outcome = channel.collect(prep, ScoreOutput.model_validate)

    assert outcome.status == "invalid"
    assert outcome.payload is None
    assert outcome.parse_error is not None
    assert "UTF-8" in outcome.parse_error
    assert outcome.parsed_by is None


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
    assert first.schema_path is not None
    assert first.schema_path.exists()
    assert second.schema_path is not None
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


def test_discard_removes_the_task_directory_and_is_idempotent(tmp_path: Path) -> None:
    """The explicit release point deletes one task dir without touching the root."""
    channel, prep = prepare(tmp_path)
    prep.result_path.write_text('{"confidence": 0.5, "summary": "ok"}', encoding="utf-8")
    assert prep.directory.is_dir()

    channel.discard(prep)
    channel.discard(prep)

    assert not prep.directory.exists()
    assert tmp_path.is_dir()


def test_discard_forgets_a_tracked_temp_directory() -> None:
    """A discarded default-root directory is no longer owned by the instance."""
    channel = StructuredSubmission()
    prep = channel.prepare("cluster.score", ScoreOutput)

    channel.discard(prep)

    assert not prep.directory.exists()
    assert prep.directory not in channel._temp_directories


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


def test_package_exports_resolve_the_submission_surface() -> None:
    """``ai_agent`` package imports and ``__all__`` expose the submission surface."""
    import app.third_party_api.ai_agent as ai_agent_package

    for exported in (StructuredSubmission, SubmissionOutcome, SubmissionPrep):
        assert exported.__module__ == "app.third_party_api.ai_agent.submission"
    assert RESULT_FILENAME == "result.json5"
    assert SCHEMA_FILENAME == "schema.json"
    assert SUBMISSION_TOOLS == ("Write(./result.json5)",)
    assert {
        "RESULT_FILENAME",
        "SCHEMA_FILENAME",
        "SUBMISSION_TOOLS",
        "StructuredSubmission",
        "SubmissionOutcome",
        "SubmissionPrep",
    } <= set(ai_agent_package.__all__)


def test_outcomes_are_frozen_value_objects() -> None:
    """An outcome cannot be mutated after a caller has branched on its status."""
    outcome = SubmissionOutcome(status="missing", parse_error="no file")

    with pytest.raises(AttributeError):
        outcome.status = "ok"  # type: ignore[misc]
    assert outcome.is_ok is False


def test_explicit_directory_and_filename_override_the_disposable_default(
    tmp_path: Path,
) -> None:
    """The edit phase submits into the workspace, not into a one-shot temp dir."""
    channel = StructuredSubmission()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    prep = channel.prepare(
        "agent.edit",
        EditPlan,
        directory=workspace,
        filename=".harness-evolution/edits.json5",
    )

    assert prep.directory == workspace
    assert prep.result_path == workspace / ".harness-evolution" / "edits.json5"
    assert prep.schema_path is None
    assert prep.allowed_tools == ("Write(./.harness-evolution/edits.json5)",)
    assert "agent.edit" in prep.prompt_addendum
    assert "./.harness-evolution/edits.json5" in prep.prompt_addendum
    assert "JSON5" in prep.prompt_addendum
    assert "./schema.json" not in prep.prompt_addendum


def test_explicit_directory_inlines_the_schema_instead_of_writing_a_file(
    tmp_path: Path,
) -> None:
    """No schema file is left in a caller-owned workspace; the prompt carries it."""
    channel = StructuredSubmission()

    prep = channel.prepare(
        "agent.edit",
        EditPlan,
        directory=tmp_path,
        filename=".harness-evolution/edits.json5",
    )

    assert not (tmp_path / SCHEMA_FILENAME).exists()
    assert prep.schema_path is None
    assert "JSON Schema" in prep.prompt_addendum
    assert '"properties"' in prep.prompt_addendum
    assert '"summary"' in prep.prompt_addendum
    assert '"edits"' in prep.prompt_addendum


def test_explicit_directory_with_the_default_filename_still_inlines_the_schema(
    tmp_path: Path,
) -> None:
    """An explicit directory always keeps the caller tree free of a schema file."""
    channel = StructuredSubmission()

    prep = channel.prepare("cluster.score", ScoreOutput, directory=tmp_path)

    assert prep.result_path == tmp_path / "result.json5"
    assert prep.schema_path is None
    assert not (tmp_path / SCHEMA_FILENAME).exists()
    assert prep.allowed_tools == SUBMISSION_TOOLS
    assert '"confidence"' in prep.prompt_addendum


def test_custom_filename_in_a_disposable_directory_keeps_the_written_schema(
    tmp_path: Path,
) -> None:
    """A custom name in a channel-owned task dir keeps the schema file contract."""
    channel = StructuredSubmission(root=tmp_path)

    prep = channel.prepare("cluster.score", ScoreOutput, filename="nested/answer.json5")

    assert prep.directory.parent == tmp_path
    assert prep.result_path == prep.directory / "nested" / "answer.json5"
    assert prep.schema_path == prep.directory / SCHEMA_FILENAME
    assert prep.schema_path is not None
    assert prep.schema_path.exists()
    assert prep.allowed_tools == ("Write(./nested/answer.json5)",)


@pytest.mark.parametrize(
    "filename",
    [
        "",
        "   ",
        " leading.json5",
        "trailing.json5 ",
        "/abs/result.json5",
        "../escape.json5",
        "a/../b.json5",
        "./result.json5",
        "a//b.json5",
        "a/./b.json5",
        "a/",
        "a\\b.json5",
        "a\x00b.json5",
        "./",
        ".",
        "..",
        "C:/result.json5",
        ".git/config",
        ".git",
        "nested/.GIT/config",
    ],
    ids=[
        "empty",
        "blank",
        "leading-space",
        "trailing-space",
        "absolute",
        "parent",
        "inner-parent",
        "dot-prefix",
        "double-slash",
        "dot-segment",
        "trailing-slash",
        "backslash",
        "nul",
        "dot-slash",
        "dot",
        "dotdot",
        "drive-prefix",
        "git-file",
        "git-dir",
        "case-folded-git",
    ],
)
def test_unsafe_filename_matrix_is_rejected(tmp_path: Path, filename: str) -> None:
    """Every traversal, platform, and Git-internal spelling fails before writing."""
    channel = StructuredSubmission()

    with pytest.raises(ValueError):
        channel.prepare(
            "agent.edit",
            EditPlan,
            directory=tmp_path,
            filename=filename,
        )


def test_explicit_directory_must_be_absolute_and_exist(tmp_path: Path) -> None:
    """An explicit directory is validated before any file is written."""
    channel = StructuredSubmission()

    with pytest.raises(ValueError, match="absolute"):
        channel.prepare("agent.edit", EditPlan, directory=Path("relative"))
    with pytest.raises(ValueError, match="existing"):
        channel.prepare(
            "agent.edit",
            EditPlan,
            directory=tmp_path / "missing",
            filename=".harness-evolution/edits.json5",
        )
    assert not (tmp_path / "missing").exists()
