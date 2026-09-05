from fastapi import APIRouter

from app.domains.auth.router import router as auth_router
from app.domains.rbac.router import router as rbac_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(rbac_router)
