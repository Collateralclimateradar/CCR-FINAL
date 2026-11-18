
"""API tests for collateral CSV preview uploads."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401
from ccr.db.base import Base
from ccr.db.session import get_db
from ccr.main import app
from ccr.models import Collateral


@pytest.fixture
def api_client():
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

    with TestClient(app) as client:
        yield client, engine

    app.dependency_overrides.clear()
    engine.dispose()


def create_organization(client):
    response = client.post(
        "/api/v1/organizations",
        json={"name": "CSV Test Bank"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def preview_url(organization_id):
    return (
        f"/api/v1/organizations/{organization_id}"
        "/collaterals/import/preview"
    )


def upload_csv(client, url, content):
    return client.post(
        url,
        files={
            "file": (
                "collaterals.csv",
                content,
                "text/csv",
            )
        },
    )


def test_preview_valid_csv(api_client):
    client, engine = api_client
    organization_id = create_organization(client)

    csv_content = (
        b"external_ref,property_type,is_synthetic\n"
        b"C-001,villa,true\n"
        b"C-002,apartment,false\n"
    )

    response = upload_csv(
        client,
        preview_url(organization_id),
        csv_content,
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["total_rows"] == 2
    assert data["valid_rows"] == 2
    assert data["invalid_rows"] == 0
    assert len(data["rows"]) == 2
    assert all(row["is_valid"] for row in data["rows"])

    with Session(engine) as session:
        collateral_count = session.scalar(
            select(func.count()).select_from(Collateral)
        )

    assert collateral_count == 0


def test_preview_invalid_csv_returns_422(api_client):
    client, _ = api_client
    organization_id = create_organization(client)

    csv_content = (
        b"external_ref,property_type\n"
        b"C-001,villa\n"
    )

    response = upload_csv(
        client,
        preview_url(organization_id),
        csv_content,
    )

    assert response.status_code == 422
    assert "detail" in response.json()


def test_preview_empty_file_returns_422(api_client):
    client, _ = api_client
    organization_id = create_organization(client)

    response = upload_csv(
        client,
        preview_url(organization_id),
        b"",
    )

    assert response.status_code == 422


def test_preview_invalid_encoding_returns_422(api_client):
    client, _ = api_client
    organization_id = create_organization(client)

    response = upload_csv(
        client,
        preview_url(organization_id),
        b"\xff\xfe\xfa",
    )

    assert response.status_code == 422


def test_preview_file_over_10mb_returns_422(api_client):
    client, _ = api_client
    organization_id = create_organization(client)

    oversized_content = (
        b"external_ref,property_type,is_synthetic\n"
        + b"A" * (10 * 1024 * 1024)
    )

    response = upload_csv(
        client,
        preview_url(organization_id),
        oversized_content,
    )

    assert response.status_code == 422


def test_preview_unknown_organization_returns_404(api_client):
    client, _ = api_client

    response = upload_csv(
        client,
        preview_url("00000000-0000-0000-0000-000000000000"),
        (
            b"external_ref,property_type,is_synthetic\n"
            b"C-001,villa,true\n"
        ),
    )

    assert response.status_code == 404
