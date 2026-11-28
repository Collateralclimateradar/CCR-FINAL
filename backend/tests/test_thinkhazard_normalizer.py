
"""Tests for ThinkHazard result normalization."""

from datetime import datetime, timezone

import pytest

from ccr.services.climate_data_provider import (
    ClimateHazard,
    HazardLevel,
)
from ccr.services.thinkhazard_normalizer import (
    ThinkHazardNormalizationError,
    normalize_thinkhazard_results,
)


LATITUDE = 25.2048
LONGITUDE = 55.2708
DIVISION_CODE = "ARE002"


def make_payload():
    """Return representative ThinkHazard classifications."""
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
                "mnemonic": "UF",
                "hazardtype": "Urban flood",
            },
            "hazardlevel": {
                "mnemonic": "MED",
                "title": "Medium",
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


def normalize(payload=None, **overrides):
    """Call the normalizer with standard valid arguments."""
    arguments = {
        "division_code": DIVISION_CODE,
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
    }
    arguments.update(overrides)

    return normalize_thinkhazard_results(
        make_payload() if payload is None else payload,
        **arguments,
    )


def test_normalizes_all_supported_hazards():
    results = normalize()

    assert len(results) == 3
    assert {result.hazard for result in results} == {
        ClimateHazard.FLOOD,
        ClimateHazard.COASTAL,
        ClimateHazard.EXTREME_HEAT,
    }


def test_normalizes_hazard_levels():
    results = normalize()

    levels = {
        result.hazard: result.level
        for result in results
    }

    assert levels[ClimateHazard.FLOOD] == HazardLevel.HIGH
    assert levels[ClimateHazard.COASTAL] == HazardLevel.MODERATE
    assert levels[ClimateHazard.EXTREME_HEAT] == HazardLevel.HIGH


def test_combines_river_and_urban_flood_using_highest_level():
    results = normalize(
        hazards=(ClimateHazard.FLOOD,),
    )

    assert len(results) == 1

    flood = results[0]

    assert flood.hazard == ClimateHazard.FLOOD
    assert flood.level == HazardLevel.HIGH


def test_filters_unrequested_hazards():
    results = normalize(
        hazards=(ClimateHazard.COASTAL,),
    )

    assert len(results) == 1
    assert results[0].hazard == ClimateHazard.COASTAL


def test_preserves_source_and_coordinates():
    results = normalize()

    for result in results:
        assert result.source == "thinkhazard"
        assert result.latitude == LATITUDE
        assert result.longitude == LONGITUDE
        assert result.retrieved_at.tzinfo is not None


def test_preserves_reference_url():
    results = normalize(
        hazards=(ClimateHazard.FLOOD,),
    )

    assert len(results) == 1
    assert results[0].reference_url == (
        "https://thinkhazard.org/en/report/ARE002/FL,UF"
    )


def test_sets_administrative_area_metadata():
    results = normalize(
        hazards=(ClimateHazard.FLOOD,),
        administrative_area="Ajman",
        administrative_level="admin1",
    )

    assert len(results) == 1

    result = results[0]

    assert result.assessment_scope == "administrative_area"
    assert result.administrative_area == "Ajman"
    assert result.administrative_level == "admin1"


def test_defaults_to_unspecified_scope_without_area_metadata():
    results = normalize(
        hazards=(ClimateHazard.FLOOD,),
    )

    result = results[0]

    assert result.assessment_scope == "unspecified"
    assert result.administrative_area is None
    assert result.administrative_level is None


def test_accepts_explicit_retrieved_at():
    retrieved_at = datetime(
        2026, 1, 15, 10, 30, tzinfo=timezone.utc
    )

    results = normalize(
        hazards=(ClimateHazard.FLOOD,),
        retrieved_at=retrieved_at,
    )

    assert results[0].retrieved_at == retrieved_at


def test_preserves_very_low_raw_category():
    payload = [
        {
            "hazardtype": {"mnemonic": "FL"},
            "hazardlevel": {
                "mnemonic": "VLO",
                "title": "Very Low",
            },
        }
    ]

    results = normalize(
        payload,
        hazards=(ClimateHazard.FLOOD,),
    )

    assert len(results) == 1
    assert results[0].level == HazardLevel.LOW
    assert results[0].raw_category == "Very Low"


def test_uses_level_mnemonic_when_title_is_missing():
    payload = [
        {
            "hazardtype": {"mnemonic": "FL"},
            "hazardlevel": {"mnemonic": "HIG"},
        }
    ]

    results = normalize(
        payload,
        hazards=(ClimateHazard.FLOOD,),
    )

    assert results[0].raw_category == "HIG"


def test_ignores_unsupported_hazard_types():
    payload = [
        {
            "hazardtype": {"mnemonic": "OTHER"},
            "hazardlevel": {
                "mnemonic": "HIG",
                "title": "High",
            },
        }
    ]

    assert normalize(payload, hazards=()) == []


def test_returns_empty_list_when_no_hazards_are_requested():
    assert normalize([], hazards=()) == []


def test_returns_unknown_for_missing_requested_hazards():
    results = normalize(
        [],
        hazards=(ClimateHazard.FLOOD,),
    )

    assert len(results) == 1
    assert results[0].hazard == ClimateHazard.FLOOD
    assert results[0].level == HazardLevel.UNKNOWN
    assert results[0].raw_category == "Not reported by ThinkHazard"
    assert results[0].reference_url is None


@pytest.mark.parametrize(
    "division_code",
    [0, -1, True, "", "invalid-code", "are002"],
)
def test_rejects_invalid_division_codes(division_code):
    with pytest.raises(ThinkHazardNormalizationError):
        normalize(
            division_code=division_code,
        )


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
def test_rejects_invalid_coordinates(latitude, longitude):
    with pytest.raises(ThinkHazardNormalizationError):
        normalize(
            latitude=latitude,
            longitude=longitude,
        )


def test_rejects_non_list_payload():
    with pytest.raises(ThinkHazardNormalizationError, match="list"):
        normalize(payload={"hazards": []})


def test_rejects_non_object_hazard_entry():
    with pytest.raises(ThinkHazardNormalizationError, match="object"):
        normalize(payload=["invalid"])


def test_rejects_missing_hazard_type():
    payload = [
        {
            "hazardlevel": {
                "mnemonic": "HIG",
                "title": "High",
            }
        }
    ]

    with pytest.raises(ThinkHazardNormalizationError):
        normalize(payload)


def test_rejects_missing_hazard_level_mnemonic():
    payload = [
        {
            "hazardtype": {"mnemonic": "FL"},
            "hazardlevel": {"title": "High"},
        }
    ]

    with pytest.raises(ThinkHazardNormalizationError):
        normalize(payload)


def test_rejects_unsupported_level_for_supported_hazard():
    payload = [
        {
            "hazardtype": {"mnemonic": "FL"},
            "hazardlevel": {
                "mnemonic": "INVALID",
                "title": "Invalid",
            },
        }
    ]

    with pytest.raises(
        ThinkHazardNormalizationError,
        match="Unsupported ThinkHazard level",
    ):
        normalize(payload)


def test_rejects_invalid_retrieved_at():
    with pytest.raises(ThinkHazardNormalizationError):
        normalize(
            retrieved_at="not-a-datetime",
        )


def test_rejects_invalid_hazard_collection():
    with pytest.raises(ThinkHazardNormalizationError, match="hazards"):
        normalize(
            hazards=[ClimateHazard.FLOOD],
        )


def test_requires_administrative_area_and_level_together():
    with pytest.raises(
        ThinkHazardNormalizationError,
        match="provided together",
    ):
        normalize(
            administrative_area="Ajman",
        )


@pytest.mark.parametrize(
    ("administrative_area", "administrative_level"),
    [
        ("", "admin1"),
        ("   ", "admin1"),
        ("Ajman", ""),
        ("Ajman", "   "),
        (123, "admin1"),
        ("Ajman", 1),
    ],
)
def test_rejects_invalid_administrative_metadata(
    administrative_area,
    administrative_level,
):
    with pytest.raises(ThinkHazardNormalizationError):
        normalize(
            administrative_area=administrative_area,
            administrative_level=administrative_level,
        )


def test_accepts_legacy_positive_integer_division_code():
    results = normalize(
        division_code=12345,
        hazards=(ClimateHazard.FLOOD,),
    )

    assert len(results) == 1
    assert "/12345/" in results[0].reference_url
