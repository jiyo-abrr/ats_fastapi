from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)


class ApplicationNotFoundError(NotFoundError):
    pass


class DuplicateApplicationError(ConflictError):
    pass


class ApplicantExcludedError(ForbiddenError):
    pass


class OnlyApplicantsCanApplyError(ForbiddenError):
    pass


class JobPostNotAcceptingApplicationsError(ValidationError):
    pass


class InvalidApplicationStatusTransitionError(ValidationError):
    pass


class InvalidAssessmentDeadlineExtensionError(ValidationError):
    pass


class ResumeUnavailableError(NotFoundError):
    """The application's résumé object could not be retrieved from storage."""


class ConcurrentApplicationUpdateError(ConflictError):
    """Another request changed this application's status between the read and
    the write. The caller should re-fetch and retry (review F02)."""
