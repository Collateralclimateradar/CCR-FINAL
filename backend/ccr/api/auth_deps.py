"""Who is calling? Turns a login token into a user, and checks roles.

Everything the caller may see is decided from the database record of the user,
never from values the caller sends.
"""
import logging
import uuid

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ccr.core.config import get_settings
from ccr.core.security import (
    AuthNotConfiguredError,
    InvalidTokenError,
    decode_access_token,
)
from ccr.db.session import get_db
from ccr.models import Organization, User, UserRole

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise _unauthorized()
    try:
        user_id: uuid.UUID = decode_access_token(credentials.credentials, get_settings())
    except AuthNotConfiguredError:
        logger.error("Login is not configured: JWT_SECRET is missing or too short.")
        raise HTTPException(status_code=503, detail="Authentication is not configured.")
    except InvalidTokenError:
        raise _unauthorized()

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    organization = db.get(Organization, user.organization_id)
    if organization is None or not organization.is_active:
        raise _unauthorized()
    return user


def require_roles(*allowed: UserRole):
    """Dependency factory: only users with one of these roles may continue."""
    allowed_values = {role.value for role in allowed}

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_values:
            raise HTTPException(status_code=403, detail="Not allowed for your role.")
        return user

    return checker
