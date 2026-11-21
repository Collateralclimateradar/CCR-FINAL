
"""Tests for administrative division resolution contracts."""

import pytest

from ccr.services.administrative_division import (
    AdministrativeDivision,
    AdministrativeDivisionNotFoundError,
    AdministrativeDivisionResolutionError,
    AdministrativeDivisionValidationError,
    validate_administrative_division,
    validate_resolution_request,
)


@pytest.fixture
def valid_division():
    return AdministrativeDivision(
        code=12345,
        name="Dubai",
        country="United Arab Emirates",
        admin1="Dubai",
        admin2="Dubai",
    )


def test_valid_division_is_accepted(valid_division):
    assert validate_administrative_division(valid_division) is valid_division


@pytest.mark.parametrize(
    "invalid_code",
    [0, -1, True, False, 1.5, "12345", None],
)
def test_invalid_division_codes_are_rejected(
    valid_division,
    invalid_code,
):
    invalid = AdministrativeDivision(
        code=invalid_code,
        name=valid_division.name,
        country=valid_division.country,
    )

    with pytest.raises(
        AdministrativeDivisionValidationError,
        match="positive integer",
    ):
        validate_administrative_division(invalid)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("name", ""),
        ("name", "   "),
        ("name", None),
        ("name", 123),
        ("country", ""),
        ("country", "   "),
        ("country", None),
        ("country", 123),
    ],
)
def test_required_text_fields_are_validated(
    valid_division,
    field_name,
    invalid_value,
):
    values = {
        "code": valid_division.code,
        "name": valid_division.name,
        "country": valid_division.country,
        "admin1": valid_division.admin1,
        "admin2": valid_division.admin2,
    }
    values[field_name] = invalid_value

    invalid = AdministrativeDivision(**values)

    with pytest.raises(
        AdministrativeDivisionValidationError,
        match=field_name,
    ):
        validate_administrative_division(invalid)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("admin1", ""),
        ("admin1", "   "),
        ("admin1", 123),
        ("admin2", ""),
        ("admin2", "   "),
        ("admin2", 123),
    ],
)
def test_optional_admin_fields_reject_invalid_values(
    valid_division,
    field_name,
    invalid_value,
):
    values = {
        "code": valid_division.code,
        "name": valid_division.name,
        "country": valid_division.country,
        "admin1": valid_division.admin1,
        "admin2": valid_division.admin2,
    }
    values[field_name] = invalid_value

    invalid = AdministrativeDivision(**values)

    with pytest.raises(
        AdministrativeDivisionValidationError,
        match=field_name,
    ):
        validate_administrative_division(invalid)


@pytest.mark.parametrize(
    ("admin1", "admin2"),
    [
        (None, None),
        ("Abu Dhabi", None),
        (None, "District A"),
    ],
)
def test_optional_admin_fields_allow_none(admin1, admin2):
    division = AdministrativeDivision(
        code=123,
        name="Test Area",
        country="United Arab Emirates",
        admin1=admin1,
        admin2=admin2,
    )

    assert validate_administrative_division(division) is division


@pytest.mark.parametrize(
    "invalid",
    [None, {}, "Dubai", 123],
)
def test_non_division_objects_are_rejected(invalid):
    with pytest.raises(
        AdministrativeDivisionValidationError,
        match="AdministrativeDivision",
    ):
        validate_administrative_division(invalid)


@pytest.mark.parametrize(
    ("latitude", "longitude", "expected"),
    [
        (25.2048, 55.2708, (25.2048, 55.2708)),
        (0, 0, (0.0, 0.0)),
        (-90, -180, (-90.0, -180.0)),
        (90, 180, (90.0, 180.0)),
        ("25.2048", "55.2708", (25.2048, 55.2708)),
    ],
)
def test_resolution_request_accepts_valid_coordinates(
    latitude,
    longitude,
    expected,
):
    assert validate_resolution_request(
        latitude,
        longitude,
    ) == expected


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [
        (91, 0),
        (-91, 0),
        (0, 181),
        (0, -181),
        ("invalid", 55),
        (25, None),
        (float("nan"), 55),
        (25, float("inf")),
    ],
)
def test_resolution_request_rejects_invalid_coordinates(
    latitude,
    longitude,
):
    from ccr.services.climate_data_provider import (
        ClimateDataValidationError,
    )

    with pytest.raises(ClimateDataValidationError):
        validate_resolution_request(latitude, longitude)


def test_resolution_exceptions_have_expected_inheritance():
    assert issubclass(
        AdministrativeDivisionNotFoundError,
        AdministrativeDivisionResolutionError,
    )
    assert issubclass(
        AdministrativeDivisionValidationError,
        AdministrativeDivisionResolutionError,
    )
