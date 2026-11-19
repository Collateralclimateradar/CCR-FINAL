
"""Login routes. These are NOT development-only: they are always available."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ccr.api.auth_deps import get_current_user
from ccr.core.config import get_settings
from ccr.core.security import (
    AuthNotConfiguredError,
    create_access_token,
    verify_password,
)
from ccr.db.session import get_db
from ccr.models import Organization, User
from ccr.schemas.auth import CurrentUser, LoginRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _bad_login() -> HTTPException:
    return HTTPException(status_code=401, detail="Invalid email or password.")


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    settings = get_settings()

    stmt = select(User).where(func.lower(User.email) == payload.email.lower())
    user = db.scalars(stmt).first()

    # Always verify a hash, including when the user does not exist.
    password_ok = verify_password(
        user.password_hash if user else None,
        payload.password,
    )

    if user is None or not password_ok or not user.is_active:
        raise _bad_login()

    organization = db.get(Organization, user.organization_id)
    if organization is None or not organization.is_active:
        raise _bad_login()

    try:
        token = create_access_token(user.id, settings)
    except AuthNotConfiguredError:
        logger.error("Login is not configured: JWT_SECRET is missing or too short.")
        raise HTTPException(
            status_code=503,
            detail="Authentication is not configured.",
        )

    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
    )


@router.get("/me", response_model=CurrentUser)
def read_me(user: User = Depends(get_current_user)):
    return user
