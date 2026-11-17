"""One valuation of one collateral at one date.

Valuations are kept as history: a new valuation is a new row, not an overwrite.
"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ccr.db.base import Base
from ccr.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Valuation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "valuations"
    __table_args__ = (
        CheckConstraint("value_amount >= 0", name="value_not_negative"),
        Index("ix_valuations_collateral_id_date", "collateral_id", "valuation_date"),
    )

    collateral_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("collaterals.id", ondelete="RESTRICT"), nullable=False
    )
    value_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    valuation_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Free text, e.g. who produced the valuation. Not invented by the system.
    source: Mapped[str | None] = mapped_column(String(100))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False)

    collateral: Mapped["Collateral"] = relationship(back_populates="valuations")


from ccr.models.collateral import Collateral  # noqa: E402,F401  (resolves the name above)
