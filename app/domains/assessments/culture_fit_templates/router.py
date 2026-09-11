import uuid

from fastapi import APIRouter, Depends, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from fastapi_querybuilder import QueryBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.assessments.culture_fit_templates.dependencies import (
    get_culture_fit_template_repository,
    get_culture_fit_template_service,
)
from app.domains.assessments.culture_fit_templates.models import (
    CultureFitTemplate as CultureFitTemplateModel,
)
from app.domains.assessments.culture_fit_templates.repository import (
    CultureFitTemplateRepository,
)
from app.domains.assessments.culture_fit_templates.schemas import (
    CultureFitQuestionCreate,
    CultureFitQuestionsReorder,
    CultureFitQuestionUpdate,
    CultureFitTemplateCreate,
    CultureFitTemplateOut,
    CultureFitTemplateUpdate,
)
from app.domains.assessments.culture_fit_templates.service import (
    CultureFitTemplateService,
)
from app.domains.rbac.dependencies import require_permission
from app.use_cases.delete_assessment_template import DeleteAssessmentTemplate
from app.use_cases.dependencies import get_delete_culture_fit_template

# Unlike positions/tags/company_addresses/job_posts, reads here are also
# gated — templates are internal HR-authoring content, not a public listing.
_manage_jobs = Depends(require_permission("manage_jobs"))

router = APIRouter(
    prefix="/culture-fit-templates",
    tags=["culture-fit-templates"],
    dependencies=[_manage_jobs],
)


@router.post(
    "", response_model=CultureFitTemplateOut, status_code=status.HTTP_201_CREATED
)
async def create_culture_fit_template(
    payload: CultureFitTemplateCreate,
    service: CultureFitTemplateService = Depends(get_culture_fit_template_service),
) -> CultureFitTemplateOut:
    return await service.create(**payload.model_dump())


@router.get("", response_model=Page[CultureFitTemplateOut])
async def list_culture_fit_templates(
    query=QueryBuilder(CultureFitTemplateModel),
    db: AsyncSession = Depends(get_db),
    repo: CultureFitTemplateRepository = Depends(get_culture_fit_template_repository),
) -> Page[CultureFitTemplateOut]:
    return await apaginate(db, query, transformer=repo.map_many)


@router.get("/{template_id}", response_model=CultureFitTemplateOut)
async def get_culture_fit_template(
    template_id: uuid.UUID,
    service: CultureFitTemplateService = Depends(get_culture_fit_template_service),
) -> CultureFitTemplateOut:
    return await service.get(template_id)


@router.put("/{template_id}", response_model=CultureFitTemplateOut)
async def update_culture_fit_template(
    template_id: uuid.UUID,
    payload: CultureFitTemplateUpdate,
    service: CultureFitTemplateService = Depends(get_culture_fit_template_service),
) -> CultureFitTemplateOut:
    return await service.update(template_id, **payload.model_dump())


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_culture_fit_template(
    template_id: uuid.UUID,
    delete_template: DeleteAssessmentTemplate = Depends(
        get_delete_culture_fit_template
    ),
) -> None:
    # 409 if any attempt references it (no DB FK across that boundary — F04).
    await delete_template.execute(template_id)


@router.post(
    "/{template_id}/questions",
    response_model=CultureFitTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_culture_fit_question(
    template_id: uuid.UUID,
    payload: CultureFitQuestionCreate,
    service: CultureFitTemplateService = Depends(get_culture_fit_template_service),
) -> CultureFitTemplateOut:
    return await service.add_question(template_id, **payload.model_dump())


# Declared before the parametrized `/questions/{question_id}` route below so
# "reorder" is never parsed as a question id.
@router.put("/{template_id}/questions/reorder", response_model=CultureFitTemplateOut)
async def reorder_culture_fit_questions(
    template_id: uuid.UUID,
    payload: CultureFitQuestionsReorder,
    service: CultureFitTemplateService = Depends(get_culture_fit_template_service),
) -> CultureFitTemplateOut:
    return await service.reorder_questions(template_id, payload.question_ids)


@router.put(
    "/{template_id}/questions/{question_id}",
    response_model=CultureFitTemplateOut,
)
async def update_culture_fit_question(
    template_id: uuid.UUID,
    question_id: uuid.UUID,
    payload: CultureFitQuestionUpdate,
    service: CultureFitTemplateService = Depends(get_culture_fit_template_service),
) -> CultureFitTemplateOut:
    return await service.update_question(
        template_id, question_id, **payload.model_dump()
    )


@router.delete(
    "/{template_id}/questions/{question_id}",
    response_model=CultureFitTemplateOut,
)
async def delete_culture_fit_question(
    template_id: uuid.UUID,
    question_id: uuid.UUID,
    service: CultureFitTemplateService = Depends(get_culture_fit_template_service),
) -> CultureFitTemplateOut:
    return await service.delete_question(template_id, question_id)
