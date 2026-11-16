"""Evolve attribution links, probe cache metadata, and run candidate snapshots.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-17
"""

from __future__ import annotations

import hashlib
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CHAR, inspect

from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | None = None
depends_on: str | None = None

DEFAULT_WORKSPACE_ID = "ws-default"
DEFAULT_CONCLUSION = "attributed"
DEFAULT_CONFIDENCE = 0.8
DEFAULT_POLICY_VERSION = "v1"
DEFAULT_ATTRIBUTION_ENGINE = "legacy-probe-import"

PROBE_ADDED_COLUMNS: tuple[sa.Column[Any], ...] = (
    sa.Column(
        "workspace_id",
        sa.String(length=36),
        nullable=False,
        server_default=DEFAULT_WORKSPACE_ID,
    ),
    sa.Column(
        "conclusion",
        sa.String(length=16),
        nullable=False,
        server_default=DEFAULT_CONCLUSION,
    ),
    sa.Column(
        "confidence",
        sa.Float(),
        nullable=False,
        server_default=sa.text("0.8"),
    ),
    sa.Column(
        "policy_version",
        sa.String(length=16),
        nullable=False,
        server_default=DEFAULT_POLICY_VERSION,
    ),
    sa.Column(
        "attribution_engine",
        sa.String(length=64),
        nullable=False,
        server_default=DEFAULT_ATTRIBUTION_ENGINE,
    ),
    sa.Column("cache_key", CHAR(length=64), nullable=True),
    sa.Column("created_run_id", sa.String(length=36), nullable=True),
    sa.Column("last_reused_run_id", sa.String(length=36), nullable=True),
    sa.Column(
        "reused_count",
        sa.Integer(),
        nullable=False,
        server_default="0",
    ),
)

PROBE_INDEXES: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    ("ix_probe_reports_workspace_object", ("workspace_id", "object_version"), False),
    ("ix_probe_reports_workspace_updated", ("workspace_id", "updated_at"), False),
    ("ix_probe_reports_conclusion", ("conclusion",), False),
    ("uq_probe_reports_cache_key", ("cache_key",), True),
)

PROBE_FOREIGN_KEYS: tuple[tuple[str, str, str, str], ...] = (
    (
        "fk_probe_reports_workspace",
        "workspace_id",
        "workspaces",
        "CASCADE",
    ),
    (
        "fk_probe_reports_created_run",
        "created_run_id",
        "evolution_runs",
        "SET NULL",
    ),
    (
        "fk_probe_reports_last_reused_run",
        "last_reused_run_id",
        "evolution_runs",
        "SET NULL",
    ),
)

CANDIDATE_INDEXES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("ix_evolution_run_candidates_run_included", ("run_id", "included")),
    ("ix_evolution_run_candidates_case", ("bad_case_id",)),
    ("ix_evolution_run_candidates_probe", ("probe_id",)),
    ("ix_evolution_run_candidates_session", ("session_id",)),
)


def _has_table(name: str) -> bool:
    """Return whether the current database contains one table."""
    return inspect(op.get_bind()).has_table(name)


def _existing_columns(table: str) -> dict[str, Any]:
    """Return the reflected columns on one table keyed by column name."""
    return {str(column["name"]): column for column in inspect(op.get_bind()).get_columns(table)}


def _existing_indexes(table: str) -> set[str]:
    """Return the reflected index names on one table."""
    return {
        str(index["name"])
        for index in inspect(op.get_bind()).get_indexes(table)
        if index.get("name") is not None
    }


def _existing_uniques(table: str) -> set[str]:
    """Return the named unique constraints on one table."""
    return {
        str(constraint["name"])
        for constraint in inspect(op.get_bind()).get_unique_constraints(table)
        if constraint.get("name") is not None
    }


def _existing_foreign_keys(table: str) -> set[str]:
    """Return the named foreign keys on one table."""
    return {
        str(foreign_key["name"])
        for foreign_key in inspect(op.get_bind()).get_foreign_keys(table)
        if foreign_key.get("name") is not None
    }


def _add_columns(table: str, columns: tuple[sa.Column[Any], ...]) -> None:
    """Add missing columns and reject an existing column with wrong nullability."""
    existing = _existing_columns(table)
    for column in columns:
        current = existing.get(str(column.name))
        if current is None:
            op.add_column(table, column)
            continue
        if bool(current["nullable"]) != bool(column.nullable):
            raise RuntimeError(
                f"{table}.{column.name} already exists with "
                f"nullable={bool(current['nullable'])}, expected "
                f"nullable={bool(column.nullable)}; repair the column before retrying 0020",
            )


