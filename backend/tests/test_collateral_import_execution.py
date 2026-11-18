
"""Tests for executing collateral CSV imports."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import ccr.models  # noqa: F401
from ccr.db.base import Base
from ccr.models import Collateral, Organization
from ccr.schemas.collateral_import import (
    CollateralImportPreview,
    CollateralImportRowPreview,
)
from ccr.services.collateral_import import (
    CollateralImportConflict,
    execute_collateral_import,
    validate_collateral_csv,
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


@pytest.fixture
def organization(db_session):
    organization = Organization(name="Import Test Bank")
    db_session.add(organization)
    db_session.commit()
    db_session.refresh(organization)
    return organization


def make_csv(*rows):
    header = "external_ref,property_type,is_synthetic"
    return ("\n".join([header, *rows])).encode("utf-8")


def preview_csv(content):
    return validate_collateral_csv(content)


def count_collaterals(db_session, organization_id):
    return len(
        db_session.scalars(
            select(Collateral).where(
                Collateral.organization_id == organization_id
            )
        ).all()
    )


def test_execute_import_saves_valid_records(
    db_session,
    organization,
):
    content = make_csv(
        "C-001,villa,true",
        "C-002,apartment,false",
    )

    preview = preview_csv(content)

    report = execute_collateral_import(
        db_session,
        organization.id,
        preview,
    )

    assert report.total_rows == 2
    assert report.imported_rows == 2
    assert report.skipped_rows == 0
    assert report.failed_rows == 0
    assert count_collaterals(db_session, organization.id) == 2


def test_execute_import_skips_invalid_rows(
    db_session,
    organization,
):
    content = make_csv(
        "C-001,villa,true",
        ",apartment,true",
    )

    preview = preview_csv(content)

    report = execute_collateral_import(
        db_session,
        organization.id,
        preview,
    )

    assert report.total_rows == 2
    assert report.imported_rows == 1
    assert report.skipped_rows == 1
    assert report.failed_rows == 0
    assert count_collaterals(db_session, organization.id) == 1


def test_execute_import_skips_existing_external_reference(
    db_session,
    organization,
):
    first_preview = preview_csv(
        make_csv("C-001,villa,true")
    )

    first_report = execute_collateral_import(
        db_session,
        organization.id,
        first_preview,
    )

    assert first_report.imported_rows == 1

    second_preview = preview_csv(
        make_csv(
            "C-001,apartment,true",
            "C-002,villa,false",
        )
    )

    second_report = execute_collateral_import(
        db_session,
        organization.id,
        second_preview,
    )

    assert second_report.total_rows == 2
    assert second_report.imported_rows == 1
    assert second_report.skipped_rows == 1
    assert count_collaterals(db_session, organization.id) == 2


def test_same_external_reference_allowed_for_another_organization(
    db_session,
    organization,
):
    another_organization = Organization(
        name="Another Import Test Bank"
    )
    db_session.add(another_organization)
    db_session.commit()
    db_session.refresh(another_organization)

    preview = preview_csv(
        make_csv("C-001,villa,true")
    )

    first_report = execute_collateral_import(
        db_session,
        organization.id,
        preview,
    )

    second_report = execute_collateral_import(
        db_session,
        another_organization.id,
        preview,
    )

    assert first_report.imported_rows == 1
    assert second_report.imported_rows == 1

    assert count_collaterals(db_session, organization.id) == 1
    assert count_collaterals(
        db_session,
        another_organization.id,
    ) == 1


def test_execute_import_skips_duplicate_references_in_csv(
    db_session,
    organization,
):
    content = make_csv(
        "C-001,villa,true",
        "C-001,apartment,true",
        "C-002,villa,false",
    )

    preview = preview_csv(content)

    report = execute_collateral_import(
        db_session,
        organization.id,
        preview,
    )

    assert report.total_rows == 3
    assert report.imported_rows == 1
    assert report.skipped_rows == 2
    assert count_collaterals(db_session, organization.id) == 1


def test_execute_import_skips_archived_external_reference(
    db_session,
    organization,
):
    existing = Collateral(
        organization_id=organization.id,
        external_ref="C-001",
        property_type="villa",
        is_synthetic=True,
        is_archived=True,
    )
    db_session.add(existing)
    db_session.commit()

    preview = preview_csv(
        make_csv("C-001,apartment,true")
    )

    report = execute_collateral_import(
        db_session,
        organization.id,
        preview,
    )

    assert report.total_rows == 1
    assert report.imported_rows == 0
    assert report.skipped_rows == 1
    assert count_collaterals(db_session, organization.id) == 1


def test_execute_import_rolls_back_on_integrity_error(
    db_session,
    organization,
    monkeypatch,
):
    content = make_csv("C-001,villa,true")
    preview = preview_csv(content)

    def fail_commit():
        raise IntegrityError(
            "INSERT",
            {},
            Exception("simulated integrity failure"),
        )

    monkeypatch.setattr(db_session, "commit", fail_commit)

    with pytest.raises(CollateralImportConflict):
        execute_collateral_import(
            db_session,
            organization.id,
            preview,
        )

    assert count_collaterals(db_session, organization.id) == 0
