"""Workspace attribution Skill package API and ZIP safety contracts."""

from __future__ import annotations

import io
import shutil
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import IO, Any
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from pydantic import SecretStr

from app.config import DatabaseDialect, Settings
from app.db.crud.evolution_targets import EvolutionTargetRepository
from app.db.models.workspace import DEFAULT_WORKSPACE_ID
from app.errors import AppError
from app.main import create_app
from app.service.evolution import attribution_skill_packages as packages
from tests.workspaces.helpers import (
    access_token,
    bearer,
    create_user,
    insert_member,
    insert_workspace,
)

ADMIN_TEMP_PASSWORD = "skill-package-temporary-password"  # noqa: S105
ADMIN_PASSWORD = "skill-package-replacement-password"  # noqa: S105


def _zip(files: dict[str, str | bytes], *, method: int = zipfile.ZIP_DEFLATED) -> bytes:
    """Build a small in-memory ZIP fixture."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=method) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


async def _login(client: httpx.AsyncClient) -> None:
    """Complete the seeded administrator's required password change."""
    login = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_TEMP_PASSWORD},
    )
    changed = await client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
        json={"oldPassword": ADMIN_TEMP_PASSWORD, "newPassword": ADMIN_PASSWORD},
    )
    assert changed.status_code == 204
    relogin = await client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_PASSWORD},
    )
    client.headers["Authorization"] = f"Bearer {relogin.json()['accessToken']}"


@pytest_asyncio.fixture
async def package_client(
    tmp_path: Path,
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient, Path]]:
    """Provide a migrated app with isolated package and default-Skill paths."""
    default_path = tmp_path / "attribute-badcases.md"
    default_path.write_text("---\nname: attribute-badcases\n---\n# Default prompt\n")
    (tmp_path / "make_probe_report.py").write_text("# fixture writer\n")
    package_root = tmp_path / "attribute"
    settings = Settings(
        db_dialect=DatabaseDialect.SQLITE,
        data_dir=tmp_path,
        jwt_secret=SecretStr("skill-package-test-signing-secret-with-length"),
        admin_username="admin",
        admin_password=SecretStr(ADMIN_TEMP_PASSWORD),
        attribution_package_dir=package_root,
        attribution_default_skill_path=default_path,
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client,
    ):
        await _login(client)
        yield app, client, package_root


def _base() -> str:
    """Return the default workspace package API path."""
    return f"/api/workspaces/{DEFAULT_WORKSPACE_ID}/attribution-skill-packages"


