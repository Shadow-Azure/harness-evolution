# ruff: noqa: RUF001
"""Pluggable patch sources for real candidate change generation.

The placeholder source keeps the V1 documentation-only patch. The minimal-config
source derives one deterministic configuration key from the bad-case evidence
and merges it into the target repository's config file. Selection is factory
driven: the run's frozen ``eval_config["patchMode"]`` wins, otherwise the
process-wide ``HE_PATCH_SOURCE_MODE`` fallback applies. New generation
strategies only add a subclass plus configuration — business code stays put.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, cast, runtime_checkable

from app.db.models.evolution import EvolutionRunRecord
from app.service.evolution.engine.contracts import ConfigError
from app.third_party_api.ai_agent.edits import EditPlan, EditStatus
from app.third_party_api.git.workspace import Patch

PATCH_SOURCE_MODES = ("placeholder", "minimal-config", "agent-edit")
DEFAULT_PATCH_SOURCE_MODE = "placeholder"
PLACEHOLDER_PATCH_NOTE = "V1 占位 patch；真实文件已写入 isolated workspace"
_CONFIG_FILENAME = "config/{}.json"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_NAME_LENGTH = 64


@dataclass(frozen=True, slots=True)
class PatchBundle:
    """One candidate change as an ordered set of file patches.

    ``note`` is the human one-liner for the commit message, ``intent`` is the
    auditable EditPlan when the change came from an agent, and ``report`` holds
    the per-edit outcomes. When ``intent`` is present, ``note`` must equal
    ``intent.summary`` so the commit message and the audited intent cannot
    drift apart. ``unified_diff`` is reserved for the real ``git diff`` that
    the agent-edit source collects before committing (bugfix-21); the default
    legacy wrapper leaves it empty, and ``CandidateWorkspace.unified_diff``
    always carries the git-produced diff after the commit.

    Hash compatibility is a hard requirement: a single-file bundle returns
    :attr:`Patch.sha256` byte-for-byte, so ``Harness-Patch-Hash`` trailers from
    existing runs stay idempotent. A multi-file bundle hashes the sorted file
    list with an explicit separator (see :attr:`sha256`).
    """

    files: tuple[Patch, ...]
    note: str
    intent: EditPlan | None = None
    report: tuple[EditStatus, ...] = ()
    unified_diff: str = ""

    def __post_init__(self) -> None:
        """Reject an empty bundle, a blank note, or a repeated file path."""
        if not self.files:
            raise ValueError("PatchBundle.files must not be empty")
        if not self.note.strip():
            raise ValueError("PatchBundle.note must not be blank")
        if self.intent is not None and self.note != self.intent.summary:
            raise ValueError("PatchBundle.note must equal intent.summary")
        ordered = tuple(sorted(self.files, key=lambda patch: patch.file))
        paths = [patch.file for patch in ordered]
        if len(set(paths)) != len(paths):
            raise ValueError("PatchBundle.files must not repeat a file path")
        object.__setattr__(self, "files", ordered)
        object.__setattr__(self, "report", tuple(self.report))

    @property
    def sha256(self) -> str:
        """Return the stable digest recorded in candidate trailers.

        A single-file bundle returns :attr:`Patch.sha256` verbatim, which hashes
        ``file`` + one NUL + the newline-joined lines. A multi-file bundle
        initializes one SHA-256 and, for each file in ascending path order,
        updates it with the file path, one NUL, the newline-joined lines, and
        one trailing NUL. The sorted order makes the digest independent of
        caller ordering.
        """
        if len(self.files) == 1:
            return self.files[0].sha256
        digest = hashlib.sha256()
        for patch in self.files:
            digest.update(patch.file.encode("utf-8"))
            digest.update(b"\0")
            digest.update("\n".join(patch.lines).encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()


@runtime_checkable
class PatchSource(Protocol):
    """One candidate change generation strategy."""

    async def build(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> Patch:
        """Return the patch applied and committed inside the candidate."""
        ...

    async def build_bundle(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> PatchBundle:
        """Return the candidate change bundle for one round."""
        ...

    async def change_note(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> str:
        """Return the one-line human description for the「改动」message section."""
        ...


class _PatchBuilder(Protocol):
    """The two legacy hooks a default single-file bundle wraps."""

    async def build(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> Patch: ...

    async def change_note(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> str: ...


async def build_default_bundle(
    source: _PatchBuilder,
    run: EvolutionRunRecord,
    round_seq: int,
    trace: object,
) -> PatchBundle:
    """Wrap the legacy ``build()``/``change_note()`` pair as a single-file bundle."""
    patch = await source.build(run, round_seq, trace)
    note = await source.change_note(run, round_seq, trace)
    return PatchBundle(files=(patch,), note=note)


class _DefaultBundleSource:
    """Give a legacy source the additive ``build_bundle()`` behavior."""

    async def build_bundle(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> PatchBundle:
        """Return a one-file bundle without changing the legacy methods."""
        return await build_default_bundle(cast("_PatchBuilder", self), run, round_seq, trace)


class PlaceholderPatchSource(_DefaultBundleSource):
    """Deterministic V1 patch that is still written and committed for real."""

    async def build(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> Patch:
        """Return the V1 candidate documentation patch."""
        del trace
        sub_dir = PurePosixPath(run.sub_dir or ".")
        relative = (
            PurePosixPath(".harness-evolution") / f"candidate-r{round_seq}.md"
            if sub_dir == PurePosixPath(".")
            else sub_dir / ".harness-evolution" / f"candidate-r{round_seq}.md"
        )
        return Patch(
            file=relative.as_posix(),
            lines=(
                f"# Harness Evolution candidate r{round_seq}",
                "",
                f"- Run: {run.id}",
                f"- Target: {run.target_name}@{run.target_version}",
                "- This V1 patch is a deterministic placeholder applied to an isolated workspace.",
            ),
        )

    async def change_note(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> str:
        """Return the V1 placeholder note."""
        del run, round_seq, trace
        return PLACEHOLDER_PATCH_NOTE


# Keyword table mapping bad-case evidence text to one minimal config change.
# Ordered; the first match wins — the table order IS the priority. The keys and
# values are harness-side conventions, NOT the target repository's config
# schema: whether a real target accepts them is decided by the evaluation
# platform's measured verdict, not here. Externalizing this table into
# configuration is deferred until a real platform integration needs runtime
# tuning. Extend by appending rules or subclassing.
_CONFIG_RULES: tuple[tuple[tuple[str, ...], str, object], ...] = (
    (("timeout", "超时"), "requestTimeoutSeconds", 30),
    (("retry", "重试"), "maxRetries", 3),
    (
        ("index", "索引", "enoent", "读取失败", "未校验"),
        "snapshotFieldCheckEnabled",
        True,
    ),
    (("permission", "权限", "forbidden"), "permissionCheckEnabled", True),
)
_DEFAULT_RULE = ("harnessGuardEnabled", True)


class MinimalConfigPatchSource(_DefaultBundleSource):
    """Merge one deterministic configuration fix into the target repository."""

    async def build(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> Patch:
        """Merge the derived key into the target config file content."""
        del round_seq
        relative = self._config_path(run)
        document = self._read_existing(run, relative)
        key, value = self._derive_change(trace)
        document[key] = value
        payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
        return Patch(
            file=relative,
            lines=tuple(payload.splitlines()),
            overwrite=True,
        )

    async def change_note(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> str:
        """Describe the real minimal configuration change for the message."""
        del round_seq
        key, _value = self._derive_change(trace)
        return (
            f"最小配置变更：{self._config_path(run)} 新增 `{key}`（针对来源问题的最小参数级修复）"
        )

    def _config_path(self, run: EvolutionRunRecord) -> str:
        """Return the workspace-relative config path for one target."""
        sub_dir = PurePosixPath(run.sub_dir or ".")
        name = _SAFE_NAME.sub("-", run.target_name).strip("-") or "target"
        name = name[:_MAX_NAME_LENGTH]
        filename = _CONFIG_FILENAME.format(name)
        if sub_dir == PurePosixPath("."):
            return filename
        return (sub_dir / filename).as_posix()

    def _read_existing(
        self,
        run: EvolutionRunRecord,
        relative: str,
    ) -> dict[str, object]:
        """Load the existing config object or start from an empty document."""
        if not run.workspace_path:
            return {}
        destination = Path(run.workspace_path).joinpath(*PurePosixPath(relative).parts)
        if not destination.exists():
            return {}
        raw = destination.read_text(encoding="utf-8")
        try:
            parsed = json.loads(raw) if raw.strip() else {}
        except ValueError as exc:
            raise ConfigError(
                f"existing target config is not valid JSON: {relative}",
            ) from exc
        if not isinstance(parsed, dict):
            raise ConfigError(
                f"existing target config is not an object: {relative}",
            )
        return {str(key): value for key, value in parsed.items()}

    def _derive_change(self, trace: object) -> tuple[str, object]:
        """Match bad-case evidence text against the deterministic rule table."""
        text = _trace_text(trace).lower()
        for keywords, key, value in _CONFIG_RULES:
            if any(keyword in text for keyword in keywords):
                return key, value
        return _DEFAULT_RULE


def _trace_text(trace: object) -> str:
    """Collect the bad-case evidence text carried by one candidate trace."""
    parts: list[str] = []
    title = getattr(trace, "cluster_title", "")
    if isinstance(title, str):
        parts.append(title)
    analysis = getattr(trace, "analysis", "")
    if isinstance(analysis, str):
        parts.append(analysis)
    for source in getattr(trace, "sources", ()) or ():
        description = getattr(source, "description", "")
        if isinstance(description, str):
            parts.append(description)
        source_analysis = getattr(source, "analysis", "")
        if isinstance(source_analysis, str):
            parts.append(source_analysis)
    return " ".join(parts)


def default_patch_source_factory(
    run: EvolutionRunRecord,
    *,
    fallback_mode: str = DEFAULT_PATCH_SOURCE_MODE,
) -> PatchSource:
    """Resolve one patch source from the run snapshot with an env fallback."""
    configured = run.eval_config.get("patchMode")
    mode = configured if isinstance(configured, str) and configured else fallback_mode
    if mode == "placeholder":
        return PlaceholderPatchSource()
    if mode == "minimal-config":
        return MinimalConfigPatchSource()
    if mode == "agent-edit":
        raise ConfigError(
            "patch source mode 'agent-edit' is reserved for bugfix-21 and not implemented yet",
        )
    raise ConfigError(f"unknown patch source mode: {mode}")


__all__ = [
    "DEFAULT_PATCH_SOURCE_MODE",
    "PATCH_SOURCE_MODES",
    "PLACEHOLDER_PATCH_NOTE",
    "MinimalConfigPatchSource",
    "PatchBundle",
    "PatchSource",
    "PlaceholderPatchSource",
    "build_default_bundle",
    "default_patch_source_factory",
]
