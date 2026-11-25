"""Deterministic EditPlan contract and applier for instruction-style patches.

The agent returns a structured plan instead of editing files directly; this
module owns the schema, the semantic validation rules, and the pure-text
applier. ``git diff`` remains the single source of truth for what actually
changed, so nothing here reports a diff of its own.

Determinism contract:

* the same plan over the same base text produces byte-identical files;
* edits run strictly in plan order and every edit re-reads its file, so an
  anchor created or changed by an earlier edit is visible to a later one;
* path resolution, glob matching, and atomic replacement never depend on the
  process working directory or on filesystem enumeration order.

Failure policy: a per-edit failure is recorded in the report and the remaining
edits still run. Every write validates the edit and the path first and then
replaces the destination atomically through a same-directory temp file, so a
failed edit leaves the file at its last consistent state. Two failures are
terminal rather than per-edit: a non-absolute or missing workspace and a
negative budget both raise :class:`EditPlanError` before any edit runs.
"""

from __future__ import annotations

import os
import re
import stat
import tempfile
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Final, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    field_validator,
    model_validator,
)

EDIT_BUDGET: Final = 8
"""Maximum number of edits the prompt may submit and the applier will run."""

MAX_CONTENT_LINES: Final = 400
"""Maximum line count for one edit's replacement or inserted content."""

EditOpName = Literal["append", "insert_after", "replace", "delete"]
"""The four closed edit operations."""

EditStatusKind = Literal["applied", "skipped_anchor_missing", "error"]
"""The closed per-edit outcome set."""

_PROTECTED_DIRS: Final[frozenset[str]] = frozenset({".git", ".harness-evolution"})
"""Directories that never belong to an EditPlan's writable scope."""

_PROTECTED_DIRS_FOLDED: Final[frozenset[str]] = frozenset(
    name.casefold() for name in _PROTECTED_DIRS
)
"""Case-folded protected names, because macOS filesystems resolve case-insensitively."""

_MAX_ERROR_CHARS: Final = 1_000
"""Upper bound for a validation or I/O detail echoed back to the caller."""

_ANCHORED_OPS: Final[frozenset[str]] = frozenset({"replace", "insert_after", "delete"})
"""Operations that need an anchor present exactly once in the current file."""


def _require_non_blank(value: str | None, *, field: str, op: str) -> str:
    """Return a non-blank cross-field value or raise a locatable ValueError."""
    if value is None or not value.strip():
        raise ValueError(f"{field} is required for op={op!r} and must not be blank")
    return value


def _has_protected_part(parts: tuple[str, ...]) -> bool:
    """Return whether any path segment names a protected directory.

    Matching is case-insensitive because macOS resolves ``.GIT`` to ``.git``
    on its default case-insensitive filesystem.
    """
    return any(part.casefold() in _PROTECTED_DIRS_FOLDED for part in parts)


def _safe_relative_path(value: str) -> PurePosixPath:
    """Validate and return a workspace-relative POSIX path.

    Shared by the Pydantic validator and the applier so a plan built by
    bypassing model validation still cannot escape the workspace or touch a
    protected directory.
    """
    if not value or not value.strip():
        raise ValueError("file must not be empty")
    if value != value.strip():
        raise ValueError("file must not have leading or trailing whitespace")
    if "\x00" in value:
        raise ValueError("file must not contain a NUL byte")
    if "\\" in value:
        raise ValueError("file must use POSIX separators")
    if re.match(r"^[A-Za-z]:", value):
        raise ValueError("file must not start with a drive prefix")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError("file must be a relative POSIX path")
    if path.as_posix() != value:
        raise ValueError("file must be a canonical POSIX path")
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("file must not contain '.', '..', or empty segments")
    if _has_protected_part(parts):
        raise ValueError(f"file must not target {sorted(_PROTECTED_DIRS)!r}")
    return path


