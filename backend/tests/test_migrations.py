"""Checks that the migration builds exactly the tables the code expects."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from ccr.core.config import get_settings
from ccr.db.base import Base
import ccr.models  # noqa: F401

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_migration_matches_models_and_can_be_undone(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'migration_test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    try:
        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))

        command.upgrade(cfg, "head")
        engine = create_engine(db_url)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names()) - {"alembic_version"}
        assert tables == set(Base.metadata.tables)
        for name, table in Base.metadata.tables.items():
            migrated = {c["name"] for c in inspector.get_columns(name)}
            assert migrated == {c.name for c in table.columns}, name

        command.downgrade(cfg, "base")
        inspector = inspect(create_engine(db_url))
        assert set(inspector.get_table_names()) - {"alembic_version"} == set()
    finally:
        get_settings.cache_clear()