def _create_indexes(
    table: str,
    indexes: tuple[tuple[str, tuple[str, ...], bool], ...],
) -> None:
    """Create the indexes that are still missing."""
    existing = _existing_indexes(table)
    for name, columns, unique in indexes:
        if name in existing:
            continue
        op.create_index(name, table, list(columns), unique=unique)


def _drop_indexes(table: str, names: tuple[str, ...]) -> None:
    """Drop the indexes that are still present."""
    existing = _existing_indexes(table)
    for name in names:
        if name in existing:
            op.drop_index(name, table_name=table)


def _create_foreign_keys(
    table: str,
    foreign_keys: tuple[tuple[str, str, str, str], ...],
) -> None:
    """Add missing foreign keys, recreating SQLite tables when required."""
    existing = _existing_foreign_keys(table)
    missing = [spec for spec in foreign_keys if spec[0] not in existing]
    if not missing or not _has_table(table):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch_op:
            for name, column, referred_table, ondelete in missing:
                if not _has_table(referred_table):
                    continue
                batch_op.create_foreign_key(
                    name,
                    referred_table,
                    [column],
                    ["id"],
                    ondelete=ondelete,
                )
        return
    for name, column, referred_table, ondelete in missing:
        if not _has_table(referred_table):
            continue
        op.create_foreign_key(
            name,
            table,
            referred_table,
            [column],
            ["id"],
            ondelete=ondelete,
        )


def _drop_foreign_keys(table: str, names: tuple[str, ...]) -> None:
    """Drop the named foreign keys that are still present."""
    existing = _existing_foreign_keys(table)
    if op.get_bind().dialect.name != "sqlite":
        for name in names:
            if name in existing:
                op.drop_constraint(name, table, type_="foreignkey")


def _make_attribute_type_nullable() -> None:
    """Allow V2 non-target probes to carry no attribute classification."""
    column = _existing_columns("probe_reports").get("attribute_type")
    if column is None or bool(column["nullable"]):
        return
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("probe_reports") as batch_op:
            batch_op.alter_column(
                "attribute_type",
                existing_type=sa.String(length=16),
                nullable=True,
            )
        return
    op.alter_column(
        "probe_reports",
        "attribute_type",
        existing_type=sa.String(length=16),
        nullable=True,
    )


def _cache_key(
    workspace_id: str,
    bad_case_id: str,
    probe_type: str,
    probe_object: str,
    object_version: str | None,
    policy_version: str,
    attribution_engine: str,
) -> str:
    """Rebuild the seven-part cache key with the same formula as the repository."""
    parts = (
        workspace_id,
        bad_case_id,
        probe_type,
        probe_object,
        object_version or "",
        policy_version,
        attribution_engine,
    )
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()


def _backfill_workspace() -> None:
    """Give linked probes their case workspace; orphans keep the default."""
    if (
        not _has_table("probe_reports")
        or not _has_table("bad_case_analysis")
        or not _has_table("bad_cases")
    ):
        return
    op.execute(
        sa.text(
            "UPDATE probe_reports SET workspace_id = COALESCE(("
            "SELECT bad_cases.workspace_id FROM bad_case_analysis "
            "JOIN bad_cases ON bad_cases.bad_case_id = bad_case_analysis.bad_case_id "
            "WHERE bad_case_analysis.probe_id = probe_reports.probe_id "
            "AND bad_cases.workspace_id IS NOT NULL "
            "ORDER BY bad_case_analysis.updated_at DESC, bad_case_analysis.id DESC "
            "LIMIT 1), :default_workspace) "
            "WHERE workspace_id IS NULL OR workspace_id = :default_workspace",
        ).bindparams(default_workspace=DEFAULT_WORKSPACE_ID),
    )


def _backfill_conclusion() -> None:
    """Map the latest legacy analysis status onto the probe conclusion."""
    if not _has_table("probe_reports") or not _has_table("bad_case_analysis"):
        return
    op.execute(
        sa.text(
            "UPDATE probe_reports SET conclusion = CASE ("
            "SELECT analysis_status FROM bad_case_analysis "
            "WHERE bad_case_analysis.probe_id = probe_reports.probe_id "
            "ORDER BY bad_case_analysis.updated_at DESC, bad_case_analysis.id DESC "
            "LIMIT 1) WHEN 'analyzed_nonissue' THEN 'non_target' ELSE 'attributed' END "
            "WHERE conclusion = :default_conclusion AND EXISTS ("
            "SELECT 1 FROM bad_case_analysis "
            "WHERE bad_case_analysis.probe_id = probe_reports.probe_id)",
        ).bindparams(default_conclusion=DEFAULT_CONCLUSION),
    )


