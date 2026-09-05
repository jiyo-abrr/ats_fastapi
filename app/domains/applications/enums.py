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
