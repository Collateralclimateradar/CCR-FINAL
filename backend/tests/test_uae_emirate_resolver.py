
"""Tests for UAE emirate resolution and ThinkHazard division mapping."""

import json
from unittest.mock import Mock

import pytest

from ccr.services.administrative_division import (
    AdministrativeDivisionNotFoundError,
)
from ccr.services.uae_emirate_resolver import (
    THINKHAZARD_CODES,
    UAEEmirateResolver,
    UAEEmirateResolverError,
)


EMIRATES = [
    ("Abu Dhabi", 3173),
    ("Ajman", 149626),
    ("Dubai", 3177),
    ("Fujairah", 149627),
    ("Ras Al Khaimah", 3179),
    ("Sharjah", 3180),
    ("Umm Al Quwain", 3181),
]


def arcgis_response(name, pcode="ARE"):
    return {
        "features": [
            {
                "attributes": {
                    "adm1_name": name,
                    "adm1_pcode": "ARE",
                    "adm0_pcode": pcode,
                }
            }
        ]
    }


def mock_urlopen(monkeypatch, payload):
    response = Mock()
    response.read.return_value = json.dumps(payload).encode("utf-8")
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)

    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        fake_urlopen,
    )
    return captured


@pytest.mark.parametrize("emirate_name,expected_code", EMIRATES)
def test_resolves_all_seven_uae_emirates(
    monkeypatch,
    emirate_name,
    expected_code,
):
    mock_urlopen(monkeypatch, arcgis_response(emirate_name))

    resolver = UAEEmirateResolver()
    result = resolver.resolve(latitude=25.2, longitude=55.3)

    assert result.code == expected_code
    assert result.name == emirate_name
    assert result.country == "United Arab Emirates"
    assert result.admin1 == emirate_name
    assert result.admin2 is None


def test_emirate_name_matching_is_case_and_whitespace_insensitive(
    monkeypatch,
):
    mock_urlopen(monkeypatch, arcgis_response("  aJmAn  "))

    resolver = UAEEmirateResolver()
    result = resolver.resolve(latitude=25.4, longitude=55.5)

    assert result.code == 149626
    assert result.name == "Ajman"


def test_query_uses_point_geometry_and_uae_filter(monkeypatch):
    captured = mock_urlopen(
        monkeypatch,
        arcgis_response("Dubai"),
    )

    resolver = UAEEmirateResolver()
    resolver.resolve(latitude=25.2, longitude=55.3)

    request = captured["request"]
    url = request.full_url

    assert "adm0_pcode" in url
    assert "ARE" in url
    assert "esriGeometryPoint" in url
    assert "esriSpatialRelIntersects" in url
    assert "adm1_name" in url
    assert captured["timeout"] == 15.0


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (91, 55),
        (-91, 55),
        (25, 181),
        (25, -181),
        (None, 55),
        (25, None),
        (True, 55),
    ],
)
def test_invalid_coordinates_do_not_make_network_call(
    monkeypatch,
    latitude,
    longitude,
):
    def unexpected_network_call(*args, **kwargs):
        pytest.fail("Network must not be called for invalid coordinates.")

    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        unexpected_network_call,
    )

    resolver = UAEEmirateResolver()

    with pytest.raises(UAEEmirateResolverError):
        resolver.resolve(latitude=latitude, longitude=longitude)


@pytest.mark.parametrize("timeout", [0, -1, True, "invalid", None])
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(ValueError):
        UAEEmirateResolver(timeout=timeout)


def test_empty_features_raise_not_found(monkeypatch):
    mock_urlopen(monkeypatch, {"features": []})

    resolver = UAEEmirateResolver()

    with pytest.raises(AdministrativeDivisionNotFoundError):
        resolver.resolve(latitude=25.2, longitude=55.3)


def test_multiple_matches_raise_resolution_error(monkeypatch):
    payload = {
        "features": [
            arcgis_response("Dubai")["features"][0],
            arcgis_response("Sharjah")["features"][0],
        ]
    }
    mock_urlopen(monkeypatch, payload)

    resolver = UAEEmirateResolver()

    with pytest.raises(UAEEmirateResolverError):
        resolver.resolve(latitude=25.2, longitude=55.3)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        "invalid",
        {},
        {"features": None},
        {"features": [{}]},
        {"features": [{"attributes": None}]},
    ],
)
def test_malformed_response_raises_resolution_error(
    monkeypatch,
    payload,
):
    mock_urlopen(monkeypatch, payload)

    resolver = UAEEmirateResolver()

    with pytest.raises(UAEEmirateResolverError):
        resolver.resolve(latitude=25.2, longitude=55.3)


def test_arcgis_error_response_raises_resolution_error(monkeypatch):
    mock_urlopen(
        monkeypatch,
        {"error": {"code": 400, "message": "Invalid query"}},
    )

    resolver = UAEEmirateResolver()

    with pytest.raises(UAEEmirateResolverError):
        resolver.resolve(latitude=25.2, longitude=55.3)


def test_non_uae_feature_is_rejected(monkeypatch):
    mock_urlopen(
        monkeypatch,
        arcgis_response("Dubai", pcode="OMN"),
    )

    resolver = UAEEmirateResolver()

    with pytest.raises(UAEEmirateResolverError):
        resolver.resolve(latitude=25.2, longitude=55.3)


def test_unmapped_emirate_is_rejected(monkeypatch):
    mock_urlopen(
        monkeypatch,
        arcgis_response("Unknown Emirate"),
    )

    resolver = UAEEmirateResolver()

    with pytest.raises(UAEEmirateResolverError):
        resolver.resolve(latitude=25.2, longitude=55.3)


def test_unique_and_complete_official_thinkhazard_codes():
    assert len(THINKHAZARD_CODES) == 7

    assert set(THINKHAZARD_CODES.values()) == {
        3173,
        149626,
        3177,
        149627,
        3179,
        3180,
        3181,
    }

    assert len(set(THINKHAZARD_CODES.values())) == 7


def test_http_error_is_converted_to_resolution_error(monkeypatch):
    from urllib.error import HTTPError

    def failing_urlopen(*args, **kwargs):
        raise HTTPError(
            url="https://example.com",
            code=503,
            msg="Service unavailable",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        failing_urlopen,
    )

    resolver = UAEEmirateResolver()

    with pytest.raises(
        UAEEmirateResolverError,
        match="HTTP 503",
    ):
        resolver.resolve(latitude=25.2, longitude=55.3)


def test_network_error_is_converted_to_resolution_error(monkeypatch):
    from urllib.error import URLError

    def failing_urlopen(*args, **kwargs):
        raise URLError("Connection failed")

    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        failing_urlopen,
    )

    resolver = UAEEmirateResolver()

    with pytest.raises(
        UAEEmirateResolverError,
        match="Could not reach",
    ):
        resolver.resolve(latitude=25.2, longitude=55.3)
