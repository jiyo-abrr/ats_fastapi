from app.core.template_service import BaseTemplateService
from app.core.unit_of_work import UnitOfWork
from app.domains.assessments.technical_assessment_templates import entities
from app.domains.assessments.technical_assessment_templates.exceptions import (
    TechnicalAssessmentQuestionNotFoundError,
    TechnicalAssessmentQuestionsReorderError,
    TechnicalAssessmentTemplateInUseError,
    TechnicalAssessmentTemplateNotFoundError,
)
from app.domains.assessments.technical_assessment_templates.repository import (
    TechnicalAssessmentTemplateRepository,
)


class TechnicalAssessmentTemplateService(
    BaseTemplateService[
        entities.TechnicalAssessmentTemplate, entities.TechnicalAssessmentQuestion
    ]
):
    """CRUD + question authoring for technical-assessment templates — logic
    lives in `BaseTemplateService` (shared byte-for-byte with pre-assessment
    and culture-fit; review F20); this subclass only binds the
    domain-specific types."""

    template_entity_cls = entities.TechnicalAssessmentTemplate
    question_entity_cls = entities.TechnicalAssessmentQuestion
    not_found_error = TechnicalAssessmentTemplateNotFoundError
    in_use_error = TechnicalAssessmentTemplateInUseError
    question_not_found_error = TechnicalAssessmentQuestionNotFoundError
    reorder_error = TechnicalAssessmentQuestionsReorderError
    label = "technical assessment"

    def __init__(
        self, templates: TechnicalAssessmentTemplateRepository, uow: UnitOfWork
    ):
        super().__init__(templates, uow)
