"""Resolve and probe the server-side data directory."""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DataDirectoryHealth:
    """Outcome of the startup write probe for the data directory."""

    ok: bool
    path: Path
    error: str | None = None


def resolve_data_directory(configured: Path) -> Path:
    """Return ``configured`` as an absolute path resolved from the process cwd."""
    path = configured.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def probe_data_directory(configured: Path) -> DataDirectoryHealth:
    """Create the data directory and prove it is writable with a temporary file."""
    path = resolve_data_directory(configured)
    probe_path: str | None = None
    try:
        path.mkdir(parents=True, exist_ok=True)
        descriptor, probe_path = tempfile.mkstemp(dir=path, prefix=".write-probe-")
        os.close(descriptor)
        os.unlink(probe_path)
        probe_path = None
    except OSError as exc:
        detail = getattr(exc, "strerror", None) or str(exc)
        logger.error(
            "data directory is not writable",
            extra={
                "path": str(path),
                "error_type": type(exc).__name__,
                "error": detail,
            },
        )
        return DataDirectoryHealth(
            ok=False,
            path=path,
            error=f"{type(exc).__name__}: {detail}",
        )
    finally:
        if probe_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(probe_path)
    logger.info("data directory ready", extra={"path": str(path)})
    return DataDirectoryHealth(ok=True, path=path)
