
"""Tests for ThinkHazard classification normalization."""

from datetime import datetime, timezone

import pytest

from ccr.services.climate_data_provider import ClimateHazard, HazardLevel
from ccr.services.thinkhazard_normalizer import (
    ThinkHazardNormalizationError,
    normalize_thinkhazard_results,
)


@pytest.fixture
def retrieved_at():
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def sample_payload():
    return [
        {
            "hazardtype": {"mnemonic": "FL", "title": "River Flood"},
            "hazardlevel": {"mnemonic": "HIG", "title": "High"},
        },
        {
            "hazardtype": {"mnemonic": "UF", "title": "Urban Flood"},
            "hazardlevel": {"mnemonic": "MED", "title": "Medium"},
        },
        {
            "hazardtype": {"mnemonic": "CF", "title": "Coastal Flood"},
            "hazardlevel": {"mnemonic": "LOW", "title": "Low"},
        },
        {
            "hazardtype": {"mnemonic": "EH", "title": "Extreme Heat"},
            "hazardlevel": {"mnemonic": "VLO", "title": "Very Low"},
        },
    ]


def test_normalizes_supported_hazards(sample_payload, retrieved_at):
    results = normalize_thinkhazard_results(
        sample_payload,
        division_code=123,
        latitude=25.2,
        longitude=55.3,
        retrieved_at=retrieved_at,
    )

    by_hazard = {result.hazard: result for result in results}

    assert set(by_hazard) == {
        ClimateHazard.FLOOD,
        ClimateHazard.COASTAL,
        ClimateHazard.EXTREME_HEAT,
    }
    assert by_hazard[ClimateHazard.FLOOD].level == HazardLevel.HIGH
    assert by_hazard[ClimateHazard.COASTAL].level == HazardLevel.LOW
    assert by_hazard[ClimateHazard.EXTREME_HEAT].level == HazardLevel.LOW
    assert by_hazard[ClimateHazard.EXTREME_HEAT].raw_category == "Very Low"


def test_combines_river_and_urban_flood_using_highest_level(
    sample_payload,
    retrieved_at,
):
    results = normalize_thinkhazard_results(
        sample_payload[:2],
        division_code=123,
        latitude=25.2,
        longitude=55.3,
        retrieved_at=retrieved_at,
    )

    assert len(results) == 1
    assert results[0].hazard == ClimateHazard.FLOOD
    assert results[0].level == HazardLevel.HIGH
    assert results[0].raw_category == "High"


def test_preserves_retrieval_timestamp(sample_payload, retrieved_at):
    results = normalize_thinkhazard_results(
        sample_payload,
        division_code=123,
        latitude=25.2,
        longitude=55.3,
        retrieved_at=retrieved_at,
    )

    assert all(result.retrieved_at == retrieved_at for result in results)


def test_preserves_coordinates(sample_payload, retrieved_at):
    results = normalize_thinkhazard_results(
        sample_payload,
        division_code=123,
        latitude=25.2,
        longitude=55.3,
        retrieved_at=retrieved_at,
    )

    assert all(result.latitude == 25.2 for result in results)
    assert all(result.longitude == 55.3 for result in results)


def test_filters_requested_hazards(sample_payload, retrieved_at):
    results = normalize_thinkhazard_results(
        sample_payload,
        division_code=123,
        latitude=25.2,
        longitude=55.3,
        retrieved_at=retrieved_at,
        hazards=(ClimateHazard.COASTAL,),
    )

    assert len(results) == 1
    assert results[0].hazard == ClimateHazard.COASTAL


def test_ignores_unsupported_hazards(sample_payload, retrieved_at):
    payload = sample_payload + [
        {
            "hazardtype": {"mnemonic": "EQ", "title": "Earthquake"},
            "hazardlevel": {"mnemonic": "HIG", "title": "High"},
        }
    ]

    results = normalize_thinkhazard_results(
        payload,
        division_code=123,
        latitude=25.2,
        longitude=55.3,
        retrieved_at=retrieved_at,
    )

    assert len(results) == 3
    assert all(
        result.hazard in {
            ClimateHazard.FLOOD,
            ClimateHazard.COASTAL,
            ClimateHazard.EXTREME_HEAT,
        }
        for result in results
    )


