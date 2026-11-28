
"""Tests for the ThinkHazard API client."""

import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from ccr.services import thinkhazard_client as client_module
from ccr.services.thinkhazard_client import (
    ThinkHazardClient,
    ThinkHazardResponseValidationError,
    ThinkHazardUnavailableError,
)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.payload


@pytest.fixture
def client():
    return ThinkHazardClient(
        base_url="https://example.test/en",
        timeout=7,
    )


def mock_json_response(monkeypatch, payload, status=200):
    response = FakeResponse(
        json.dumps(payload).encode("utf-8"),
        status=status,
    )
    calls = []

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return response

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    return calls


def test_client_uses_valid_defaults():
    client = ThinkHazardClient()

    assert client.base_url == "https://thinkhazard.org/en"
    assert client.timeout == 15.0


@pytest.mark.parametrize(
    "base_url",
    [
        "ftp://example.com",
        "example.com",
        "https://",
        "https://example.com?query=1",
        "https://example.com#fragment",
    ],
)
def test_client_rejects_invalid_base_url(base_url):
    with pytest.raises(ValueError, match="base_url"):
        ThinkHazardClient(base_url=base_url)


@pytest.mark.parametrize("timeout", [0, -1, True, "15", None])
def test_client_rejects_invalid_timeout(timeout):
    with pytest.raises(ValueError, match="timeout"):
        ThinkHazardClient(timeout=timeout)


@pytest.mark.parametrize(
    "division_code",
    [0, -1, True, False, 1.5, "123", None],
)
def test_all_hazards_rejects_invalid_division_code(
    client,
    division_code,
):
    with pytest.raises(ValueError, match="division_code"):
        client.get_all_hazards(division_code)


@pytest.mark.parametrize(
    "hazard_type",
    ["", "fl", "FLOOD", "A1", "F L", None, 123],
)
def test_hazard_report_rejects_invalid_hazard_type(
    client,
    hazard_type,
):
    with pytest.raises(ValueError, match="hazard_type"):
        client.get_hazard_report(123, hazard_type)


def test_get_all_hazards_returns_valid_payload(
    client,
    monkeypatch,
):
    payload = [
        {
            "hazardtype": {"mnemonic": "FL", "name": "River Flood"},
            "hazardlevel": {"mnemonic": "H", "name": "High"},
        }
    ]
    calls = mock_json_response(monkeypatch, payload)

    result = client.get_all_hazards(12345)

    assert result == payload
    assert len(calls) == 1

    request, timeout = calls[0]
    assert request.full_url == (
        "https://example.test/en/report/12345.json"
    )
    assert request.get_method() == "GET"
    assert request.get_header("Accept") == "application/json"
    assert timeout == 7


@pytest.mark.parametrize(
    "division_code",
    [
        3173,
        149626,
        3177,
        149627,
        3179,
        3180,
        3181,
    ],
)
def test_official_uae_emirate_codes_are_used_in_report_url(
    client,
    monkeypatch,
    division_code,
):
    payload = [
        {
            "hazardtype": {"mnemonic": "FL", "name": "River Flood"},
            "hazardlevel": {"mnemonic": "HIG", "name": "High"},
        }
    ]
    calls = mock_json_response(monkeypatch, payload)

    result = client.get_all_hazards(division_code)

    assert result == payload
    assert len(calls) == 1

    request, _ = calls[0]
    assert request.full_url == (
        f"https://example.test/en/report/{division_code}.json"
    )


@pytest.mark.parametrize(
    "division_code",
    [
        3173,
        149626,
        3177,
        149627,
        3179,
        3180,
        3181,
    ],
)
def test_official_uae_emirate_codes_are_used_in_hazard_report_url(
    client,
    monkeypatch,
    division_code,
):
    payload = {
        "hazard_category": {
            "hazard_level": "High",
        },
        "sources": [],
    }
    calls = mock_json_response(monkeypatch, payload)

    result = client.get_hazard_report(division_code, "FL")

    assert result == payload
    request, _ = calls[0]
    assert request.full_url == (
        f"https://example.test/en/report/{division_code}/FL.json"
    )


