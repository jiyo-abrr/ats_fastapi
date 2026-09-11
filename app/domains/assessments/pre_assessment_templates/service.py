from app.core.template_service import BaseTemplateService
from app.core.unit_of_work import UnitOfWork
from app.domains.assessments.pre_assessment_templates import entities
from app.domains.assessments.pre_assessment_templates.exceptions import (
    PreAssessmentQuestionNotFoundError,
    PreAssessmentQuestionsReorderError,
    PreAssessmentTemplateInUseError,
    PreAssessmentTemplateNotFoundError,
)
from app.domains.assessments.pre_assessment_templates.repository import (
    PreAssessmentTemplateRepository,
)


class PreAssessmentTemplateService(
    BaseTemplateService[entities.PreAssessmentTemplate, entities.PreAssessmentQuestion]
):
    """CRUD + question authoring for pre-assessment templates — logic lives in
    `BaseTemplateService` (shared byte-for-byte with culture-fit and technical;
    review F20); this subclass only binds the domain-specific types."""

    template_entity_cls = entities.PreAssessmentTemplate
    question_entity_cls = entities.PreAssessmentQuestion
    not_found_error = PreAssessmentTemplateNotFoundError
    in_use_error = PreAssessmentTemplateInUseError
    question_not_found_error = PreAssessmentQuestionNotFoundError
    reorder_error = PreAssessmentQuestionsReorderError
    label = "pre-assessment"

    def __init__(self, templates: PreAssessmentTemplateRepository, uow: UnitOfWork):
        super().__init__(templates, uow)
