"""DEVELOPMENT-ONLY routes for organizations.

There is no login yet (Phase 6). These routes are only enabled when the
ENVIRONMENT setting is "development" or "test".
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ccr.api.deps import get_organization_or_404
from ccr.db.session import get_db
from ccr.models import Organization
from ccr.schemas.organization import OrganizationCreate, OrganizationRead

router = APIRouter(prefix="/organizations", tags=["organizations (development only)"])


@router.post("", response_model=OrganizationRead, status_code=201)
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db)):
    org = Organization(name=payload.name)
    db.add(org)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="An organization with this name already exists."
        )
    db.refresh(org)
    return org


@router.get("/{organization_id}", response_model=OrganizationRead)
def read_organization(org: Organization = Depends(get_organization_or_404)):
    return org
