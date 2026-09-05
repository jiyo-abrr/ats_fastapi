import uuid

from fastapi import APIRouter, Depends, status

from app.domains.culture_fit_templates.dependencies import (
    get_culture_fit_template_service,
)
from app.domains.culture_fit_templates.schemas import (
    CultureFitQuestionCreate,
    CultureFitTemplateCreate,
    CultureFitTemplateOut,
    CultureFitTemplateUpdate,
)
from app.domains.culture_fit_templates.service import CultureFitTemplateService
from app.domains.rbac.dependencies import require_permission

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


@router.get("", response_model=list[CultureFitTemplateOut])
async def list_culture_fit_templates(
    service: CultureFitTemplateService = Depends(get_culture_fit_template_service),
) -> list[CultureFitTemplateOut]:
    return await service.list()


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
    service: CultureFitTemplateService = Depends(get_culture_fit_template_service),
) -> None:
    await service.delete(template_id)


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
