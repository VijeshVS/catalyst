from fastapi import APIRouter
from app.api.v1.health import router as health_router
from app.api.v1.flags import router as flags_router
from app.api.v1.evaluate import router as eval_router
from app.api.v1.bootstrap import router as bootstrap_router
from app.api.v1.audit import router as audit_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.projects import router as projects_router

api_v1_router = APIRouter()
api_v1_router.include_router(health_router)
api_v1_router.include_router(organizations_router)
api_v1_router.include_router(projects_router)
api_v1_router.include_router(flags_router)
api_v1_router.include_router(eval_router)
api_v1_router.include_router(bootstrap_router)
api_v1_router.include_router(audit_router)

__all__ = ["api_v1_router"]
