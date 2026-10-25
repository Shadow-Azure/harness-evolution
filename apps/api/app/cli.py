"""Development-only data seeding commands."""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import ServicePhase, Settings
from app.db.base import Database
from app.db.factory import create_database
from app.db.migrate import upgrade_database
from app.fixture_corpus import FixtureCorpus, load_fixture_corpus
from app.fixtures_seed import (
    CorpusSeedResult,
    run_corpus_seed,
)
from app.fixtures_seed import (
    SeedEnvironmentError as SeedEnvironmentError,
)
from app.service.acquisition.local_sessions import (
    LocalSessionSourceError,
    assemble_local_sessions,
    import_local_sessions,
    normalize_local_sessions,
    verify_local_sessions,
)
from app.service.identity.service import IdentityService


class M1SeedManifest(BaseModel):
    """Strict manifest for the only data actions allowed in M1."""

    model_config = ConfigDict(extra="forbid")

    actions: tuple[Literal["identity-admin"], ...] = Field(min_length=1, max_length=1)
    scope: Literal["m1-shell"]
    version: Literal[1]


@dataclass(frozen=True, slots=True)
class SeedResult:
    """Stable output of one idempotent M1 seed invocation."""

    admin_user_id: str | None
    status: Literal["seeded", "noop"]


def load_seed_manifest(path: Path) -> M1SeedManifest:
    """Read and validate the closed M1 seed manifest schema."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return M1SeedManifest.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError(f"invalid seed manifest {path}: {exc}") from exc


def load_any_seed_manifest(path: Path) -> M1SeedManifest | FixtureCorpus:
    """Load either the compatibility M1 manifest or the M2 synthetic corpus."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid seed manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid seed manifest {path}: top level must be an object")
    if payload.get("scope") == "m1-shell":
        return load_seed_manifest(path)
    if payload.get("scope") == "m2-synthetic":
        return load_fixture_corpus(path)
    raise ValueError(f"invalid seed manifest {path}: unknown scope")


def _ensure_seed_environment(settings: Settings) -> None:
    """Reject production and live targets before opening the database."""
    if settings.production:
        raise SeedEnvironmentError("seed refuses a production target")
    if settings.phase is ServicePhase.LIVE:
        raise SeedEnvironmentError("seed refuses a live target")


async def _seed(
    settings: Settings,
    manifest: M1SeedManifest,
    database: Database,
) -> SeedResult:
    """Apply the validated manifest through existing storage boundaries."""
    await database.start()
    try:
        await upgrade_database(database)
        identity = IdentityService(settings, database)
        if "identity-admin" in manifest.actions:
            await identity.seed_admin_if_empty()
        username = settings.admin_username
        user = await identity.users.get_by_username(username.lower()) if username else None
        return SeedResult(
            admin_user_id=user.id if user else None,
            status="seeded" if user else "noop",
        )
    finally:
        await database.dispose()


async def run_seed(
    settings: Settings,
    manifest: M1SeedManifest,
) -> SeedResult:
    """Run one idempotent M1 seed against the configured database."""
    _ensure_seed_environment(settings)
    return await _seed(settings, manifest, create_database(settings))


async def run_any_seed(
    settings: Settings,
    manifest: M1SeedManifest | FixtureCorpus,
) -> SeedResult | CorpusSeedResult:
    """Apply one of the supported closed manifest formats."""
    if isinstance(manifest, FixtureCorpus):
        return await run_corpus_seed(settings, manifest)
    return await run_seed(settings, manifest)


def _parser() -> argparse.ArgumentParser:
    """Build the command-line parser without starting any service."""
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    subcommands = parser.add_subparsers(dest="command", required=True)
    seed = subcommands.add_parser("seed", help="seed development-only M1 state")
    seed.add_argument(
        "--manifest",
        default="../../fixtures/m2-synthetic/corpus.json",
        type=Path,
    )
    check = subcommands.add_parser(
        "fixtures-check",
        help="validate a fixture corpus without opening a database",
    )
    check.add_argument(
        "--corpus",
        default="../../fixtures/m2-synthetic/corpus.json",
        type=Path,
    )
    import_local = subcommands.add_parser(
        "import-local",
        help="import development-only Claude session JSONL payloads",
    )
    import_local.add_argument(
        "--sessions-dir",
        default="../../claude-code-sessions",
        type=Path,
    )
    verify_local = subcommands.add_parser(
        "verify-local",
        help="verify local session identities against the development database",
    )
    verify_local.add_argument(
        "--sessions-dir",
        default="../../claude-code-sessions",
        type=Path,
    )
    normalize_local = subcommands.add_parser(
        "normalize-local",
        help="parse local payloads and print aggregate-only statistics",
    )
    normalize_local.add_argument(
        "--sessions-dir",
        default="../../claude-code-sessions",
        type=Path,
    )
    tree_local = subcommands.add_parser(
        "tree-local",
        help="assemble local Agent trees and print aggregate-only statistics",
    )
    tree_local.add_argument(
        "--sessions-dir",
        default="../../claude-code-sessions",
        type=Path,
    )
    return parser


def _absolute_path_without_resolving_symlinks(path: Path) -> Path:
    """Make a path absolute while preserving its final symlink boundary."""
    return Path(os.path.abspath(path))


def main(argv: list[str] | None = None) -> int:
    """Execute a CLI command and return a process-compatible status."""
    args = _parser().parse_args(argv)
    try:
        if args.command == "fixtures-check":
            corpus = load_fixture_corpus(args.corpus.resolve())
            result = {
                "agents": len(corpus.agents),
                "bytes": corpus.total_bytes,
                "root_sessions": len(corpus.root_sessions),
                "status": "valid",
            }
        elif args.command == "seed":
            manifest = load_any_seed_manifest(args.manifest.resolve())
            result = asdict(asyncio.run(run_any_seed(Settings(), manifest)))
        elif args.command == "import-local":
            result = asdict(
                asyncio.run(
                    import_local_sessions(
                        Settings(),
                        _absolute_path_without_resolving_symlinks(args.sessions_dir),
                    ),
                ),
            )
        elif args.command == "verify-local":
            result = asdict(
                asyncio.run(
                    verify_local_sessions(
                        Settings(),
                        _absolute_path_without_resolving_symlinks(args.sessions_dir),
                    ),
                ),
            )
        elif args.command == "normalize-local":
            result = asdict(
                normalize_local_sessions(
                    Settings(),
                    _absolute_path_without_resolving_symlinks(args.sessions_dir),
                ),
            )
        elif args.command == "tree-local":
            result = asdict(
                assemble_local_sessions(
                    Settings(),
                    _absolute_path_without_resolving_symlinks(args.sessions_dir),
                ),
            )
        else:
            return 2
    except (
        LocalSessionSourceError,
        OSError,
        SeedEnvironmentError,
        ValueError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
