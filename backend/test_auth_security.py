
"""Security tests for login and JWT authentication."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401
from ccr.core.config import get_settings
from ccr.core.security import (
    create_access_token,
    hash_password,
)
from ccr.db.base import Base
from ccr.db.session import get_db
from ccr.main import app
from ccr.models import Organization, User


@pytest.fixture
def auth_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client, engine
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


@pytest.fixture
def auth_account(auth_client):
    client, engine = auth_client

    organization_id = uuid.uuid4()
    user_id = uuid.uuid4()

    email = f"security-{uuid.uuid4().hex}@example.com"
    password = "Secure-Test-Password-2026!"

    with Session(engine) as db:
        organization = Organization(
            id=organization_id,
            name=f"Security Test {uuid.uuid4().hex[:8]}",
            is_active=True,
        )

        user = User(
            id=user_id,
            organization_id=organization_id,
            email=email,
            full_name="Security Test User",
            role="admin",
            is_active=True,
            password_hash=hash_password(password),
        )

        db.add_all([organization, user])
        db.commit()

    return {
        "client": client,
        "engine": engine,
        "organization_id": organization_id,
        "user_id": user_id,
        "email": email,
        "password": password,
    }


def test_login_accepts_valid_credentials(auth_account):
    client = auth_account["client"]

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": auth_account["email"],
            "password": auth_account["password"],
        },
    )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["access_token"]
    assert response.json()["expires_in"] > 0


def test_login_rejects_unknown_email(auth_account):
    response = auth_account["client"].post(
        "/api/v1/auth/login",
        json={
            "email": "unknown@example.com",
            "password": auth_account["password"],
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_rejects_wrong_password(auth_account):
    response = auth_account["client"].post(
        "/api/v1/auth/login",
        json={
            "email": auth_account["email"],
            "password": "Definitely-Wrong-Password!",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_login_rejects_inactive_user(auth_account):
    with Session(auth_account["engine"]) as db:
        user = db.get(User, auth_account["user_id"])
        user.is_active = False
        db.commit()

    response = auth_account["client"].post(
        "/api/v1/auth/login",
        json={
            "email": auth_account["email"],
            "password": auth_account["password"],
        },
    )

    assert response.status_code == 401


def test_login_rejects_inactive_organization(auth_account):
    with Session(auth_account["engine"]) as db:
        organization = db.get(
            Organization,
            auth_account["organization_id"],
        )
        organization.is_active = False
        db.commit()

    response = auth_account["client"].post(
        "/api/v1/auth/login",
        json={
            "email": auth_account["email"],
            "password": auth_account["password"],
        },
    )

    assert response.status_code == 401


def test_me_rejects_missing_authorization_header(auth_account):
    response = auth_account["client"].get(
        "/api/v1/auth/me"
    )

    assert response.status_code == 401


def test_me_rejects_invalid_token(auth_account):
    response = auth_account["client"].get(
        "/api/v1/auth/me",
        headers={
            "Authorization": "Bearer invalid-token"
        },
    )

    assert response.status_code == 401


def test_me_rejects_expired_token(auth_account):
    settings = get_settings()

    expired_time = datetime.now(timezone.utc) - timedelta(
        minutes=settings.jwt_expire_minutes + 5
    )

    token = create_access_token(
        auth_account["user_id"],
        settings,
        now=expired_time,
    )

    response = auth_account["client"].get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 401


def test_me_rejects_token_for_inactive_user(auth_account):
    settings = get_settings()

    token = create_access_token(
        auth_account["user_id"],
        settings,
    )

    with Session(auth_account["engine"]) as db:
        user = db.get(User, auth_account["user_id"])
        user.is_active = False
        db.commit()

    response = auth_account["client"].get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 401


def test_me_rejects_token_for_inactive_organization(auth_account):
    settings = get_settings()

    token = create_access_token(
        auth_account["user_id"],
        settings,
    )

    with Session(auth_account["engine"]) as db:
        organization = db.get(
            Organization,
            auth_account["organization_id"],
        )
        organization.is_active = False
        db.commit()

    response = auth_account["client"].get(
        "/api/v1/auth/me",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 401
