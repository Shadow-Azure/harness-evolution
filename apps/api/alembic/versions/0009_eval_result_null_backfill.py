"""Backfill historical JSON null evaluation results to SQL NULL.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-28
"""

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Rewrite the legacy JSON ``null`` text as SQL NULL for the pending-result guard."""
    if op.get_bind().dialect.name == "mysql":
        op.execute(
            "UPDATE evolution_rounds SET eval_result = NULL WHERE JSON_TYPE(eval_result) = 'NULL'",
        )
        return
    op.execute("UPDATE evolution_rounds SET eval_result = NULL WHERE eval_result = 'null'")


def downgrade() -> None:
    """Leave the repaired data in place: the backfill is intentionally irreversible."""
    # A repaired SQL NULL is indistinguishable from a row that never had a result,
    # so re-creating the JSON text 'null' would only break the IS NULL guard again.
    return
