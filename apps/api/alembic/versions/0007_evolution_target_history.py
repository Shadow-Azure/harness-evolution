"""Allow historical evolution runs to outlive deleted target configuration.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-27
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Make the target FK nullable and clear it when configuration is deleted."""
    with op.batch_alter_table("evolution_runs", recreate="auto") as batch_op:
        batch_op.drop_constraint(
            "fk_evolution_runs_target_config",
            type_="foreignkey",
        )
        batch_op.alter_column(
            "target_config_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.create_foreign_key(
            "fk_evolution_runs_target_config",
            "evolution_targets",
            ["target_config_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Restore the required FK after discarding rows that cannot represent it."""
    op.execute("DELETE FROM evolution_runs WHERE target_config_id IS NULL")
    with op.batch_alter_table("evolution_runs", recreate="auto") as batch_op:
        batch_op.drop_constraint(
            "fk_evolution_runs_target_config",
            type_="foreignkey",
        )
        batch_op.alter_column(
            "target_config_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch_op.create_foreign_key(
            "fk_evolution_runs_target_config",
            "evolution_targets",
            ["target_config_id"],
            ["id"],
        )
