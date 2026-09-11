from app.core.template_service import BaseTemplateService
from app.core.unit_of_work import UnitOfWork
from app.domains.assessments.culture_fit_templates import entities
from app.domains.assessments.culture_fit_templates.exceptions import (
    CultureFitQuestionNotFoundError,
    CultureFitQuestionsReorderError,
    CultureFitTemplateInUseError,
    CultureFitTemplateNotFoundError,
)
from app.domains.assessments.culture_fit_templates.repository import (
    CultureFitTemplateRepository,
)


class CultureFitTemplateService(
    BaseTemplateService[entities.CultureFitTemplate, entities.CultureFitQuestion]
):
    """CRUD + question authoring for culture-fit templates — logic lives in
    `BaseTemplateService` (shared byte-for-byte with pre-assessment and
    technical; review F20); this subclass only binds the domain-specific
    types."""

    template_entity_cls = entities.CultureFitTemplate
    question_entity_cls = entities.CultureFitQuestion
    not_found_error = CultureFitTemplateNotFoundError
    in_use_error = CultureFitTemplateInUseError
    question_not_found_error = CultureFitQuestionNotFoundError
    reorder_error = CultureFitQuestionsReorderError
    label = "culture-fit"

    def __init__(self, templates: CultureFitTemplateRepository, uow: UnitOfWork):
        super().__init__(templates, uow)
