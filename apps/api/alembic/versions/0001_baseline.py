"""Establish the empty cross-dialect schema baseline.

Revision ID: 0001
Revises:
Create Date: 2026-10-25
"""

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """Apply the baseline without introducing domain tables."""


def downgrade() -> None:
    """Revert the baseline without touching domain data."""
