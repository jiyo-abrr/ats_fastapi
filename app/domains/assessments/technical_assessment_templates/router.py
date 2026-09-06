import uuid

from fastapi import APIRouter, Depends, status
from fastapi_pagination import Page
from fastapi_pagination.ext.sqlalchemy import apaginate
from fastapi_querybuilder import QueryBuilder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.domains.assessments.technical_assessment_templates.dependencies import (
    get_technical_assessment_template_repository,
    get_technical_assessment_template_service,
)
from app.domains.assessments.technical_assessment_templates.models import (
    TechnicalAssessmentTemplate as TechnicalAssessmentTemplateModel,
)
from app.domains.assessments.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)
from app.domains.assessments.technical_assessment_templates.schemas import (
    TechnicalAssessmentQuestionCreate,
    TechnicalAssessmentTemplateCreate,
    TechnicalAssessmentTemplateOut,
    TechnicalAssessmentTemplateUpdate,
)
from app.domains.assessments.technical_assessment_templates.service import (
    TechnicalAssessmentTemplateService,
)
from app.domains.rbac.dependencies import require_permission

# Unlike positions/tags/company_addresses/job_posts, reads here are also
# gated — templates are internal HR-authoring content, not a public listing.
_manage_jobs = Depends(require_permission("manage_jobs"))

router = APIRouter(
    prefix="/technical-assessment-templates",
    tags=["technical-assessment-templates"],
    dependencies=[_manage_jobs],
)


@router.post(
    "",
    response_model=TechnicalAssessmentTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_technical_assessment_template(
    payload: TechnicalAssessmentTemplateCreate,
    service: TechnicalAssessmentTemplateService = Depends(
        get_technical_assessment_template_service
    ),
) -> TechnicalAssessmentTemplateOut:
    return await service.create(**payload.model_dump())


@router.get("", response_model=Page[TechnicalAssessmentTemplateOut])
async def list_technical_assessment_templates(
    query=QueryBuilder(TechnicalAssessmentTemplateModel),
    db: AsyncSession = Depends(get_db),
    repo: TechnicalAssessmentTemplateRepository = Depends(
        get_technical_assessment_template_repository
    ),
) -> Page[TechnicalAssessmentTemplateOut]:
    return await apaginate(db, query, transformer=repo.map_many)


@router.get("/{template_id}", response_model=TechnicalAssessmentTemplateOut)
async def get_technical_assessment_template(
    template_id: uuid.UUID,
    service: TechnicalAssessmentTemplateService = Depends(
        get_technical_assessment_template_service
    ),
) -> TechnicalAssessmentTemplateOut:
    return await service.get(template_id)


@router.put("/{template_id}", response_model=TechnicalAssessmentTemplateOut)
async def update_technical_assessment_template(
    template_id: uuid.UUID,
    payload: TechnicalAssessmentTemplateUpdate,
    service: TechnicalAssessmentTemplateService = Depends(
        get_technical_assessment_template_service
    ),
) -> TechnicalAssessmentTemplateOut:
    return await service.update(template_id, **payload.model_dump())


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_technical_assessment_template(
    template_id: uuid.UUID,
    service: TechnicalAssessmentTemplateService = Depends(
        get_technical_assessment_template_service
    ),
) -> None:
    await service.delete(template_id)


@router.post(
    "/{template_id}/questions",
    response_model=TechnicalAssessmentTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_technical_assessment_question(
    template_id: uuid.UUID,
    payload: TechnicalAssessmentQuestionCreate,
    service: TechnicalAssessmentTemplateService = Depends(
        get_technical_assessment_template_service
    ),
) -> TechnicalAssessmentTemplateOut:
    return await service.add_question(template_id, **payload.model_dump())
