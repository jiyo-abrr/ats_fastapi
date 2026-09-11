from enum import StrEnum

from app.domains.applications.enums import ApplicationStatus


class InterviewMode(StrEnum):
    VIDEO = "video"
    ONSITE = "onsite"
    PHONE = "phone"


# When an application reaches one of these, any interview slot it holds is
# released — it no longer blocks another applicant's booking and drops off the
# calendar. The InterviewRequest / InterviewSlot rows stay for history; only
# the capacity/calendar *queries* filter them out (review F28, decision:
# auto-release). success / failed are kept — that interview actually happened.
INTERVIEW_RELEASED_APPLICATION_STATUSES = frozenset(
    {
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.DENIED,
        ApplicationStatus.DISQUALIFIED,
    }
)
