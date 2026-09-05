from app.core.exceptions import ConflictError, NotFoundError


class PreAssessmentTemplateNotFoundError(NotFoundError):
    pass


class PreAssessmentTemplateInUseError(ConflictError):
    pass
