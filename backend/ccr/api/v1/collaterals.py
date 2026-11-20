
"""Role-protected routes for organization collaterals and valuations."""

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

from ccr.api.auth_deps import require_roles
from ccr.api.deps import get_authorized_organization_or_404
from ccr.db.session import get_db
from ccr.models import (
    Collateral,
    Organization,
    User,
    UserRole,
    Valuation,
)
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
from ccr.services.audit import record_audit_event
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
    tags=["collaterals"],
)

EDITOR_ROLES = (UserRole.ADMIN, UserRole.ANALYST)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


async def _read_csv_upload(file: UploadFile) -> bytes:
    """Read an uploaded CSV, rejecting files over the size limit."""

    content = await file.read(MAX_UPLOAD_BYTES + 1)

    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=422,
            detail="File too large. Maximum size is 10 MB.",
        )

    return content


    @router.post(
    "/import/preview",
    response_model=CollateralImportPreview,
    status_code=200,
)
async def preview_collateral_import(
    file: UploadFile = File(...),
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    user: User = Depends(require_roles(*EDITOR_ROLES)),
):
    """Validate a collateral CSV without writing to the database."""

    try:
        content = await _read_csv_upload(file)
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
    '/import',
    response_model=CollateralImportReport,
    status_code=200,
)
async def execute_collateral_csv_import(
    file: UploadFile = File(...),
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*EDITOR_ROLES)),
):
    """Validate and import collateral CSV records for the caller's bank."""

    try:
        content = await _read_csv_upload(file)
        validation_result = validate_collateral_csv(content)

        report = execute_collateral_import(
            db=db,
            organization_id=org.id,
            validation_result=validation_result,
            actor_user_id=user.id,
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
        stmt = stmt.where(
            Collateral.is_archived.is_(False)
        )

    collateral = db.scalars(stmt).first()

    if collateral is None:
        raise HTTPException(
            status_code=404,
            detail="Collateral not found.",
        )

    return collateral


@router.post(
    "",
    response_model=CollateralRead,
    status_code=201,
)
def create_collateral(
    payload: CollateralCreate,
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*EDITOR_ROLES)),
):
    """Create a collateral and audit it in the same transaction."""

    collateral = Collateral(
        organization_id=org.id,
        **payload.model_dump(),
    )

    db.add(collateral)

    try:
        db.flush()

        record_audit_event(
            db,
            organization_id=org.id,
            actor_user_id=user.id,
            action="collateral.created",
            entity_type="collateral",
            entity_id=collateral.id,
            after_data={
                "external_ref": collateral.external_ref,
                "property_type": collateral.property_type,
                "country_code": collateral.country_code,
                "region": collateral.region,
                "city": collateral.city,
                "is_synthetic": collateral.is_synthetic,
            },
        )

        db.commit()

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "A collateral with this external_ref already exists "
                "in this organization."
            ),
        ) from exc

    except Exception:
        db.rollback()
        raise

    db.refresh(collateral)

    return collateral


@router.get(
    "",
    response_model=list[CollateralRead],
)
def list_collaterals(
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    include_archived: bool = Query(False),
):
    stmt = select(Collateral).where(
        Collateral.organization_id == org.id
    )

    if not include_archived:
        stmt = stmt.where(
            Collateral.is_archived.is_(False)
        )

    stmt = (
        stmt.order_by(Collateral.external_ref)
        .limit(limit)
        .offset(offset)
    )

    return db.scalars(stmt).all()


@router.get(
    '/{collateral_id}',
    response_model=CollateralRead,
)
def read_collateral(
    collateral_id: uuid.UUID,
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    include_archived: bool = Query(False),
):
    return _get_collateral_or_404(
        db,
        org.id,
        collateral_id,
        include_archived=include_archived,
    )


