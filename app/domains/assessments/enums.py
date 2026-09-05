from enum import StrEnum


class AttemptStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"


class TemplateType(StrEnum):
    """Which of the 3 independent template domains an attempt's template_id
    belongs to. Private to this domain — none of the 3 template domains know
    about each other or about this enum; `assessments` is the one place that
    legitimately depends on all 3 and needs to dispatch between them, since
    template_id alone is ambiguous without knowing which table it's in (no
    single FK target is possible across 3 separate tables)."""

    PRE_ASSESSMENT = "pre_assessment"
    CULTURE_FIT = "culture_fit"
    TECHNICAL = "technical"
