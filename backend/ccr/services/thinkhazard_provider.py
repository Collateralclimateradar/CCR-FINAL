
"""Tests for the ThinkHazard climate data provider adapter."""

import pytest

from ccr.services.administrative_division import (
    AdministrativeDivision,
    AdministrativeDivisionNotFoundError,
    AdministrativeDivisionResolutionError,
    AdministrativeDivisionValidationError,
)
from ccr.services.climate_data_provider import (
    ClimateDataUnavailableError,
    ClimateDataValidationError,
    ClimateHazard,
    HazardLevel,
)
from ccr.services.thinkhazard_client import (
    ThinkHazardClient,
    ThinkHazardClientError,
    ThinkHazardUnavailableError,
)
from ccr.services.thinkhazard_provider import ThinkHazardProvider


LATITUDE = 25.2048
LONGITUDE = 55.2708
DIVISION_CODE = 12345


class FakeDivisionResolver:
    """Return a configured administrative division."""

    def __init__(self, result=None, error=None):
        self.result = result or AdministrativeDivision(
            code=DIVISION_CODE,
            name="Test Division",
            country="United Arab Emirates",
        )
        self.error = error
        self.calls = []

    def resolve(self, *, latitude, longitude):
        self.calls.append((latitude, longitude))

        if self.error is not None:
            raise self.error

        return self.result


def flood_payload():
    return [
        {
            "hazardtype": {
                "mnemonic": "FL",
                "hazardtype": "River flood",
            },
            "hazardlevel": {
                "mnemonic": "HIG",
                "title": "High",
            },
        },
        {
            "hazardtype": {
                "mnemonic": "CF",
                "hazardtype": "Coastal flood",
            },
            "hazardlevel": {
                "mnemonic": "MED",
                "title": "Medium",
            },
        },
        {
            "hazardtype": {
                "mnemonic": "EH",
                "hazardtype": "Extreme heat",
            },
            "hazardlevel": {
                "mnemonic": "HIG",
                "title": "High",
            },
        },
    ]


@pytest.fixture
def client():
    return ThinkHazardClient()


@pytest.fixture
def resolver():
    return FakeDivisionResolver()


def make_provider(client, resolver):
    return ThinkHazardProvider(
        client=client,
        division_resolver=resolver,
    )


def test_provider_name(client, resolver):
    provider = make_provider(client, resolver)

    assert provider.name == "thinkhazard"


def test_rejects_invalid_client(resolver):
    with pytest.raises(TypeError, match="client"):
        ThinkHazardProvider(
            client=object(),
            division_resolver=resolver,
        )


def test_rejects_missing_resolver(client):
    with pytest.raises(TypeError, match="division_resolver"):
        ThinkHazardProvider(
            client=client,
            division_resolver=None,
        )


def test_returns_normalized_results(
    client,
    resolver,
    monkeypatch,
):
    monkeypatch.setattr(
        client,
        "get_all_hazards",
        lambda code: flood_payload(),
    )

    provider = make_provider(client, resolver)

    results = provider.assess_location(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        hazards=(
            ClimateHazard.FLOOD,
            ClimateHazard.COASTAL,
            ClimateHazard.EXTREME_HEAT,
        ),
    )

    assert len(results) == 3
    assert {result.hazard for result in results} == {
        ClimateHazard.FLOOD,
        ClimateHazard.COASTAL,
        ClimateHazard.EXTREME_HEAT,
    }

    flood = next(
        result for result in results
        if result.hazard == ClimateHazard.FLOOD
    )

    assert flood.level == HazardLevel.HIGH
    assert flood.source == "thinkhazard"
    assert flood.latitude == LATITUDE
    assert flood.longitude == LONGITUDE
    assert flood.raw_category == "High"
    assert flood.retrieved_at.tzinfo is not None

    assert resolver.calls == [(LATITUDE, LONGITUDE)]


def test_requests_only_selected_hazards(
    client,
    resolver,
    monkeypatch,
):
    monkeypatch.setattr(
        client,
        "get_all_hazards",
        lambda code: flood_payload(),
    )

    provider = make_provider(client, resolver)

    results = provider.assess_location(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        hazards=(ClimateHazard.COASTAL,),
    )

    assert len(results) == 1
    assert results[0].hazard == ClimateHazard.COASTAL
    assert results[0].level == HazardLevel.MODERATE


