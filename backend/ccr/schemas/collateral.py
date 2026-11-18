
"""Data shapes for collaterals.

The organization is never accepted from the client body.
It is determined by the organization in the URL.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


Ref = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]

PropertyType = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=50),
]

Place = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]


class CollateralCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_ref: Ref
    property_type: PropertyType
    description: str | None = None
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    region: Place | None = None
    city: Place | None = None

    latitude: Decimal | None = Field(
        default=None,
        ge=-90,
        le=90,
        max_digits=9,
        decimal_places=6,
    )

    longitude: Decimal | None = Field(
        default=None,
        ge=-180,
        le=180,
        max_digits=9,
        decimal_places=6,
    )

    is_synthetic: bool

    @model_validator(mode="after")
    def coordinates_together(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError(
                "latitude and longitude must be provided together"
            )
        return self


class CollateralUpdate(BaseModel):
    """Fields that may be changed through a partial update."""

    model_config = ConfigDict(extra="forbid")

    external_ref: Ref | None = None
    property_type: PropertyType | None = None
    description: str | None = None
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    region: Place | None = None
    city: Place | None = None

    latitude: Decimal | None = Field(
        default=None,
        ge=-90,
        le=90,
        max_digits=9,
        decimal_places=6,
    )

    longitude: Decimal | None = Field(
        default=None,
        ge=-180,
        le=180,
        max_digits=9,
        decimal_places=6,
    )

    is_synthetic: bool | None = None


class CollateralRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    external_ref: str
    property_type: str
    description: str | None
    country_code: str | None
    region: str | None
    city: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    is_synthetic: bool
    is_archived: bool
    created_at: datetime
