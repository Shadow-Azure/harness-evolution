"""Deterministic structured submission channel shared by CLI Agent providers.

An agent writes one lenient JSON5 literal (``result.json5``) into a disposable
per-call task directory; this module reads it without executing model code,
parses it with a fixed fallback ladder, validates it against the caller's
Pydantic model, and turns a failure into a locatable retry prompt. Pydantic is
the single schema source of truth: ``schema.json`` is derived from the caller
model, never hand-authored.

The component starts no model call, owns no business rule, and never branches
on a backend. It is the layer-1 reliability defense of the six-layer JSON
design (07 §5.5.3).
"""

# ruff: noqa: RUF001

from __future__ import annotations

import json
import re
import shutil
import tempfile
import uuid
import weakref
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

import json5
import json_repair
from pydantic import BaseModel

RESULT_FILENAME: Final = "result.json5"
"""Name of the one literal file the agent may write inside a task directory."""

SCHEMA_FILENAME: Final = "schema.json"
"""Name of the caller-derived schema the agent reads for the expected shape."""

SUBMISSION_TOOLS: Final[tuple[str, ...]] = ("Write(./result.json5)",)
"""The sole tool whitelist granted while producing one submission."""

_MAX_ERROR_CHARS: Final = 4_000
"""Upper bound for an error text kept in an outcome, so logs stay bounded."""

_MAX_TASK_KEY_CHARS: Final = 48
"""Upper bound for the sanitized task-key prefix of a directory name."""

_UNSAFE_TASK_KEY_CHARS: Final = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class SubmissionPrep:
    """Everything one one-shot submission round needs.

    ``directory`` is minted by :meth:`StructuredSubmission.prepare` and is
    never reused across calls. ``allowed_tools`` is exactly the single write
    tool the agent may call; the result path is relative to ``directory``.
    """

    task_key: str
    directory: Path
    result_path: Path
    schema_path: Path
    prompt_addendum: str
    allowed_tools: tuple[str, ...] = SUBMISSION_TOOLS


@dataclass(frozen=True, slots=True)
class SubmissionOutcome:
    """Terminal result of one collection round.

    ``status`` is the closed three-state set: ``ok`` (validated payload),
    ``invalid`` (unparseable or rejected payload), ``missing`` (no readable
    file). ``parse_error`` covers the read/parse ladder; ``validation_error``
    preserves the caller validator's concrete error text.
    """

    status: Literal["ok", "invalid", "missing"]
    payload: Mapping[str, Any] | None = None
    validated: BaseModel | None = None
    parse_error: str | None = None
    validation_error: str | None = None

    @property
    def is_ok(self) -> bool:
        """Return whether the payload passed the caller's model."""
        return self.status == "ok"


