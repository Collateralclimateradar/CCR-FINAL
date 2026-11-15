"""API version 1: collects all v1 routes."""
from fastapi import APIRouter

from ccr.api.v1.health import router as health_router

api_router = APIRouter()
api_router.include_router(health_router)
