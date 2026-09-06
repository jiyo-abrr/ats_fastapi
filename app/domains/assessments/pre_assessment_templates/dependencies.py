from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.unit_of_work import UnitOfWork, get_unit_of_work
from app.domains.assessments.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)
from app.domains.assessments.pre_assessment_templates.service import (
    PreAssessmentTemplateService,
)


def get_pre_assessment_template_repository(
    db: AsyncSession = Depends(get_db),
) -> PreAssessmentTemplateRepository:
    return PreAssessmentTemplateRepository(db)


def get_pre_assessment_template_service(
    templates: PreAssessmentTemplateRepository = Depends(
        get_pre_assessment_template_repository
    ),
    uow: UnitOfWork = Depends(get_unit_of_work),
) -> PreAssessmentTemplateService:
    return PreAssessmentTemplateService(templates, uow)
