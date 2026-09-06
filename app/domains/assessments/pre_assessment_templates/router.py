import uuid

from fastapi import APIRouter, Depends, status

from app.domains.assessments.pre_assessment_templates.dependencies import (
    get_pre_assessment_template_service,
)
from app.domains.assessments.pre_assessment_templates.schemas import (
    PreAssessmentQuestionCreate,
    PreAssessmentTemplateCreate,
    PreAssessmentTemplateOut,
    PreAssessmentTemplateUpdate,
)
from app.domains.assessments.pre_assessment_templates.service import (
    PreAssessmentTemplateService,
)
from app.domains.rbac.dependencies import require_permission

# Unlike positions/tags/company_addresses/job_posts, reads here are also
# gated — templates are internal HR-authoring content, not a public listing.
_manage_jobs = Depends(require_permission("manage_jobs"))

router = APIRouter(
    prefix="/pre-assessment-templates",
    tags=["pre-assessment-templates"],
    dependencies=[_manage_jobs],
)


@router.post(
    "", response_model=PreAssessmentTemplateOut, status_code=status.HTTP_201_CREATED
)
async def create_pre_assessment_template(
    payload: PreAssessmentTemplateCreate,
    service: PreAssessmentTemplateService = Depends(
        get_pre_assessment_template_service
    ),
) -> PreAssessmentTemplateOut:
    return await service.create(**payload.model_dump())


@router.get("", response_model=list[PreAssessmentTemplateOut])
async def list_pre_assessment_templates(
    service: PreAssessmentTemplateService = Depends(
        get_pre_assessment_template_service
    ),
) -> list[PreAssessmentTemplateOut]:
    return await service.list()


@router.get("/{template_id}", response_model=PreAssessmentTemplateOut)
async def get_pre_assessment_template(
    template_id: uuid.UUID,
    service: PreAssessmentTemplateService = Depends(
        get_pre_assessment_template_service
    ),
) -> PreAssessmentTemplateOut:
    return await service.get(template_id)


@router.put("/{template_id}", response_model=PreAssessmentTemplateOut)
async def update_pre_assessment_template(
    template_id: uuid.UUID,
    payload: PreAssessmentTemplateUpdate,
    service: PreAssessmentTemplateService = Depends(
        get_pre_assessment_template_service
    ),
) -> PreAssessmentTemplateOut:
    return await service.update(template_id, **payload.model_dump())


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pre_assessment_template(
    template_id: uuid.UUID,
    service: PreAssessmentTemplateService = Depends(
        get_pre_assessment_template_service
    ),
) -> None:
    await service.delete(template_id)


@router.post(
    "/{template_id}/questions",
    response_model=PreAssessmentTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_pre_assessment_question(
    template_id: uuid.UUID,
    payload: PreAssessmentQuestionCreate,
    service: PreAssessmentTemplateService = Depends(
        get_pre_assessment_template_service
    ),
) -> PreAssessmentTemplateOut:
    return await service.add_question(template_id, **payload.model_dump())
