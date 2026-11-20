
"""Climate risk assessments linked to bank-owned real estate collateral."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from ccr.db.base import Base
from ccr.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class ClimateRiskAssessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Stores a climate hazard assessment for a specific bank collateral."""

    __tablename__ = "climate_risk_assessments"

    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "collateral_id"],
            ["collaterals.organization_id", "collaterals.id"],
            name="fk_climate_risk_assessments_org_collateral",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "organization_id",
            "collateral_id",
            "hazard_type",
            "assessment_date",
            "model_version",
            name="uq_climate_assessment_version",
        ),
        CheckConstraint(
            "hazard_type IN ('flood', 'coastal', 'extreme_heat')",
            name="valid_hazard_type",
        ),
        CheckConstraint(
            "risk_level IN ('low', 'moderate', 'high', 'very_high')",
            name="valid_risk_level",
        ),
        CheckConstraint(
            "risk_score >= 0 AND risk_score <= 100",
            name="risk_score_range",
        ),
        Index(
            "ix_climate_assessment_org_hazard_date",
            "organization_id",
            "hazard_type",
            "assessment_date",
        ),
        Index(
            "ix_climate_assessment_collateral",
            "collateral_id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )

    collateral_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )

    hazard_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    risk_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    risk_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
    )

    assessment_date: Mapped[date] = mapped_column(
        nullable=False,
    )

    source: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    model_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="1.0",
    )

    is_synthetic: Mapped[bool] = mapped_column(
        nullable=False,
    )
