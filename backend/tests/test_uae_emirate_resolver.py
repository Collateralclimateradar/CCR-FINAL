
"""Tests for UAE coordinate-to-emirate resolution."""

import json
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from ccr.services.administrative_division import (
    AdministrativeDivisionNotFoundError,
)
from ccr.services.uae_emirate_resolver import (
    ARCGIS_QUERY_URL,
    THINKHAZARD_CODES,
    UAEEmirateResolver,
    UAEEmirateResolverError,
)


class FakeResponse:
    """Minimal context-manager response for mocked ArcGIS requests."""

    def __init__(self, payload):
        self.body = (
            payload
            if isinstance(payload, bytes)
            else json.dumps(payload).encode("utf-8")
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.body


def feature(
    emirate_name,
    *,
    country_code="ARE",
):
    return {
        "attributes": {
            "adm1_name": emirate_name,
            "adm1_pcode": "ARE001",
            "adm0_pcode": country_code,
        }
    }


@pytest.mark.parametrize(
    ("emirate_name", "expected_code"),
    [
        ("Abu Dhabi", "ARE001"),
        ("Ajman", "ARE002"),
        ("Dubai", "ARE003"),
        ("Fujairah", "ARE004"),
        ("Ras Al Khaimah", "ARE005"),
        ("Sharjah", "ARE006"),
        ("Umm Al Quwain", "ARE007"),
    ],
)
def test_resolves_all_seven_uae_emirates(
    monkeypatch,
    emirate_name,
    expected_code,
):
    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        lambda request, timeout: FakeResponse(
            {"features": [feature(emirate_name)]}
        ),
    )

    result = UAEEmirateResolver().resolve(
        latitude=25.2048,
        longitude=55.2708,
    )

    assert result.code == expected_code
    assert result.name == emirate_name
    assert result.country == "United Arab Emirates"
    assert result.admin1 == emirate_name
    assert result.admin2 is None


def test_emirate_name_matching_is_case_and_whitespace_insensitive(
    monkeypatch,
):
    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        lambda request, timeout: FakeResponse(
            {"features": [feature("  aJmAn  ")]}
        ),
    )

    result = UAEEmirateResolver().resolve(
        latitude=25.4,
        longitude=55.5,
    )

    assert result.code == "ARE002"
    assert result.name == "Ajman"


def test_request_uses_point_coordinates_and_uae_filter(
    monkeypatch,
):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout

        return FakeResponse(
            {"features": [feature("Ajman")]}
        )

    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        fake_urlopen,
    )

    UAEEmirateResolver(timeout=7).resolve(
        latitude=25.4,
        longitude=55.5,
    )

    parsed = urlparse(captured["url"])
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "gis.unocha.org"
    assert parsed.path == urlparse(ARCGIS_QUERY_URL).path

    assert params["where"] == ["adm0_pcode = 'ARE'"]
    assert params["geometryType"] == ["esriGeometryPoint"]
    assert params["inSR"] == ["4326"]
    assert params["spatialRel"] == ["esriSpatialRelIntersects"]
    assert params["returnGeometry"] == ["false"]
    assert params["f"] == ["json"]
    assert captured["timeout"] == 7

    geometry = json.loads(params["geometry"][0])

    assert geometry == {
        "x": 55.5,
        "y": 25.4,
        "spatialReference": {"wkid": 4326},
    }


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
        (True, 55),
        (25, False),
    ],
)
def test_rejects_invalid_coordinates_without_network_call(
    monkeypatch,
    latitude,
    longitude,
):
    def unexpected_call(*args, **kwargs):
        raise AssertionError("Network call must not happen.")

    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        unexpected_call,
    )

    with pytest.raises(UAEEmirateResolverError):
        UAEEmirateResolver().resolve(
            latitude=latitude,
            longitude=longitude,
        )


@pytest.mark.parametrize(
    "timeout",
    [0, -1, True, "15", None],
)
def test_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError):
        UAEEmirateResolver(timeout=timeout)


