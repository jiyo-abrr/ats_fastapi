from app.core.exceptions import ConflictError, NotFoundError, ValidationError


class TechnicalAssessmentTemplateNotFoundError(NotFoundError):
    pass


class TechnicalAssessmentTemplateInUseError(ConflictError):
    pass


class TechnicalAssessmentQuestionNotFoundError(NotFoundError):
    pass


class TechnicalAssessmentQuestionsReorderError(ValidationError):
    pass
