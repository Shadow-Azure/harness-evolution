"""Deterministic structured submission channel shared by CLI Agent providers.

An agent writes one lenient JSON5 literal (``result.json5``) into a disposable
per-call task directory; this module reads it without executing model code,
parses it with a fixed fallback ladder, validates it against the caller's
Pydantic model, and turns a failure into a locatable retry prompt. Pydantic is
the single schema source of truth: ``schema.json`` is derived from the caller
model, never hand-authored.

The accepted top level is exactly one JSON object. A literal whose top level
parses to a list or scalar is ``invalid`` and never reaches the caller
validator, so a list-shaped ``RootModel`` output would require extending this
channel deliberately instead of arriving through the generic collector.

The component starts no model call, owns no business rule, and never branches
on a backend. It is the layer-1 reliability defense of the six-layer JSON
design (07 §5.5.3).
"""

# ruff: noqa: RUF001

from __future__ import annotations

import contextlib
import json
import re
import shutil
import tempfile
import uuid
import weakref
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

import json5
import json_repair
from pydantic import BaseModel

RESULT_FILENAME: Final = "result.json5"
"""Name of the one literal file the agent may write inside a task directory."""

SCHEMA_FILENAME: Final = "schema.json"
"""Name of the caller-derived schema the agent reads for the expected shape."""

SUBMISSION_TOOLS: Final[tuple[str, ...]] = ("Write(./result.json5)",)
"""The sole tool whitelist granted while producing one submission."""

_RESULT_SIZE_LIMIT: Final = 1024 * 1024
"""Bytes of result file the channel will read; anything larger is rejected unread."""

_MAX_ERROR_CHARS: Final = 4_000
"""Upper bound for an error text kept in an outcome, so logs stay bounded."""

_MAX_TASK_KEY_CHARS: Final = 48
"""Upper bound for the sanitized task-key prefix of a directory name."""

_REPAIR_LOG_ENTRIES: Final = 5
"""Upper bound for the number of repair actions kept in an outcome."""

_REPAIR_LOG_ENTRY_CHARS: Final = 500
"""Upper bound for one rendered repair action, so provenance stays loggable."""

_UNSAFE_TASK_KEY_CHARS: Final = re.compile(r"[^A-Za-z0-9._-]+")

_ParsedBy = Literal["strict", "json5", "repair"]


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
    ``invalid`` (unreadable as text, oversized, unparseable, non-object, or
    rejected payload), ``missing`` (the file could not be read at all).

    Provenance for layer 4/5: ``parsed_by`` names the ladder tier that produced
    the document (``None`` when no tier did, e.g. ``missing`` or all tiers
    failed; a non-object top level still names its tier). ``repair_log`` carries
    up to five bounded repair actions reported by the repairer; it can still be
    empty when the repairer silently normalizes (for example, closing a missing
    brace), so ``parsed_by == "repair"`` is the authoritative provenance flag.
    ``parse_error`` covers the read/parse ladder; ``validation_error`` preserves
    the caller validator's concrete error text.
    """

    status: Literal["ok", "invalid", "missing"]
    payload: Mapping[str, Any] | None = None
    validated: BaseModel | None = None
    parse_error: str | None = None
    validation_error: str | None = None
    parsed_by: Literal["strict", "json5", "repair"] | None = None
    repair_log: tuple[str, ...] = ()

    @property
    def is_ok(self) -> bool:
        """Return whether the payload passed the caller's model."""
        return self.status == "ok"


@dataclass(frozen=True, slots=True)
class _ParseResult:
    """One traversal of the parse ladder: payload or error, plus provenance."""

    payload: Mapping[str, Any] | None
    parse_error: str | None
    parsed_by: _ParsedBy | None
    repair_log: tuple[str, ...]


