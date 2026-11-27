
"""Normalized contract for CCR climate data providers.

This module defines a common interface for external climate data sources.
It does not fetch external data or generate synthetic risk scores.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Protocol


class ClimateHazard(str, Enum):
    FLOOD = "flood"
    COASTAL = "coastal"
    EXTREME_HEAT = "extreme_heat"


class HazardLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    VERY_HIGH = "very_high"
    UNKNOWN = "unknown"


class ClimateDataProviderError(Exception):
    """Base exception for climate provider errors."""


class ClimateDataUnavailableError(ClimateDataProviderError):
    """Raised when a provider has no usable data."""


class ClimateDataValidationError(ClimateDataProviderError):
    """Raised when provider data is invalid."""


@dataclass(frozen=True)
class ClimateHazardResult:
    """Normalized hazard result with explicit geographic assessment scope."""

    source: str
    hazard: ClimateHazard
    level: HazardLevel
    retrieved_at: datetime
    latitude: float
    longitude: float
    raw_category: str | None = None
    reference_url: str | None = None
    assessment_scope: str = "unspecified"
    administrative_area: str | None = None
    administrative_level: str | None = None


class ClimateDataProvider(Protocol):
    """Interface implemented by external climate data sources."""

    @property
    def name(self) -> str:
        """Return the stable provider identifier."""
        ...

    def assess_location(
        self,
        *,
        latitude: float,
        longitude: float,
        hazards: tuple[ClimateHazard, ...],
    ) -> list[ClimateHazardResult]:
        """Retrieve normalized hazard information for a location."""
        ...


def validate_coordinates(
    latitude: float,
    longitude: float,
) -> tuple[float, float]:
    """Validate geographic coordinates."""

    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        raise ClimateDataValidationError(
            "Latitude and longitude must be numeric."
        ) from None

    if not isfinite(lat) or not isfinite(lon):
        raise ClimateDataValidationError(
            "Coordinates must be finite numbers."
        )

    if not -90 <= lat <= 90:
        raise ClimateDataValidationError(
            "Latitude must be between -90 and 90."
        )

    if not -180 <= lon <= 180:
        raise ClimateDataValidationError(
            "Longitude must be between -180 and 180."
        )

    return lat, lon


def validate_provider_result(
    result: ClimateHazardResult,
) -> ClimateHazardResult:
    """Validate a normalized result before it enters CCR."""

    if not isinstance(result, ClimateHazardResult):
        raise ClimateDataValidationError(
            "Provider must return a ClimateHazardResult."
        )

    if not isinstance(result.source, str) or not result.source.strip():
        raise ClimateDataValidationError(
            "Provider source cannot be empty."
        )

    if not isinstance(result.hazard, ClimateHazard):
        raise ClimateDataValidationError(
            "Invalid climate hazard."
        )

    if not isinstance(result.level, HazardLevel):
        raise ClimateDataValidationError(
            "Invalid hazard level."
        )

    if not isinstance(result.retrieved_at, datetime):
        raise ClimateDataValidationError(
            "retrieved_at must be a datetime."
        )

    validate_coordinates(result.latitude, result.longitude)

    if result.reference_url is not None and not isinstance(
        result.reference_url, str
    ):
        raise ClimateDataValidationError(
            "reference_url must be a string or None."
        )

    if result.assessment_scope not in {
        "unspecified",
        "point",
        "administrative_area",
    }:
        raise ClimateDataValidationError(
            "Invalid climate assessment scope."
        )

    if result.administrative_area is not None and (
        not isinstance(result.administrative_area, str)
        or not result.administrative_area.strip()
    ):
        raise ClimateDataValidationError(
            "administrative_area must be a non-empty string or None."
        )

    if result.administrative_level is not None and (
        not isinstance(result.administrative_level, str)
        or not result.administrative_level.strip()
    ):
        raise ClimateDataValidationError(
            "administrative_level must be a non-empty string or None."
        )

    if result.assessment_scope == "administrative_area":
        if not result.administrative_area:
            raise ClimateDataValidationError(
                "Administrative-area results must identify the area."
            )
        if not result.administrative_level:
            raise ClimateDataValidationError(
                "Administrative-area results must identify the level."
            )

    return result
