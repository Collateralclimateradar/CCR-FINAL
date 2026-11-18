"""Application entry point."""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ccr.api.v1 import api_router, dev_router
from ccr.core.config import Settings, get_settings
from ccr.core.logging import configure_logging
from ccr.db.session import dispose_engine

logger = logging.getLogger(__name__)


def dev_routes_enabled(settings: Settings) -> bool:
    """Development routes have no login, so they need explicit permission.

    They are OFF by default, and always OFF in production.
    """
    return settings.enable_dev_routes and settings.environment.lower() != "production"


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

    if dev_routes_enabled(settings):
        logger.warning(
            "Development routes are ON (no login yet). Never expose this to the internet."
        )
        app.include_router(dev_router, prefix="/api/v1")
    elif settings.enable_dev_routes:
        logger.error(
            "ENABLE_DEV_ROUTES is set but ignored because ENVIRONMENT is production."
        )
    return app


app = create_app()
