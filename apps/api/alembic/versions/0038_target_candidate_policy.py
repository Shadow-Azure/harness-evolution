"""Store the candidate policy atomically with the evolution target."""

import sqlalchemy as sa
from alembic.script import ScriptDirectory

from alembic import op

revision = "0038"
down_revision = "0037"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    # Candidate previews used 0035 and 0036 before those numbers landed on main.
    # Replay only the schema those stamps skipped, preserving the preview's JSON.
    scripts = ScriptDirectory.from_config(op.get_context().config)
    if not inspector.has_table("evolution_target_members"):
        scripts.get_revision("0035").module.upgrade()
        scripts.get_revision("0037").module.upgrade()
    if "result_commit" not in {col["name"] for col in inspector.get_columns("evolution_runs")}:
        scripts.get_revision("0036").module.upgrade()

    columns = inspector.get_columns("evolution_run_candidates")
    if not any(column["name"] == "source_evidence" for column in columns):
        op.add_column(
            "evolution_run_candidates", sa.Column("source_evidence", sa.JSON(), nullable=True)
        )
    columns = inspector.get_columns("evolution_targets")
    if not any(column["name"] == "candidate_policy" for column in columns):
        op.add_column("evolution_targets", sa.Column("candidate_policy", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("evolution_run_candidates", "source_evidence")
    op.drop_column("evolution_targets", "candidate_policy")
