
"""Add optional bank-internal owner reference to collateral.

Revision ID: 0006_owner_reference
Revises: 0005_climate_risk
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_owner_reference"
down_revision = "0005_climate_risk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collaterals",
        sa.Column(
            "owner_reference",
            sa.String(length=100),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "collaterals",
        "owner_reference",
    )
