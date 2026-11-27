
"""Run a geographic climate screening for one bank collateral."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ccr.models.collateral import Collateral
from ccr.services.climate_data_provider import (
    ClimateDataProvider,
    ClimateDataValidationError,
    ClimateHazard,
    ClimateHazardResult,
    validate_provider_result,
)


DEFAULT_HAZARDS = (
    ClimateHazard.FLOOD,
    ClimateHazard.COASTAL,
    ClimateHazard.EXTREME_HEAT,
)


class CollateralScreeningError(ValueError):
    """Base error for collateral location screening."""


class CollateralScreeningNotFoundError(CollateralScreeningError):
    """Raised when collateral is not found in the organization."""


class CollateralLocationMissingError(CollateralScreeningError):
    """Raised when collateral has no complete geographic coordinates."""


def screen_collateral_location(
    db: Session,
    *,
    organization_id: uuid.UUID,
    collateral_id: uuid.UUID,
    provider: ClimateDataProvider,
    hazards: tuple[ClimateHazard, ...] = DEFAULT_HAZARDS,
) -> list[ClimateHazardResult]:
    """Retrieve provider classifications for an organization's collateral.

    This service performs geographic screening only. It does not convert
    provider categories into numeric risk scores, estimate financial losses,
    persist assessments, or claim property-level hazard precision.
    """

    if not isinstance(provider, ClimateDataProvider):
        raise TypeError("provider must implement ClimateDataProvider.")

    if not isinstance(hazards, tuple) or any(
        not isinstance(hazard, ClimateHazard)
        for hazard in hazards
    ):
        raise ClimateDataValidationError(
            "hazards must be a tuple of ClimateHazard values."
        )

    if len(set(hazards)) != len(hazards):
        raise ClimateDataValidationError(
            "hazards cannot contain duplicates."
        )

    statement = select(Collateral).where(
        Collateral.id == collateral_id,
        Collateral.organization_id == organization_id,
        Collateral.is_archived.is_(False),
    )

    collateral = db.execute(statement).scalar_one_or_none()

    if collateral is None:
        raise CollateralScreeningNotFoundError(
            "Collateral not found for this organization."
        )

    if collateral.latitude is None or collateral.longitude is None:
        raise CollateralLocationMissingError(
            "Collateral must have both latitude and longitude "
            "before climate screening."
        )

    results = provider.assess_location(
        latitude=float(collateral.latitude),
        longitude=float(collateral.longitude),
        hazards=hazards,
    )

    if not isinstance(results, list):
        raise ClimateDataValidationError(
            "Climate provider must return a list of results."
        )

    validated_results = []
    returned_hazards = set()

    for result in results:
        validated = validate_provider_result(result)

        if validated.hazard not in hazards:
            raise ClimateDataValidationError(
                "Climate provider returned an unrequested hazard."
            )

        if validated.hazard in returned_hazards:
            raise ClimateDataValidationError(
                "Climate provider returned a duplicate hazard."
            )

        returned_hazards.add(validated.hazard)
        validated_results.append(validated)

    return validated_results