@pytest.mark.parametrize("division_code", [0, -1, True, "123", None])
def test_rejects_invalid_division_code(
    sample_payload,
    division_code,
):
    with pytest.raises(ThinkHazardNormalizationError):
        normalize_thinkhazard_results(
            sample_payload,
            division_code=division_code,
            latitude=25.2,
            longitude=55.3,
        )


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (91, 55.3),
        (-91, 55.3),
        (25.2, 181),
        (25.2, -181),
        (float("nan"), 55.3),
        (25.2, float("inf")),
    ],
)
def test_rejects_invalid_coordinates(
    sample_payload,
    latitude,
    longitude,
):
    with pytest.raises(ThinkHazardNormalizationError):
        normalize_thinkhazard_results(
            sample_payload,
            division_code=123,
            latitude=latitude,
            longitude=longitude,
        )


def test_rejects_non_list_payload():
    with pytest.raises(ThinkHazardNormalizationError):
        normalize_thinkhazard_results(
            {},
            division_code=123,
            latitude=25.2,
            longitude=55.3,
        )


@pytest.mark.parametrize(
    "payload",
    [
        [None],
        ["invalid"],
        [{}],
        [{"hazardtype": [], "hazardlevel": {}}],
        [{"hazardtype": {}, "hazardlevel": {}}],
        [
            {
                "hazardtype": {"mnemonic": "FL"},
                "hazardlevel": {},
            }
        ],
        [
            {
                "hazardtype": {},
                "hazardlevel": {"mnemonic": "HIG"},
            }
        ],
    ],
)
def test_rejects_malformed_hazard_entries(payload):
    with pytest.raises(ThinkHazardNormalizationError):
        normalize_thinkhazard_results(
            payload,
            division_code=123,
            latitude=25.2,
            longitude=55.3,
        )


def test_rejects_unsupported_level_for_supported_hazard():
    payload = [
        {
            "hazardtype": {"mnemonic": "FL"},
            "hazardlevel": {"mnemonic": "INVALID"},
        }
    ]

    with pytest.raises(ThinkHazardNormalizationError):
        normalize_thinkhazard_results(
            payload,
            division_code=123,
            latitude=25.2,
            longitude=55.3,
        )


def test_uses_default_retrieved_at_when_not_provided(sample_payload):
    results = normalize_thinkhazard_results(
        sample_payload,
        division_code=123,
        latitude=25.2,
        longitude=55.3,
    )

    assert results
    assert all(isinstance(result.retrieved_at, datetime) for result in results)
    assert all(result.retrieved_at.tzinfo is not None for result in results)


def test_rejects_invalid_retrieved_at(sample_payload):
    with pytest.raises(ThinkHazardNormalizationError):
        normalize_thinkhazard_results(
            sample_payload,
            division_code=123,
            latitude=25.2,
            longitude=55.3,
            retrieved_at="not-a-datetime",
        )


@pytest.mark.parametrize(
    "hazards",
    [
        [],
        [ClimateHazard.FLOOD],
        "flood",
        (ClimateHazard.FLOOD, "invalid"),
    ],
)
def test_rejects_invalid_hazards_filter(sample_payload, hazards):
    with pytest.raises(ThinkHazardNormalizationError):
        normalize_thinkhazard_results(
            sample_payload,
            division_code=123,
            latitude=25.2,
            longitude=55.3,
            hazards=hazards,
        )


def test_creates_reference_url(sample_payload, retrieved_at):
    results = normalize_thinkhazard_results(
        sample_payload,
        division_code=123,
        latitude=25.2,
        longitude=55.3,
        retrieved_at=retrieved_at,
    )

    assert all(
        result.reference_url.startswith(
            "https://thinkhazard.org/en/report/123/"
        )
        for result in results
    )
