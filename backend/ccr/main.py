"""Application entry point."""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ccr.api.v1 import api_router
from ccr.core.config import get_settings
from ccr.core.logging import configure_logging
from ccr.db.session import dispose_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    logger.info(
        "Starting %s v%s (%s)",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )
    yield
    dispose_engine()
    logger.info("Application stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    is_production = settings.environment.lower() == "production"
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        # Interactive docs are hidden in production.
        docs_url=None if is_production else "/docs",
        redoc_url=None,
        openapi_url=None if is_production else "/openapi.json",
        lifespan=lifespan,
    )
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
