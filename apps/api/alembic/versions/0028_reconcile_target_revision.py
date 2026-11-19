"""Reconcile developer databases that reached 0023 through the Skill branch."""
from alembic import op
from alembic.script import ScriptDirectory

revision = "0028"
down_revision = "0027"


def upgrade() -> None:
    """Apply the idempotent main revision for legacy branch databases."""
    scripts = ScriptDirectory.from_config(op.get_context().config)
    scripts.get_revision("0023").module.upgrade()


def downgrade() -> None:
    """The reconciled columns belong to main revision 0023."""