def test_empty_features_raise_not_found_error(monkeypatch):
    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        lambda request, timeout: FakeResponse(
            {"features": []}
        ),
    )

    with pytest.raises(AdministrativeDivisionNotFoundError):
        UAEEmirateResolver().resolve(
            latitude=25.4,
            longitude=55.5,
        )


def test_multiple_matching_features_are_rejected(monkeypatch):
    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        lambda request, timeout: FakeResponse(
            {
                "features": [
                    feature("Ajman"),
                    feature("Sharjah"),
                ]
            }
        ),
    )

    with pytest.raises(
        UAEEmirateResolverError,
        match="multiple emirate boundaries",
    ):
        UAEEmirateResolver().resolve(
            latitude=25.4,
            longitude=55.5,
        )


@pytest.mark.parametrize(
    "payload",
    [
        [],
        "unexpected",
        {},
        {"features": None},
        {"features": "invalid"},
    ],
)
def test_rejects_unexpected_boundary_responses(
    monkeypatch,
    payload,
):
    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        lambda request, timeout: FakeResponse(payload),
    )

    with pytest.raises(UAEEmirateResolverError):
        UAEEmirateResolver().resolve(
            latitude=25.4,
            longitude=55.5,
        )


def test_rejects_arcgis_error_response(monkeypatch):
    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        lambda request, timeout: FakeResponse(
            {
                "error": {
                    "code": 400,
                    "message": "Invalid query",
                },
                "features": [],
            }
        ),
    )

    with pytest.raises(
        UAEEmirateResolverError,
        match="query error",
    ):
        UAEEmirateResolver().resolve(
            latitude=25.4,
            longitude=55.5,
        )


@pytest.mark.parametrize(
    "attributes",
    [
        None,
        {},
        {"adm1_name": "Ajman"},
        {
            "adm1_name": "Ajman",
            "adm0_pcode": "OMN",
        },
        {
            "adm1_name": "",
            "adm0_pcode": "ARE",
        },
        {
            "adm1_name": "Unknown Emirate",
            "adm0_pcode": "ARE",
        },
    ],
)
def test_rejects_invalid_or_unmapped_features(
    monkeypatch,
    attributes,
):
    payload = {
        "features": [
            {"attributes": attributes}
        ]
    }

    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        lambda request, timeout: FakeResponse(payload),
    )

    with pytest.raises(UAEEmirateResolverError):
        UAEEmirateResolver().resolve(
            latitude=25.4,
            longitude=55.5,
        )


def test_rejects_non_object_feature(monkeypatch):
    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        lambda request, timeout: FakeResponse(
            {"features": ["invalid"]}
        ),
    )

    with pytest.raises(
        UAEEmirateResolverError,
        match="attributes",
    ):
        UAEEmirateResolver().resolve(
            latitude=25.4,
            longitude=55.5,
        )


def test_rejects_invalid_json(monkeypatch):
    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        lambda request, timeout: FakeResponse(b"{invalid-json"),
    )

    with pytest.raises(
        UAEEmirateResolverError,
        match="invalid JSON",
    ):
        UAEEmirateResolver().resolve(
            latitude=25.4,
            longitude=55.5,
        )


def test_handles_http_error(monkeypatch):
    def fail_request(request, timeout):
        raise HTTPError(
            request.full_url,
            503,
            "Service unavailable",
            None,
            BytesIO(b""),
        )

    monkeypatch.setattr(
        "ccr.services.uae_emirate_resolver.urlopen",
        fail_request,
    )

    with pytest.raises(
        UAEEmirateResolverError,
        match="HTTP 503",
    ):
        UAEEmirateResolver().resolve(
            latitude=25.4,
            longitude=55.5,
        )


def test_all_emirate_codes_are_unique_and_complete():
    assert len(THINKHAZARD_CODES) == 7
    assert set(THINKHAZARD_CODES.values()) == {
        "ARE001",
        "ARE002",
        "ARE003",
        "ARE004",
        "ARE005",
        "ARE006",
        "ARE007",
    }
