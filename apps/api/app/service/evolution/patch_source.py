# ruff: noqa: RUF001
"""Pluggable patch sources for real candidate change generation.

The placeholder source keeps the V1 documentation-only patch. The minimal-config
source derives one deterministic configuration key from the bad-case evidence
and merges it into the target repository's config file. The agent-edit source
collects a structured EditPlan from the AI agent provider, applies it
deterministically against a scratch mirror of the target files, and turns the
changed bytes into a multi-file PatchBundle. Selection is factory driven: the
run's frozen ``eval_config["patchMode"]`` wins, otherwise the process-wide
``HE_PATCH_SOURCE_MODE`` fallback applies. New generation strategies only add a
subclass plus configuration — business code stays put.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol, cast, runtime_checkable

from app.db.models.evolution import EvolutionRunRecord
from app.service.evolution.ai_observability import AiAgentCall
from app.service.evolution.engine.contracts import ConfigError
from app.third_party_api.ai_agent.base import AIAgentProvider
from app.third_party_api.ai_agent.contracts import (
    EDIT_PLAN_FILENAME,
    AgentProviderError,
    EditRequest,
)
from app.third_party_api.ai_agent.edits import (
    EDIT_BUDGET,
    MAX_CONTENT_LINES,
    EditApplication,
    EditPlan,
    EditStatus,
    apply_edit_plan,
)
from app.third_party_api.git.workspace import Patch

PATCH_SOURCE_MODES = ("placeholder", "minimal-config", "agent-edit")
DEFAULT_PATCH_SOURCE_MODE = "placeholder"
AGENT_EDIT_TASK = "agent.edit"
"""Task key recorded on the agent-edit provider call."""
PLACEHOLDER_PATCH_NOTE = "V1 占位 patch；真实文件已写入 isolated workspace"
_CONFIG_FILENAME = "config/{}.json"
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_NAME_LENGTH = 64
_MAX_PROMPT_EVIDENCE_CHARS = 1_800
_MAX_EDIT_ERROR_CHARS = 4_000


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


class AgentEditPatchSource:
    """Collect an agent EditPlan and apply it deterministically on a scratch mirror.

    The provider explores the prepared workspace read-only and writes one
    ``edits.json5``; this source mirrors only the plan's target files into a
    throwaway directory, runs :func:`apply_edit_plan` there, and turns the
    changed bytes into full-file patches. Repository bytes are therefore never
    mutated before the candidate commit: an out-of-scope or failed edit cannot
    leak into the run branch, so no ``git checkout -- .`` rollback is needed.

    A plan that does not apply cleanly is a hard failure for this turn; it is
    never retried with a second model call.
    """

    def __init__(self, provider: AIAgentProvider) -> None:
        """Bind the AI agent backend."""
        self._provider = provider
        self._last_ai_call: AiAgentCall | None = None

    @property
    def last_ai_call(self) -> AiAgentCall | None:
        """Return the observability record of the most recent provider call.

        The candidate service reads this after ``build_bundle`` so a call whose
        plan later fails to apply is still recorded as one ``ai_agent_call``.
        The source is created per publish, and every build resets the field.
        """
        return self._last_ai_call

    async def build(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> Patch:
        """Return the single-file projection; multi-file plans must use the bundle."""
        bundle = await self.build_bundle(run, round_seq, trace)
        if len(bundle.files) != 1:
            raise ConfigError(
                "agent-edit produced multiple files; the candidate must use build_bundle()",
            )
        return bundle.files[0]

    async def change_note(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> str:
        """Reject the legacy note hook: the note is the plan summary."""
        del run, round_seq, trace
        raise ConfigError("agent-edit change notes come from the EditPlan summary")

    async def build_bundle(
        self,
        run: EvolutionRunRecord,
        round_seq: int,
        trace: object,
    ) -> PatchBundle:
        """Ask the agent for one plan, apply it on a mirror, and bundle the files."""
        del round_seq
        self._last_ai_call = None
        workspace = _agent_workspace(run)
        allowed = _allowed_paths(run.sub_dir)
        try:
            result = await self._provider.edit_workspace(
                EditRequest(
                    workspace=workspace,
                    prompt=_edit_prompt(run, trace, allowed=allowed),
                    allowed_paths=allowed,
                ),
            )
        except AgentProviderError as exc:
            # The provider call happened even though no plan came back; keep the
            # normalized error record so the failure is cost-attributable too.
            self._last_ai_call = AiAgentCall.failed(AGENT_EDIT_TASK, exc)
            raise
        self._last_ai_call = AiAgentCall.from_edit(AGENT_EDIT_TASK, result)
        plan = result.plan
        if plan is None:
            raise ConfigError("agent provider returned no EditPlan for the edit request")
        application, contents = _apply_on_scratch(workspace, plan, allowed=allowed)
        if not application.files:
            detail = _application_detail(application)
            raise ConfigError(f"agent edit produced no applicable change: {detail}")
        files = tuple(_patch_from_content(name, contents[name]) for name in application.files)
        return PatchBundle(
            files=files,
            note=plan.summary,
            intent=plan,
            report=application.report,
        )


def _agent_workspace(run: EvolutionRunRecord) -> Path:
    """Return the prepared workspace or fail before any provider call."""
    if run.workspace_path is None:
        raise ConfigError("agent-edit patch generation requires a prepared workspace")
    workspace = Path(run.workspace_path)
    if not workspace.is_dir():
        raise ConfigError("agent-edit workspace does not exist")
    return workspace


def _allowed_paths(sub_dir: str) -> tuple[str, ...]:
    """Return the applier glob that confines edits to the target sub-directory."""
    normalized = sub_dir.strip().strip("/")
    if not normalized or normalized == ".":
        return ("**",)
    return (f"{normalized}/**",)


def _apply_on_scratch(
    workspace: Path,
    plan: EditPlan,
    *,
    allowed: tuple[str, ...],
) -> tuple[EditApplication, dict[str, str]]:
    """Apply the plan to a mirrored file set and return the changed file text."""
    with tempfile.TemporaryDirectory(prefix="he-agent-edit-") as raw:
        scratch = Path(raw)
        _mirror_plan_files(workspace, scratch, plan)
        application = apply_edit_plan(plan, workspace=scratch, allowed_paths=allowed)
        contents = {
            name: _read_text(scratch.joinpath(*PurePosixPath(name).parts))
            for name in application.files
        }
    return application, contents


def _mirror_plan_files(workspace: Path, scratch: Path, plan: EditPlan) -> None:
    """Copy each plan target from the workspace into the scratch mirror."""
    root = workspace.resolve()
    for edit in plan.edits:
        relative = PurePosixPath(edit.file)
        source = workspace.joinpath(*relative.parts)
        try:
            resolved = source.resolve()
            resolved.relative_to(root)
        except (OSError, ValueError):
            continue
        try:
            if not resolved.is_file():
                continue
        except OSError:
            continue
        destination = scratch.joinpath(*relative.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(resolved, destination)


def _read_text(path: Path) -> str:
    """Read one UTF-8 file without newline translation."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        return handle.read()


