"""The login-free development routes must be closed unless explicitly enabled."""
import pytest
from fastapi.testclient import TestClient

from ccr.core.config import get_settings
from ccr.main import create_app


@pytest.fixture
def make_client(monkeypatch):
    def _make(environment, flag):
        monkeypatch.setenv("ENVIRONMENT", environment)
        if flag is None:
            monkeypatch.delenv("ENABLE_DEV_ROUTES", raising=False)
        else:
            monkeypatch.setenv("ENABLE_DEV_ROUTES", flag)
        get_settings.cache_clear()
        return TestClient(create_app())

    yield _make
    get_settings.cache_clear()


def test_dev_routes_are_closed_by_default(make_client):
    client = make_client("development", None)
    assert client.post("/api/v1/organizations", json={"name": "X"}).status_code == 404


def test_dev_routes_open_only_when_explicitly_enabled(make_client):
    client = make_client("development", "true")
    # An empty body is rejected with 422: the route exists, but the input is invalid.
    assert client.post("/api/v1/organizations", json={}).status_code == 422


def test_dev_routes_stay_closed_in_production_even_if_enabled(make_client):
    client = make_client("production", "true")
    assert client.post("/api/v1/organizations", json={"name": "X"}).status_code == 404


def test_health_is_available_with_dev_routes_closed(make_client):
    client = make_client("production", None)
    assert client.get("/api/v1/health").status_code in (200, 503)
