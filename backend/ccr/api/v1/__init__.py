"""API version 1: collects all v1 routes."""
from fastapi import APIRouter

from ccr.api.v1.collaterals import router as collaterals_router
from ccr.api.v1.health import router as health_router
from ccr.api.v1.organizations import router as organizations_router

# Always available.
api_router = APIRouter()
api_router.include_router(health_router)

# DEVELOPMENT ONLY: no login exists yet, so main.py enables these routes
# only when ENVIRONMENT is "development" or "test".
dev_router = APIRouter()
dev_router.include_router(organizations_router)
dev_router.include_router(collaterals_router)
