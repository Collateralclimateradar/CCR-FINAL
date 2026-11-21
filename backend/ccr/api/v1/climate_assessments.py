
"""Organization-protected climate risk assessment endpoints."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ccr.api.auth_deps import require_roles
from ccr.api.deps import get_authorized_organization_or_404
from ccr.db.session import get_db
from ccr.models import Organization, User, UserRole
from ccr.models.climate_risk_assessment import ClimateRiskAssessment
from ccr.services.audit import record_audit_event
from ccr.services.climate_risk_assessment_service import (
    CollateralNotFoundError,
    create_climate_risk_assessment,
)

router = APIRouter(
    prefix="/organizations/{organization_id}/climate-assessments",
    tags=["climate-assessments"],
)

EDITOR_ROLES = (UserRole.ADMIN, UserRole.ANALYST)


class ClimateAssessmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    collateral_id: uuid.UUID
    hazard_type: Literal["flood", "coastal", "extreme_heat"]
    risk_score: Decimal = Field(
        ge=0,
        le=100,
        max_digits=5,
        decimal_places=2,
    )
    assessment_date: date
    source: str | None = Field(default=None, max_length=255)
    model_version: str = Field(
        default="1.0",
        min_length=1,
        max_length=50,
    )


class ClimateAssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    collateral_id: uuid.UUID
    hazard_type: str
    risk_level: str
    risk_score: Decimal
    assessment_date: date
    source: str | None
    model_version: str
    is_synthetic: bool


@router.post(
    "",
    response_model=ClimateAssessmentRead,
    status_code=201,
)
def create_climate_assessment(
    payload: ClimateAssessmentCreate,
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*EDITOR_ROLES)),
):
    """Create and audit a climate assessment for owned collateral."""

    try:
        assessment = create_climate_risk_assessment(
            db,
            organization_id=org.id,
            collateral_id=payload.collateral_id,
            hazard_type=payload.hazard_type,
            risk_score=payload.risk_score,
            assessment_date=payload.assessment_date,
            source=payload.source,
            model_version=payload.model_version,
        )

        record_audit_event(
            db,
            organization_id=org.id,
            actor_user_id=user.id,
            action="climate_assessment.created",
            entity_type="climate_risk_assessment",
            entity_id=assessment.id,
            after_data={
                "collateral_id": str(assessment.collateral_id),
                "hazard_type": assessment.hazard_type,
                "risk_score": str(assessment.risk_score),
                "risk_level": assessment.risk_level,
                "assessment_date": str(assessment.assessment_date),
                "model_version": assessment.model_version,
                "is_synthetic": assessment.is_synthetic,
            },
        )

        db.commit()

    except CollateralNotFoundError as exc:
        db.rollback()
        raise HTTPException(
            status_code=404,
            detail="Collateral not found.",
        ) from exc

    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "An assessment with this hazard, date, and model version "
                "already exists for this collateral."
            ),
        ) from exc

    except Exception:
        db.rollback()
        raise

    db.refresh(assessment)
    return assessment
