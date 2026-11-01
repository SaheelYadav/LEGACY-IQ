"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints.code_intelligence import router as code_intel_router
from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.organizations import router as organizations_router
from app.api.v1.endpoints.projects import router as projects_router
from app.api.v1.endpoints.repositories import router as repositories_router
from app.api.v1.endpoints.search import router as search_router
from app.api.v1.endpoints.technical_intelligence import router as tech_intel_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(organizations_router, tags=["organizations"])
api_v1_router.include_router(projects_router, tags=["projects"])
api_v1_router.include_router(repositories_router, tags=["repositories"])
api_v1_router.include_router(code_intel_router, tags=["code-intelligence"])
api_v1_router.include_router(tech_intel_router, tags=["technical-intelligence"])
api_v1_router.include_router(search_router, tags=["search"])
