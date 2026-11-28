
"""Authenticated geographic climate screening for bank collateral."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ccr.api.auth_deps import get_current_user
from ccr.api.deps import get_authorized_organization_or_404
from ccr.db.session import get_db
from ccr.models import Organization, User
from ccr.services.audit import record_audit_event
from ccr.services.climate_data_provider import (
    ClimateDataUnavailableError,
    ClimateDataValidationError,
    ClimateHazard,
    HazardLevel,
)
from ccr.services.climate_location_screening import (
    DEFAULT_HAZARDS,
    CollateralLocationMissingError,
    CollateralScreeningNotFoundError,
    screen_collateral_location,
)
from ccr.services.thinkhazard_client import ThinkHazardClient
from ccr.services.thinkhazard_provider import ThinkHazardProvider
from ccr.services.uae_emirate_resolver import UAEEmirateResolver


ASSESSMENT_NOTICE = (
    "This result is an administrative-area climate hazard screening. "
    "It is not a property-level risk determination, a site-specific "
    "engineering assessment, or an estimate of financial loss. "
    "Hazard classifications do not by themselves measure collateral "
    "exposure, vulnerability, or expected financial impact."
)


router = APIRouter(
    prefix="/organizations/{organization_id}/collaterals",
    tags=["climate-location-screening"],
)


def get_climate_data_provider() -> ThinkHazardProvider:
    """Build the UAE geographic screening provider."""

    return ThinkHazardProvider(
        client=ThinkHazardClient(),
        division_resolver=UAEEmirateResolver(),
    )


class ClimateLocationScreeningRequest(BaseModel):
    """Hazards requested for a collateral location screening."""

    model_config = ConfigDict(extra="forbid")

    hazards: list[ClimateHazard] = Field(
        default_factory=lambda: list(DEFAULT_HAZARDS),
        min_length=1,
    )


class ClimateHazardResultRead(BaseModel):
    """A normalized geographic hazard classification."""

    hazard: ClimateHazard
    level: HazardLevel
    source: str
    retrieved_at: datetime
    latitude: float
    longitude: float
    raw_category: str | None
    reference_url: str | None
    assessment_scope: str
    administrative_area: str | None
    administrative_level: str | None


class ClimateLocationScreeningRead(BaseModel):
    """Response returned by the geographic screening endpoint."""

    collateral_id: uuid.UUID
    provider: str
    screened_at: datetime
    assessment_notice: str
    results: list[ClimateHazardResultRead]


@router.post(
    "/{collateral_id}/climate-location-screening",
    response_model=ClimateLocationScreeningRead,
)
def screen_collateral_climate_location(
    collateral_id: uuid.UUID,
    payload: ClimateLocationScreeningRequest,
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    provider: ThinkHazardProvider = Depends(
        get_climate_data_provider
    ),
):
    """Screen an active collateral using its stored geographic coordinates."""

    try:
        results = screen_collateral_location(
            db,
            organization_id=org.id,
            collateral_id=collateral_id,
            provider=provider,
            hazards=tuple(payload.hazards),
        )

    except CollateralScreeningNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Collateral not found.",
        ) from exc

    except CollateralLocationMissingError as exc:
        raise HTTPException(
            status_code=422,
            detail="Collateral must have valid coordinates before screening.",
        ) from exc

    except ClimateDataUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail="Climate data is temporarily unavailable.",
        ) from exc

    except ClimateDataValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail="The climate data provider returned invalid data.",
        ) from exc

    screened_at = datetime.now(timezone.utc)

    try:
        record_audit_event(
            db,
            organization_id=org.id,
            actor_user_id=user.id,
            action="collateral.climate_location_screened",
            entity_type="collateral",
            entity_id=collateral_id,
            after_data={
                "provider": provider.name,
                "hazards_requested": [
                    hazard.value for hazard in payload.hazards
                ],
                "result_count": len(results),
                "assessment_scopes": sorted(
                    {result.assessment_scope for result in results}
                ),
                "screened_at": screened_at.isoformat(),
            },
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    return ClimateLocationScreeningRead(
        collateral_id=collateral_id,
        provider=provider.name,
        screened_at=screened_at,
        assessment_notice=ASSESSMENT_NOTICE,
        results=[
            ClimateHazardResultRead(
                hazard=result.hazard,
                level=result.level,
                source=result.source,
                retrieved_at=result.retrieved_at,
                latitude=result.latitude,
                longitude=result.longitude,
                raw_category=result.raw_category,
                reference_url=result.reference_url,
                assessment_scope=result.assessment_scope,
                administrative_area=result.administrative_area,
                administrative_level=result.administrative_level,
            )
            for result in results
        ],
    )
