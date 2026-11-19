"""Workspace attribution Skill package validation, storage, and selection."""

from __future__ import annotations

import asyncio
import hashlib
import io
import re
import shutil
import stat
import zipfile
import zlib
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from pathlib import Path, PurePosixPath

from pydantic import Field

from app.db.crud.attribution_skill_packages import (
    AttributionSkillPackageConflict,
    AttributionSkillPackageRecord,
    AttributionSkillPackageRepository,
)
from app.errors import AppError, ErrorCode
from app.service.identity.schemas import IdentityModel
from app.utils.ids import new_id
from app.utils.time import now_shanghai

DEFAULT_PACKAGE_ID = "default-attribute-badcases"
DEFAULT_SKILL_NAME = "attribute-badcases"
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024
MAX_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_FILE_COUNT = 200
MAX_PROMPT_BYTES = 512 * 1024
_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_FRONTMATTER_NAME = re.compile(r"(?m)^name\s*:\s*['\"]?([^'\"\s]+)['\"]?\s*$")


class AttributionSkillPackage(IdentityModel):
    """Package metadata rendered by workspace administration."""

    id: str
    skill_name: str
    uploader_name: str
    archive_name: str
    file_count: int = Field(ge=1)
    size_bytes: int = Field(ge=0)
    content_hash: str
    is_active: bool
    built_in: bool
    uploaded_at: datetime | None


class EffectiveAttributionSkillPackage(AttributionSkillPackage):
    """The effective package plus its exact SKILL.md prompt."""

    prompt: str


class AttributionSkillPackageList(IdentityModel):
    """All workspace packages and the currently effective prompt."""

    items: list[AttributionSkillPackage]
    effective: EffectiveAttributionSkillPackage


@dataclass(frozen=True, slots=True)
class _ValidatedArchive:
    """Validated files ready for extraction."""

    skill_name: str
    skill_md_path: str
    prompt: str
    files: tuple[tuple[str, bytes], ...]