@pytest.mark.asyncio
async def test_package_isolation_and_oversized_prompt(
    package_client: tuple[FastAPI, httpx.AsyncClient, Path],
) -> None:
    """Even global admins cannot address a package through a different workspace."""
    app, client, package_root = package_client
    other_id = await insert_workspace(app.state.database, name="other")
    other = f"/api/workspaces/{other_id}/attribution-skill-packages"
    prompt = "---\nname: isolated\n---\n"
    upload = await client.post(
        _base(),
        files={"file": ("skill.zip", _zip({"isolated/SKILL.md": prompt}))},
    )
    assert upload.status_code == 201, upload.text
    package_id = upload.json()["id"]

    assert len((await client.get(other)).json()["items"]) == 1
    assert (await client.get(f"{other}/{package_id}/download")).status_code == 404
    assert (await client.post(f"{other}/{package_id}/activate")).status_code == 404
    assert (await client.delete(f"{other}/{package_id}")).status_code == 404

    oversized = await client.post(
        other,
        files={"file": ("large.zip", _zip({"SKILL.md": prompt + "x" * (512 * 1024)}))},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "ATTRIBUTION_SKILL_PACKAGE_TOO_LARGE"
    assert not (package_root / other_id).exists()


@pytest.mark.asyncio
async def test_upload_inspect_download_and_delete_resource(
    package_client: tuple[FastAPI, httpx.AsyncClient, Path],
) -> None:
    """Inspect, download and remove a custom package alongside the built-in Skill."""
    _, client, package_root = package_client
    initial = await client.get(_base())
    assert initial.status_code == 200
    assert initial.json()["items"][0]["skillName"] == "attribute-badcases"
    assert initial.json()["runtimeEnabled"] is False
    assert initial.json()["items"][0]["uploaderName"] == "default"
    assert initial.json()["items"][0]["fileCount"] == 2
    default_zip = await client.get(f"{_base()}/default-attribute-badcases/download")
    with zipfile.ZipFile(io.BytesIO(default_zip.content)) as bundle:
        assert set(bundle.namelist()) == {
            "attribute-badcases/SKILL.md",
            "attribute-badcases/make_probe_report.py",
        }

    prompt = "---\nname: incident-attribution\n---\n# Custom prompt\n"
    uploaded = await client.post(
        _base(),
        files={
            "file": (
                "incident-attribution.zip",
                _zip({"incident-attribution/SKILL.md": prompt, "refs/check.md": "check"}),
                "application/zip",
            ),
        },
    )
    assert uploaded.status_code == 201, uploaded.text
    package_id = uploaded.json()["id"]
    assert uploaded.json()["fileCount"] == 2
    assert (
        package_root
        / DEFAULT_WORKSPACE_ID
        / "attribute_skill"
        / "uploads"
        / package_id
        / "refs/check.md"
    ).is_file()

    detail = await client.get(f"{_base()}/{package_id}")
    assert detail.status_code == 200
    assert detail.json() == {
        "prompt": prompt,
        "files": ["incident-attribution/SKILL.md", "refs/check.md"],
        "targets": [],
    }

    downloaded = await client.get(f"{_base()}/{package_id}/download")
    assert downloaded.status_code == 200
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
        assert archive.read("incident-attribution/SKILL.md").decode() == prompt

    deleted = await client.delete(f"{_base()}/{package_id}")
    assert deleted.status_code == 204
    assert not (
        package_root / DEFAULT_WORKSPACE_ID / "attribute_skill" / "uploads" / package_id
    ).exists()
    fallback = await client.get(_base())
    assert [item["skillName"] for item in fallback.json()["items"]] == ["attribute-badcases"]


@pytest.mark.asyncio
async def test_rejects_unsafe_or_ambiguous_archives(
    package_client: tuple[FastAPI, httpx.AsyncClient, Path],
) -> None:
    """Traversal and multiple SKILL.md files fail before filesystem writes."""
    _, client, package_root = package_client
    reserved = await client.post(
        _base(),
        files={"file": ("skill.zip", _zip({"SKILL.md": "---\nname: attribute-badcases\n---\n"}))},
    )
    assert reserved.status_code == 409
    assert reserved.json()["error"]["code"] == "ATTRIBUTION_SKILL_PACKAGE_EXISTS"
    assert not (package_root / DEFAULT_WORKSPACE_ID).exists()

    traversal = await client.post(
        _base(),
        files={
            "file": (
                "unsafe.zip",
                _zip(
                    {
                        "../escape.txt": "escape",
                        "safe/SKILL.md": "---\nname: safe-skill\n---\n",
                    },
                ),
                "application/zip",
            ),
        },
    )
    assert traversal.status_code == 422
    assert traversal.json()["error"]["code"] == "ATTRIBUTION_SKILL_PACKAGE_INVALID"
    assert not (package_root.parent / "escape.txt").exists()

    ambiguous = await client.post(
        _base(),
        files={
            "file": (
                "ambiguous.zip",
                _zip(
                    {
                        "one/SKILL.md": "---\nname: one\n---\n",
                        "two/SKILL.md": "---\nname: two\n---\n",
                    },
                ),
                "application/zip",
            ),
        },
    )
    assert ambiguous.status_code == 422
    assert ambiguous.json()["error"]["code"] == "ATTRIBUTION_SKILL_PACKAGE_INVALID"


@pytest.mark.asyncio
async def test_default_package_cannot_be_deleted(
    package_client: tuple[FastAPI, httpx.AsyncClient, Path],
) -> None:
    """The last-known-good default remains downloadable and undeletable."""
    _, client, _ = package_client
    response = await client.delete(f"{_base()}/default-attribute-badcases")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ATTRIBUTION_SKILL_PACKAGE_INVALID"


@pytest.mark.asyncio
async def test_viewer_can_read_and_download_but_cannot_mutate(
    package_client: tuple[FastAPI, httpx.AsyncClient, Path],
) -> None:
    """Package endpoints apply the workspace role matrix to every operation."""
    app, client, _ = package_client
    viewer_id = await create_user(app.state.database, username="skill-viewer")
    await insert_member(
        app.state.database,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id=viewer_id,
        role="viewer",
    )
    headers = bearer(access_token(app, user_id=viewer_id))

    listed = await client.get(_base(), headers=headers)
    assert listed.status_code == 200
    downloaded = await client.get(
        f"{_base()}/default-attribute-badcases/download",
        headers=headers,
    )
    assert downloaded.status_code == 200
    denied = await client.post(
        _base(),
        headers=headers,
        files={
            "file": (
                "viewer.zip",
                _zip({"viewer/SKILL.md": "---\nname: viewer-skill\n---\n"}),
                "application/zip",
            ),
        },
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"


@pytest.mark.asyncio
async def test_upload_rejects_incomplete_archives_before_allocating_package(
    package_client: tuple[FastAPI, httpx.AsyncClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Malformed input, naming collisions and size limits leave no asset or metadata."""
    _, client, root = package_client
    prompt = "---\nname: compact\n---\n"
    # Simulate transport damage to one otherwise valid stored entry.
    damaged = _zip({"SKILL.md": prompt}, method=zipfile.ZIP_STORED).replace(
        b"name: compact", b"name: corRupt"
    )
    monkeypatch.setattr(packages, "MAX_FILE_COUNT", 3)
    monkeypatch.setattr(packages, "MAX_EXPANDED_BYTES", 512)
    examples = [
        (b"incomplete archive", 422, "valid ZIP"),
        (damaged, 422, "unreadable"),
        (_zip({"compact/": b""}), 422, "does not contain files"),
        (_zip({"SKILL.md": b"\xff"}), 422, "UTF-8"),
        (_zip({"SKILL.md": "# missing name"}), 422, "frontmatter"),
        (_zip({"SKILL.md": prompt}, method=zipfile.ZIP_BZIP2), 422, "stored or deflate"),
        (_zip({"SKILL.md": prompt, "Refs.txt": "A", "refs.txt": "B"}), 422, "duplicate"),
        (_zip({"SKILL.md": prompt, "refs": "one", "refs/notes": "two"}), 422, "directory"),
        (_zip({"SKILL.md": prompt, "a": "", "b": "", "c": ""}), 413, "files"),
        (_zip({"SKILL.md": prompt, "manual.txt": "a" * 512}), 413, "expanded"),
    ]
    for archive, status, reason in examples:
        response = await client.post(_base(), files={"file": ("source.zip", archive)})
        assert response.status_code == status, reason
        assert reason in response.json()["error"]["message"]

    monkeypatch.setattr(packages, "MAX_ARCHIVE_BYTES", 16)
    oversized = await client.post(_base(), files={"file": ("big.zip", _zip({"SKILL.md": prompt}))})
    assert oversized.status_code == 413
    assert "compressed" in oversized.json()["error"]["message"]
    assert not (root / DEFAULT_WORKSPACE_ID).exists()
    assert len((await client.get(_base())).json()["items"]) == 1


@pytest.mark.asyncio
async def test_duplicate_uploads_and_partial_writes_clean_up_only_the_new_asset(
    package_client: tuple[FastAPI, httpx.AsyncClient, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, client, root = package_client
    prompt = "---\nname: repeatable\n---\n"
    archive = _zip({"SKILL.md": prompt, "reference.md": "original"})
    endpoint = _base()
    first = await client.post(endpoint, files={"file": ("original", archive)})
    assert first.status_code == 201
    assert first.json()["archiveName"] == "repeatable.zip"
    package_id = first.json()["id"]
    other = await insert_workspace(app.state.database, name="independent")
    there = await client.post(
        f"/api/workspaces/{other}/attribution-skill-packages", files={"file": ("same.zip", archive)}
    )
    assert there.status_code == 201
    assert there.json()["id"] != package_id
    duplicate = await client.post(endpoint, files={"file": ("retry.zip", archive)})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"]["skillName"] == "repeatable"

    service = app.state.attribution_skill_packages
    uploads = root / DEFAULT_WORKSPACE_ID / "attribute_skill" / "uploads"
    assert {p.name for p in uploads.iterdir()} == {package_id}
    original_open = Path.open

    def out_of_space(path: Path, mode: str = "r", *args: Any, **kwargs: Any) -> IO[Any]:
        if mode == "xb" and path.name == "reference.md":
            raise OSError("volume full")
        return original_open(path, mode, *args, **kwargs)

    kwargs = dict(
        workspace_id=DEFAULT_WORKSPACE_ID,
        uploader_id="admin",
        uploader_name="test",
        archive_name="new.zip",
        archive=archive,
    )
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", out_of_space)
        with pytest.raises(OSError, match="volume full"):
            await service.upload(**kwargs)
    assert {p.name for p in uploads.iterdir()} == {package_id}
    with monkeypatch.context() as patch:
        patch.setattr(
            service._repository, "create", AsyncMock(side_effect=RuntimeError("db offline"))
        )
        with pytest.raises(RuntimeError, match="db offline"):
            await service.upload(**kwargs)
    assert {p.name for p in uploads.iterdir()} == {package_id}
    assert (await client.get(f"{endpoint}/{package_id}")).json()["prompt"] == prompt


@pytest.mark.asyncio
async def test_runtime_reads_verified_layout_and_platform_writer_after_upload(
    package_client: tuple[FastAPI, httpx.AsyncClient, Path],
) -> None:
    app, client, root = package_client
    service = app.state.attribution_skill_packages
    prompt = "---\nname: portable\n---\n"
    archive = _zip(
        {
            "portable/": b"",
            "portable/SKILL.md": prompt,
            "portable/make_probe_report.py": "custom unused writer",
            "portable/refs/guide.md": "guide",
            "notes.txt": "loose resource",
        }
    )
    result = await client.post(_base(), files={"file": ("portable.zip", archive)})
    assert result.status_code == 201
    pk = result.json()["id"]
    name, files = await service.runtime_files(DEFAULT_WORKSPACE_ID, pk)
    assert name == "portable"
    assert files == {
        "SKILL.md": prompt.encode(),
        "make_probe_report.py": b"# fixture writer\n",
        "refs/guide.md": b"guide",
        "notes.txt": b"loose resource",
    }

    # An older package can acquire a conflicting loose resource when restored from disk.
    storage = root / DEFAULT_WORKSPACE_ID / "attribute_skill" / "uploads" / pk
    (storage / "refs").mkdir()
    (storage / "refs" / "guide.md").write_text("different")
    with pytest.raises(AppError, match="ambiguous runtime file path"):
        await service.runtime_files(DEFAULT_WORKSPACE_ID, pk)
    shutil.rmtree(storage)
    with pytest.raises(RuntimeError, match="files are unavailable"):
        await service.download(DEFAULT_WORKSPACE_ID, pk)
    assert (await client.delete(f"{_base()}/{pk}")).status_code == 204
    assert (await client.get(f"{_base()}/{pk}")).status_code == 404


@pytest.mark.asyncio
async def test_disabled_targets_protect_their_package_until_reassigned(
    package_client: tuple[FastAPI, httpx.AsyncClient, Path],
) -> None:
    app, client, _ = package_client
    database = app.state.database
    owner = DEFAULT_WORKSPACE_ID
    other = await insert_workspace(database, name="second-owner")
    prompt = "---\nname: review-guide\n---\n"
    upload = await client.post(_base(), files={"file": ("guide.zip", _zip({"SKILL.md": prompt}))})
    assert upload.status_code == 201
    package_id = upload.json()["id"]
    targets = EvolutionTargetRepository(database)
    target = await targets.insert(
        dict(
            workspace_id=owner,
            object_type="skill",
            object_name="parked",
            repo_url="https://example.test/skill.git",
            sub_dir="skill",
            default_ref="main",
            validation_project_id="validation",
            test_project_id="test",
            enabled=False,
            attribution_package_id=package_id,
        )
    )
    detail = f"{_base()}/{package_id}"
    assert (await client.get(detail)).json()["targets"] == ["parked"]
    assert (await client.delete(detail)).status_code == 409
    with pytest.raises(AppError) as foreign:
        await targets.bind_package(other, target.id, package_id)
    assert foreign.value.status_code == 404
    with pytest.raises(AppError) as absent:
        await targets.bind_package(owner, target.id, "missing-resource")
    assert absent.value.status_code == 422
    assert (await client.get(detail)).json()["targets"] == ["parked"]
    await targets.bind_package(owner, target.id, packages.DEFAULT_PACKAGE_ID)
    rebound = await targets.get(target.id)
    assert rebound is not None and rebound.attribution_generation != target.attribution_generation
    assert not rebound.attribution_will_retry
    await targets.bind_package(owner, target.id, packages.DEFAULT_PACKAGE_ID)
    assert (await targets.get(target.id)) == rebound
    assert (await client.get(detail)).json()["targets"] == []
    assert (await client.delete(detail)).status_code == 204
    assert (await client.get(f"{_base()}/{packages.DEFAULT_PACKAGE_ID}")).json()["targets"] == [
        "parked"
    ]
