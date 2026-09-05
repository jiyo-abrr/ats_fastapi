import pytest

from app.core.question_types import (
    InvalidAnswerValueError,
    InvalidQuestionConfigError,
    QuestionType,
    validate_answer_value,
    validate_question_config,
)


class TestValidateQuestionConfig:
    def test_single_choice_requires_options(self):
        with pytest.raises(InvalidQuestionConfigError):
            validate_question_config(QuestionType.SINGLE_CHOICE, None)

    def test_single_choice_accepts_valid_options(self):
        validate_question_config(QuestionType.SINGLE_CHOICE, {"options": ["A", "B"]})

    def test_multiple_choice_requires_string_options(self):
        with pytest.raises(InvalidQuestionConfigError):
            validate_question_config(QuestionType.MULTIPLE_CHOICE, {"options": [1, 2]})

    def test_rating_rejects_min_greater_than_max(self):
        with pytest.raises(InvalidQuestionConfigError):
            validate_question_config(QuestionType.RATING, {"min": 5, "max": 1})

    def test_text_accepts_no_config(self):
        validate_question_config(QuestionType.TEXT, None)


class TestValidateAnswerValue:
    def test_text_rejects_empty_string(self):
        with pytest.raises(InvalidAnswerValueError):
            validate_answer_value(QuestionType.TEXT, None, "  ")

    def test_single_choice_rejects_value_not_in_options(self):
        with pytest.raises(InvalidAnswerValueError):
            validate_answer_value(
                QuestionType.SINGLE_CHOICE, {"options": ["A", "B"]}, "C"
            )

    def test_multiple_choice_enforces_min_selections(self):
        with pytest.raises(InvalidAnswerValueError):
            validate_answer_value(
                QuestionType.MULTIPLE_CHOICE,
                {"options": ["A", "B", "C"], "min_selections": 2},
                ["A"],
            )

    def test_boolean_rejects_non_bool(self):
        with pytest.raises(InvalidAnswerValueError):
            validate_answer_value(QuestionType.BOOLEAN, None, "yes")

    def test_rating_enforces_bounds(self):
        with pytest.raises(InvalidAnswerValueError):
            validate_answer_value(QuestionType.RATING, {"min": 1, "max": 5}, 10)

    def test_rating_accepts_value_in_bounds(self):
        validate_answer_value(QuestionType.RATING, {"min": 1, "max": 5}, 3)

    def test_date_rejects_invalid_string(self):
        with pytest.raises(InvalidAnswerValueError):
            validate_answer_value(QuestionType.DATE, None, "not-a-date")

    def test_date_enforces_min_date(self):
        with pytest.raises(InvalidAnswerValueError):
            validate_answer_value(
                QuestionType.DATE, {"min_date": "2026-01-01"}, "2025-01-01"
            )
