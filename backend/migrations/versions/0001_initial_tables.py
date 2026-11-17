"""Create the first four tables: organizations, users, collaterals, valuations.

Revision ID: 0001_initial_tables
Revises:
Create Date: 2026-11-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_tables"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
        sa.UniqueConstraint("name", name=op.f("uq_organizations_name")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "role IN ('admin', 'analyst', 'viewer')", name=op.f("ck_users_role_valid")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_users_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )
    op.create_index(op.f("ix_users_organization_id"), "users", ["organization_id"])

    op.create_table(
        "collaterals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("external_ref", sa.String(length=100), nullable=False),
        sa.Column("property_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "latitude BETWEEN -90 AND 90", name=op.f("ck_collaterals_latitude_range")
        ),
        sa.CheckConstraint(
            "longitude BETWEEN -180 AND 180", name=op.f("ck_collaterals_longitude_range")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_collaterals_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collaterals")),
        sa.UniqueConstraint("organization_id", "external_ref", name="org_external_ref"),
    )
    op.create_index(
        op.f("ix_collaterals_organization_id"), "collaterals", ["organization_id"]
    )

    op.create_table(
        "valuations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collateral_id", sa.Uuid(), nullable=False),
        sa.Column("value_amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("valuation_date", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("is_synthetic", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "value_amount >= 0", name=op.f("ck_valuations_value_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["collateral_id"],
            ["collaterals.id"],
            name=op.f("fk_valuations_collateral_id_collaterals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_valuations")),
    )
    op.create_index(
        "ix_valuations_collateral_id_date",
        "valuations",
        ["collateral_id", "valuation_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_valuations_collateral_id_date", table_name="valuations")
    op.drop_table("valuations")
    op.drop_index(op.f("ix_collaterals_organization_id"), table_name="collaterals")
    op.drop_table("collaterals")
    op.drop_index(op.f("ix_users_organization_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
