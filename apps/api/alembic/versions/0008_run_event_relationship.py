"""Add the evolution run relationship to durable event history.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-28
"""

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Attach the event projection to its now-existing evolution run parent."""
    with op.batch_alter_table(
        "evolution_run_events",
        recreate="always",
    ) as batch_op:
        batch_op.create_foreign_key(
            "fk_evolution_run_events_run",
            "evolution_runs",
            ["run_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    """Remove only the parent relationship while preserving event history."""
    with op.batch_alter_table(
        "evolution_run_events",
        recreate="always",
    ) as batch_op:
        batch_op.drop_constraint(
            "fk_evolution_run_events_run",
            type_="foreignkey",
        )