class StructuredSubmission:
    """Mint one disposable task directory per call and collect its literal.

    The directory is one-shot by construction: every :meth:`prepare` call
    derives a fresh uuid-suffixed directory and never reuses an earlier one.
    Without a root the directory is a disposable system temp dir owned by this
    instance; a supplied root is kept for the caller and each call still mints
    a unique child below it.

    Lifecycle: a long-lived instance keeps every ``prepare`` directory until
    :meth:`discard` removes it or the instance itself is collected (which
    removes the remaining temp dirs). :meth:`collect` never discards, because
    layer-5 raw evidence may still be wanted. A caller that analyzes many tasks
    should call :meth:`discard` once it stops retrying that task.
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

        The accepted top level is exactly one JSON object: a list or scalar is
        ``invalid`` and never reaches ``validate``. Parse order is strict JSON,
        then JSON5, then json-repair as the salvage tier only. A file larger than
        1 MiB is rejected unread. Any exception from ``validate`` is folded into
        ``validation_error``; malformed bytes and oversized files never escape
        as a traceback.
        """
        try:
            size = prep.result_path.stat().st_size
        except OSError as exc:
            return SubmissionOutcome(
                status="missing",
                parse_error=_bounded(
                    f"{RESULT_FILENAME} 不存在或不可读：{_describe_io(exc, prep.result_path)}"
                ),
            )
        except MemoryError:
            return SubmissionOutcome(
                status="invalid",
                parse_error=f"{RESULT_FILENAME} 无法读取大小：MemoryError",
            )
        if size > _RESULT_SIZE_LIMIT:
            return SubmissionOutcome(
                status="invalid",
                parse_error=(
                    f"{RESULT_FILENAME} 大小 {size} 字节，超过 {_RESULT_SIZE_LIMIT} 字节"
                    "（1 MiB）上限，已拒绝读取"
                ),
            )

        try:
            text = prep.result_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            return SubmissionOutcome(
                status="invalid",
                parse_error=_bounded(f"{RESULT_FILENAME} 不是合法的 UTF-8 文本：{_describe(exc)}"),
            )
        except OSError as exc:
            return SubmissionOutcome(
                status="missing",
                parse_error=_bounded(
                    f"{RESULT_FILENAME} 不存在或不可读：{_describe_io(exc, prep.result_path)}"
                ),
            )

        parsed = _parse_document(text)
        if parsed.payload is None:
            return SubmissionOutcome(
                status="invalid",
                parse_error=parsed.parse_error,
                parsed_by=parsed.parsed_by,
            )

        try:
            validated = validate(parsed.payload)
        except Exception as exc:  # any validator failure is terminal data
            return SubmissionOutcome(
                status="invalid",
                payload=parsed.payload,
                validation_error=_bounded(_describe(exc)),
                parsed_by=parsed.parsed_by,
                repair_log=parsed.repair_log,
            )
        return SubmissionOutcome(
            status="ok",
            payload=parsed.payload,
            validated=validated,
            parsed_by=parsed.parsed_by,
            repair_log=parsed.repair_log,
        )

    def discard(self, prep: SubmissionPrep) -> None:
        """Remove one task directory after the caller stops retrying its task.

        Idempotent: a directory that is already gone is ignored, and the
        directory is dropped from the instance's tracked temp list either way.
        The caller-owned root itself is never touched; only the one-shot child
        directory named by ``prep`` is removed.
        """
        shutil.rmtree(prep.directory, ignore_errors=True)
        with contextlib.suppress(ValueError):
            self._temp_directories.remove(prep.directory)

    def feedback_prompt(self, outcome: SubmissionOutcome) -> str:
        """Render a localized retry prompt for a non-ok outcome.

        ``ok`` returns the empty string: the caller has its validated payload
        and must not resume the session. Every other state names the concrete
        reason and the relative write path, repeats no ``parse_error`` prefix,
        and never leaks the absolute task directory.
        """
        if outcome.status == "ok":
            return ""
        retry = (
            f"{RESULT_FILENAME} 未通过校验，请修正后重新写入 ./{RESULT_FILENAME}"
            f"（JSON5 宽松格式，形状见 ./{SCHEMA_FILENAME}）。"
        )
        if outcome.status == "missing":
            detail = outcome.parse_error or f"{RESULT_FILENAME} 不存在或不可读"
            return f"{detail}\n{retry}"
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