def _backfill_attribute_type() -> None:
    """Collapse the V1 nonissue marker and empty strings into NULL."""
    if not _has_table("probe_reports"):
        return
    op.execute(
        sa.text(
            "UPDATE probe_reports SET attribute_type = NULL "
            "WHERE attribute_type IN ('nonissue', '')",
        ),
    )


def _backfill_cache_keys() -> None:
    """Recompute cache keys for linked legacy probes; orphan probes stay NULL."""
    if not _has_table("probe_reports") or not _has_table("bad_case_analysis"):
        return
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                "SELECT probe_reports.probe_id, probe_reports.workspace_id, "
                "probe_reports.probe_type, probe_reports.probe_object, "
                "probe_reports.object_version, probe_reports.policy_version, "
                "probe_reports.attribution_engine, "
                "(SELECT bad_case_analysis.bad_case_id FROM bad_case_analysis "
                "WHERE bad_case_analysis.probe_id = probe_reports.probe_id "
                "ORDER BY bad_case_analysis.updated_at DESC, bad_case_analysis.id DESC "
                "LIMIT 1) AS bad_case_id "
                "FROM probe_reports WHERE probe_reports.cache_key IS NULL",
            ),
        )
        .mappings()
        .all()
    )
    seen: set[str] = set()
    for row in rows:
        bad_case_id = row["bad_case_id"]
        if bad_case_id is None:
            continue
        workspace_id = row["workspace_id"] or DEFAULT_WORKSPACE_ID
        cache_key = _cache_key(
            str(workspace_id),
            str(bad_case_id),
            str(row["probe_type"]),
            str(row["probe_object"]),
            row["object_version"],
            str(row["policy_version"]),
            str(row["attribution_engine"]),
        )
        if cache_key in seen:
            continue
        seen.add(cache_key)
        bind.execute(
            sa.text(
                "UPDATE probe_reports SET cache_key = :cache_key "
                "WHERE probe_id = :probe_id AND cache_key IS NULL",
            ),
            {"cache_key": cache_key, "probe_id": row["probe_id"]},
        )


def _normalize_reused_count() -> None:
    """Default the reuse counter on tables that were only partially migrated."""
    if not _has_table("probe_reports"):
        return
    op.execute(
        sa.text("UPDATE probe_reports SET reused_count = 0 WHERE reused_count IS NULL"),
    )