class EditOp(BaseModel):
    """One deterministic text edit inside a workspace-relative file.

    Pydantic is the single source of truth for the shape: the op-specific
    required fields, the rationale, and the path safety rules all live here so
    the submission channel can reject a plan before the applier touches disk.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    op: EditOpName
    file: str
    target: str | None = None
    content: str | None = None
    rationale: str

    @field_validator("file")
    @classmethod
    def _validate_file(cls, value: str) -> str:
        """Reject unsafe paths before an edit can be applied."""
        _safe_relative_path(value)
        return value

    @field_validator("rationale")
    @classmethod
    def _validate_rationale(cls, value: str) -> str:
        """Require a non-blank reason for every edit."""
        if not value.strip():
            raise ValueError("rationale must not be blank")
        return value

    @field_validator("content")
    @classmethod
    def _validate_content_size(cls, value: str | None) -> str | None:
        """Bound one edit's content so a plan stays reviewable and replayable."""
        if value is not None and len(value.splitlines()) > MAX_CONTENT_LINES:
            raise ValueError(f"content must not exceed {MAX_CONTENT_LINES} lines")
        return value

    @model_validator(mode="after")
    def _validate_op_fields(self) -> Self:
        """Enforce the op-specific required and forbidden fields.

        ``insert_after`` anchors the unique text fragment that content is
        inserted after; the fragment may span multiple lines, and the applier
        resolves the end of its last line, so no line count is enforced here.
        """
        if self.op == "append":
            if self.target is not None:
                raise ValueError("append must not set target")
            _require_non_blank(self.content, field="content", op=self.op)
        elif self.op in _ANCHORED_OPS:
            _require_non_blank(self.target, field="target", op=self.op)
            if self.op == "delete":
                if self.content is not None:
                    raise ValueError("delete must not set content")
            else:
                _require_non_blank(self.content, field="content", op=self.op)
        return self


class EditPlan(BaseModel):
    """One auditable edit plan: a summary plus an ordered immutable edit tuple.

    ``edits`` is a tuple so the frozen model is deeply immutable: callers cannot
    append past the construction-time budget check. JSON arrays still validate
    and still serialize as arrays.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    summary: str
    edits: tuple[EditOp, ...]

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, value: str) -> str:
        """Require a non-blank human summary for the candidate message."""
        if not value.strip():
            raise ValueError("summary must not be blank")
        return value

    @model_validator(mode="after")
    def _validate_budget(self) -> Self:
        """Reject a plan above the prompt-side edit budget."""
        if len(self.edits) > EDIT_BUDGET:
            raise ValueError(
                f"edits must not exceed edit_budget={EDIT_BUDGET}; got {len(self.edits)}",
            )
        return self


@dataclass(frozen=True, slots=True)
class EditStatus:
    """One per-edit outcome, locatable by index, op, and file."""

    index: int
    op: str
    file: str
    status: EditStatusKind
    message: str = ""

    def __post_init__(self) -> None:
        """Reject a negative index or an unknown status value."""
        if self.index < 0:
            raise ValueError("EditStatus.index must not be negative")
        if self.status not in {"applied", "skipped_anchor_missing", "error"}:
            raise ValueError(f"unknown EditStatus.status: {self.status!r}")


@dataclass(frozen=True, slots=True)
class EditApplication:
    """The deterministic result of applying one plan.

    ``files`` is the sorted unique set of files whose bytes actually changed.
    ``report`` holds one status per plan edit in order (including budget
    rejections); ``skipped`` is the subset that was not applied, ready to feed
    back to a model.
    """

    files: tuple[str, ...]
    report: tuple[EditStatus, ...]
    skipped: tuple[EditStatus, ...]

    @property
    def applied(self) -> tuple[EditStatus, ...]:
        """Return the statuses that were applied."""
        return tuple(status for status in self.report if status.status == "applied")

    @property
    def errors(self) -> tuple[EditStatus, ...]:
        """Return the statuses that failed a semantic or I/O check."""
        return tuple(status for status in self.report if status.status == "error")


class EditPlanError(RuntimeError):
    """A locatable application-time failure safe to feed back to a model.

    The message format is ``edits[<index>] (file=<file>, op=<op>): <constraint>``
    so a retry prompt can name the exact edit without echoing plan content.
    """


class _AnchorMissing(EditPlanError):
    """The anchor (or its file) does not exist in the current workspace state."""


@dataclass(frozen=True, slots=True)
class _EditOutcome:
    """One text edit's result: new text, or ``None`` with a skip reason."""

    text: str | None
    message: str = ""


def _constraint_message(index: int, file: str, op: str, constraint: str) -> str:
    """Render the stable, locatable error prefix shared by every failure."""
    return f"edits[{index}] (file={file!r}, op={op}): {constraint}"


def _validation_detail(exc: ValidationError) -> str:
    """Render bounded field locations and messages without echoing input."""
    parts: list[str] = []
    for error in exc.errors(include_url=False, include_input=False):
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)[:_MAX_ERROR_CHARS] or "invalid edit"


