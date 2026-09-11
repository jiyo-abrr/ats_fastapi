import uuid

from fastapi import APIRouter, Depends, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from fastapi_querybuilder import QueryBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.assessments.pre_assessment_templates.dependencies import (
    get_pre_assessment_template_repository,
    get_pre_assessment_template_service,
)
from app.domains.assessments.pre_assessment_templates.models import (
    PreAssessmentTemplate as PreAssessmentTemplateModel,
)
from app.domains.assessments.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)
from app.domains.assessments.pre_assessment_templates.schemas import (
    PreAssessmentQuestionCreate,
    PreAssessmentQuestionsReorder,
    PreAssessmentQuestionUpdate,
    PreAssessmentTemplateCreate,
    PreAssessmentTemplateOut,
    PreAssessmentTemplateUpdate,
)
from app.domains.assessments.pre_assessment_templates.service import (
    PreAssessmentTemplateService,
)
from app.domains.rbac.dependencies import require_permission
from app.use_cases.delete_assessment_template import DeleteAssessmentTemplate
from app.use_cases.dependencies import get_delete_pre_assessment_template

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


@router.get("", response_model=Page[PreAssessmentTemplateOut])
async def list_pre_assessment_templates(
    query=QueryBuilder(PreAssessmentTemplateModel),
    db: AsyncSession = Depends(get_db),
    repo: PreAssessmentTemplateRepository = Depends(
        get_pre_assessment_template_repository
    ),
) -> Page[PreAssessmentTemplateOut]:
    return await apaginate(db, query, transformer=repo.map_many)


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
    delete_template: DeleteAssessmentTemplate = Depends(
        get_delete_pre_assessment_template
    ),
) -> None:
    # 409 if any attempt references it (no DB FK across that boundary — F04).
    await delete_template.execute(template_id)


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


# Declared before the parametrized `/questions/{question_id}` route below so
# "reorder" is never parsed as a question id.
@router.put("/{template_id}/questions/reorder", response_model=PreAssessmentTemplateOut)
async def reorder_pre_assessment_questions(
    template_id: uuid.UUID,
    payload: PreAssessmentQuestionsReorder,
    service: PreAssessmentTemplateService = Depends(
        get_pre_assessment_template_service
    ),
) -> PreAssessmentTemplateOut:
    return await service.reorder_questions(template_id, payload.question_ids)


@router.put(
    "/{template_id}/questions/{question_id}",
    response_model=PreAssessmentTemplateOut,
)
async def update_pre_assessment_question(
    template_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: PreAssessmentQuestionUpdate,
    service: PreAssessmentTemplateService = Depends(
        get_pre_assessment_template_service
    ),
) -> PreAssessmentTemplateOut:
    return await service.update_question(
        template_id, question_id, **payload.model_dump()
    )


@router.delete(
    "/{template_id}/questions/{question_id}",
    response_model=PreAssessmentTemplateOut,
)
async def delete_pre_assessment_question(
    template_id: uuid.UUID,
    question_id: uuid.UUID,
    service: PreAssessmentTemplateService = Depends(
        get_pre_assessment_template_service
    ),
) -> PreAssessmentTemplateOut:
    return await service.delete_question(template_id, question_id)
