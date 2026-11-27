"""Store the candidate policy atomically with the evolution target."""

import sqlalchemy as sa
from alembic.script import ScriptDirectory

from alembic import op

revision = "0036"
down_revision = "0035"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # The published candidate-policy preview also used 0035. Bring its single-member
    # targets forward with the official 0035 backfill before adding the new columns.
    if not inspector.has_table("evolution_target_members"):
        scripts = ScriptDirectory.from_config(op.get_context().config)
        scripts.get_revision(down_revision).module.upgrade()
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