def _io_detail(exc: OSError) -> str:
    """Describe an I/O failure without leaking an absolute workspace path."""
    return (exc.strerror or type(exc).__name__)[:_MAX_ERROR_CHARS]


def _raw_field(raw: object, field: str) -> str:
    """Best-effort field extraction for an edit that failed model validation."""
    value: object = getattr(raw, field, None)
    if value is None and isinstance(raw, Mapping):
        value = raw.get(field)
    return str(value) if value is not None else "<unknown>"


def _coerce_edit(raw: object, index: int) -> EditOp:
    """Validate one plan entry, including one built by bypassing EditPlan.

    An ``EditOp`` produced with ``model_construct`` skips the Pydantic
    validators, so it is re-validated from its field values rather than trusted
    by isinstance. Otherwise a bypassed blank content or unknown op could reach
    the text applier.
    """
    if isinstance(raw, EditOp):
        raw = raw.model_dump()
    try:
        return EditOp.model_validate(raw)
    except ValidationError as exc:
        raise EditPlanError(
            _constraint_message(
                index,
                _raw_field(raw, "file"),
                _raw_field(raw, "op"),
                _validation_detail(exc),
            ),
        ) from None


@lru_cache(maxsize=256)
def _compile_glob(pattern: str) -> re.Pattern[str]:
    """Compile a POSIX glob where ``**`` crosses separators and ``*`` does not."""
    translated: list[str] = []
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "*":
            if pattern.startswith("**", index):
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    index += 1
                    translated.append("(?:.*/)?")
                else:
                    translated.append(".*")
                continue
            translated.append("[^/]*")
        elif character == "?":
            translated.append("[^/]")
        else:
            translated.append(re.escape(character))
        index += 1
    return re.compile("^" + "".join(translated) + "$")


def _matches_allowed(file: str, allowed_paths: tuple[str, ...]) -> bool:
    """Return whether one file is inside the caller's allowed glob scope.

    An empty tuple matches nothing; the applier only calls this for a
    non-``None`` scope, because ``None`` means the caller explicitly did not
    narrow the writable set.
    """
    for raw_pattern in allowed_paths:
        pattern = raw_pattern.strip()
        if not pattern:
            continue
        if pattern.startswith("./"):
            pattern = pattern[2:]
        if _compile_glob(pattern).fullmatch(file):
            return True
        if pattern.endswith("/**") and file == pattern[:-3].rstrip("/"):
            return True
    return False


def _load_target(
    workspace: Path,
    edit: EditOp,
    index: int,
    allowed_paths: tuple[str, ...] | None,
) -> tuple[str, Path]:
    """Validate scope and resolve one existing UTF-8 file inside the workspace."""
    try:
        relative = _safe_relative_path(edit.file)
    except ValueError as exc:
        raise EditPlanError(_constraint_message(index, edit.file, edit.op, str(exc))) from None
    if allowed_paths is not None and not _matches_allowed(edit.file, allowed_paths):
        raise EditPlanError(
            _constraint_message(
                index,
                edit.file,
                edit.op,
                f"file is outside allowed_paths {list(allowed_paths)!r}",
            ),
        )
    destination = workspace.joinpath(*relative.parts)
    root = workspace.resolve()
    try:
        resolved = destination.resolve()
    except OSError as exc:
        raise EditPlanError(
            _constraint_message(
                index,
                edit.file,
                edit.op,
                f"path could not be resolved: {_io_detail(exc)}",
            ),
        ) from None
    try:
        resolved_relative = resolved.relative_to(root)
    except ValueError:
        raise EditPlanError(
            _constraint_message(index, edit.file, edit.op, "path escapes the workspace"),
        ) from None
    if _has_protected_part(resolved_relative.parts):
        raise EditPlanError(
            _constraint_message(
                index,
                edit.file,
                edit.op,
                "path resolves into a protected directory",
            ),
        )
    if allowed_paths is not None and not _matches_allowed(
        resolved_relative.as_posix(), allowed_paths
    ):
        raise EditPlanError(
            _constraint_message(
                index,
                edit.file,
                edit.op,
                f"resolved path is outside allowed_paths {list(allowed_paths)!r}",
            ),
        )
    if not resolved.exists():
        raise _AnchorMissing(
            _constraint_message(index, edit.file, edit.op, "file does not exist"),
        )
    if not resolved.is_file():
        raise EditPlanError(
            _constraint_message(index, edit.file, edit.op, "target is not a regular file"),
        )
    try:
        with resolved.open("r", encoding="utf-8", newline="") as handle:
            text = handle.read()
    except UnicodeDecodeError:
        raise EditPlanError(
            _constraint_message(index, edit.file, edit.op, "file is not valid UTF-8"),
        ) from None
    except OSError as exc:
        raise EditPlanError(
            _constraint_message(
                index,
                edit.file,
                edit.op,
                f"file could not be read: {_io_detail(exc)}",
            ),
        ) from None
    return text, resolved