def _describe_io(exc: OSError, path: Path) -> str:
    """Describe an IO failure without leaking the absolute task path.

    ``OSError.__str__`` embeds the full filename, which would put a temporary
    directory into a retry prompt; the bare name plus the OS reason is enough
    for the model and safe to log.
    """
    reason = exc.strerror or _describe(exc)
    return reason.replace(str(path), path.name)


def _bounded(text: str) -> str:
    """Cap diagnostic text at line boundaries so no retained line is cut off.

    Error texts are multi-line (Pydantic emits one block per violation), and a
    retry prompt is easier to act on when every shown line is complete. The
    character ceiling remains a backstop for a single pathological line.
    """
    normalized = text.strip()
    if len(normalized) <= _MAX_ERROR_CHARS:
        return normalized
    lines = normalized.splitlines()
    kept: list[str] = []
    used = 0
    for line in lines:
        projected = used + len(line) + (1 if kept else 0)
        if projected > _MAX_ERROR_CHARS:
            break
        kept.append(line)
        used = projected
    if not kept:
        return f"{normalized[:_MAX_ERROR_CHARS]}…（还有 {len(lines)} 行未展示）"
    hidden = len(lines) - len(kept)
    return "\n".join(kept) + f"\n…（还有 {hidden} 行未展示）"


def _bound_repair_log(logs: list[dict[str, str]]) -> tuple[str, ...]:
    """Render at most ``_REPAIR_LOG_ENTRIES`` repair actions, each size-capped."""
    rendered: list[str] = []
    for entry in logs[:_REPAIR_LOG_ENTRIES]:
        action = entry.get("text", "").strip()
        context = entry.get("context", "").strip()
        line = f"{action}（上下文：{context}）" if context else action
        rendered.append(line[:_REPAIR_LOG_ENTRY_CHARS])
    return tuple(rendered)


def _load_with_repair_log(text: str) -> tuple[Any, tuple[str, ...]]:
    """Run the salvage tier with its action log enabled, then bound the log."""
    loaded = cast(
        "tuple[Any, list[dict[str, str]]]",
        json_repair.loads(text, logging=True),
    )
    candidate, logs = loaded
    return candidate, _bound_repair_log(logs)


def _parse_document(text: str) -> _ParseResult:
    """Parse one literal through the fixed ladder and return payload or error.

    The repair tier is reached only when both strict JSON and JSON5 fail, and it
    runs with ``logging=True`` so a salvaged value stays auditable. A
    successful-but-non-mapping top level stops the ladder immediately: a list
    or scalar is a caller mistake, not a syntax problem to salvage.
    """
    errors: list[str] = []
    tiers: tuple[tuple[_ParsedBy, str], ...] = (
        ("strict", "strict JSON"),
        ("json5", "JSON5"),
        ("repair", "json-repair"),
    )
    for parsed_by, label in tiers:
        repair_log: tuple[str, ...] = ()
        try:
            if parsed_by == "repair":
                candidate, repair_log = _load_with_repair_log(text)
            elif parsed_by == "json5":
                candidate = json5.loads(text)
            else:
                candidate = json.loads(text)
        except Exception as exc:  # malformed input must never escape
            errors.append(f"{label}: {_describe(exc)}")
            continue
        if not isinstance(candidate, Mapping):
            trail = f"（前序错误：{'；'.join(errors)}）" if errors else ""
            return _ParseResult(
                payload=None,
                parse_error=_bounded(
                    f"{label} 解析结果不是 JSON 对象：{type(candidate).__name__}{trail}"
                ),
                parsed_by=parsed_by,
                repair_log=(),
            )
        return _ParseResult(
            payload=candidate,
            parse_error=None,
            parsed_by=parsed_by,
            repair_log=repair_log,
        )
    return _ParseResult(
        payload=None,
        parse_error=_bounded("；".join(errors) or "无法解析"),
        parsed_by=None,
        repair_log=(),
    )


__all__ = [
    "RESULT_FILENAME",
    "SCHEMA_FILENAME",
    "SUBMISSION_TOOLS",
    "StructuredSubmission",
    "SubmissionOutcome",
    "SubmissionPrep",
]