def _patch_from_content(relative: str, text: str) -> Patch:
    """Turn one full file's text into an overwrite patch with stable lines."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return Patch(file=relative, lines=tuple(lines), overwrite=True)


def _edit_prompt(
    run: EvolutionRunRecord,
    trace: object,
    *,
    allowed: tuple[str, ...],
) -> str:
    """Build the bounded goal prompt for one edit session."""
    title = _bounded(str(getattr(trace, "cluster_title", "") or ""), 300) or "未命名问题簇"
    analysis = _bounded(str(getattr(trace, "analysis", "") or ""), _MAX_PROMPT_EVIDENCE_CHARS)
    evidence: list[str] = []
    for source in getattr(trace, "sources", ()) or ():
        description = _bounded(str(getattr(source, "description", "") or ""), 240)
        source_analysis = _bounded(str(getattr(source, "analysis", "") or ""), 360)
        line = description or source_analysis
        if line:
            evidence.append(f"- {line}")
    lines = [
        "你在受控工作区里为自进化候选生成编辑计划：先只读探索，再把结构化 EditPlan 写入 "
        f"{EDIT_PLAN_FILENAME}，不要直接编辑任何其他文件。",
        f"对象：{run.target_name}@{run.target_version}（{run.target_type}）",
        f"问题簇：{title}",
    ]
    if analysis:
        lines.extend(("## 归因分析", analysis))
    if evidence:
        lines.extend(("## 代表证据", "\n".join(evidence[:5])))
    lines.extend(
        (
            "## 修复要求",
            f"- file 必须落在允许范围 {list(allowed)!r} 内；"
            "锚文本必须是文件内唯一出现的文本片段，可跨行；"
            "insert_after 把 content 插到该片段末行之后。",
            f"- 最多 {EDIT_BUDGET} 条编辑，单条内容最多 {MAX_CONTENT_LINES} 行；"
            "优先最小、可回退的真实修复。",
            "- 提交格式：{summary, edits:[{op,file,target,content,rationale}]}。",
        ),
    )
    return "\n\n".join(lines)


def _application_detail(application: EditApplication) -> str:
    """Join the bounded non-applied statuses for an error message."""
    parts = [
        status.message or f"edits[{status.index}] {status.op} {status.file}"
        for status in application.skipped
    ]
    return _bounded("; ".join(parts), _MAX_EDIT_ERROR_CHARS) or "no edit applied"


def _bounded(text: str, limit: int) -> str:
    """Trim one prompt or diagnostic fragment to a character budget."""
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 1)].rstrip() + "…"


def default_patch_source_factory(
    run: EvolutionRunRecord,
    *,
    fallback_mode: str = DEFAULT_PATCH_SOURCE_MODE,
    provider: AIAgentProvider | None = None,
) -> PatchSource:
    """Resolve one patch source from the run snapshot with an env fallback."""
    configured = run.eval_config.get("patchMode")
    mode = configured if isinstance(configured, str) and configured else fallback_mode
    if mode == "placeholder":
        return PlaceholderPatchSource()
    if mode == "minimal-config":
        return MinimalConfigPatchSource()
    if mode == "agent-edit":
        if provider is None:
            raise ConfigError(
                "patch source mode 'agent-edit' requires a configured AI agent provider",
            )
        return AgentEditPatchSource(provider)
    raise ConfigError(f"unknown patch source mode: {mode}")


__all__ = [
    "DEFAULT_PATCH_SOURCE_MODE",
    "PATCH_SOURCE_MODES",
    "PLACEHOLDER_PATCH_NOTE",
    "AgentEditPatchSource",
    "MinimalConfigPatchSource",
    "PatchBundle",
    "PatchSource",
    "PlaceholderPatchSource",
    "build_default_bundle",
    "default_patch_source_factory",
]
