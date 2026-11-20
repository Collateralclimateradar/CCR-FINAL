
"""Tests for database models using an isolated SQLite database."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ccr.db.base import Base
from ccr.models import (
    ClimateRiskAssessment,
    Collateral,
    Organization,
    User,
    Valuation,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    with Session(engine) as db:
        yield db

    engine.dispose()


def make_org(session, name="Test Bank"):
    org = Organization(name=name)
    session.add(org)
    session.flush()
    return org


def make_collateral(org, ref="C-001", **kwargs):
    values = dict(
        organization_id=org.id,
        external_ref=ref,
        property_type="villa",
        is_synthetic=True,
    )
    values.update(kwargs)
    return Collateral(**values)


def make_climate_assessment(org, collateral, **kwargs):
    values = dict(
        organization_id=org.id,
        collateral_id=collateral.id,
        hazard_type="flood",
        risk_level="moderate",
        risk_score=Decimal("45.00"),
        assessment_date=date(2026, 11, 20),
        source="Test climate dataset",
        model_version="1.0",
        is_synthetic=True,
    )
    values.update(kwargs)
    return ClimateRiskAssessment(**values)


def test_collateral_with_valuation_history(session):
    org = make_org(session)
    col = make_collateral(org)
    col.valuations.append(
        Valuation(
            value_amount=Decimal("1500000.00"),
            currency="AED",
            valuation_date=date(2026, 1, 1),
            is_synthetic=True,
        )
    )
    session.add(col)
    session.commit()

    assert len(col.valuations) == 1
    assert col.valuations[0].collateral.external_ref == "C-001"


def test_same_ref_not_allowed_twice_in_one_organization(session):
    org = make_org(session)
    session.add_all([make_collateral(org), make_collateral(org)])

    with pytest.raises(IntegrityError):
        session.commit()


def test_same_ref_allowed_in_different_organizations(session):
    bank_a = make_org(session, "Bank A")
    bank_b = make_org(session, "Bank B")
    session.add_all([make_collateral(bank_a), make_collateral(bank_b)])
    session.commit()


def test_invalid_latitude_is_rejected(session):
    org = make_org(session)
    session.add(make_collateral(org, latitude=Decimal("123.0")))

    with pytest.raises(IntegrityError):
        session.commit()


def test_negative_valuation_is_rejected(session):
    org = make_org(session)
    col = make_collateral(org)
    col.valuations.append(
        Valuation(
            value_amount=Decimal("-1.00"),
            currency="AED",
            valuation_date=date(2026, 1, 1),
            is_synthetic=True,
        )
    )
    session.add(col)

    with pytest.raises(IntegrityError):
        session.commit()


def test_synthetic_flag_is_required(session):
    org = make_org(session)
    session.add(
        Collateral(
            organization_id=org.id,
            external_ref="X",
            property_type="villa",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_user_role_must_be_valid(session):
    org = make_org(session)
    session.add(
        User(
            organization_id=org.id,
            email="a@b.com",
            full_name="A",
            role="boss",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_valid_climate_assessment_can_be_saved(session):
    org = make_org(session)
    collateral = make_collateral(org)
    session.add(collateral)
    session.flush()

    assessment = make_climate_assessment(org, collateral)
    session.add(assessment)
    session.commit()

    saved = session.query(ClimateRiskAssessment).one()
    assert saved.hazard_type == "flood"
    assert saved.risk_level == "moderate"
    assert saved.risk_score == Decimal("45.00")
    assert saved.collateral_id == collateral.id
    assert saved.organization_id == org.id


@pytest.mark.parametrize("score", [Decimal("-0.01"), Decimal("100.01")])
def test_climate_risk_score_out_of_range_is_rejected(session, score):
    org = make_org(session)
    collateral = make_collateral(org)
    session.add(collateral)
    session.flush()

    session.add(make_climate_assessment(org, collateral, risk_score=score))

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("hazard", ["earthquake", "wildfire", "unknown"])
def test_invalid_climate_hazard_is_rejected(session, hazard):
    org = make_org(session)
    collateral = make_collateral(org)
    session.add(collateral)
    session.flush()

    session.add(make_climate_assessment(org, collateral, hazard_type=hazard))

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize("level", ["critical", "unknown", "medium"])
def test_invalid_climate_risk_level_is_rejected(session, level):
    org = make_org(session)
    collateral = make_collateral(org)
    session.add(collateral)
    session.flush()

    session.add(make_climate_assessment(org, collateral, risk_level=level))

    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_climate_assessment_is_rejected(session):
    org = make_org(session)
    collateral = make_collateral(org)
    session.add(collateral)
    session.flush()

    session.add_all(
        [
            make_climate_assessment(org, collateral),
            make_climate_assessment(org, collateral),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_climate_assessment_cannot_use_another_organization_id(session):
    bank_a = make_org(session, "Bank A")
    bank_b = make_org(session, "Bank B")

    collateral = make_collateral(bank_a)
    session.add(collateral)
    session.flush()

    assessment = make_climate_assessment(
        bank_b,
        collateral,
        organization_id=bank_b.id,
    )
    session.add(assessment)

    with pytest.raises(IntegrityError):
        session.commit()