class StructuredSubmission:
    """Mint one disposable task directory per call and collect its literal.

    The directory is one-shot by construction: every :meth:`prepare` call
    derives a fresh uuid-suffixed directory and never reuses an earlier one.
    Without a root the directory is a disposable system temp dir owned by this
    instance and removed when the instance is collected; a supplied root is
    kept for the caller and each call still mints a unique child below it.
    """

    def __init__(self, root: Path | None = None) -> None:
        """Bind an optional caller-owned root; the default is per-call temp dirs."""
        self._root = root
        self._temp_directories: list[Path] = []
        self._finalizer = weakref.finalize(
            self,
            _discard_directories,
            self._temp_directories,
        )

    def prepare(self, task_key: str, output_schema: type[BaseModel]) -> SubmissionPrep:
        """Create one fresh task directory, write ``schema.json``, and build the prompt.

        ``task_key`` must be non-blank and ``output_schema`` must be a Pydantic
        model; both are rejected with :class:`ValueError` before any directory
        is created, so a caller mistake never leaves a half-built task dir.
        """
        normalized_key = task_key.strip()
        if not normalized_key:
            raise ValueError("task_key must not be empty")
        if not (isinstance(output_schema, type) and issubclass(output_schema, BaseModel)):
            raise ValueError("output_schema must be a Pydantic BaseModel subclass")

        directory = self._new_task_directory(normalized_key)
        schema_path = directory / SCHEMA_FILENAME
        schema_path.write_text(
            f"{json.dumps(output_schema.model_json_schema(), ensure_ascii=False, indent=2)}\n",
            encoding="utf-8",
        )
        return SubmissionPrep(
            task_key=normalized_key,
            directory=directory,
            result_path=directory / RESULT_FILENAME,
            schema_path=schema_path,
            prompt_addendum=self._prompt_addendum(normalized_key),
            allowed_tools=SUBMISSION_TOOLS,
        )

    def collect(
        self,
        prep: SubmissionPrep,
        validate: Callable[[Mapping[str, Any]], BaseModel],
    ) -> SubmissionOutcome:
        """Read, parse, and validate one submission without ever raising.

        Parse order is strict JSON, then JSON5, then json-repair as the salvage
        tier only. A non-mapping top level is ``invalid`` and never escalates
        to the next tier. Any exception from ``validate`` is folded into
        ``validation_error``; malformed bytes never escape as a traceback.
        """
        try:
            text = prep.result_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return SubmissionOutcome(
                status="missing",
                parse_error=_bounded(f"{prep.result_path.name} 不可读：{_describe(exc)}"),
            )

        payload, parse_error = _parse_document(text)
        if payload is None:
            return SubmissionOutcome(status="invalid", parse_error=parse_error)

        try:
            validated = validate(payload)
        except Exception as exc:  # any validator failure is terminal data
            return SubmissionOutcome(
                status="invalid",
                payload=payload,
                validation_error=_bounded(_describe(exc)),
            )
        return SubmissionOutcome(status="ok", payload=payload, validated=validated)

    def feedback_prompt(self, outcome: SubmissionOutcome) -> str:
        """Render a localized retry prompt for a non-ok outcome.

        ``ok`` returns the empty string: the caller has its validated payload
        and must not resume the session. ``missing`` and ``invalid`` include
        the concrete parse/validation text so a subclass can feed this back
        through ``--resume`` once.
        """
        if outcome.status == "ok":
            return ""
        retry = (
            f"{RESULT_FILENAME} 未通过校验，请修正后重新写入 ./{RESULT_FILENAME}"
            f"（JSON5 宽松格式，形状见 ./{SCHEMA_FILENAME}）。"
        )
        if outcome.status == "missing":
            detail = outcome.parse_error or "文件不存在"
            return f"{RESULT_FILENAME} 不存在或不可读：{detail}\n{retry}"
        if outcome.validation_error is not None:
            return f"{RESULT_FILENAME} 中有字段违反约束：\n{outcome.validation_error}\n{retry}"
        detail = outcome.parse_error or "无法解析"
        return f"{RESULT_FILENAME} 解析失败：{detail}\n{retry}"

    def _new_task_directory(self, task_key: str) -> Path:
        """Mint a directory that no earlier call can share."""
        if self._root is None:
            directory = Path(tempfile.mkdtemp(prefix="he-ai-submission-"))
            self._temp_directories.append(directory)
            return directory
        self._root.mkdir(parents=True, exist_ok=True)
        directory = self._root / f"{_safe_task_key(task_key)}-{uuid.uuid4().hex}"
        directory.mkdir()
        return directory

    def _prompt_addendum(self, task_key: str) -> str:
        """Build the instruction fragment appended to the caller's prompt."""
        return (
            f"任务 {task_key}：只把最终结论写进当前目录的 ./{RESULT_FILENAME}，然后停止。\n"
            f"1. 文件内容必须是单个 JSON5 对象，字段形状以当前目录的 ./{SCHEMA_FILENAME} 为准。\n"
            "2. JSON5 是宽松格式：允许 // 与 /* */ 注释、尾逗号、单引号字符串、不加引号的裸键。\n"
            "3. 不要在文件之外输出解释、Markdown 围栏或任何散文，结论只存在于该文件里。\n"
        )


def _safe_task_key(task_key: str) -> str:
    """Collapse a task key into a filesystem-safe directory prefix."""
    collapsed = _UNSAFE_TASK_KEY_CHARS.sub("-", task_key).strip("-._")[:_MAX_TASK_KEY_CHARS]
    return collapsed or "task"


def _discard_directories(directories: list[Path]) -> None:
    """Remove the temp dirs this instance minted, ignoring races and permissions."""
    for directory in directories:
        shutil.rmtree(directory, ignore_errors=True)


def _describe(exc: BaseException) -> str:
    """Return a non-empty one-paragraph description of an exception."""
    return str(exc).strip() or type(exc).__name__


def _bounded(text: str) -> str:
    """Cap diagnostic text so an outcome stays safe to persist and display."""
    normalized = text.strip()
    if len(normalized) <= _MAX_ERROR_CHARS:
        return normalized
    return f"{normalized[:_MAX_ERROR_CHARS]}…[truncated]"


def _parse_document(text: str) -> tuple[Mapping[str, Any] | None, str | None]:
    """Parse one literal through the fixed ladder and return payload or error.

    The repair tier is reached only when both strict JSON and JSON5 fail, and a
    successful-but-non-mapping top level stops the ladder immediately: a list
    or scalar is a caller mistake, not a syntax problem to salvage.
    """
    errors: list[str] = []
    loaders: tuple[tuple[str, Callable[[str], Any]], ...] = (
        ("strict JSON", json.loads),
        ("JSON5", json5.loads),
        ("json-repair", json_repair.loads),
    )
    for name, loader in loaders:
        try:
            candidate = loader(text)
        except Exception as exc:  # malformed input must never escape
            errors.append(f"{name}: {_describe(exc)}")
            continue
        if not isinstance(candidate, Mapping):
            trail = f"（前序错误：{'；'.join(errors)}）" if errors else ""
            return None, _bounded(
                f"{name} 解析结果不是 JSON 对象：{type(candidate).__name__}{trail}"
            )
        return candidate, None
    return None, _bounded("；".join(errors) or "无法解析 result.json5")


__all__ = [
    "RESULT_FILENAME",
    "SCHEMA_FILENAME",
    "SUBMISSION_TOOLS",
    "StructuredSubmission",
    "SubmissionOutcome",
    "SubmissionPrep",
]
