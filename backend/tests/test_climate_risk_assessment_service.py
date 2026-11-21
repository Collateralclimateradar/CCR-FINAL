
"""Tests for climate risk assessment creation service."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ccr.services.climate_risk_assessment_service import (
    CollateralNotFoundError,
    create_climate_risk_assessment,
)


class FakeResult:
    def __init__(self, collateral):
        self.collateral = collateral

    def scalar_one_or_none(self):
        return self.collateral


class FakeSession:
    def __init__(self, collateral):
        self.collateral = collateral
        self.added = []
        self.flush_called = False
        self.executed_statement = None

    def execute(self, statement):
        self.executed_statement = statement
        return FakeResult(self.collateral)

    def add(self, instance):
        self.added.append(instance)

    def flush(self):
        self.flush_called = True


@pytest.fixture
def identifiers():
    return {
        "organization_id": uuid4(),
        "collateral_id": uuid4(),
    }


@pytest.fixture
def collateral(identifiers):
    return SimpleNamespace(
        id=identifiers["collateral_id"],
        organization_id=identifiers["organization_id"],
        is_synthetic=False,
    )


def test_creates_assessment_and_derives_risk_level(
    identifiers, collateral
):
    db = FakeSession(collateral)

    assessment = create_climate_risk_assessment(
        db,
        organization_id=identifiers["organization_id"],
        collateral_id=identifiers["collateral_id"],
        hazard_type="flood",
        risk_score=Decimal("80"),
        assessment_date=date(2026, 1, 15),
        source="test-source",
    )

    assert assessment.risk_score == Decimal("80")
    assert assessment.risk_level == "very_high"
    assert assessment.hazard_type == "flood"
    assert assessment.source == "test-source"
    assert assessment.model_version == "1.0"
    assert assessment.is_synthetic is False
    assert db.added == [assessment]
    assert db.flush_called is True


def test_inherits_synthetic_status_from_collateral(
    identifiers, collateral
):
    collateral.is_synthetic = True
    db = FakeSession(collateral)

    assessment = create_climate_risk_assessment(
        db,
        organization_id=identifiers["organization_id"],
        collateral_id=identifiers["collateral_id"],
        hazard_type="extreme_heat",
        risk_score=40,
        assessment_date=date(2026, 1, 15),
    )

    assert assessment.is_synthetic is True


def test_rejects_unsupported_hazard(identifiers, collateral):
    db = FakeSession(collateral)

    with pytest.raises(ValueError, match="Unsupported"):
        create_climate_risk_assessment(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            hazard_type="earthquake",
            risk_score=40,
            assessment_date=date(2026, 1, 15),
        )

    assert db.added == []
    assert db.flush_called is False


def test_rejects_invalid_score(identifiers, collateral):
    db = FakeSession(collateral)

    with pytest.raises(ValueError, match="between 0 and 100"):
        create_climate_risk_assessment(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            hazard_type="flood",
            risk_score=101,
            assessment_date=date(2026, 1, 15),
        )

    assert db.added == []
    assert db.flush_called is False


def test_rejects_collateral_not_owned_by_organization(identifiers):
    db = FakeSession(None)

    with pytest.raises(CollateralNotFoundError):
        create_climate_risk_assessment(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            hazard_type="coastal",
            risk_score=60,
            assessment_date=date(2026, 1, 15),
        )

    assert db.added == []
    assert db.flush_called is False


def test_rejects_empty_model_version(identifiers, collateral):
    db = FakeSession(collateral)

    with pytest.raises(ValueError, match="Model version"):
        create_climate_risk_assessment(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            hazard_type="flood",
            risk_score=50,
            assessment_date=date(2026, 1, 15),
            model_version="   ",
        )

    assert db.added == []
    assert db.flush_called is False


def test_rejects_invalid_assessment_date(identifiers, collateral):
    db = FakeSession(collateral)

    with pytest.raises(ValueError, match="Assessment date"):
        create_climate_risk_assessment(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            hazard_type="flood",
            risk_score=50,
            assessment_date="2026-01-15",
        )

    assert db.added == []
    assert db.flush_called is False
