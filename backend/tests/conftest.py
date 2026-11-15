"""Test setup. Tests never need a real PostgreSQL database."""
import os

# Must be set before the app is imported.
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ccr.db.session import get_db
from ccr.main import app


class BrokenSession:
    """Pretends to be a database session whose database is down."""

    def execute(self, *args, **kwargs):
        raise ConnectionError("simulated database outage: secret-detail-123")

    def close(self):
        pass


@pytest.fixture
def client_db_up():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    def override():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_db_down():
    def override():
        yield BrokenSession()

    app.dependency_overrides[get_db] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
