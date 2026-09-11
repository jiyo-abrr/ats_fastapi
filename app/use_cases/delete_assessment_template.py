"""`delete_assessment_template` — refuses to delete an assessment template
that has attempts pointing at it.

`AssessmentAttempt.template_id` carries no DB foreign key (it's polymorphic
over 3 tables — see CLAUDE.md), so a plain `DELETE` on the template row does
*not* fail when attempts reference it: the template service only catches the
job-post-attachment FK violation. This use case adds the missing check.

It lives in `app/use_cases/` because the 3 template domains must stay
independent of `attempts` (D03) — the check crosses that boundary, so it can't
live in a template service.
"""

import uuid

from app.domains.assessments.attempts.enums import TemplateType
from app.domains.assessments.attempts.repository import AssessmentAttemptRepository
from app.domains.assessments.culture_fit_templates.exceptions import (
    CultureFitTemplateInUseError,
)
from app.domains.assessments.culture_fit_templates.service import (
    CultureFitTemplateService,
)
from app.domains.assessments.pre_assessment_templates.exceptions import (
    PreAssessmentTemplateInUseError,
)
from app.domains.assessments.pre_assessment_templates.service import (
    PreAssessmentTemplateService,
)
from app.domains.assessments.technical_assessment_templates.exceptions import (
    TechnicalAssessmentTemplateInUseError,
)
from app.domains.assessments.technical_assessment_templates.service import (
    TechnicalAssessmentTemplateService,
)

_IN_USE_ERROR = {
    TemplateType.PRE_ASSESSMENT: PreAssessmentTemplateInUseError,
    TemplateType.CULTURE_FIT: CultureFitTemplateInUseError,
    TemplateType.TECHNICAL: TechnicalAssessmentTemplateInUseError,
}

_TemplateService = (
    PreAssessmentTemplateService
    | CultureFitTemplateService
    | TechnicalAssessmentTemplateService
)


class DeleteAssessmentTemplate:
    def __init__(
        self,
        template_type: TemplateType,
        template_service: _TemplateService,
        attempts: AssessmentAttemptRepository,
    ):
        self.template_type = template_type
        self.template_service = template_service
        self.attempts = attempts

    async def execute(self, template_id: uuid.UUID) -> None:
        if await self.attempts.exists_for_template(self.template_type, template_id):
            raise _IN_USE_ERROR[self.template_type](
                f"This {self.template_type.value.replace('_', ' ')} template has "
                "assessment attempts and can't be deleted."
            )
        await self.template_service.delete(template_id)
