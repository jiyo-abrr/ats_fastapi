import uuid

import pytest
from pydantic import ValidationError

from app.domains.evaluations.schemas import ApplicationEvaluationIn, EvaluationImportIn


def _score(dimension, rating="strong"):
    return {"dimension": dimension, "rating": rating, "reason": "r"}


def test_rejects_duplicate_dimension_within_a_category():
    with pytest.raises(ValidationError):
        ApplicationEvaluationIn(
            application_id=uuid.uuid4(),
            resume_scores=[_score("tenure_stability"), _score("tenure_stability")],
        )


def test_same_unknown_dimension_string_across_categories_is_fine():
    # An identical *unknown* dimension string is allowed in both lists — the
    # per-category dedup is independent.
    ApplicationEvaluationIn(
        application_id=uuid.uuid4(),
        resume_scores=[_score("custom_signal")],
        assessment_scores=[_score("custom_signal")],
    )


def test_rejects_dimension_from_the_wrong_category():
    with pytest.raises(ValidationError):
        ApplicationEvaluationIn(
            application_id=uuid.uuid4(),
            resume_scores=[_score("technical")],  # an assessment dimension
        )
    with pytest.raises(ValidationError):
        ApplicationEvaluationIn(
            application_id=uuid.uuid4(),
            assessment_scores=[_score("tenure_stability")],  # a resume dimension
        )


def test_unknown_dimension_strings_are_still_accepted():
    ApplicationEvaluationIn(
        application_id=uuid.uuid4(),
        resume_scores=[_score("gut_feel"), _score("vibes")],
    )


def test_rejects_overlong_reason_and_summary():
    with pytest.raises(ValidationError):
        ApplicationEvaluationIn(
            application_id=uuid.uuid4(),
            summary="x" * 5001,
        )
    with pytest.raises(ValidationError):
        ApplicationEvaluationIn(
            application_id=uuid.uuid4(),
            resume_scores=[
                {"dimension": "d", "rating": "strong", "reason": "x" * 2001}
            ],
        )


def test_rejects_duplicate_application_id_in_one_import():
    app_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        EvaluationImportIn(
            job_post_id=uuid.uuid4(),
            evaluations=[
                {"application_id": str(app_id), "recommendation": "advance"},
                {"application_id": str(app_id), "recommendation": "reject"},
            ],
        )
