from app.core.exceptions import ConflictError, NotFoundError, ValidationError


class PreAssessmentTemplateNotFoundError(NotFoundError):
    pass


class PreAssessmentTemplateInUseError(ConflictError):
    pass


class PreAssessmentQuestionNotFoundError(NotFoundError):
    pass


class PreAssessmentQuestionsReorderError(ValidationError):
    pass
