from fastapi import APIRouter

from app.domains.analytics.router import router as analytics_router
from app.domains.applications.router import router as application_router
from app.domains.assessments.attempts.router import router as assessment_router
from app.domains.assessments.culture_fit_templates.router import (
    router as culture_fit_template_router,
)
from app.domains.assessments.pre_assessment_templates.router import (
    router as pre_assessment_template_router,
)
from app.domains.assessments.technical_assessment_templates.router import (
    router as technical_assessment_template_router,
)
from app.domains.auth.router import router as auth_router
from app.domains.company_addresses.router import router as company_address_router
from app.domains.evaluations.router import router as evaluation_router
from app.domains.interviews.router import (
    availability_router as interview_availability_router,
)
from app.domains.interviews.router import interview_router
from app.domains.job_posts.router import router as job_post_router
from app.domains.positions.router import router as position_router
from app.domains.rbac.router import router as rbac_router
from app.domains.tags.router import router as tag_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(auth_router)
v1_router.include_router(analytics_router)
v1_router.include_router(rbac_router)
v1_router.include_router(company_address_router)
v1_router.include_router(position_router)
v1_router.include_router(tag_router)
v1_router.include_router(pre_assessment_template_router)
v1_router.include_router(culture_fit_template_router)
v1_router.include_router(technical_assessment_template_router)
v1_router.include_router(job_post_router)
# Interviews + evaluations mount their own routers under /applications; include
# them before application_router so their static paths (e.g. /applications/export,
# /applications/evaluations) win over /applications/{application_id}.
v1_router.include_router(interview_availability_router)
v1_router.include_router(interview_router)
v1_router.include_router(evaluation_router)
v1_router.include_router(application_router)
v1_router.include_router(assessment_router)