def test_empty_hazards_skip_external_calls(
    client,
    resolver,
    monkeypatch,
):
    def unexpected_call(_code):
        raise AssertionError("ThinkHazard must not be called.")

    monkeypatch.setattr(
        client,
        "get_all_hazards",
        unexpected_call,
    )

    provider = make_provider(client, resolver)

    results = provider.assess_location(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        hazards=(),
    )

    assert results == []
    assert resolver.calls == []


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (91, 0),
        (-91, 0),
        (0, 181),
        (0, -181),
        (float("nan"), 0),
        (0, float("inf")),
    ],
)
def test_rejects_invalid_coordinates(
    client,
    resolver,
    latitude,
    longitude,
):
    provider = make_provider(client, resolver)

    with pytest.raises(ClimateDataValidationError):
        provider.assess_location(
            latitude=latitude,
            longitude=longitude,
            hazards=(ClimateHazard.FLOOD,),
        )

    assert resolver.calls == []


def test_rejects_invalid_hazard_collection(
    client,
    resolver,
):
    provider = make_provider(client, resolver)

    with pytest.raises(ClimateDataValidationError, match="hazards"):
        provider.assess_location(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            hazards=[ClimateHazard.FLOOD],
        )


def test_handles_missing_administrative_division(client):
    resolver = FakeDivisionResolver(
        error=AdministrativeDivisionNotFoundError(
            "No matching division."
        )
    )
    provider = make_provider(client, resolver)

    with pytest.raises(ClimateDataUnavailableError):
        provider.assess_location(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            hazards=(ClimateHazard.FLOOD,),
        )


def test_handles_resolver_failure(client):
    resolver = FakeDivisionResolver(
        error=AdministrativeDivisionResolutionError(
            "Resolver failed."
        )
    )
    provider = make_provider(client, resolver)

    with pytest.raises(ClimateDataUnavailableError):
        provider.assess_location(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            hazards=(ClimateHazard.FLOOD,),
        )


def test_handles_resolver_validation_error(client):
    resolver = FakeDivisionResolver(
        error=AdministrativeDivisionValidationError(
            "Resolver returned invalid division data."
        )
    )
    provider = make_provider(client, resolver)

    with pytest.raises(ClimateDataValidationError):
        provider.assess_location(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            hazards=(ClimateHazard.FLOOD,),
        )


def test_rejects_invalid_resolver_result(client):
    resolver = FakeDivisionResolver(
        result=AdministrativeDivision(
            code=0,
            name="Test Division",
            country="United Arab Emirates",
        )
    )
    provider = make_provider(client, resolver)

    with pytest.raises(ClimateDataValidationError):
        provider.assess_location(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            hazards=(ClimateHazard.FLOOD,),
        )


def test_handles_thinkhazard_unavailability(
    client,
    resolver,
    monkeypatch,
):
    def unavailable(_code):
        raise ThinkHazardUnavailableError("Service unavailable.")

    monkeypatch.setattr(
        client,
        "get_all_hazards",
        unavailable,
    )

    provider = make_provider(client, resolver)

    with pytest.raises(ClimateDataUnavailableError):
        provider.assess_location(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            hazards=(ClimateHazard.FLOOD,),
        )


def test_handles_invalid_thinkhazard_response(
    client,
    resolver,
    monkeypatch,
):
    def invalid_response(_code):
        raise ThinkHazardClientError("Invalid response.")

    monkeypatch.setattr(
        client,
        "get_all_hazards",
        invalid_response,
    )

    provider = make_provider(client, resolver)

    with pytest.raises(ClimateDataValidationError):
        provider.assess_location(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            hazards=(ClimateHazard.FLOOD,),
        )


def test_handles_normalization_failure(
    client,
    resolver,
    monkeypatch,
):
    monkeypatch.setattr(
        client,
        "get_all_hazards",
        lambda code: [
            {
                "hazardtype": {"mnemonic": "FL"},
                "hazardlevel": {"mnemonic": "INVALID"},
            }
        ],
    )

    provider = make_provider(client, resolver)

    with pytest.raises(ClimateDataValidationError):
        provider.assess_location(
            latitude=LATITUDE,
            longitude=LONGITUDE,
            hazards=(ClimateHazard.FLOOD,),
        )
