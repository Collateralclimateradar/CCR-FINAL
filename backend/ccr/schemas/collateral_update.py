
"""Validation schema for partial collateral updates."""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

PropertyType = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)
]

Place = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class CollateralUpdate(BaseModel):
    """Only supplied fields are changed; omitted fields remain untouched."""

    model_config = ConfigDict(extra="forbid")

    property_type: PropertyType | None = None
    description: str | None = None
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    region: Place | None = None
    city: Place | None = None
    latitude: Decimal | None = Field(
        default=None, ge=-90, le=90, max_digits=9, decimal_places=6
    )
    longitude: Decimal | None = Field(
        default=None, ge=-180, le=180, max_digits=9, decimal_places=6
    )

    @model_validator(mode="after")
    def validate_coordinates(self):
        fields = self.model_fields_set

        if ("latitude" in fields) != ("longitude" in fields):
            raise ValueError(
                "latitude and longitude must be updated together"
            )

        if "property_type" in fields and self.property_type is None:
            raise ValueError("property_type cannot be null")

        return self
