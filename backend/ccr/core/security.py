"""Password hashing and login tokens.

- Passwords are hashed with Argon2. The plain password is never stored.
- Tokens are signed JWTs that carry only the user id. Role and organization
  are always read from the database, so changes take effect immediately.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from ccr.core.config import Settings

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "climate-guard-ai"
MIN_SECRET_LENGTH = 32


class AuthNotConfiguredError(RuntimeError):
    """JWT_SECRET is missing or too short, so login must stay disabled."""


class InvalidTokenError(Exception):
    """The token is missing a field, expired, forged, or malformed."""


_hasher = PasswordHasher()
# Used to spend the same time when the email is unknown (hides which emails exist).
_DUMMY_HASH = _hasher.hash("dummy-password-used-only-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """True only if the password matches. Never raises for bad input."""
    hash_to_check = stored_hash or _DUMMY_HASH
    try:
        matches = _hasher.verify(hash_to_check, password)
    except (VerificationError, InvalidHashError):
        return False
    return bool(matches) and stored_hash is not None


def _secret(settings: Settings) -> str:
    if len(settings.jwt_secret) < MIN_SECRET_LENGTH:
        raise AuthNotConfiguredError(
            "JWT_SECRET must be set to at least 32 characters to enable login."
        )
    return settings.jwt_secret


def create_access_token(
    user_id: uuid.UUID, settings: Settings, now: datetime | None = None
) -> str:
    issued_at = now or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        "iss": JWT_ISSUER,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(payload, _secret(settings), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    """Return the user id inside a valid token, or raise InvalidTokenError."""
    secret = _secret(settings)
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise InvalidTokenError("Invalid token.") from exc
