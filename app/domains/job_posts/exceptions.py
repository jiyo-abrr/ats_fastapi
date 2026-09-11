from app.core.exceptions import ConflictError, NotFoundError


class JobPostNotFoundError(NotFoundError):
    pass


class AssessmentTemplateAlreadyAttachedError(ConflictError):
    pass


class JobPostAssessmentsIncompleteError(ConflictError):
    """A job post must have all three assessments (pre-assessment, culture fit,
    technical) attached before it can be published, and they can't be detached
    while it stays published."""


class JobPostInUseError(ConflictError):
    """The job post has applications and can't be deleted — those records
    (applications, assessments, interviews, evaluations, audit trails) outlive
    the requisition. See docs/decisions/D04."""
