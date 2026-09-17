"""job_post_reports() — the per-posting recruitment report backing the
"Reportorial / Recruitment Analytics" dashboard: funnel counts, assessment
scores, recurring applicants, engagement, posting duration, and the
deterministic recommendation for each job post."""

from datetime import UTC, datetime, timedelta

from app.domains.analytics.repository import AnalyticsRepository
from app.domains.evaluations.models import ApplicationEvaluation
from tests.integration.factories import (
    make_application,
    make_attempt,
    make_job_post,
    make_user,
)


async def test_reports_lifetime_funnel_scores_and_recommendation(db_session):
    jp = await make_job_post(db_session, status="published")
    jp.published_at = datetime.now(UTC) - timedelta(days=10)
    await db_session.flush()

    recruiter = await make_user(db_session, role="applicant")

    applicant_a = await make_user(db_session, role="applicant")
    applicant_b = await make_user(db_session, role="applicant")
    app_a = await make_application(
        db_session, job_post=jp, applicant=applicant_a, status="interview"
    )
    await make_application(
        db_session, job_post=jp, applicant=applicant_b, status="applied"
    )

    # Only app_a engaged with an assessment.
    await make_attempt(
        db_session,
        application=app_a,
        template_id=app_a.id,
        status="completed",
    )

    db_session.add(
        ApplicationEvaluation(
            application_id=app_a.id,
            imported_by_user_id=recruiter.id,
            recommendation="advance",
            fit_score=90,
        )
    )
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    reports = await repo.job_post_reports(position_id=None)

    report = next(r for r in reports if r["id"] == jp.id)
    assert report["applied"] == 2
    assert report["screened"] == 1  # app_a moved past "applied"
    assert report["passed"] == 1  # app_a is in "interview"
    assert report["accepted"] == 0
    assert report["rejected"] == 0
    assert report["average_score"] == 90.0
    assert report["highest_score"] == 90
    assert report["engagement_rate"] == 50.0
    assert report["posting_duration_days"] == 10
    assert report["recommendation"] == "Prioritize high-scoring candidates"


async def test_recurring_applicant_counted_across_job_posts(db_session):
    jp1 = await make_job_post(db_session, status="published")
    jp2 = await make_job_post(db_session, status="published")
    applicant = await make_user(db_session, role="applicant")

    await make_application(db_session, job_post=jp1, applicant=applicant)
    await make_application(db_session, job_post=jp2, applicant=applicant)
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    reports = await repo.job_post_reports(position_id=None)

    report1 = next(r for r in reports if r["id"] == jp1.id)
    report2 = next(r for r in reports if r["id"] == jp2.id)
    assert report1["recurring_applicants"] == 1
    assert report2["recurring_applicants"] == 1


async def test_draft_post_has_no_recommendation_and_no_duration(db_session):
    jp = await make_job_post(db_session, status="draft")
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    reports = await repo.job_post_reports(position_id=None)

    report = next(r for r in reports if r["id"] == jp.id)
    assert report["recommendation"] is None
    assert report["posting_duration_days"] is None
    assert report["applied"] == 0
    assert report["engagement_rate"] == 0.0
