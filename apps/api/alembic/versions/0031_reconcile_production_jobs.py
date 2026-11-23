"""Converge previously stamped attribution databases on the production schema."""

import sqlalchemy as sa
from alembic.script import ScriptDirectory

from alembic import op

revision = "0031"
down_revision = "0030"


def upgrade() -> None:
    """Preserve existing rows regardless of which line originally stamped 0024-0026."""
    scripts = ScriptDirectory.from_config(op.get_context().config)
    for released in ("0024", "0025", "0026"):
        scripts.get_revision(released).module.upgrade()
    indexes = {i["name"] for i in sa.inspect(op.get_bind()).get_indexes("job_runs")}
    if "ix_job_runs_lease_expiry" in indexes:
        # The released 0025 index covers the same ordered pair of columns.
        op.drop_index("ix_job_runs_lease_expiry", table_name="job_runs")


def downgrade() -> None:
    """Production lease, push and pause columns belong to their original revisions."""