def _create_candidates() -> None:
    """Create the run candidate snapshot table when it is still missing."""
    if _has_table("evolution_run_candidates"):
        _create_indexes(
            "evolution_run_candidates",
            tuple((name, columns, False) for name, columns in CANDIDATE_INDEXES),
        )
        return
    foreign_keys: list[sa.ForeignKeyConstraint] = [
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["evolution_runs.id"],
            name="fk_evolution_run_candidates_run",
            ondelete="CASCADE",
        ),
    ]
    if _has_table("workspaces"):
        foreign_keys.append(
            sa.ForeignKeyConstraint(
                ["workspace_id"],
                ["workspaces.id"],
                name="fk_evolution_run_candidates_workspace",
                ondelete="CASCADE",
            ),
        )
    if _has_table("bad_cases"):
        foreign_keys.append(
            sa.ForeignKeyConstraint(
                ["bad_case_id"],
                ["bad_cases.bad_case_id"],
                name="fk_evolution_run_candidates_case",
                ondelete="CASCADE",
            ),
        )
    if _has_table("probe_reports"):
        foreign_keys.append(
            sa.ForeignKeyConstraint(
                ["probe_id"],
                ["probe_reports.probe_id"],
                name="fk_evolution_run_candidates_probe",
                ondelete="SET NULL",
            ),
        )
    op.create_table(
        "evolution_run_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("bad_case_id", sa.String(length=64), nullable=False),
        sa.Column("object_trigger_agent_id", sa.String(length=64), nullable=True),
        sa.Column("object_trigger_event_index", sa.Integer(), nullable=True),
        sa.Column("object_trigger_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("case_trigger_agent_id", sa.String(length=64), nullable=True),
        sa.Column("case_trigger_event_index", sa.Integer(), nullable=True),
        sa.Column("case_trigger_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_state", sa.String(length=16), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False),
        sa.Column("included_reason", sa.String(length=16), nullable=False),
        sa.Column("probe_id", sa.String(length=64), nullable=True),
        sa.Column(
            "is_cached",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        *foreign_keys,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "bad_case_id",
            name="uq_evolution_run_candidates_run_case",
        ),
    )
    for name, columns in CANDIDATE_INDEXES:
        op.create_index(name, "evolution_run_candidates", list(columns))


def _evolve_bad_case_analysis() -> None:
    """Replace the per-case unique rule with the per-link unique rule."""
    if not _has_table("bad_case_analysis"):
        return
    uniques = _existing_uniques("bad_case_analysis")
    column = _existing_columns("bad_case_analysis")["analysis_status"]
    drop_legacy = "uq_bad_case_analysis_case" in uniques
    add_link = "uq_bad_case_analysis_case_probe" not in uniques
    relax_status = not bool(column["nullable"])
    if op.get_bind().dialect.name == "sqlite":
        if drop_legacy or add_link or relax_status:
            with op.batch_alter_table("bad_case_analysis") as batch_op:
                if drop_legacy:
                    batch_op.drop_constraint(
                        "uq_bad_case_analysis_case",
                        type_="unique",
                    )
                if relax_status:
                    batch_op.alter_column(
                        "analysis_status",
                        existing_type=sa.String(length=32),
                        nullable=True,
                    )
                if add_link:
                    batch_op.create_unique_constraint(
                        "uq_bad_case_analysis_case_probe",
                        ["bad_case_id", "probe_id"],
                    )
    else:
        if drop_legacy:
            op.drop_constraint(
                "uq_bad_case_analysis_case",
                "bad_case_analysis",
                type_="unique",
            )
        if add_link:
            op.create_unique_constraint(
                "uq_bad_case_analysis_case_probe",
                "bad_case_analysis",
                ["bad_case_id", "probe_id"],
            )
        if relax_status:
            op.alter_column(
                "bad_case_analysis",
                "analysis_status",
                existing_type=sa.String(length=32),
                nullable=True,
            )
    _create_indexes(
        "bad_case_analysis",
        (("ix_bad_case_analysis_case_updated", ("bad_case_id", "updated_at"), False),),
    )


def upgrade() -> None:
    """Evolve attribution tables in place and add run candidate snapshots.

    The problem-side tables are owned outside this service and may be absent
    when the runtime upgrades an internal-only deployment, so every step is
    guarded by table presence. Each column/index is added only when missing to
    let a retry after a partially applied MySQL DDL attempt resume.
    """
    if _has_table("probe_reports"):
        _add_columns("probe_reports", PROBE_ADDED_COLUMNS)
        _make_attribute_type_nullable()
        _create_indexes("probe_reports", PROBE_INDEXES)
        _create_foreign_keys("probe_reports", PROBE_FOREIGN_KEYS)
        _normalize_reused_count()
    _evolve_bad_case_analysis()
    _backfill_workspace()
    _backfill_conclusion()
    _backfill_attribute_type()
    _backfill_cache_keys()
    _create_candidates()


def _restore_attribute_type_not_null() -> None:
    """Restore the V1 non-null attribute classification before dropping columns."""
    if not _has_table("probe_reports"):
        return
    column = _existing_columns("probe_reports").get("attribute_type")
    if column is None:
        return
    if bool(column["nullable"]):
        op.execute(
            sa.text(
                "UPDATE probe_reports SET attribute_type = 'nonissue' WHERE attribute_type IS NULL",
            ),
        )
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table("probe_reports") as batch_op:
                batch_op.alter_column(
                    "attribute_type",
                    existing_type=sa.String(length=16),
                    nullable=False,
                )
            return
        op.alter_column(
            "probe_reports",
            "attribute_type",
            existing_type=sa.String(length=16),
            nullable=False,
        )


def _restore_analysis_status_not_null() -> None:
    """Map V2-only links back onto the legacy status vocabulary."""
    if not _has_table("bad_case_analysis"):
        return
    column = _existing_columns("bad_case_analysis").get("analysis_status")
    if column is None:
        return
    if bool(column["nullable"]):
        if _has_table("probe_reports"):
            op.execute(
                sa.text(
                    "UPDATE bad_case_analysis SET analysis_status = COALESCE(("
                    "SELECT CASE WHEN probe_reports.conclusion = 'non_target' "
                    "THEN 'analyzed_nonissue' ELSE 'analyzed_issue' END "
                    "FROM probe_reports "
                    "WHERE probe_reports.probe_id = bad_case_analysis.probe_id), "
                    "'analyzed_issue') "
                    "WHERE analysis_status IS NULL",
                ),
            )
        else:
            op.execute(
                sa.text(
                    "UPDATE bad_case_analysis SET analysis_status = 'analyzed_issue' "
                    "WHERE analysis_status IS NULL",
                ),
            )


def _dedupe_analysis_links() -> None:
    """Keep only the newest attribution per case before restoring the V1 rule."""
    if not _has_table("bad_case_analysis"):
        return
    bind = op.get_bind()
    rows = (
        bind.execute(
            sa.text(
                "SELECT id, bad_case_id FROM bad_case_analysis "
                "ORDER BY bad_case_id, updated_at DESC, id DESC",
            ),
        )
        .mappings()
        .all()
    )
    keep: dict[str, int] = {}
    for row in rows:
        keep.setdefault(str(row["bad_case_id"]), int(row["id"]))
    keep_ids = set(keep.values())
    delete_ids = [int(row["id"]) for row in rows if int(row["id"]) not in keep_ids]
    statement = sa.text("DELETE FROM bad_case_analysis WHERE id IN :ids").bindparams(
        sa.bindparam("ids", expanding=True),
    )
    for chunk_start in range(0, len(delete_ids), 500):
        chunk = delete_ids[chunk_start : chunk_start + 500]
        bind.execute(statement, {"ids": chunk})


def _restore_bad_case_analysis() -> None:
    """Restore the V1 unique rule and non-null analysis status."""
    if not _has_table("bad_case_analysis"):
        return
    _restore_analysis_status_not_null()
    _dedupe_analysis_links()
    _drop_indexes(
        "bad_case_analysis",
        ("ix_bad_case_analysis_case_updated",),
    )
    uniques = _existing_uniques("bad_case_analysis")
    drop_link = "uq_bad_case_analysis_case_probe" in uniques
    add_legacy = "uq_bad_case_analysis_case" not in uniques
    column = _existing_columns("bad_case_analysis")["analysis_status"]
    tighten_status = bool(column["nullable"])
    if op.get_bind().dialect.name == "sqlite":
        if drop_link or add_legacy or tighten_status:
            with op.batch_alter_table("bad_case_analysis") as batch_op:
                if drop_link:
                    batch_op.drop_constraint(
                        "uq_bad_case_analysis_case_probe",
                        type_="unique",
                    )
                if tighten_status:
                    batch_op.alter_column(
                        "analysis_status",
                        existing_type=sa.String(length=32),
                        nullable=False,
                    )
                if add_legacy:
                    batch_op.create_unique_constraint(
                        "uq_bad_case_analysis_case",
                        ["bad_case_id"],
                    )
    else:
        if drop_link:
            op.drop_constraint(
                "uq_bad_case_analysis_case_probe",
                "bad_case_analysis",
                type_="unique",
            )
        if tighten_status:
            op.alter_column(
                "bad_case_analysis",
                "analysis_status",
                existing_type=sa.String(length=32),
                nullable=False,
            )
        if add_legacy:
            op.create_unique_constraint(
                "uq_bad_case_analysis_case",
                "bad_case_analysis",
                ["bad_case_id"],
            )


def _drop_probe_columns() -> None:
    """Drop every column this revision added to probe reports."""
    if not _has_table("probe_reports"):
        return
    _restore_attribute_type_not_null()
    _drop_foreign_keys(
        "probe_reports",
        (
            "fk_probe_reports_workspace",
            "fk_probe_reports_created_run",
            "fk_probe_reports_last_reused_run",
        ),
    )
    _drop_indexes(
        "probe_reports",
        (
            "uq_probe_reports_cache_key",
            "ix_probe_reports_workspace_object",
            "ix_probe_reports_workspace_updated",
            "ix_probe_reports_conclusion",
        ),
    )
    existing = _existing_columns("probe_reports")
    present = tuple(column.name for column in PROBE_ADDED_COLUMNS if str(column.name) in existing)
    if not present:
        return
    if op.get_bind().dialect.name == "sqlite":
        foreign_keys = _existing_foreign_keys("probe_reports")
        with op.batch_alter_table("probe_reports") as batch_op:
            for name, *_rest in PROBE_FOREIGN_KEYS:
                if name in foreign_keys:
                    batch_op.drop_constraint(name, type_="foreignkey")
            for name in present:
                batch_op.drop_column(name)
        return
    for name in present:
        op.drop_column("probe_reports", name)


def downgrade() -> None:
    """Remove candidate snapshots and restore the V1 attribution schema."""
    if _has_table("evolution_run_candidates"):
        op.drop_table("evolution_run_candidates")
    _restore_bad_case_analysis()
    _drop_probe_columns()
