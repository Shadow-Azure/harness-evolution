"""Data-directory resolution and production path rules."""

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.config import Settings
from app.data_dir import probe_data_directory, resolve_data_directory


def test_resolve_data_directory_anchors_relative_paths_to_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A relative HE_DATA_DIR keeps resolving from the process cwd."""
    monkeypatch.chdir(tmp_path)

    assert resolve_data_directory(Path("data")) == tmp_path / "data"


def test_probe_creates_directory_and_cleans_up_probe_file(tmp_path: Path) -> None:
    """A writable data directory is created and the probe leaves no residue."""
    target = tmp_path / "nested" / "data"

    health = probe_data_directory(target)

    assert health.ok is True
    assert health.error is None
    assert health.path == target
    assert target.is_dir()
    assert list(target.glob(".write-probe-*")) == []


def test_probe_reports_unusable_directory(tmp_path: Path) -> None:
    """A path that cannot be a directory fails the probe with a stable error."""
    unusable = tmp_path / "data-file"
    unusable.write_text("not a directory", encoding="utf-8")

    health = probe_data_directory(unusable)

    assert health.ok is False
    assert health.path == unusable
    assert health.error is not None
    assert health.error.startswith("FileExistsError")


def test_production_rejects_relative_data_directory() -> None:
    """Production must not resolve the data directory from the release cwd."""
    with pytest.raises(ValidationError, match="HE_DATA_DIR must be an absolute path"):
        Settings(
            production=True,
            jwt_secret=SecretStr("test-signing-secret-with-sufficient-length"),
            data_dir=Path("data"),
        )


def test_production_accepts_absolute_data_directory(tmp_path: Path) -> None:
    """An absolute production data directory passes configuration validation."""
    settings = Settings(
        production=True,
        jwt_secret=SecretStr("test-signing-secret-with-sufficient-length"),
        data_dir=tmp_path,
    )

    assert settings.data_dir == tmp_path


def test_local_development_keeps_relative_default() -> None:
    """Local development continues to use ./data without production rules."""
    settings = Settings(jwt_secret=SecretStr("test-signing-secret-with-sufficient-length"))

    assert settings.data_dir == Path("data")
