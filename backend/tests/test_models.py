"""Tests for the database tables, using a temporary in-memory database."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ccr.db.base import Base
from ccr.models import Collateral, Organization, User, Valuation


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


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
        Collateral(organization_id=org.id, external_ref="X", property_type="villa")
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_user_role_must_be_valid(session):
    org = make_org(session)
    session.add(
        User(organization_id=org.id, email="a@b.com", full_name="A", role="boss")
    )
    with pytest.raises(IntegrityError):
        session.commit()
