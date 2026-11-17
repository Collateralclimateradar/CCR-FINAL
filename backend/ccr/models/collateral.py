
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
        UniqueConstraint("organization_id", "external_ref", name="org_external_ref"),
        CheckConstraint("latitude BETWEEN -90 AND 90", name="latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="longitude_range"),
    )

    # Every query must filter on this column: it keeps banks' data separate.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("organizations.id", ondelete="RESTRICT"), index=True, nullable=False
    )

    # The bank's own reference for this asset.
    external_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    property_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    country_code: Mapped[str | None] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(100))
    city: Mapped[str | None] = mapped_column(String(100))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))

    # No default on purpose: whoever creates a record must say if it is synthetic.
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # Archived records remain in the database to preserve financial history.
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        index=True,
    )

    valuations: Mapped[list["Valuation"]] = relationship(back_populates="collateral")


from ccr.models.valuation import Valuation  # noqa: E402  (resolves the name above)
