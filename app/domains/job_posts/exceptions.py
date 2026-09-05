from app.core.exceptions import ConflictError, NotFoundError


class JobPostNotFoundError(NotFoundError):
    pass


class AssessmentTemplateAlreadyAttachedError(ConflictError):
    pass
