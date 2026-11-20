
"""Create climate risk assessments for bank collateral.

Revision ID: 0005_create_climate_risk_assessments
Revises: 0004_create_audit_logs
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_create_climate_risk_assessments"
down_revision = "0004_create_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite requires batch mode to add a table-level unique constraint.
    with op.batch_alter_table("collaterals") as batch_op:
        batch_op.create_unique_constraint(
            "uq_collaterals_org_id_id",
            ["organization_id", "id"],
        )

    op.create_table(
        "climate_risk_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("collateral_id", sa.Uuid(), nullable=False),
        sa.Column("hazard_type", sa.String(length=30), nullable=False),
        sa.Column("risk_level", sa.String(length=20), nullable=False),
        sa.Column("risk_score", sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column("assessment_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column(
            "model_version",
            sa.String(length=50),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "hazard_type IN ('flood', 'coastal', 'extreme_heat')",
            name="ck_climate_risk_assessments_valid_hazard_type",
        ),
        sa.CheckConstraint(
            "risk_level IN ('low', 'moderate', 'high', 'very_high')",
            name="ck_climate_risk_assessments_valid_risk_level",
        ),
        sa.CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="ck_climate_risk_assessments_risk_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "collateral_id"],
            ["collaterals.organization_id", "collaterals.id"],
            name="fk_climate_risk_assessments_org_collateral",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name="pk_climate_risk_assessments",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "collateral_id",
            "hazard_type",
            "assessment_date",
            "model_version",
            name="uq_climate_assessment_version",
        ),
    )

    op.create_index(
        "ix_climate_assessment_org_hazard_date",
        "climate_risk_assessments",
        ["organization_id", "hazard_type", "assessment_date"],
    )
    op.create_index(
        "ix_climate_assessment_collateral",
        "climate_risk_assessments",
        ["collateral_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_climate_assessment_collateral",
        table_name="climate_risk_assessments",
    )
    op.drop_index(
        "ix_climate_assessment_org_hazard_date",
        table_name="climate_risk_assessments",
    )
    op.drop_table("climate_risk_assessments")

    with op.batch_alter_table("collaterals") as batch_op:
        batch_op.drop_constraint(
            "uq_collaterals_org_id_id",
            type_="unique",
        )
