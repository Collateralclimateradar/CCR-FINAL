
"""Tests for the real climate screening provider dependency wiring."""

from ccr.api.v1 import climate_location_screening
from ccr.services.thinkhazard_client import ThinkHazardClient
from ccr.services.thinkhazard_provider import ThinkHazardProvider


def test_climate_provider_factory_wires_real_client_and_uae_resolver(
    monkeypatch,
):
    created = {}

    real_client = ThinkHazardClient()
    fake_resolver = object()

    def build_client():
        created["client"] = real_client
        return real_client

    def build_resolver():
        created["resolver"] = fake_resolver
        return fake_resolver

    monkeypatch.setattr(
        climate_location_screening,
        "ThinkHazardClient",
        build_client,
    )
    monkeypatch.setattr(
        climate_location_screening,
        "UAEEmirateResolver",
        build_resolver,
    )

    provider = climate_location_screening.get_climate_data_provider()

    assert isinstance(provider, ThinkHazardProvider)
    assert provider.name == "thinkhazard"
    assert provider._client is real_client
    assert provider._division_resolver is fake_resolver
    assert created["client"] is real_client
    assert created["resolver"] is fake_resolver
