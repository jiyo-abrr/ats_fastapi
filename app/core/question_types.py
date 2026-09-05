"""Shared question-type vocabulary for the assessments feature.

Lives in app/core (not any single domain) because four domains need it —
pre_assessment_templates, culture_fit_templates, technical_assessment_templates
(each validating what HR authors), and assessments (validating what an
applicant submits) — and none of those domains may depend on each other for
it (assessments already depends one-way on the three template domains; the
template domains must stay independent of each other and of assessments).
Pure enum + pure validation functions, no ORM/FastAPI — same category as
app/core/security.py's JWT/password primitives.
"""

from datetime import date
from enum import StrEnum
from typing import Any

from app.core.exceptions import ValidationError


class QuestionType(StrEnum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    BOOLEAN = "boolean"
    NUMBER = "number"
    RATING = "rating"
    DATE = "date"


class InvalidQuestionConfigError(ValidationError):
    pass


class InvalidAnswerValueError(ValidationError):
    pass


def validate_question_config(question_type: str, config: dict | None) -> None:
    """Shape validation for a question's authored config — run at
    question-creation time so a malformed template can't be built in the
    first place. Distinct from validate_answer_value(), which validates what
    an applicant submits, not what HR authored."""
    qtype = QuestionType(question_type)

    if qtype in (QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE):
        options = (config or {}).get("options")
        if not options or not isinstance(options, list):
            raise InvalidQuestionConfigError(
                f"'{qtype}' questions require a non-empty 'options' list in config"
            )
        if not all(isinstance(option, str) for option in options):
            raise InvalidQuestionConfigError("'options' must be a list of strings")

    if qtype in (QuestionType.RATING, QuestionType.NUMBER) and config:
        min_value, max_value = config.get("min"), config.get("max")
        if min_value is not None and max_value is not None and min_value >= max_value:
            raise InvalidQuestionConfigError(
                f"'{qtype}' config 'min' must be less than 'max'"
            )


def validate_answer_value(question_type: str, config: dict | None, value: Any) -> None:
    """Validates what an applicant *submitted* against the question's type/
    config — distinct from validate_question_config(), which validates what
    HR authored."""
    qtype = QuestionType(question_type)
    cfg = config or {}

    if qtype in (QuestionType.TEXT, QuestionType.LONG_TEXT):
        if not isinstance(value, str) or not value.strip():
            raise InvalidAnswerValueError("Answer must be a non-empty string")
        max_length = cfg.get("max_length")
        if max_length is not None and len(value) > max_length:
            raise InvalidAnswerValueError(
                f"Answer exceeds max_length of {max_length}"
            )

    elif qtype == QuestionType.SINGLE_CHOICE:
        options = cfg.get("options") or []
        if value not in options:
            raise InvalidAnswerValueError(f"Answer must be one of {options}")

    elif qtype == QuestionType.MULTIPLE_CHOICE:
        options = cfg.get("options") or []
        if not isinstance(value, list) or not all(v in options for v in value):
            raise InvalidAnswerValueError(
                f"Answer must be a list of values from {options}"
            )
        min_selections = cfg.get("min_selections") or 0
        max_selections = cfg.get("max_selections")
        if len(value) < min_selections:
            raise InvalidAnswerValueError(
                f"At least {min_selections} selection(s) required"
            )
        if max_selections is not None and len(value) > max_selections:
            raise InvalidAnswerValueError(
                f"At most {max_selections} selection(s) allowed"
            )

    elif qtype == QuestionType.BOOLEAN:
        if not isinstance(value, bool):
            raise InvalidAnswerValueError("Answer must be true or false")

    elif qtype in (QuestionType.NUMBER, QuestionType.RATING):
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise InvalidAnswerValueError("Answer must be a number")
        min_value, max_value = cfg.get("min"), cfg.get("max")
        if min_value is not None and value < min_value:
            raise InvalidAnswerValueError(f"Answer must be >= {min_value}")
        if max_value is not None and value > max_value:
            raise InvalidAnswerValueError(f"Answer must be <= {max_value}")

    elif qtype == QuestionType.DATE:
        if not isinstance(value, str):
            raise InvalidAnswerValueError("Answer must be an ISO date string")
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise InvalidAnswerValueError(
                "Answer must be a valid ISO date string"
            ) from None
        min_date, max_date = cfg.get("min_date"), cfg.get("max_date")
        if min_date is not None and parsed < date.fromisoformat(min_date):
            raise InvalidAnswerValueError(f"Answer must be on or after {min_date}")
        if max_date is not None and parsed > date.fromisoformat(max_date):
            raise InvalidAnswerValueError(f"Answer must be on or before {max_date}")
