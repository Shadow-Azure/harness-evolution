"""Store the candidate policy atomically with the evolution target."""

import sqlalchemy as sa

from alembic import op

revision = "0035"
down_revision = "0034"


def upgrade() -> None:
    columns = sa.inspect(op.get_bind()).get_columns("evolution_run_candidates")
    if not any(column["name"] == "source_evidence" for column in columns):
        op.add_column(
            "evolution_run_candidates", sa.Column("source_evidence", sa.JSON(), nullable=True)
        )
    columns = sa.inspect(op.get_bind()).get_columns("evolution_targets")
    if not any(column["name"] == "candidate_policy" for column in columns):
        op.add_column("evolution_targets", sa.Column("candidate_policy", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("evolution_run_candidates", "source_evidence")
    op.drop_column("evolution_targets", "candidate_policy")
