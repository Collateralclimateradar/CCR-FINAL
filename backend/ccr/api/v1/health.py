"""Health check endpoint: GET /api/v1/health."""
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from ccr.core.config import get_settings
from ccr.db.session import get_db

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


class AppInfo(BaseModel):
    name: str
    version: str
    environment: str


class DatabaseInfo(BaseModel):
    status: Literal["up", "down"]


class HealthResponse(BaseModel):
    status: Literal["healthy", "unhealthy"]
    app: AppInfo
    database: DatabaseInfo
    timestamp: datetime


def check_database(db: Session) -> bool:
    """Really talk to the database. Returns False if it cannot answer."""
    try:
        db.execute(text("SELECT 1"))
        return True
    except Exception:  # any failure means the database is not usable
        logger.exception("Database health check failed")
        return False


@router.get("/health", response_model=HealthResponse)
def health(response: Response, db: Session = Depends(get_db)) -> HealthResponse:
    settings = get_settings()
    db_up = check_database(db)
    if not db_up:
        response.status_code = 503  # service unavailable
    return HealthResponse(
        status="healthy" if db_up else "unhealthy",
        app=AppInfo(
            name=settings.app_name,
            version=settings.app_version,
            environment=settings.environment,
        ),
        database=DatabaseInfo(status="up" if db_up else "down"),
        timestamp=datetime.now(timezone.utc),
    )
