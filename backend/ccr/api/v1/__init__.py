
"""API version 1: collects all v1 routes."""

from fastapi import APIRouter

from ccr.api.v1.audit import router as audit_router
from ccr.api.v1.auth import router as auth_router
from ccr.api.v1.climate_assessments import (
    router as climate_assessments_router,
)
from ccr.api.v1.climate_location_screening import (
    router as climate_location_screening_router,
)
from ccr.api.v1.collaterals import router as collaterals_router
from ccr.api.v1.health import router as health_router
from ccr.api.v1.organizations import router as organizations_router

# Always available.
api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(audit_router)
api_router.include_router(climate_assessments_router)
api_router.include_router(climate_location_screening_router)

# DEVELOPMENT ONLY: no login exists yet for these routes.
# main.py enables them only when development routes are explicitly enabled.
dev_router = APIRouter()
dev_router.include_router(organizations_router)
dev_router.include_router(collaterals_router)