@router.patch(
    '/{collateral_id}',
    response_model=CollateralRead,
)
def update_collateral(
    collateral_id: uuid.UUID,
    payload: CollateralUpdate,
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*EDITOR_ROLES)),
):
    """Partially update a collateral record and audit the changes."""

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

    new_latitude = updates.get(
        "latitude",
        collateral.latitude,
    )

    new_longitude = updates.get(
        "longitude",
        collateral.longitude,
    )

    if (new_latitude is None) != (new_longitude is None):
        raise HTTPException(
            status_code=422,
            detail=(
                "latitude and longitude must be provided together."
            ),
        )

    audit_fields = (
        "external_ref",
        "property_type",
        "country_code",
        "region",
        "city",
        "latitude",
        "longitude",
        "is_synthetic",
    )

    before_data = {
        field: getattr(collateral, field)
        for field in audit_fields
    }

    for field, value in updates.items():
        setattr(collateral, field, value)

    after_data = {
        field: getattr(collateral, field)
        for field in audit_fields
    }

    try:
        record_audit_event(
            db,
            organization_id=org.id,
            actor_user_id=user.id,
            action="collateral.updated",
            entity_type="collateral",
            entity_id=collateral.id,
            before_data=before_data,
            after_data=after_data,
        )

        db.commit()

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "The update conflicts with an existing collateral "
                "record in this organization."
            ),
        ) from exc

    except Exception:
        db.rollback()
        raise

    db.refresh(collateral)

    return collateral


@router.delete(
    '/{collateral_id}',
    response_model=CollateralRead,
)
def archive_collateral(
    collateral_id: uuid.UUID,
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):
    """Archive and audit without permanently deleting financial records."""

    collateral = _get_collateral_or_404(
        db,
        org.id,
        collateral_id,
    )

    before_data = {
        "is_archived": False,
    }

    collateral.is_archived = True

    after_data = {
        "is_archived": True,
    }

    try:
        record_audit_event(
            db,
            organization_id=org.id,
            actor_user_id=user.id,
            action="collateral.archived",
            entity_type="collateral",
            entity_id=collateral.id,
            before_data=before_data,
            after_data=after_data,
        )

        db.commit()

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to archive this collateral.",
        ) from exc

    except Exception:
        db.rollback()
        raise

    db.refresh(collateral)

    return collateral


@router.post(
    '/{collateral_id}/restore',
    response_model=CollateralRead,
)
def restore_collateral(
    collateral_id: uuid.UUID,
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(UserRole.ADMIN)
    ),
):
    """Restore an archived collateral and audit the restoration."""

    collateral = _get_collateral_or_404(
        db,
        org.id,
        collateral_id,
        include_archived=True,
    )

    if not collateral.is_archived:
        raise HTTPException(
            status_code=409,
            detail="Collateral is not archived.",
        )

    before_data = {
        "is_archived": True,
    }

    collateral.is_archived = False

    after_data = {
        "is_archived": False,
    }

    try:
        record_audit_event(
            db,
            organization_id=org.id,
            actor_user_id=user.id,
            action="collateral.restored",
            entity_type="collateral",
            entity_id=collateral.id,
            before_data=before_data,
            after_data=after_data,
        )

        db.commit()

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to restore this collateral.",
        ) from exc

    except Exception:
        db.rollback()
        raise

    db.refresh(collateral)

    return collateral


@router.post(
    '/{collateral_id}/valuations',
    response_model=ValuationRead,
    status_code=201,
)
def create_valuation(
    collateral_id: uuid.UUID,
    payload: ValuationCreate,
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*EDITOR_ROLES)),
):
    """Create a valuation and record its audit event atomically."""

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

    try:
        db.flush()

        record_audit_event(
            db,
            organization_id=org.id,
            actor_user_id=user.id,
            action="valuation.created",
            entity_type="valuation",
            entity_id=valuation.id,
            after_data={
                "collateral_id": str(collateral.id),
                "value_amount": str(valuation.value_amount),
                "currency": valuation.currency,
                "valuation_date": str(valuation.valuation_date),
                "source": valuation.source,
                "is_synthetic": valuation.is_synthetic,
            },
        )

        db.commit()

    except IntegrityError as exc:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Unable to create this valuation.",
        ) from exc

    except Exception:
        db.rollback()
        raise

    db.refresh(valuation)

    return valuation


@router.get(
    '/{collateral_id}/valuations',
    response_model=list[ValuationRead],
)
def list_valuations(
    collateral_id: uuid.UUID,
    org: Organization = Depends(
        get_authorized_organization_or_404
    ),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
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
        .where(
            Valuation.collateral_id == collateral.id
        )
        .order_by(
            Valuation.valuation_date.desc(),
            Valuation.id,
        )
        .limit(limit)
        .offset(offset)
    )

    return db.scalars(stmt).all()
