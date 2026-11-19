
"""Shared building blocks for API routes."""
import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ccr.db.session import get_db
from ccr.models import Organization, User
from ccr.api.auth_deps import get_current_user


def get_organization_or_404(
    organization_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Organization:
    """Find an organization by ID, or answer 404."""
    org = db.get(Organization, organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found.")
    return org


def get_authorized_organization_or_404(
    organization_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Organization:
    """Return the caller's organization only if it matches the URL.

    Users cannot access another organization's resources by changing the
    organization_id in the URL. A 404 is returned to avoid disclosing
    whether another organization exists.
    """
    if user.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Organization not found.")

    organization = db.get(Organization, organization_id)
    if organization is None or not organization.is_active:
        raise HTTPException(status_code=404, detail="Organization not found.")

    return organization
