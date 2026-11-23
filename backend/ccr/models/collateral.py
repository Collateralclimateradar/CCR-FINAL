
"""A real estate asset that secures a loan. Always owned by one organization."""

import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ccr.db.base import Base
from ccr.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Collateral(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "collaterals"

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "external_ref",
            name="org_external_ref",
        ),
        UniqueConstraint(
            "organization_id",
            "id",
            name="org_id_id",
        ),
        CheckConstraint(
            "latitude BETWEEN -90 AND 90",
            name="latitude_range",
        ),
        CheckConstraint(
            "longitude BETWEEN -180 AND 180",
            name="longitude_range",
        ),
    )

    # Each collateral belongs to exactly one organization.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    # The bank's internal reference for the property.
    external_ref: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # Optional bank-internal reference identifying the property owner.
    owner_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    property_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    country_code: Mapped[str | None] = mapped_column(
        String(2),
        nullable=True,
    )

    region: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    latitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    longitude: Mapped[Decimal | None] = mapped_column(
        Numeric(9, 6),
        nullable=True,
    )

    # Explicitly identifies demo/synthetic records.
    is_synthetic: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
    )

    # Archived properties remain available for financial history.
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    valuations: Mapped[list["Valuation"]] = relationship(
        back_populates="collateral",
    )


from ccr.models.valuation import Valuation  # noqa: E402
