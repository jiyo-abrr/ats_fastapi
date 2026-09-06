from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.assessments.culture_fit_templates.repository import (
    CultureFitTemplateRepository,
)
from app.domains.assessments.culture_fit_templates.service import (
    CultureFitTemplateService,
)


def get_culture_fit_template_repository(
    db: AsyncSession = Depends(get_db),
) -> CultureFitTemplateRepository:
    return CultureFitTemplateRepository(db)


def get_culture_fit_template_service(
    templates: CultureFitTemplateRepository = Depends(
        get_culture_fit_template_repository
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> CultureFitTemplateService:
    return CultureFitTemplateService(templates, uow)
