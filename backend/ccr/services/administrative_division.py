
"""Administrative-area resolution contract for location-based hazard providers.

This module deliberately does not guess an administrative area from coordinates.
A concrete resolver must use an authoritative boundary dataset or service and
return the matching provider division code.
"""

import re
from dataclasses import dataclass
from typing import Protocol

from ccr.services.climate_data_provider import validate_coordinates


_PROVIDER_DIVISION_CODE_PATTERN = re.compile(
    r"^[A-Z]{3}[A-Z0-9-]{0,29}$"
)


class AdministrativeDivisionResolutionError(Exception):
    """Base exception for administrative-division resolution failures."""


class AdministrativeDivisionNotFoundError(
    AdministrativeDivisionResolutionError
):
    """Raised when coordinates do not match a supported administrative area."""


class AdministrativeDivisionValidationError(
    AdministrativeDivisionResolutionError
):
    """Raised when a resolver returns invalid administrative-area data."""


@dataclass(frozen=True)
class AdministrativeDivision:
    """An administrative area and the code accepted by a hazard provider."""

    code: int | str
    name: str
    country: str
    admin1: str | None = None
    admin2: str | None = None


class AdministrativeDivisionResolver(Protocol):
    """Resolve a geographic point to a provider-supported division."""

    def resolve(
        self,
        *,
        latitude: float,
        longitude: float,
    ) -> AdministrativeDivision:
        """Return the administrative division containing the point.

        Implementations must raise AdministrativeDivisionNotFoundError
        when no supported division contains the supplied coordinates.
        """
        ...


def _is_valid_division_code(code: object) -> bool:
    """Accept legacy numeric IDs and modern ThinkHazard string codes."""

    if isinstance(code, bool):
        return False

    if isinstance(code, int):
        return code > 0

    if isinstance(code, str):
        return bool(_PROVIDER_DIVISION_CODE_PATTERN.fullmatch(code))

    return False


def validate_administrative_division(
    division: AdministrativeDivision,
) -> AdministrativeDivision:
    """Validate a resolved division before it is used in provider requests."""

    if not isinstance(division, AdministrativeDivision):
        raise AdministrativeDivisionValidationError(
            "Resolver must return an AdministrativeDivision."
        )

    if not _is_valid_division_code(division.code):
        raise AdministrativeDivisionValidationError(
            "Administrative division code must be a positive integer "
            "or a valid uppercase provider code."
        )

    for field_name in ("name", "country"):
        value = getattr(division, field_name)
        if not isinstance(value, str) or not value.strip():
            raise AdministrativeDivisionValidationError(
                f"Administrative division {field_name} cannot be empty."
            )

    for field_name in ("admin1", "admin2"):
        value = getattr(division, field_name)
        if value is not None and (
            not isinstance(value, str) or not value.strip()
        ):
            raise AdministrativeDivisionValidationError(
                f"Administrative division {field_name} must be "
                "a non-empty string or None."
            )

    return division


def validate_resolution_request(
    latitude: float,
    longitude: float,
) -> tuple[float, float]:
    """Validate coordinates before passing them to a resolver."""

    return validate_coordinates(latitude, longitude)
