
"""DEVELOPMENT-ONLY routes for collaterals and their valuations.

There is no login yet (Phase 6). Every query is limited to the organization
named in the URL, so one bank never sees another bank's records.
"""

import uuid

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ccr.api.deps import get_organization_or_404
from ccr.db.session import get_db
from ccr.models import Collateral, Organization, Valuation
from ccr.schemas.collateral import (
    CollateralCreate,
    CollateralRead,
    CollateralUpdate,
)
from ccr.schemas.collateral_import import (
    CollateralImportPreview,
    CollateralImportReport,
)
from ccr.schemas.valuation import ValuationCreate, ValuationRead
from ccr.services.collateral_import import (
    CSVImportError,
    validate_collateral_csv,
)
from ccr.services.collateral_import_execution import (
    CollateralImportConflict,
    execute_collateral_import,
)


router = APIRouter(
    prefix="/organizations/{organization_id}/collaterals",
    tags=["collaterals (development only)"],
)


@router.post(
    "/import/preview",
    response_model=CollateralImportPreview,
    status_code=200,
)
async def preview_collateral_import(
    file: UploadFile = File(...),
    org: Organization = Depends(get_organization_or_404),
):
    """
    Validate an uploaded collateral CSV without writing to the database.

    Development-only endpoint. Authentication is not implemented yet.
    """

    try:
        content = await file.read(10 * 1024 * 1024 + 1)

        result = validate_collateral_csv(content)

        return result.preview

    except CSVImportError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    finally:
        await file.close()


@router.post(
    "/import",
    response_model=CollateralImportReport,
    status_code=200,
)
async def execute_collateral_csv_import(
    file: UploadFile = File(...),
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    """
    Validate and import collateral CSV records.

    Invalid rows and existing references are skipped.
    Database integrity conflicts roll back the entire transaction.

    Development-only endpoint. Authentication is not implemented yet.
    """

    try:
        content = await file.read(10 * 1024 * 1024 + 1)

        validation_result = validate_collateral_csv(content)

        report = execute_collateral_import(
            db=db,
            organization_id=org.id,
            validation_result=validation_result,
        )

        return report

    except CSVImportError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    except CollateralImportConflict as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

    finally:
        await file.close()


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
        raise HTTPException(
            status_code=404,
            detail="Collateral not found.",
        )

    return collateral


@router.post("", response_model=CollateralRead, status_code=201)
def create_collateral(
    payload: CollateralCreate,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    collateral = Collateral(
        organization_id=org.id,
        **payload.model_dump(),
    )
    db.add(collateral)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "A collateral with this external_ref already exists "
                "in this organization."
            ),
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


@router.patch("/{collateral_id}", response_model=CollateralRead)
def update_collateral(
    collateral_id: uuid.UUID,
    payload: CollateralUpdate,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    """Partially update an active collateral record."""

    collateral = _get_collateral_or_404(
        db,
        org.id,
        collateral_id,
    )

    updates = payload.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=422,
            detail="At least one field must be provided.",
        )

    new_latitude = updates.get("latitude", collateral.latitude)
    new_longitude = updates.get("longitude", collateral.longitude)

    if (new_latitude is None) != (new_longitude is None):
        raise HTTPException(
            status_code=422,
            detail="latitude and longitude must be provided together.",
        )

    for field, value in updates.items():
        setattr(collateral, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "The update conflicts with an existing collateral "
                "record in this organization."
            ),
        )

    db.refresh(collateral)
    return collateral


@router.delete("/{collateral_id}", response_model=CollateralRead)
def archive_collateral(
    collateral_id: uuid.UUID,
    org: Organization = Depends(get_organization_or_404),
    db: Session = Depends(get_db),
):
    """Archive without permanently deleting financial records."""

    collateral = _get_collateral_or_404(
        db,
        org.id,
        collateral_id,
    )

    collateral.is_archived = True

    db.commit()
    db.refresh(collateral)

    return collateral


@router.post(
    "/{collateral_id}/restore",
    response_model=CollateralRead,
)
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
        db,
        org.id,
        collateral_id,
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
