
"""Tests for geographic climate screening of bank collateral."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ccr.services.climate_data_provider import (
    ClimateDataValidationError,
    ClimateHazard,
    ClimateHazardResult,
    HazardLevel,
)
from ccr.services.climate_location_screening import (
    DEFAULT_HAZARDS,
    CollateralLocationMissingError,
    CollateralScreeningNotFoundError,
    screen_collateral_location,
)


class FakeResult:
    def __init__(self, collateral):
        self.collateral = collateral

    def scalar_one_or_none(self):
        return self.collateral


class FakeSession:
    def __init__(self, collateral):
        self.collateral = collateral
        self.executed_statement = None

    def execute(self, statement):
        self.executed_statement = statement
        return FakeResult(self.collateral)


class FakeProvider:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def assess_location(self, *, latitude, longitude, hazards):
        self.calls.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "hazards": hazards,
            }
        )
        return self.results


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
        latitude=Decimal("25.204800"),
        longitude=Decimal("55.270800"),
        is_archived=False,
    )


@pytest.fixture
def valid_result():
    return ClimateHazardResult(
        source="test-provider",
        hazard=ClimateHazard.FLOOD,
        level=HazardLevel.HIGH,
        retrieved_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        latitude=25.2048,
        longitude=55.2708,
        raw_category="High",
        reference_url="https://example.com/source",
    )


def test_returns_validated_results_using_default_hazards(
    identifiers,
    collateral,
    valid_result,
):
    db = FakeSession(collateral)
    provider = FakeProvider([valid_result])

    results = screen_collateral_location(
        db,
        organization_id=identifiers["organization_id"],
        collateral_id=identifiers["collateral_id"],
        provider=provider,
    )

    assert results == [valid_result]
    assert provider.calls == [
        {
            "latitude": 25.2048,
            "longitude": 55.2708,
            "hazards": DEFAULT_HAZARDS,
        }
    ]


def test_passes_custom_hazards_to_provider(
    identifiers,
    collateral,
    valid_result,
):
    db = FakeSession(collateral)
    provider = FakeProvider([valid_result])
    hazards = (ClimateHazard.FLOOD,)

    screen_collateral_location(
        db,
        organization_id=identifiers["organization_id"],
        collateral_id=identifiers["collateral_id"],
        provider=provider,
        hazards=hazards,
    )

    assert provider.calls[0]["hazards"] == hazards


def test_empty_provider_results_are_allowed(
    identifiers,
    collateral,
):
    db = FakeSession(collateral)
    provider = FakeProvider([])

    results = screen_collateral_location(
        db,
        organization_id=identifiers["organization_id"],
        collateral_id=identifiers["collateral_id"],
        provider=provider,
    )

    assert results == []


def test_query_is_scoped_to_organization_and_active_collateral(
    identifiers,
    collateral,
    valid_result,
):
    db = FakeSession(collateral)
    provider = FakeProvider([valid_result])

    screen_collateral_location(
        db,
        organization_id=identifiers["organization_id"],
        collateral_id=identifiers["collateral_id"],
        provider=provider,
    )

    statement = str(db.executed_statement)

    assert "organization_id" in statement
    assert "is_archived" in statement
    assert "collaterals.id" in statement


def test_raises_when_collateral_is_not_found(identifiers):
    db = FakeSession(None)
    provider = FakeProvider([])

    with pytest.raises(CollateralScreeningNotFoundError):
        screen_collateral_location(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            provider=provider,
        )

    assert provider.calls == []


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (None, Decimal("55.270800")),
        (Decimal("25.204800"), None),
        (None, None),
    ],
)
def test_rejects_missing_coordinates(
    identifiers,
    collateral,
    latitude,
    longitude,
):
    collateral.latitude = latitude
    collateral.longitude = longitude

    db = FakeSession(collateral)
    provider = FakeProvider([])

    with pytest.raises(CollateralLocationMissingError):
        screen_collateral_location(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            provider=provider,
        )

    assert provider.calls == []


def test_rejects_provider_without_callable_method(
    identifiers,
    collateral,
):
    db = FakeSession(collateral)

    with pytest.raises(TypeError, match="assess_location"):
        screen_collateral_location(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            provider=object(),
        )


@pytest.mark.parametrize(
    "hazards",
    [
        [ClimateHazard.FLOOD],
        "flood",
        (ClimateHazard.FLOOD, "coastal"),
        None,
    ],
)
def test_rejects_invalid_hazard_collection(
    identifiers,
    collateral,
    hazards,
):
    db = FakeSession(collateral)
    provider = FakeProvider([])

    with pytest.raises(ClimateDataValidationError):
        screen_collateral_location(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            provider=provider,
            hazards=hazards,
        )

    assert provider.calls == []


def test_rejects_duplicate_requested_hazards(
    identifiers,
    collateral,
):
    db = FakeSession(collateral)
    provider = FakeProvider([])
    hazards = (
        ClimateHazard.FLOOD,
        ClimateHazard.FLOOD,
    )

    with pytest.raises(
        ClimateDataValidationError,
        match="duplicates",
    ):
        screen_collateral_location(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            provider=provider,
            hazards=hazards,
        )

    assert provider.calls == []


@pytest.mark.parametrize(
    "provider_results",
    [
        None,
        (),
        "invalid",
        {"hazards": []},
    ],
)
def test_rejects_non_list_provider_response(
    identifiers,
    collateral,
    provider_results,
):
    db = FakeSession(collateral)
    provider = FakeProvider(provider_results)

    with pytest.raises(
        ClimateDataValidationError,
        match="list",
    ):
        screen_collateral_location(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            provider=provider,
        )


def test_rejects_invalid_provider_result(
    identifiers,
    collateral,
):
    db = FakeSession(collateral)
    provider = FakeProvider([{"hazard": "flood"}])

    with pytest.raises(
        ClimateDataValidationError,
        match="ClimateHazardResult",
    ):
        screen_collateral_location(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            provider=provider,
        )


def test_rejects_unrequested_hazard(
    identifiers,
    collateral,
    valid_result,
):
    db = FakeSession(collateral)
    provider = FakeProvider([valid_result])

    with pytest.raises(
        ClimateDataValidationError,
        match="unrequested",
    ):
        screen_collateral_location(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            provider=provider,
            hazards=(ClimateHazard.COASTAL,),
        )


def test_rejects_duplicate_provider_hazards(
    identifiers,
    collateral,
    valid_result,
):
    db = FakeSession(collateral)
    provider = FakeProvider([valid_result, valid_result])

    with pytest.raises(
        ClimateDataValidationError,
        match="duplicate",
    ):
        screen_collateral_location(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            provider=provider,
        )


def test_rejects_result_with_invalid_coordinates(
    identifiers,
    collateral,
    valid_result,
):
    invalid_result = ClimateHazardResult(
        source=valid_result.source,
        hazard=valid_result.hazard,
        level=valid_result.level,
        retrieved_at=valid_result.retrieved_at,
        latitude=95,
        longitude=valid_result.longitude,
    )

    db = FakeSession(collateral)
    provider = FakeProvider([invalid_result])

    with pytest.raises(
        ClimateDataValidationError,
        match="Latitude",
    ):
        screen_collateral_location(
            db,
            organization_id=identifiers["organization_id"],
            collateral_id=identifiers["collateral_id"],
            provider=provider,
        )