def _append_text(text: str, content: str) -> str:
    """Append content at EOF with exactly one trailing newline.

    Existing bytes are preserved; a file without a final newline gains one at
    the boundary, and content's own trailing newlines collapse to one.
    """
    body = content.rstrip("\n")
    prefix = text if text.endswith("\n") or not text else f"{text}\n"
    return f"{prefix}{body}\n"


def _insert_after_text(text: str, target: str, content: str) -> str:
    """Insert content lines directly after the unique block matched by ``target``.

    ``target`` may span multiple lines. When it ends with a line terminator the
    insertion point is right after that terminator; otherwise it is the end of
    the line containing the match's last character, and an unterminated final
    line gains one. Inserted lines reuse the anchor line's ``\\r\\n`` or ``\\n``
    style, so a single-line target keeps producing the historical bytes.
    """
    try:
        match_end = text.index(target) + len(target)
    except ValueError:  # pragma: no cover - counted before this call
        raise EditPlanError("insert_after anchor is not contained in the file") from None
    if target.endswith("\r\n"):
        ending, prefix, suffix = "\r\n", text[:match_end], text[match_end:]
    elif target.endswith("\r"):
        if text.startswith("\n", match_end):
            # The target stops halfway through a CRLF terminator; finish it.
            match_end += 1
            ending = "\r\n"
        else:
            ending = "\n"
        prefix, suffix = text[:match_end], text[match_end:]
    elif target.endswith("\n"):
        ending, prefix, suffix = "\n", text[:match_end], text[match_end:]
    else:
        newline = text.find("\n", match_end)
        if newline != -1:
            ending = "\r\n" if newline > 0 and text[newline - 1] == "\r" else "\n"
            prefix, suffix = text[: newline + 1], text[newline + 1 :]
        else:
            carriage = text.find("\r", match_end)
            if carriage != -1:
                ending, prefix, suffix = "\n", text[: carriage + 1], text[carriage + 1 :]
            else:
                ending = "\n"
                prefix, suffix = f"{text[:match_end]}{ending}", ""
    inserted = content.splitlines() or [""]
    body = "".join(f"{line}{ending}" for line in inserted)
    return f"{prefix}{body}{suffix}"


def _apply_one(edit: EditOp, text: str, index: int) -> _EditOutcome:
    """Apply one already-validated edit to the current file text."""
    if edit.op == "append":
        content = edit.content
        if content is None:
            raise EditPlanError(
                _constraint_message(index, edit.file, edit.op, "content is required")
            )
        return _EditOutcome(_append_text(text, content))

    target = edit.target
    if target is None:
        raise EditPlanError(_constraint_message(index, edit.file, edit.op, "target is required"))

    if edit.op == "insert_after":
        occurrences = text.count(target)
        if occurrences == 0:
            return _EditOutcome(
                None,
                _constraint_message(index, edit.file, edit.op, "anchor not found"),
            )
        if occurrences > 1:
            raise EditPlanError(
                _constraint_message(
                    index,
                    edit.file,
                    edit.op,
                    f"anchor is ambiguous ({occurrences} occurrences)",
                ),
            )
        content = edit.content
        if content is None:
            raise EditPlanError(
                _constraint_message(index, edit.file, edit.op, "content is required")
            )
        return _EditOutcome(_insert_after_text(text, target, content))

    occurrences = text.count(target)
    if occurrences == 0:
        return _EditOutcome(
            None,
            _constraint_message(index, edit.file, edit.op, "anchor not found"),
        )
    if occurrences > 1:
        raise EditPlanError(
            _constraint_message(
                index,
                edit.file,
                edit.op,
                f"anchor is ambiguous ({occurrences} occurrences)",
            ),
        )
    if edit.op == "replace":
        content = edit.content
        if content is None:
            raise EditPlanError(
                _constraint_message(index, edit.file, edit.op, "content is required")
            )
        return _EditOutcome(text.replace(target, content, 1))
    return _EditOutcome(text.replace(target, "", 1))


