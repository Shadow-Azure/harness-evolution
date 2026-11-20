"""Keep retry and terminal errors for a target's current attribution generation."""

import sqlalchemy as sa

from alembic import op

revision = "0030"
down_revision = "0029"


def upgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("evolution_targets")}
    for column in (
        sa.Column("attribution_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attribution_error", sa.String(64), nullable=True),
    ):
        if column.name not in existing:
            op.add_column("evolution_targets", column)


def downgrade() -> None:
    existing = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("evolution_targets")}
    for column in ("attribution_error", "attribution_failures"):
        if column in existing:
            op.drop_column("evolution_targets", column)
