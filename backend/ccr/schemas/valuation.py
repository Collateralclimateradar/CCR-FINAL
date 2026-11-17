"""Data shapes for valuations."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Source = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class ValuationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    valuation_date: date
    source: Source | None = None
    # Required on purpose: the sender must say if the record is synthetic.
    is_synthetic: bool


class ValuationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    collateral_id: uuid.UUID
    value_amount: Decimal
    currency: str
    valuation_date: date
    source: str | None
    is_synthetic: bool
    created_at: datetime
