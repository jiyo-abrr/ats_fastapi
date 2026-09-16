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


class InterviewAlreadyConfirmedError(ConflictError):
    """The candidate already confirmed a time. Self-service rescheduling is
    disabled — a change could silently invalidate HR's calendar or a slot
    another candidate passed on; HR must clear and re-send instead."""


class InterviewNotConfirmedError(ConflictError):
    """Reopen was called but nothing is currently confirmed on this
    interview — there's nothing to un-confirm."""


class SlotNotOnRequestError(ValidationError):
    """The referenced slot is not part of this interview request."""


class InvalidAvailabilityWindowError(ValidationError):
    pass


class UnknownInterviewerError(ValidationError):
    pass


class UnknownCompanyAddressError(ValidationError):
    """A `company_address_id` doesn't refer to an existing company address."""
