from app.core.exceptions import ConflictError, NotFoundError


class JobPostNotFoundError(NotFoundError):
    pass


class AssessmentTemplateAlreadyAttachedError(ConflictError):
    pass


class JobPostAssessmentsIncompleteError(ConflictError):
    """A job post must have all three assessments (pre-assessment, culture fit,
    technical) attached before it can be published, and they can't be detached
    while it stays published."""
