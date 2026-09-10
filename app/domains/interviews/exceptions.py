from app.core.exceptions import ConflictError, NotFoundError, ValidationError


class InterviewRequestNotFoundError(NotFoundError):
    """No interview has been scheduled for the application yet."""


class InterviewApplicationNotFoundError(NotFoundError):
    pass


class InterviewJobPostNotFoundError(NotFoundError):
    pass


class ApplicationNotInInterviewError(ConflictError):
    """Interview scheduling is only available while the application is in the
    `interview` stage."""


class SlotUnavailableError(ConflictError):
    """The chosen time overlaps another confirmed interview or is no longer
    open."""


class SlotNotOnRequestError(ValidationError):
    """The referenced slot is not part of this interview request."""


class InvalidAvailabilityWindowError(ValidationError):
    pass


class UnknownInterviewerError(ValidationError):
    pass