def test_get_hazard_report_returns_valid_payload(
    client,
    monkeypatch,
):
    payload = {
        "hazard_category": {
            "hazard_level": "High",
        },
        "sources": [],
    }
    calls = mock_json_response(monkeypatch, payload)

    result = client.get_hazard_report(12345, "FL")

    assert result == payload
    request, _ = calls[0]
    assert request.full_url == (
        "https://example.test/en/report/12345/FL.json"
    )


def test_get_divisions_for_hazard_returns_valid_payload(
    client,
    monkeypatch,
):
    payload = [
        {
            "code": 12345,
            "name": "Test Division",
        }
    ]
    calls = mock_json_response(monkeypatch, payload)

    result = client.get_divisions_for_hazard("FL")

    assert result == payload
    request, _ = calls[0]
    assert request.full_url == (
        "https://example.test/en/admindiv_hazardsets/FL.json"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        "invalid",
        None,
        [{"hazardtype": {}, "hazardlevel": {}}],
        [{"hazardtype": {"mnemonic": "FL"}}],
        [{"hazardlevel": {"mnemonic": "H"}}],
        [
            {
                "hazardtype": {"mnemonic": 123},
                "hazardlevel": {"mnemonic": "H"},
            }
        ],
        [
            {
                "hazardtype": {"mnemonic": "FL"},
                "hazardlevel": {"mnemonic": None},
            }
        ],
    ],
)
def test_get_all_hazards_rejects_invalid_payload(
    client,
    monkeypatch,
    payload,
):
    mock_json_response(monkeypatch, payload)

    with pytest.raises(ThinkHazardResponseValidationError):
        client.get_all_hazards(12345)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        None,
        "invalid",
        {},
        {"hazard_category": None},
        {"hazard_category": {}},
        {"hazard_category": {"hazard_level": 123}},
    ],
)
def test_get_hazard_report_rejects_invalid_payload(
    client,
    monkeypatch,
    payload,
):
    mock_json_response(monkeypatch, payload)

    with pytest.raises(ThinkHazardResponseValidationError):
        client.get_hazard_report(12345, "FL")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        None,
        "invalid",
        [{"code": 0, "name": "Test"}],
        [{"code": -1, "name": "Test"}],
        [{"code": True, "name": "Test"}],
        [{"code": "123", "name": "Test"}],
        [{"code": 123}],
        [{"code": 123, "name": 456}],
        ["invalid"],
    ],
)
def test_get_divisions_rejects_invalid_payload(
    client,
    monkeypatch,
    payload,
):
    mock_json_response(monkeypatch, payload)

    with pytest.raises(ThinkHazardResponseValidationError):
        client.get_divisions_for_hazard("FL")


def test_client_rejects_non_200_response(
    client,
    monkeypatch,
):
    mock_json_response(
        monkeypatch,
        {"error": "Unavailable"},
        status=503,
    )

    with pytest.raises(
        ThinkHazardUnavailableError,
        match="503",
    ):
        client.get_all_hazards(12345)


def test_client_converts_http_error(
    client,
    monkeypatch,
):
    def fake_urlopen(request, timeout):
        raise HTTPError(
            request.full_url,
            503,
            "Service Unavailable",
            None,
            BytesIO(b""),
        )

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)

    with pytest.raises(
        ThinkHazardUnavailableError,
        match="503",
    ):
        client.get_all_hazards(12345)


def test_client_converts_url_error(
    client,
    monkeypatch,
):
    def fake_urlopen(request, timeout):
        raise URLError("Connection failed")

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)

    with pytest.raises(
        ThinkHazardUnavailableError,
        match="Could not retrieve data",
    ):
        client.get_all_hazards(12345)


@pytest.mark.parametrize(
    "payload",
    [
        b"not-json",
        b"\xff\xfe",
    ],
)
def test_client_rejects_invalid_json(
    client,
    monkeypatch,
    payload,
):
    response = FakeResponse(payload)

    monkeypatch.setattr(
        client_module,
        "urlopen",
        lambda request, timeout: response,
    )

    with pytest.raises(ThinkHazardResponseValidationError):
        client.get_all_hazards(12345)
