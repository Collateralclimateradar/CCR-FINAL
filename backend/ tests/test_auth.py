"""Tests for password hashing, login tokens, and role checks."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401
from ccr.api.auth_deps import require_roles
from ccr.core.config import get_settings
from ccr.core.security import (
    JWT_ALGORITHM,
    JWT_ISSUER,
    create_access_token,
    hash_password,
    verify_password,
)
from ccr.db.base import Base
from ccr.db.session import get_db
from ccr.main import app
from ccr.models import Organization, User, UserRole

PASSWORD = "correct-horse-battery-staple"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"


@pytest.fixture
def env():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    yield TestClient(app), engine
    app.dependency_overrides.clear()


def add_user(
    engine,
    org_name="Bank A",
    email="admin@banka.test",
    role="admin",
    is_active=True,
    org_active=True,
    with_password=True,
):
    with Session(engine) as session:
        org = session.scalars(select(Organization).where(Organization.name == org_name)).first()
        if org is None:
            org = Organization(name=org_name, is_active=org_active)
            session.add(org)
            session.flush()
        user = User(
            organization_id=org.id,
            email=email,
            full_name="Test User",
            role=role,
            is_active=is_active,
            password_hash=hash_password(PASSWORD) if with_password else None,
        )
        session.add(user)
        session.commit()
        return str(user.id), str(org.id)


def login(client, email="admin@banka.test", password=PASSWORD):
    return client.post(LOGIN_URL, json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---- password hashing -------------------------------------------------------


def test_password_is_hashed_not_stored_as_plain_text():
    hashed = hash_password(PASSWORD)
    assert hashed.startswith("$argon2")
    assert PASSWORD not in hashed
    assert hash_password(PASSWORD) != hashed  # random salt each time


def test_verify_password_accepts_only_the_right_password():
    hashed = hash_password(PASSWORD)
    assert verify_password(hashed, PASSWORD) is True
    assert verify_password(hashed, "wrong-password") is False
    assert verify_password("not-a-real-hash", PASSWORD) is False
    assert verify_password(None, PASSWORD) is False


# ---- login ------------------------------------------------------------------


def test_login_returns_token_and_me_works(env):
    client, engine = env
    user_id, org_id = add_user(engine)
    response = login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().jwt_expire_minutes * 60

    me = client.get(ME_URL, headers=bearer(body["access_token"]))
    assert me.status_code == 200
    assert me.json()["id"] == user_id
    assert me.json()["organization_id"] == org_id
    assert "password" not in me.text


def test_login_email_is_case_insensitive(env):
    client, engine = env
    add_user(engine)
    assert login(client, email="ADMIN@BankA.test").status_code == 200


def test_wrong_password_and_unknown_email_give_the_same_answer(env):
    client, engine = env
    add_user(engine)
    wrong_password = login(client, password="not-the-password")
    unknown_email = login(client, email="nobody@banka.test")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_user_without_password_cannot_log_in(env):
    client, engine = env
    add_user(engine, with_password=False)
    assert login(client).status_code == 401


def test_inactive_user_cannot_log_in(env):
    client, engine = env
    add_user(engine, is_active=False)
    assert login(client).status_code == 401


def test_user_of_inactive_organization_cannot_log_in(env):
    client, engine = env
    add_user(engine, org_active=False)
    assert login(client).status_code == 401


def test_login_rejects_oversized_password(env):
    client, engine = env
    add_user(engine)
    assert login(client, password="x" * 1000).status_code == 422


# ---- tokens -----------------------------------------------------------------


def test_missing_or_garbage_token_is_rejected(env):
    client, engine = env
    assert client.get(ME_URL).status_code == 401
    assert client.get(ME_URL, headers=bearer("garbage")).status_code == 401


def test_expired_token_is_rejected(env):
    client, engine = env
    user_id, _ = add_user(engine)
    old = datetime.now(timezone.utc) - timedelta(hours=3)
    token = create_access_token(uuid.UUID(user_id), get_settings(), now=old)
    assert client.get(ME_URL, headers=bearer(token)).status_code == 401


def test_token_signed_with_another_secret_is_rejected(env):
    client, engine = env
    user_id, _ = add_user(engine)
    now = datetime.now(timezone.utc)
    forged = jwt.encode(
        {
            "sub": user_id,
            "iss": JWT_ISSUER,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        "a-completely-different-secret-with-32-plus-characters",
        algorithm=JWT_ALGORITHM,
    )
    assert client.get(ME_URL, headers=bearer(forged)).status_code == 401


def test_unsigned_token_is_rejected(env):
    client, engine = env
    user_id, _ = add_user(engine)
    now = datetime.now(timezone.utc)
    unsigned = jwt.encode(
        {
            "sub": user_id,
            "iss": JWT_ISSUER,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=5)).timestamp()),
        },
        None,
        algorithm="none",
    )
    assert client.get(ME_URL, headers=bearer(unsigned)).status_code == 401


def test_deactivating_a_user_stops_an_existing_token(env):
    client, engine = env
    user_id, _ = add_user(engine)
    token = login(client).json()["access_token"]
    assert client.get(ME_URL, headers=bearer(token)).status_code == 200
    with Session(engine) as session:
        session.get(User, uuid.UUID(user_id)).is_active = False
        session.commit()
    assert client.get(ME_URL, headers=bearer(token)).status_code == 401


def test_role_comes_from_the_database_not_the_token(env):
    client, engine = env
    user_id, _ = add_user(engine, role="admin")
    token = login(client).json()["access_token"]
    with Session(engine) as session:
        session.get(User, uuid.UUID(user_id)).role = "viewer"
        session.commit()
    assert client.get(ME_URL, headers=bearer(token)).json()["role"] == "viewer"


def test_login_is_disabled_when_secret_is_too_short(env, monkeypatch):
    client, engine = env
    add_user(engine)
    monkeypatch.setenv("JWT_SECRET", "too-short")
    get_settings.cache_clear()
    try:
        assert login(client).status_code == 503
    finally:
        get_settings.cache_clear()


# ---- roles ------------------------------------------------------------------


def test_require_roles_allows_and_blocks_by_role(env):
    client, engine = env
    add_user(engine, email="admin@banka.test", role="admin")
    add_user(engine, email="viewer@banka.test", role="viewer")

    probe = FastAPI()

    @probe.get("/admin-only")
    def admin_only(user: User = Depends(require_roles(UserRole.ADMIN))):
        return {"ok": True}

    probe.dependency_overrides[get_db] = app.dependency_overrides[get_db]
    probe_client = TestClient(probe)

    admin_token = login(client, email="admin@banka.test").json()["access_token"]
    viewer_token = login(client, email="viewer@banka.test").json()["access_token"]

    assert probe_client.get("/admin-only").status_code == 401
    assert probe_client.get("/admin-only", headers=bearer(viewer_token)).status_code == 403
    assert probe_client.get("/admin-only", headers=bearer(admin_token)).status_code == 200
