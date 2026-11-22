"""Persist cooperative run control and elapsed evaluation pauses."""

import sqlalchemy as sa

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Backfill old runs as running and old rounds with zero paused time."""
    for table, columns in _columns().items():
        existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
        for column in columns:
            if column.name not in existing:
                op.add_column(table, column)


def downgrade() -> None:
    """Remove the additive control fields."""
    for table, columns in _columns().items():
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.drop_column(column.name)


def _columns() -> dict[str, tuple[sa.Column, ...]]:
    return {
        "evolution_runs": (
            sa.Column("control_state", sa.String(16), nullable=False, server_default="running"),
            sa.Column("pause_requested_at", sa.DateTime(timezone=True)),
            sa.Column("paused_at", sa.DateTime(timezone=True)),
            sa.Column("paused_by", sa.String(36)),
            sa.Column("resumed_at", sa.DateTime(timezone=True)),
        ),
        "evolution_rounds": (
            sa.Column("eval_paused_seconds", sa.Float, nullable=False, server_default="0"),
        ),
    }
