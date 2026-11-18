
"""API integration tests for executing collateral CSV imports."""

import uuid

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
def import_api_client():
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


def create_organization(client, name="Import Test Bank"):
    response = client.post(
        "/api/v1/organizations",
        json={"name": name},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def import_url(organization_id):
    return (
        f"/api/v1/organizations/{organization_id}"
        "/collaterals/import"
    )


def upload_csv(client, organization_id, content):
    return client.post(
        import_url(organization_id),
        files={
            "file": (
                "collaterals.csv",
                content,
                "text/csv",
            )
        },
    )


def collateral_count(engine, organization_id=None):
    with Session(engine) as session:
        stmt = select(func.count()).select_from(Collateral)

        if organization_id is not None:
            organization_uuid = uuid.UUID(str(organization_id))
            stmt = stmt.where(
                Collateral.organization_id == organization_uuid
            )

        return session.scalar(stmt)


def test_import_valid_csv_persists_records(import_api_client):
    client, engine = import_api_client
    organization_id = create_organization(client)

    csv_content = (
        b"external_ref,property_type,is_synthetic\n"
        b"C-001,villa,true\n"
        b"C-002,apartment,false\n"
    )

    response = upload_csv(client, organization_id, csv_content)

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["total_rows"] == 2
    assert data["imported_rows"] == 2
    assert data["skipped_rows"] == 0
    assert data["failed_rows"] == 0
    assert collateral_count(engine, organization_id) == 2


def test_import_skips_invalid_rows_and_imports_valid_rows(
    import_api_client,
):
    client, engine = import_api_client
    organization_id = create_organization(client)

    csv_content = (
        b"external_ref,property_type,is_synthetic\n"
        b"C-001,villa,true\n"
        b",apartment,true\n"
    )

    response = upload_csv(client, organization_id, csv_content)

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["total_rows"] == 2
    assert data["imported_rows"] == 1
    assert data["skipped_rows"] == 1
    assert data["failed_rows"] == 0
    assert collateral_count(engine, organization_id) == 1


def test_import_skips_existing_external_reference(import_api_client):
    client, engine = import_api_client
    organization_id = create_organization(client)

    first_csv = (
        b"external_ref,property_type,is_synthetic\n"
        b"C-001,villa,true\n"
    )

    first_response = upload_csv(
        client,
        organization_id,
        first_csv,
    )
    assert first_response.status_code == 200, first_response.text
    assert first_response.json()["imported_rows"] == 1

    second_csv = (
        b"external_ref,property_type,is_synthetic\n"
        b"C-001,apartment,true\n"
        b"C-002,villa,false\n"
    )

    second_response = upload_csv(
        client,
        organization_id,
        second_csv,
    )

    assert second_response.status_code == 200, second_response.text

    data = second_response.json()

    assert data["total_rows"] == 2
    assert data["imported_rows"] == 1
    assert data["skipped_rows"] == 1
    assert any(
        issue["code"] == "EXTERNAL_REF_ALREADY_EXISTS"
        for issue in data["issues"]
    )
    assert collateral_count(engine, organization_id) == 2


def test_import_duplicate_references_in_csv_are_skipped(
    import_api_client,
):
    client, engine = import_api_client
    organization_id = create_organization(client)

    csv_content = (
        b"external_ref,property_type,is_synthetic\n"
        b"C-001,villa,true\n"
        b"C-001,apartment,true\n"
        b"C-002,villa,false\n"
    )

    response = upload_csv(client, organization_id, csv_content)

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["total_rows"] == 3
    assert data["imported_rows"] == 1
    assert data["skipped_rows"] == 2
    assert collateral_count(engine, organization_id) == 1


def test_same_external_reference_is_allowed_in_another_organization(
    import_api_client,
):
    client, engine = import_api_client

    first_organization_id = create_organization(
        client,
        "First Import Bank",
    )
    second_organization_id = create_organization(
        client,
        "Second Import Bank",
    )

    csv_content = (
        b"external_ref,property_type,is_synthetic\n"
        b"C-001,villa,true\n"
    )

    first_response = upload_csv(
        client,
        first_organization_id,
        csv_content,
    )
    second_response = upload_csv(
        client,
        second_organization_id,
        csv_content,
    )

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text

    assert first_response.json()["imported_rows"] == 1
    assert second_response.json()["imported_rows"] == 1

    assert collateral_count(engine) == 2
    assert collateral_count(engine, first_organization_id) == 1
    assert collateral_count(engine, second_organization_id) == 1


def test_import_unknown_organization_returns_404(import_api_client):
    client, engine = import_api_client

    response = upload_csv(
        client,
        "00000000-0000-0000-0000-000000000000",
        (
            b"external_ref,property_type,is_synthetic\n"
            b"C-001,villa,true\n"
        ),
    )

    assert response.status_code == 404
    assert collateral_count(engine) == 0


def test_import_invalid_csv_structure_returns_422(import_api_client):
    client, engine = import_api_client
    organization_id = create_organization(client)

    response = upload_csv(
        client,
        organization_id,
        (
            b"external_ref,property_type\n"
            b"C-001,villa\n"
        ),
    )

    assert response.status_code == 422
    assert collateral_count(engine, organization_id) == 0


def test_import_oversized_csv_returns_422(import_api_client):
    client, engine = import_api_client
    organization_id = create_organization(client)

    oversized_content = (
        b"external_ref,property_type,is_synthetic\n"
        + b"A" * (10 * 1024 * 1024)
    )

    response = upload_csv(
        client,
        organization_id,
        oversized_content,
    )

    assert response.status_code == 422
    assert collateral_count(engine, organization_id) == 0

