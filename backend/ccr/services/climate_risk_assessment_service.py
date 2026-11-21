
"""Service for creating organization-scoped climate risk assessments."""

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ccr.models.climate_risk_assessment import ClimateRiskAssessment
from ccr.models.collateral import Collateral
from ccr.services.climate_risk_scoring import (
    MODEL_VERSION,
    classify_risk,
    normalize_score,
)

SUPPORTED_HAZARDS = frozenset(
    {"flood", "coastal", "extreme_heat"}
)


class CollateralNotFoundError(ValueError):
    """Raised when collateral is missing or outside the organization."""


def create_climate_risk_assessment(
    db: Session,
    *,
    organization_id: uuid.UUID,
    collateral_id: uuid.UUID,
    hazard_type: str,
    risk_score,
    assessment_date: date,
    source: str | None = None,
    model_version: str = MODEL_VERSION,
) -> ClimateRiskAssessment:
    """Create an assessment after verifying collateral ownership.

    The risk level is derived internally from the score.
    Synthetic status is inherited from the collateral.
    The transaction is flushed but not committed by this service.
    """

    if hazard_type not in SUPPORTED_HAZARDS:
        raise ValueError("Unsupported climate hazard type.")

    if not isinstance(assessment_date, date):
        raise ValueError("Assessment date must be a date.")

    if not model_version or not model_version.strip():
        raise ValueError("Model version cannot be empty.")

    normalized_score = normalize_score(risk_score)
    risk_level = classify_risk(normalized_score)

    statement = select(Collateral).where(
        Collateral.id == collateral_id,
        Collateral.organization_id == organization_id,
    )

    collateral = db.execute(statement).scalar_one_or_none()

    if collateral is None:
        raise CollateralNotFoundError(
            "Collateral not found for this organization."
        )

    assessment = ClimateRiskAssessment(
        organization_id=organization_id,
        collateral_id=collateral_id,
        hazard_type=hazard_type,
        risk_score=normalized_score,
        risk_level=risk_level,
        assessment_date=assessment_date,
        source=source,
        model_version=model_version.strip(),
        is_synthetic=collateral.is_synthetic,
    )

    db.add(assessment)
    db.flush()

    return assessment
