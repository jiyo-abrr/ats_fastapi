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
