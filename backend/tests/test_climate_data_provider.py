
"""Tests for the normalized climate data provider contract."""

from datetime import datetime, timezone

import pytest

from ccr.services.climate_data_provider import (
    ClimateDataValidationError,
    ClimateHazard,
    ClimateHazardResult,
    HazardLevel,
    validate_coordinates,
    validate_provider_result,
)


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (25.2048, 55.2708, (25.2048, 55.2708)),
        (0, 0, (0.0, 0.0)),
        (-90, -180, (-90.0, -180.0)),
        (90, 180, (90.0, 180.0)),
    ],
)
def test_validate_coordinates_accepts_valid_values(
    latitude, longitude, expected
):
    assert validate_coordinates(latitude, longitude) == expected


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (91, 0),
        (-91, 0),
        (0, 181),
        (0, -181),
    ],
)
def test_validate_coordinates_rejects_out_of_range_values(
    latitude, longitude
):
    with pytest.raises(ClimateDataValidationError):
        validate_coordinates(latitude, longitude)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        ("not-a-number", 50),
        (25, "not-a-number"),
        (None, 50),
        (25, None),
    ],
)
def test_validate_coordinates_rejects_non_numeric_values(
    latitude, longitude
):
    with pytest.raises(ClimateDataValidationError):
        validate_coordinates(latitude, longitude)


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (float("nan"), 50),
        (25, float("inf")),
        (float("-inf"), 50),
    ],
)
def test_validate_coordinates_rejects_non_finite_values(
    latitude, longitude
):
    with pytest.raises(ClimateDataValidationError):
        validate_coordinates(latitude, longitude)


@pytest.fixture
def valid_result():
    return ClimateHazardResult(
        source="thinkhazard",
        hazard=ClimateHazard.FLOOD,
        level=HazardLevel.HIGH,
        retrieved_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
        latitude=25.2048,
        longitude=55.2708,
        raw_category="High",
        reference_url="https://example.com/source",
    )


def test_validate_provider_result_accepts_valid_result(valid_result):
    assert validate_provider_result(valid_result) is valid_result


def test_validate_provider_result_rejects_wrong_object():
    with pytest.raises(
        ClimateDataValidationError,
        match="ClimateHazardResult",
    ):
        validate_provider_result({"source": "thinkhazard"})


def test_validate_provider_result_rejects_empty_source(valid_result):
    invalid = ClimateHazardResult(
        source="   ",
        hazard=valid_result.hazard,
        level=valid_result.level,
        retrieved_at=valid_result.retrieved_at,
        latitude=valid_result.latitude,
        longitude=valid_result.longitude,
    )

    with pytest.raises(ClimateDataValidationError, match="source"):
        validate_provider_result(invalid)


def test_validate_provider_result_rejects_invalid_hazard(valid_result):
    invalid = ClimateHazardResult(
        source=valid_result.source,
        hazard="flood",
        level=valid_result.level,
        retrieved_at=valid_result.retrieved_at,
        latitude=valid_result.latitude,
        longitude=valid_result.longitude,
    )

    with pytest.raises(ClimateDataValidationError, match="hazard"):
        validate_provider_result(invalid)


def test_validate_provider_result_rejects_invalid_level(valid_result):
    invalid = ClimateHazardResult(
        source=valid_result.source,
        hazard=valid_result.hazard,
        level="high",
        retrieved_at=valid_result.retrieved_at,
        latitude=valid_result.latitude,
        longitude=valid_result.longitude,
    )

    with pytest.raises(ClimateDataValidationError, match="level"):
        validate_provider_result(invalid)


def test_validate_provider_result_rejects_invalid_retrieved_at(
    valid_result,
):
    invalid = ClimateHazardResult(
        source=valid_result.source,
        hazard=valid_result.hazard,
        level=valid_result.level,
        retrieved_at="2026-01-15",
        latitude=valid_result.latitude,
        longitude=valid_result.longitude,
    )

    with pytest.raises(ClimateDataValidationError, match="retrieved_at"):
        validate_provider_result(invalid)


def test_validate_provider_result_rejects_invalid_coordinates(
    valid_result,
):
    invalid = ClimateHazardResult(
        source=valid_result.source,
        hazard=valid_result.hazard,
        level=valid_result.level,
        retrieved_at=valid_result.retrieved_at,
        latitude=95,
        longitude=valid_result.longitude,
    )

    with pytest.raises(ClimateDataValidationError, match="Latitude"):
        validate_provider_result(invalid)


def test_validate_provider_result_rejects_non_string_reference_url(
    valid_result,
):
    invalid = ClimateHazardResult(
        source=valid_result.source,
        hazard=valid_result.hazard,
        level=valid_result.level,
        retrieved_at=valid_result.retrieved_at,
        latitude=valid_result.latitude,
        longitude=valid_result.longitude,
        reference_url=123,
    )

    with pytest.raises(ClimateDataValidationError, match="reference_url"):
        validate_provider_result(invalid)


def test_validate_provider_result_allows_missing_reference_url(
    valid_result,
):
    result = ClimateHazardResult(
        source=valid_result.source,
        hazard=valid_result.hazard,
        level=valid_result.level,
        retrieved_at=valid_result.retrieved_at,
        latitude=valid_result.latitude,
        longitude=valid_result.longitude,
    )

    assert validate_provider_result(result) is result
