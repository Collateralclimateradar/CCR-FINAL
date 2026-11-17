"""DEVELOPMENT-ONLY routes for collaterals and their valuations.

There is no login yet (Phase 6). Every query is limited to the organization
named in the URL, so one bank never sees another bank's records.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ccr.api.deps import get_organization_or_404
from ccr.db.session import get_db
from ccr.models import Collateral, Organization, Valuation
from ccr.schemas.collateral import CollateralCreate, CollateralRead
from ccr.schemas.valuation import ValuationCreate, ValuationRead

router = APIRouter(
    prefix="/organizations/{organization_id}/collaterals",
    tags=["collaterals (development only)"],
)


def _get_collateral_or_404(db: Session, organization_id: uuid.UUID, collateral_id: uuid.UUID):
    stmt = select(Collateral).where(
        Collateral.id == collateral_id,
        Collateral.organization_id == organization_id,  # tenant isolation
    )
    collateral = db.scalars(stmt).first()
    if collateral is None:
        raise HTTPException(status_code=404, detail="Collateral not found.")
    return collateral


@router.post("", response_model=CollateralRead, status_code=201)
def create_collateral(
    payload: CollateralCreate,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    collateral = Collateral(organization_id=org.id, **payload.model_dump())
    db.add(collateral)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A collateral with this external_ref already exists in this organization.",
        )
    db.refresh(collateral)
    return collateral


@router.get("", response_model=list[CollateralRead])
def list_collaterals(
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    stmt = (
        select(Collateral)
        .where(Collateral.organization_id == org.id)  # tenant isolation
        .order_by(Collateral.external_ref)
        .limit(limit)
        .offset(offset)
    )
    return db.scalars(stmt).all()


@router.get("/{collateral_id}", response_model=CollateralRead)
def read_collateral(
    collateral_id: uuid.UUID,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    return _get_collateral_or_404(db, org.id, collateral_id)


@router.post(
    "/{collateral_id}/valuations", response_model=ValuationRead, status_code=201
)
def create_valuation(
    collateral_id: uuid.UUID,
    payload: ValuationCreate,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    collateral = _get_collateral_or_404(db, org.id, collateral_id)
    valuation = Valuation(collateral_id=collateral.id, **payload.model_dump())
    db.add(valuation)
    db.commit()
    db.refresh(valuation)
    return valuation


@router.get("/{collateral_id}/valuations", response_model=list[ValuationRead])
def list_valuations(
    collateral_id: uuid.UUID,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    collateral = _get_collateral_or_404(db, org.id, collateral_id)
    stmt = (
        select(Valuation)
        .where(Valuation.collateral_id == collateral.id)
        .order_by(Valuation.valuation_date.desc())
    )
    return db.scalars(stmt).all()
