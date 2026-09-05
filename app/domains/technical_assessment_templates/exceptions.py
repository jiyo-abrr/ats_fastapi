from app.core.exceptions import ConflictError, NotFoundError


class TechnicalAssessmentTemplateNotFoundError(NotFoundError):
    pass


class TechnicalAssessmentTemplateInUseError(ConflictError):
    pass
