
"""End-to-end integration tests for UAE ThinkHazard screening."""

import json
from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock

import pytest

from ccr.services.climate_data_provider import (
    ClimateHazard,
    HazardLevel,
)
from ccr.services.thinkhazard_client import ThinkHazardClient
from ccr.services.thinkhazard_provider import ThinkHazardProvider
from ccr.services.uae_emirate_resolver import UAEEmirateResolver


EMIRATES = [
    ("Abu Dhabi", 3173),
    ("Ajman", 149626),
    ("Dubai", 3177),
    ("Fujairah", 149627),
    ("Ras Al Khaimah", 3179),
    ("Sharjah", 3180),
    ("Umm Al Quwain", 3181),
]


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


def arcgis_payload(emirate_name):
    return {
        "features": [
            {
                "attributes": {
                    "adm1_name": emirate_name,
                    "adm1_pcode": "ARE",
                    "adm0_pcode": "ARE",
                }
            }
        ]
    }


def thinkhazard_payload():
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
                "mnemonic": "LOW",
                "title": "Low",
            },
        },
    ]


@pytest.mark.parametrize(
    "emirate_name,expected_code",
    EMIRATES,
)
def test_full_uae_thinkhazard_provider_flow(
    monkeypatch,
    emirate_name,
    expected_code,
):
    captured = {
        "boundary_request": None,
        "thinkhazard_request": None,
    }

    def fake_boundary_urlopen(request, timeout):
        captured["boundary_request"] = request
        return FakeResponse(arcgis_payload(emirate_name))

    def fake_thinkhazard_urlopen(request, timeout):
        captured["thinkhazard_request"] = request
        return FakeResponse(thinkhazard_payload())

    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        fake_boundary_urlopen,
    )
    monkeypatch.setattr(
        "ccr.services.thinkhazard_client.urlopen",
        fake_thinkhazard_urlopen,
    )

    resolver = UAEEmirateResolver()
    client = ThinkHazardClient()

    provider = ThinkHazardProvider(
        client=client,
        division_resolver=resolver,
    )

    results = provider.assess_location(
        latitude=25.2,
        longitude=55.3,
        hazards=(
            ClimateHazard.FLOOD,
            ClimateHazard.COASTAL,
            ClimateHazard.EXTREME_HEAT,
        ),
    )

    assert len(results) == 3

    results_by_hazard = {
        result.hazard: result
        for result in results
    }

    assert results_by_hazard[ClimateHazard.FLOOD].level == HazardLevel.HIGH
    assert results_by_hazard[ClimateHazard.COASTAL].level == HazardLevel.MODERATE
    assert results_by_hazard[ClimateHazard.EXTREME_HEAT].level == HazardLevel.LOW

    for result in results:
        assert result.source == "thinkhazard"
        assert result.assessment_scope == "administrative_area"
        assert result.administrative_area == emirate_name
        assert result.administrative_level == "admin1"
        assert result.latitude == 25.2
        assert result.longitude == 55.3

    boundary_request = captured["boundary_request"]
    assert boundary_request is not None

    boundary_params = parse_qs(
        urlsplit(boundary_request.full_url).query
    )

    assert boundary_params["where"] == ["adm0_pcode = 'ARE'"]
    assert boundary_params["geometryType"] == ["esriGeometryPoint"]

    thinkhazard_request = captured["thinkhazard_request"]
    assert thinkhazard_request is not None

    assert thinkhazard_request.full_url.endswith(
        f"/report/{expected_code}.json"
    )
