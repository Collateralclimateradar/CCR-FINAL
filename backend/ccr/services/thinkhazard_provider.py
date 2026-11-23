
"""ThinkHazard implementation of the CCR climate data provider contract.

This adapter connects:
- An injected administrative-division resolver.
- The ThinkHazard HTTP client.
- The ThinkHazard response normalizer.

It does not calculate property-level risk or financial losses.
"""

from ccr.services.administrative_division import (
    AdministrativeDivisionNotFoundError,
    AdministrativeDivisionResolutionError,
    AdministrativeDivisionResolver,
    validate_administrative_division,
)
from ccr.services.climate_data_provider import (
    ClimateDataProvider,
    ClimateDataUnavailableError,
    ClimateDataValidationError,
    ClimateHazard,
    ClimateHazardResult,
    validate_coordinates,
)
from ccr.services.thinkhazard_client import (
    ThinkHazardClient,
    ThinkHazardClientError,
    ThinkHazardUnavailableError,
)
from ccr.services.thinkhazard_normalizer import (
    ThinkHazardNormalizationError,
    normalize_thinkhazard_results,
)


class ThinkHazardProvider(ClimateDataProvider):
    """Retrieve and normalize ThinkHazard data for geographic locations."""

    def __init__(
        self,
        *,
        client: ThinkHazardClient,
        division_resolver: AdministrativeDivisionResolver,
    ) -> None:
        if not isinstance(client, ThinkHazardClient):
            raise TypeError("client must be a ThinkHazardClient.")

        if division_resolver is None:
            raise TypeError("division_resolver cannot be None.")

        self._client = client
        self._division_resolver = division_resolver

    @property
    def name(self) -> str:
        """Return the stable provider identifier."""

        return "thinkhazard"

    def assess_location(
        self,
        *,
        latitude: float,
        longitude: float,
        hazards: tuple[ClimateHazard, ...],
    ) -> list[ClimateHazardResult]:
        """Retrieve normalized hazard classifications for one location."""

        try:
            lat, lon = validate_coordinates(latitude, longitude)
        except ClimateDataValidationError:
            raise

        if not isinstance(hazards, tuple) or any(
            not isinstance(hazard, ClimateHazard)
            for hazard in hazards
        ):
            raise ClimateDataValidationError(
                "hazards must be a tuple of ClimateHazard values."
            )

        if not hazards:
            return []

        try:
            division = self._division_resolver.resolve(
                latitude=lat,
                longitude=lon,
            )
        except AdministrativeDivisionNotFoundError as exc:
            raise ClimateDataUnavailableError(
                "No supported ThinkHazard administrative division "
                "was found for this location."
            ) from exc
        except AdministrativeDivisionResolutionError as exc:
            raise ClimateDataUnavailableError(
                "Administrative division resolution is temporarily unavailable."
            ) from exc

        try:
            division = validate_administrative_division(division)
        except AdministrativeDivisionResolutionError as exc:
            raise ClimateDataValidationError(
                "The administrative division resolver returned "
                "invalid data."
            ) from exc

        try:
            payload = self._client.get_all_hazards(division.code)
        except ThinkHazardUnavailableError as exc:
            raise ClimateDataUnavailableError(
                "ThinkHazard is temporarily unavailable."
            ) from exc
        except ThinkHazardClientError as exc:
            raise ClimateDataValidationError(
                "ThinkHazard returned an invalid response."
            ) from exc

        try:
            return normalize_thinkhazard_results(
                payload,
                division_code=division.code,
                latitude=lat,
                longitude=lon,
                hazards=hazards,
            )
        except ThinkHazardNormalizationError as exc:
            raise ClimateDataValidationError(
                "ThinkHazard data could not be normalized."
            ) from exc
