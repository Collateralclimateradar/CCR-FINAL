"""Add is_archived to collaterals.

Revision ID: 0002_add_collateral_is_archived
Revises: 0001_initial_tables
Create Date: 2026-11-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_add_collateral_is_archived"
down_revision = "0001_initial_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collaterals",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_collaterals_is_archived",
        "collaterals",
        ["is_archived"],
    )


def downgrade() -> None:
    op.drop_index("ix_collaterals_is_archived", table_name="collaterals")
    op.drop_column("collaterals", "is_archived")
