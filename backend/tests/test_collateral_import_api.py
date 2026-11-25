"""API tests for authenticated collateral CSV preview uploads."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401
from ccr.core.security import hash_password
from ccr.db.base import Base
from ccr.db.session import get_db
from ccr.main import app
from ccr.models import Collateral, Organization, User


def create_test_engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def create_organization(client):
    """Create a test organization and return its ID and JWT headers."""
    response = client.post(
        "/api/v1/organizations",
        json={"name": f"CSV Test Bank {uuid.uuid4().hex[:8]}"},
    )
    assert response.status_code == 201, response.text

    organization_id = response.json()["id"]
    password = "Test-Password-2026!"
    email = f"csv-{uuid.uuid4().hex}@example.com"

    with Session(client.test_engine) as db:
        organization = db.get(
            Organization,
            uuid.UUID(organization_id),
        )
        assert organization is not None

        user = User(
            organization_id=organization.id,
            email=email,
            full_name="CSV Test Admin",
            role="admin",
            is_active=True,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.commit()

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert login_response.status_code == 200, login_response.text

    headers = {
        "Authorization": (
            f"Bearer {login_response.json()['access_token']}"
        )
    }

    return organization_id, headers


def upload_csv(client, url, content, headers):
    return client.post(
        url,
        files={
            "file": (
                "collaterals.csv",
                content,
                "text/csv",
            )
        },
        headers=headers,
    )


def preview_url(organization_id):
    return (
        f"/api/v1/organizations/{organization_id}"
        "/collaterals/import/preview"
    )


def import_url(organization_id):
    return (
        f"/api/v1/organizations/{organization_id}"
        "/collaterals/import"
    )


def setup_test_app():
    engine = create_test_engine()
    Base.metadata.create_all(engine)

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    client.test_engine = engine

    return client, engine


def cleanup_test_app(engine):
    app.dependency_overrides.clear()
    engine.dispose()


def test_preview_valid_csv():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            csv_content = (
                b"external_ref,property_type,is_synthetic\n"
                b"C-001,villa,true\n"
                b"C-002,apartment,false\n"
            )

            response = upload_csv(
                client,
                preview_url(organization_id),
                csv_content,
                headers,
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

            # Preview must never write records to the database.
            assert collateral_count == 0
    finally:
        cleanup_test_app(engine)


def test_preview_invalid_csv_returns_422():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            csv_content = (
                b"external_ref,property_type\n"
                b"C-001,villa\n"
            )

            response = upload_csv(
                client,
                preview_url(organization_id),
                csv_content,
                headers,
            )

            assert response.status_code == 422
            assert "detail" in response.json()
    finally:
        cleanup_test_app(engine)


def test_preview_empty_file_returns_422():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            response = upload_csv(
                client,
                preview_url(organization_id),
                b"",
                headers,
            )

            assert response.status_code == 422
    finally:
        cleanup_test_app(engine)


def test_preview_invalid_encoding_returns_422():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            response = upload_csv(
                client,
                preview_url(organization_id),
                b"\xff\xfe\xfa",
                headers,
            )

            assert response.status_code == 422
    finally:
        cleanup_test_app(engine)


def test_preview_file_over_10mb_returns_422():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            oversized_content = (
                b"external_ref,property_type,is_synthetic\n"
                + b"A" * (10 * 1024 * 1024)
            )

            response = upload_csv(
                client,
                preview_url(organization_id),
                oversized_content,
                headers,
            )

            assert response.status_code == 422
    finally:
        cleanup_test_app(engine)


def test_preview_unknown_organization_returns_404():
    client, engine = setup_test_app()

    try:
        with client:
            _, headers = create_organization(client)

            response = upload_csv(
                client,
                preview_url(
                    "00000000-0000-0000-0000-000000000000"
                ),
                (
                    b"external_ref,property_type,is_synthetic\n"
                    b"C-001,villa,true\n"
                ),
                headers,
            )

            assert response.status_code == 404
    finally:
        cleanup_test_app(engine)


def test_preview_duplicate_external_refs_marks_both_rows_invalid():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            csv_content = (
                b"external_ref,property_type,is_synthetic\n"
                b"C-001,villa,true\n"
                b"C-001,apartment,true\n"
            )

            response = upload_csv(
                client,
                preview_url(organization_id),
                csv_content,
                headers,
            )

            assert response.status_code == 200, response.text

            data = response.json()

            assert data["total_rows"] == 2
            assert data["valid_rows"] == 0
            assert data["invalid_rows"] == 2
            assert all(
                not row["is_valid"]
                for row in data["rows"]
            )

            duplicate_issues = [
                issue
                for issue in data["issues"]
                if issue["code"] == "DUPLICATE_EXTERNAL_REF"
            ]

            assert len(duplicate_issues) == 2
    finally:
        cleanup_test_app(engine)


def test_preview_rejects_more_than_10000_rows():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            header = "external_ref,property_type,is_synthetic\n"
            rows = "".join(
                f"C-{number},villa,true\n"
                for number in range(1, 10002)
            )

            response = upload_csv(
                client,
                preview_url(organization_id),
                (header + rows).encode("utf-8"),
                headers,
            )

            assert response.status_code == 422
            assert "detail" in response.json()
    finally:
        cleanup_test_app(engine)


def test_preview_malformed_csv_returns_422():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            csv_content = (
                b"external_ref,property_type,is_synthetic\n"
                b'"C-001,villa,true\n'
            )

            response = upload_csv(
                client,
                preview_url(organization_id),
                csv_content,
                headers,
            )

            assert response.status_code == 422
            assert "detail" in response.json()
    finally:
        cleanup_test_app(engine)


def test_preview_accepts_owner_reference():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            csv_content = (
                b"external_ref,owner_reference,"
                b"property_type,is_synthetic\n"
                b"C-OWNER-001,OWNER-001,villa,true\n"
            )

            response = upload_csv(
                client,
                preview_url(organization_id),
                csv_content,
                headers,
            )

            assert response.status_code == 200, response.text

            data = response.json()

            assert data["total_rows"] == 1
            assert data["valid_rows"] == 1
            assert data["invalid_rows"] == 0
            assert data["rows"][0]["is_valid"] is True

            # Preview must not persist the collateral.
            with Session(engine) as session:
                collateral_count = session.scalar(
                    select(func.count()).select_from(Collateral)
                )

            assert collateral_count == 0
    finally:
        cleanup_test_app(engine)


def test_preview_rejects_owner_reference_over_100_characters():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            long_owner_reference = "O" * 101

            csv_content = (
                "external_ref,owner_reference,"
                "property_type,is_synthetic\n"
                f"C-OWNER-002,{long_owner_reference},villa,true\n"
            ).encode("utf-8")

            response = upload_csv(
                client,
                preview_url(organization_id),
                csv_content,
                headers,
            )

            assert response.status_code == 200, response.text

            data = response.json()

            assert data["total_rows"] == 1
            assert data["valid_rows"] == 0
            assert data["invalid_rows"] == 1
            assert data["rows"][0]["is_valid"] is False

            owner_reference_issues = [
                issue
                for issue in data["rows"][0]["issues"]
                if issue["field"] == "owner_reference"
            ]

            assert owner_reference_issues
    finally:
        cleanup_test_app(engine)


def test_api_import_persists_owner_reference_and_blank_as_null():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            csv_content = (
                b"external_ref,owner_reference,"
                b"property_type,is_synthetic\n"
                b"C-IMPORT-001,OWNER-001,villa,true\n"
                b"C-IMPORT-002,,apartment,false\n"
            )

            response = upload_csv(
                client,
                import_url(organization_id),
                csv_content,
                headers,
            )

            assert response.status_code == 200, response.text

            report = response.json()

            assert report["total_rows"] == 2
            assert report["imported_rows"] == 2
            assert report["skipped_rows"] == 0
            assert report["failed_rows"] == 0

            with Session(engine) as session:
                imported_collaterals = session.scalars(
                    select(Collateral).where(
                        Collateral.organization_id
                        == uuid.UUID(organization_id),
                        Collateral.external_ref.in_(
                            ["C-IMPORT-001", "C-IMPORT-002"]
                        ),
                    )
                ).all()

                by_external_ref = {
                    collateral.external_ref: collateral
                    for collateral in imported_collaterals
                }

            assert len(by_external_ref) == 2

            assert (
                by_external_ref["C-IMPORT-001"].owner_reference
                == "OWNER-001"
            )

            assert (
                by_external_ref["C-IMPORT-002"].owner_reference
                is None
            )
    finally:
        cleanup_test_app(engine)
def test_api_import_skips_existing_external_ref_without_overwriting():
    client, engine = setup_test_app()

    try:
        with client:
            organization_id, headers = create_organization(client)

            organization_uuid = uuid.UUID(organization_id)

            # Create a collateral that already exists.
            with Session(engine) as session:
                existing = Collateral(
                    organization_id=organization_uuid,
                    external_ref="C-EXISTING-001",
                    owner_reference="OWNER-ORIGINAL",
                    property_type="villa",
                    is_synthetic=True,
                )
                session.add(existing)
                session.commit()

            csv_content = (
                b"external_ref,owner_reference,"
                b"property_type,is_synthetic\n"
                b"C-EXISTING-001,OWNER-CHANGED,apartment,false\n"
                b"C-NEW-001,OWNER-NEW,villa,true\n"
            )

            response = upload_csv(
                client,
                import_url(organization_id),
                csv_content,
                headers,
            )

            assert response.status_code == 200, response.text

            report = response.json()

            assert report["total_rows"] == 2
            assert report["imported_rows"] == 1
            assert report["skipped_rows"] == 1
            assert report["failed_rows"] == 0

            assert any(
                issue["code"] == "EXTERNAL_REF_ALREADY_EXISTS"
                for issue in report["issues"]
            )

            with Session(engine) as session:
                collaterals = session.scalars(
                    select(Collateral).where(
                        Collateral.organization_id == organization_uuid
                    )
                ).all()

                by_external_ref = {
                    collateral.external_ref: collateral
                    for collateral in collaterals
                }

            # Existing record must remain unchanged.
            assert (
                by_external_ref["C-EXISTING-001"].owner_reference
                == "OWNER-ORIGINAL"
            )

            assert (
                by_external_ref["C-EXISTING-001"].property_type
                == "villa"
            )

            # New record must be imported.
            assert "C-NEW-001" in by_external_ref

            assert (
                by_external_ref["C-NEW-001"].owner_reference
                == "OWNER-NEW"
            )

            # Exactly two records: the original and the new one.
            assert len(by_external_ref) == 2

    finally:
        cleanup_test_app(engine)
