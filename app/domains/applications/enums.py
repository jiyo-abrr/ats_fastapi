from enum import StrEnum


class ApplicationStatus(StrEnum):
    APPLIED = "applied"
    PRESCREENING = "prescreening"
    INTERVIEW = "interview"
    DENIED = "denied"
    SUCCESS = "success"
    FAILED = "failed"
    DISQUALIFIED = "disqualified"
    WITHDRAWN = "withdrawn"


# Forward-only transitions HR/admin may drive via PATCH /applications/{id}/status.
# `withdrawn` (applicant-only) and `disqualified` (system/scheduler-only) are not
# valid targets here. Source of truth for both the service check and the
# `allowed_status_transitions` field on ApplicationOut / ApplicationReviewOut —
# it lives here (pure data, no deps) so schemas and service can each read it
# without importing the other.
ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.APPLIED: frozenset(
        {ApplicationStatus.PRESCREENING, ApplicationStatus.DENIED}
    ),
    ApplicationStatus.PRESCREENING: frozenset(
        {ApplicationStatus.INTERVIEW, ApplicationStatus.DENIED}
    ),
    ApplicationStatus.INTERVIEW: frozenset(
        {ApplicationStatus.SUCCESS, ApplicationStatus.FAILED}
    ),
}

# Statuses an applicant is still allowed to withdraw from.
WITHDRAWABLE_STATUSES: frozenset[ApplicationStatus] = frozenset(
    {
        ApplicationStatus.APPLIED,
        ApplicationStatus.PRESCREENING,
        ApplicationStatus.INTERVIEW,
    }
)


def allowed_transitions_for(status: str) -> list[str]:
    """Sorted list of statuses HR/admin may move `status` to (empty if terminal
    or unrecognized)."""
    try:
        current = ApplicationStatus(status)
    except ValueError:
        return []
    return sorted(s.value for s in ALLOWED_TRANSITIONS.get(current, frozenset()))


def can_withdraw(status: str) -> bool:
    try:
        return ApplicationStatus(status) in WITHDRAWABLE_STATUSES
    except ValueError:
        return False