class AttributionSkillPackageService:
    """Own safe ZIP assets without bypassing executable Skill quality gates."""

    def __init__(
        self,
        repository: AttributionSkillPackageRepository,
        package_root: Path,
        default_skill_path: Path,
    ) -> None:
        """Bind database metadata to one configured filesystem root."""
        self._repository = repository
        self._root = package_root.resolve()
        self._default_skill_path = default_skill_path.resolve()

    async def list(self, workspace_id: str) -> AttributionSkillPackageList:
        """List the immutable default and every custom package in one workspace."""
        records, active_id, default = await asyncio.gather(
            self._repository.list(workspace_id),
            self._repository.active_id(workspace_id),
            asyncio.to_thread(self._default),
        )
        if not any(record.id == active_id for record in records):
            active_id = None
        items = [self._public(default, active_id is None)]
        items.extend(self._public(record, record.id == active_id) for record in records)
        effective_record = next((record for record in records if record.id == active_id), default)
        effective = self._effective(effective_record, active_id)
        return AttributionSkillPackageList(items=items, effective=effective)

    async def upload(
        self,
        *,
        workspace_id: str,
        uploader_id: str,
        uploader_name: str,
        archive_name: str,
        archive: bytes,
    ) -> AttributionSkillPackage:
        """Validate and extract one ZIP, then persist its workspace metadata."""
        if len(archive) > MAX_ARCHIVE_BYTES:
            raise self._too_large("compressed archive exceeds 10 MiB")
        validated = await asyncio.to_thread(self._validate_archive, archive)
        package_id = new_id()
        relative_storage = str(PurePosixPath(workspace_id, package_id))
        storage = self._storage_path(relative_storage)
        await asyncio.to_thread(self._extract, storage, validated.files)
        record = AttributionSkillPackageRecord(
            id=package_id,
            workspace_id=workspace_id,
            skill_name=validated.skill_name,
            uploader_id=uploader_id,
            uploader_name=uploader_name,
            archive_name=self._safe_archive_name(archive_name, validated.skill_name),
            file_count=len(validated.files),
            size_bytes=len(archive),
            content_hash=hashlib.sha256(archive).hexdigest(),
            storage_path=relative_storage,
            skill_md_path=validated.skill_md_path,
            prompt_text=validated.prompt,
            created_at=now_shanghai(),
        )
        try:
            await self._repository.create(record)
        except AttributionSkillPackageConflict as exc:
            await asyncio.to_thread(shutil.rmtree, storage, True)
            raise AppError(
                status_code=HTTPStatus.CONFLICT,
                code=ErrorCode.ATTRIBUTION_SKILL_PACKAGE_EXISTS,
                message="an attribution Skill package with this name already exists",
                details={"skillName": validated.skill_name},
            ) from exc
        except Exception:
            await asyncio.to_thread(shutil.rmtree, storage, True)
            raise
        return self._public(record, False)

    async def activate(
        self,
        workspace_id: str,
        package_id: str,
        actor_id: str,
    ) -> EffectiveAttributionSkillPackage:
        """Select a custom package, or clear the binding for the built-in default."""
        if package_id == DEFAULT_PACKAGE_ID:
            await self._repository.activate(workspace_id, None, actor_id)
            return self._effective(await asyncio.to_thread(self._default), None)
        record = await self._required(workspace_id, package_id)
        await self._repository.activate(workspace_id, package_id, actor_id)
        return self._effective(record, package_id)

    async def download(self, workspace_id: str, package_id: str) -> tuple[str, bytes]:
        """Return a regenerated ZIP for the default or one workspace package."""
        if package_id == DEFAULT_PACKAGE_ID:
            default = await asyncio.to_thread(self._default)
            data = await asyncio.to_thread(self._default_zip, default.prompt_text)
            return f"{DEFAULT_SKILL_NAME}.zip", data
        record = await self._required(workspace_id, package_id)
        storage = self._storage_path(record.storage_path)
        data = await asyncio.to_thread(self._zip_directory, storage)
        return f"{record.skill_name}.zip", data

    async def delete(self, workspace_id: str, package_id: str) -> None:
        """Delete one custom package; an active deletion falls back to default."""
        if package_id == DEFAULT_PACKAGE_ID:
            raise AppError(
                status_code=HTTPStatus.CONFLICT,
                code=ErrorCode.ATTRIBUTION_SKILL_PACKAGE_INVALID,
                message="the built-in attribution Skill package cannot be deleted",
            )
        record = await self._repository.delete(workspace_id, package_id)
        if record is None:
            raise self._not_found()
        await asyncio.to_thread(shutil.rmtree, self._storage_path(record.storage_path), True)

    async def _required(
        self,
        workspace_id: str,
        package_id: str,
    ) -> AttributionSkillPackageRecord:
        record = await self._repository.get(workspace_id, package_id)
        if record is None:
            raise self._not_found()
        return record

    def _default(self) -> AttributionSkillPackageRecord:
        try:
            prompt = self._default_skill_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise RuntimeError("default attribution Skill is unavailable") from exc
        payload = prompt.encode()
        return AttributionSkillPackageRecord(
            id=DEFAULT_PACKAGE_ID,
            workspace_id="",
            skill_name=DEFAULT_SKILL_NAME,
            uploader_id=None,
            uploader_name="default",
            archive_name=f"{DEFAULT_SKILL_NAME}.zip",
            file_count=1,
            size_bytes=len(payload),
            content_hash=hashlib.sha256(payload).hexdigest(),
            storage_path="",
            skill_md_path=f"{DEFAULT_SKILL_NAME}/SKILL.md",
            prompt_text=prompt,
            created_at=now_shanghai(),
        )

    @staticmethod
    def _public(
        record: AttributionSkillPackageRecord,
        active: bool,
    ) -> AttributionSkillPackage:
        built_in = record.id == DEFAULT_PACKAGE_ID
        return AttributionSkillPackage(
            id=record.id,
            skill_name=record.skill_name,
            uploader_name=record.uploader_name,
            archive_name=record.archive_name,
            file_count=record.file_count,
            size_bytes=record.size_bytes,
            content_hash=record.content_hash,
            is_active=active,
            built_in=built_in,
            uploaded_at=None if built_in else record.created_at,
        )

    def _effective(
        self,
        record: AttributionSkillPackageRecord,
        active_id: str | None,
    ) -> EffectiveAttributionSkillPackage:
        return EffectiveAttributionSkillPackage(
            **self._public(record, record.id == active_id or active_id is None).model_dump(),
            prompt=record.prompt_text,
        )

    def _storage_path(self, relative: str) -> Path:
        candidate = (self._root / relative).resolve()
        if candidate == self._root or self._root not in candidate.parents:
            raise RuntimeError("invalid attribution Skill storage path")
        return candidate

    @classmethod
    def _validate_archive(cls, archive: bytes) -> _ValidatedArchive:
        try:
            source = zipfile.ZipFile(io.BytesIO(archive))
        except zipfile.BadZipFile as exc:
            raise cls._invalid("file is not a valid ZIP archive") from exc
        files: list[tuple[str, bytes]] = []
        seen_paths: set[str] = set()
        total = 0
        skill_paths: list[str] = []
        with source:
            for info in source.infolist():
                path = cls._safe_member(info)
                if info.is_dir():
                    continue
                key = path.casefold()
                if key in seen_paths:
                    raise cls._invalid("archive contains duplicate file paths")
                seen_paths.add(key)
                if len(files) >= MAX_FILE_COUNT:
                    raise cls._too_large("archive contains more than 200 files")
                total += info.file_size
                if total > MAX_EXPANDED_BYTES:
                    raise cls._too_large("expanded archive exceeds 20 MiB")
                is_prompt = PurePosixPath(path).name == "SKILL.md"
                if is_prompt and info.file_size > MAX_PROMPT_BYTES:
                    raise cls._too_large("SKILL.md exceeds 512 KiB")
                if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
                    raise cls._invalid("archive must use stored or deflate ZIP entries")
                try:
                    content = source.read(info)
                except (EOFError, RuntimeError, zipfile.BadZipFile, zlib.error) as exc:
                    raise cls._invalid("archive contains an unreadable file") from exc
                files.append((path, content))
                if is_prompt:
                    skill_paths.append(path)
        for path, _ in files:
            if any(
                parent.as_posix().casefold() in seen_paths for parent in PurePosixPath(path).parents
            ):
                raise cls._invalid("archive contains a file and directory at the same path")
        if not files:
            raise cls._invalid("archive does not contain files")
        if len(skill_paths) != 1:
            raise cls._invalid("archive must contain exactly one SKILL.md")
        skill_path = skill_paths[0]
        prompt_bytes = next(content for path, content in files if path == skill_path)
        try:
            prompt = prompt_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise cls._invalid("SKILL.md must be UTF-8") from exc
        frontmatter = re.match(r"\A\ufeff?---[ \t]*\r?\n(.*?)^---[ \t]*\r?$", prompt, re.M | re.S)
        match = _FRONTMATTER_NAME.search(frontmatter.group(1)) if frontmatter else None
        if match is None or not _SKILL_NAME.fullmatch(match.group(1)):
            raise cls._invalid("SKILL.md frontmatter must contain a valid name")
        return _ValidatedArchive(match.group(1), skill_path, prompt, tuple(files))

    @staticmethod
    def _safe_member(info: zipfile.ZipInfo) -> str:
        raw = info.orig_filename.replace("\\", "/")
        path = PurePosixPath(raw)
        mode = info.external_attr >> 16
        if (
            not path.parts
            or "\x00" in raw
            or raw.startswith("/")
            or len(raw) > 512
            or any(
                part == ".." or ":" in part or len(part.encode("utf-8")) > 255
                for part in path.parts
            )
            or stat.S_ISLNK(mode)
            or info.flag_bits & 0x1
        ):
            raise AttributionSkillPackageService._invalid(
                "archive contains an unsafe path, symlink, or encrypted file",
            )
        return str(path)

    @staticmethod
    def _extract(storage: Path, files: tuple[tuple[str, bytes], ...]) -> None:
        storage.mkdir(parents=True, exist_ok=False)
        try:
            for relative, content in files:
                destination = storage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as output:
                    output.write(content)
        except OSError:
            shutil.rmtree(storage, ignore_errors=True)
            raise

    @staticmethod
    def _zip_directory(storage: Path) -> bytes:
        if not storage.is_dir():
            raise RuntimeError("attribution Skill package files are unavailable")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(item for item in storage.rglob("*") if item.is_file()):
                archive.write(path, path.relative_to(storage).as_posix())
        return output.getvalue()

    @staticmethod
    def _default_zip(prompt: str) -> bytes:
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(f"{DEFAULT_SKILL_NAME}/SKILL.md", prompt)
        return output.getvalue()

    @staticmethod
    def _safe_archive_name(name: str, skill_name: str) -> str:
        candidate = Path(name).name
        if len(candidate) <= 255 and candidate.lower().endswith(".zip"):
            return candidate
        return f"{skill_name}.zip"

    @staticmethod
    def _not_found() -> AppError:
        return AppError(
            status_code=HTTPStatus.NOT_FOUND,
            code=ErrorCode.ATTRIBUTION_SKILL_PACKAGE_NOT_FOUND,
            message="attribution Skill package was not found",
        )

    @staticmethod
    def _invalid(message: str) -> AppError:
        return AppError(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            code=ErrorCode.ATTRIBUTION_SKILL_PACKAGE_INVALID,
            message=message,
        )

    @staticmethod
    def _too_large(message: str) -> AppError:
        return AppError(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            code=ErrorCode.ATTRIBUTION_SKILL_PACKAGE_TOO_LARGE,
            message=message,
        )
