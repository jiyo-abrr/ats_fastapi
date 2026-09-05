from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)
from app.domains.technical_assessment_templates.service import (
    TechnicalAssessmentTemplateService,
)


def get_technical_assessment_template_repository(
    db: AsyncSession = Depends(get_db),
) -> TechnicalAssessmentTemplateRepository:
    return TechnicalAssessmentTemplateRepository(db)


def get_technical_assessment_template_service(
    templates: TechnicalAssessmentTemplateRepository = Depends(
        get_technical_assessment_template_repository
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> TechnicalAssessmentTemplateService:
    return TechnicalAssessmentTemplateService(templates, uow)
