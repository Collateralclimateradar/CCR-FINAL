"""Shared building blocks for API routes."""
import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ccr.db.session import get_db
from ccr.models import Organization


def get_organization_or_404(
    organization_id: uuid.UUID, db: Session = Depends(get_db)
) -> Organization:
    """Find the organization named in the URL, or answer 404."""
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return org
