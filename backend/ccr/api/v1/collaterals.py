
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


def _get_collateral_or_404(
    db: Session,
    organization_id: uuid.UUID,
    collateral_id: uuid.UUID,
    *,
    include_archived: bool = False,
):
    stmt = select(Collateral).where(
        Collateral.id == collateral_id,
        Collateral.organization_id == organization_id,
    )

    if not include_archived:
        stmt = stmt.where(Collateral.is_archived.is_(False))

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
    include_archived: bool = Query(False),
):
    stmt = select(Collateral).where(
        Collateral.organization_id == org.id
    )

    if not include_archived:
        stmt = stmt.where(Collateral.is_archived.is_(False))

    stmt = (
        stmt.order_by(Collateral.external_ref)
        .limit(limit)
        .offset(offset)
    )

    return db.scalars(stmt).all()


@router.get("/{collateral_id}", response_model=CollateralRead)
def read_collateral(
    collateral_id: uuid.UUID,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
    include_archived: bool = Query(False),
):
    return _get_collateral_or_404(
        db,
        org.id,
        collateral_id,
        include_archived=include_archived,
    )


@router.delete("/{collateral_id}", response_model=CollateralRead)
def archive_collateral(
    collateral_id: uuid.UUID,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    """Archive without permanently deleting financial records."""

    collateral = _get_collateral_or_404(
        db, org.id, collateral_id
    )

    collateral.is_archived = True

    db.commit()
    db.refresh(collateral)

    return collateral


@router.post("/{collateral_id}/restore", response_model=CollateralRead)
def restore_collateral(
    collateral_id: uuid.UUID,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    """Restore an archived collateral."""

    collateral = _get_collateral_or_404(
        db,
        org.id,
        collateral_id,
        include_archived=True,
    )

    collateral.is_archived = False

    db.commit()
    db.refresh(collateral)

    return collateral


@router.post(
    "/{collateral_id}/valuations",
    response_model=ValuationRead,
    status_code=201,
)
def create_valuation(
    collateral_id: uuid.UUID,
    payload: ValuationCreate,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    collateral = _get_collateral_or_404(
        db, org.id, collateral_id
    )

    valuation = Valuation(
        collateral_id=collateral.id,
        **payload.model_dump(),
    )

    db.add(valuation)
    db.commit()
    db.refresh(valuation)

    return valuation


@router.get(
    "/{collateral_id}/valuations",
    response_model=list[ValuationRead],
)
def list_valuations(
    collateral_id: uuid.UUID,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
    include_archived: bool = Query(False),
):
    collateral = _get_collateral_or_404(
        db,
        org.id,
        collateral_id,
        include_archived=include_archived,
    )

    stmt = (
        select(Valuation)
        .where(Valuation.collateral_id == collateral.id)
        .order_by(Valuation.valuation_date.desc())
    )

    return db.scalars(stmt).all()
