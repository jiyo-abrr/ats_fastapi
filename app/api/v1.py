from fastapi import APIRouter

from app.domains.applications.router import router as application_router
from app.domains.auth.router import router as auth_router
from app.domains.company_addresses.router import router as company_address_router
from app.domains.job_posts.router import router as job_post_router
from app.domains.positions.router import router as position_router
from app.domains.rbac.router import router as rbac_router
from app.domains.tags.router import router as tag_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(rbac_router)
v1_router.include_router(company_address_router)
v1_router.include_router(position_router)
v1_router.include_router(tag_router)
v1_router.include_router(job_post_router)
v1_router.include_router(application_router)
