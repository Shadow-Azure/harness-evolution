"""Reconcile the trigger line for databases stamped on the original Skill branch."""

from alembic.script import ScriptDirectory

from alembic import op

revision = "0026a"
down_revision = "0025a"


def upgrade() -> None:
    """Older branch databases ran a different revision with the ID 0022."""
    scripts = ScriptDirectory.from_config(op.get_context().config)
    scripts.get_revision("0022").module.upgrade()


def downgrade() -> None:
    """The trigger line belongs to the released revision 0022."""
