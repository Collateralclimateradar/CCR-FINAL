
"""Tests for transactional collateral CSV import execution."""

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ccr.db.base import Base
from ccr.models import Collateral, Organization
from ccr.services.collateral_import import validate_collateral_csv
from ccr.services.collateral_import_execution import (
    CollateralImportConflict,
    execute_collateral_import,
)


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    engine.dispose()


def create_organization(db, name):
    organization = Organization(name=name)
    db.add(organization)
    db.commit()
    db.refresh(organization)
    return organization


def make_validation(csv_content):
    return validate_collateral_csv(
        csv_content.encode("utf-8")
    )


def collateral_count(db, organization_id):
    return db.scalar(
        select(func.count())
        .select_from(Collateral)
        .where(
            Collateral.organization_id == organization_id
        )
    )


def test_import_saves_valid_records(db_session):
    organization = create_organization(
        db_session,
        "Bank A",
    )

    result = make_validation(
        "external_ref,property_type,is_synthetic\n"
        "C-001,villa,true\n"
        "C-002,apartment,false\n"
    )

    report = execute_collateral_import(
        db_session,
        organization.id,
        result,
    )

    assert report.total_rows == 2
    assert report.imported_rows == 2
    assert report.skipped_rows == 0
    assert report.failed_rows == 0

    assert collateral_count(
        db_session,
        organization.id,
    ) == 2


def test_invalid_rows_are_skipped(db_session):
    organization = create_organization(
        db_session,
        "Bank B",
    )

    result = make_validation(
        "external_ref,property_type,is_synthetic\n"
        "C-001,villa,true\n"
        "C-002,,true\n"
    )

    report = execute_collateral_import(
        db_session,
        organization.id,
        result,
    )

    assert report.total_rows == 2
    assert report.imported_rows == 1
    assert report.skipped_rows == 1
    assert report.failed_rows == 0

    assert collateral_count(
        db_session,
        organization.id,
    ) == 1


def test_existing_reference_is_skipped(db_session):
    organization = create_organization(
        db_session,
        "Bank C",
    )

    db_session.add(
        Collateral(
            organization_id=organization.id,
            external_ref="C-001",
            property_type="villa",
            is_synthetic=True,
        )
    )
    db_session.commit()

    result = make_validation(
        "external_ref,property_type,is_synthetic\n"
        "C-001,apartment,true\n"
        "C-002,villa,true\n"
    )

    report = execute_collateral_import(
        db_session,
        organization.id,
        result,
    )

    assert report.total_rows == 2
    assert report.imported_rows == 1
    assert report.skipped_rows == 1
    assert report.failed_rows == 0

    assert collateral_count(
        db_session,
        organization.id,
    ) == 2

    assert any(
        issue.code == "EXTERNAL_REF_ALREADY_EXISTS"
        for issue in report.issues
    )


def test_same_reference_in_another_organization_is_allowed(
    db_session,
):
    organization_a = create_organization(
        db_session,
        "Bank D",
    )

    organization_b = create_organization(
        db_session,
        "Bank E",
    )

    db_session.add(
        Collateral(
            organization_id=organization_a.id,
            external_ref="SHARED-001",
            property_type="villa",
            is_synthetic=True,
        )
    )
    db_session.commit()

    result = make_validation(
        "external_ref,property_type,is_synthetic\n"
        "SHARED-001,apartment,true\n"
    )

    report = execute_collateral_import(
        db_session,
        organization_b.id,
        result,
    )

    assert report.imported_rows == 1
    assert report.skipped_rows == 0

    assert collateral_count(
        db_session,
        organization_a.id,
    ) == 1

    assert collateral_count(
        db_session,
        organization_b.id,
    ) == 1


def test_duplicate_references_inside_csv_are_skipped(
    db_session,
):
    organization = create_organization(
        db_session,
        "Bank F",
    )

    result = make_validation(
        "external_ref,property_type,is_synthetic\n"
        "DUP-001,villa,true\n"
        "DUP-001,apartment,true\n"
        "UNIQUE-001,villa,false\n"
    )

    assert result.preview.valid_rows == 1
    assert result.preview.invalid_rows == 2
    assert len(result.valid_records) == 1

    report = execute_collateral_import(
        db_session,
        organization.id,
        result,
    )

    assert report.total_rows == 3
    assert report.imported_rows == 1
    assert report.skipped_rows == 2
    assert report.failed_rows == 0

    assert collateral_count(
        db_session,
        organization.id,
    ) == 1


def test_archived_reference_is_also_skipped(db_session):
    organization = create_organization(
        db_session,
        "Bank G",
    )

    db_session.add(
        Collateral(
            organization_id=organization.id,
            external_ref="ARCHIVED-001",
            property_type="villa",
            is_synthetic=True,
            is_archived=True,
        )
    )
    db_session.commit()

    result = make_validation(
        "external_ref,property_type,is_synthetic\n"
        "ARCHIVED-001,apartment,true\n"
    )

    report = execute_collateral_import(
        db_session,
        organization.id,
        result,
    )

    assert report.imported_rows == 0
    assert report.skipped_rows == 1

    assert collateral_count(
        db_session,
        organization.id,
    ) == 1


def test_integrity_error_rolls_back_entire_import(
    db_session,
    monkeypatch,
):
    organization = create_organization(
        db_session,
        "Bank H",
    )

    result = make_validation(
        "external_ref,property_type,is_synthetic\n"
        "C-101,villa,true\n"
        "C-102,apartment,false\n"
    )

    def fail_commit():
        raise IntegrityError(
            "INSERT",
            {},
            Exception("Simulated database integrity error"),
        )

    monkeypatch.setattr(
        db_session,
        "commit",
        fail_commit,
    )

    with pytest.raises(CollateralImportConflict):
        execute_collateral_import(
            db_session,
            organization.id,
            result,
        )

    assert collateral_count(
        db_session,
        organization.id,
    ) == 0
