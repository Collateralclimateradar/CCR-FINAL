"""Organization = one bank (or financial institution). Each has its own data."""
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from ccr.db.base import Base
from ccr.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