def _atomic_write(destination: Path, text: str) -> None:
    """Replace one file atomically through a same-directory temp file."""
    descriptor, temp_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if destination.exists():
            os.chmod(temp_path, stat.S_IMODE(destination.stat().st_mode))
        os.replace(temp_path, destination)
    except BaseException:
        with suppress(OSError):
            temp_path.unlink()
        raise


def apply_edit_plan(
    plan: EditPlan,
    *,
    workspace: Path,
    allowed_paths: tuple[str, ...] | None = None,
    edit_budget: int = EDIT_BUDGET,
) -> EditApplication:
    """Apply every edit in order and return a deterministic per-edit report.

    ``allowed_paths=None`` means the caller explicitly did not narrow the
    writable set; an empty tuple denies every file, so a scope that was
    computed but ended up empty fails closed instead of silently widening.

    The applier never widens the module ceiling: ``edit_budget`` may tighten
    the limit below :data:`EDIT_BUDGET` but is clamped to it, so a caller
    cannot bypass the hard gate. Edits beyond the effective limit are recorded
    as ``error`` statuses and skipped.

    An anchor that is absent is ``skipped_anchor_missing`` (including a missing
    file); an ambiguous anchor, an out-of-scope or escaping path, an invalid
    edit, and an I/O failure are ``error``. Every one of those leaves the
    current file consistent, so the loop continues with the remaining edits.
    """
    workspace = Path(workspace)
    if not workspace.is_absolute():
        raise EditPlanError("workspace must be an absolute path")
    if not workspace.is_dir():
        raise EditPlanError("workspace must be an existing directory")
    if edit_budget < 0:
        raise EditPlanError("edit_budget must not be negative")
    limit = min(edit_budget, EDIT_BUDGET)

    raw_edits = list(plan.edits)
    statuses: list[EditStatus] = []
    changed: set[str] = set()

    for index, raw in enumerate(raw_edits):
        if index >= limit:
            op = _raw_field(raw, "op")
            file = _raw_field(raw, "file")
            statuses.append(
                EditStatus(
                    index=index,
                    op=op,
                    file=file,
                    status="error",
                    message=_constraint_message(
                        index,
                        file,
                        op,
                        (
                            f"edit budget exceeded: {len(raw_edits)} edits submitted, "
                            f"effective limit {limit}"
                        ),
                    ),
                ),
            )
            continue
        try:
            edit = _coerce_edit(raw, index)
            text, destination = _load_target(workspace, edit, index, allowed_paths)
            outcome = _apply_one(edit, text, index)
            if outcome.text is None:
                statuses.append(
                    EditStatus(
                        index=index,
                        op=edit.op,
                        file=edit.file,
                        status="skipped_anchor_missing",
                        message=outcome.message,
                    ),
                )
                continue
            if outcome.text != text:
                _atomic_write(destination, outcome.text)
                changed.add(edit.file)
            statuses.append(
                EditStatus(
                    index=index,
                    op=edit.op,
                    file=edit.file,
                    status="applied",
                ),
            )
        except _AnchorMissing as exc:
            statuses.append(
                EditStatus(
                    index=index,
                    op=_raw_field(raw, "op"),
                    file=_raw_field(raw, "file"),
                    status="skipped_anchor_missing",
                    message=str(exc),
                ),
            )
        except EditPlanError as exc:
            statuses.append(
                EditStatus(
                    index=index,
                    op=_raw_field(raw, "op"),
                    file=_raw_field(raw, "file"),
                    status="error",
                    message=str(exc),
                ),
            )
        except OSError as exc:
            file = _raw_field(raw, "file")
            op = _raw_field(raw, "op")
            statuses.append(
                EditStatus(
                    index=index,
                    op=op,
                    file=file,
                    status="error",
                    message=_constraint_message(
                        index,
                        file,
                        op,
                        f"write failed: {_io_detail(exc)}",
                    ),
                ),
            )

    report = tuple(statuses)
    return EditApplication(
        files=tuple(sorted(changed)),
        report=report,
        skipped=tuple(status for status in report if status.status != "applied"),
    )


__all__ = [
    "EDIT_BUDGET",
    "MAX_CONTENT_LINES",
    "EditApplication",
    "EditOp",
    "EditOpName",
    "EditPlan",
    "EditPlanError",
    "EditStatus",
    "EditStatusKind",
    "apply_edit_plan",
]
