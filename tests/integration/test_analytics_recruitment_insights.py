"""recruitment_insights() — the "Key Recruitment Insights" summary that used
to be computed client-side (top turnout/engagement/duration, strongest
recommendation, recommendation distribution, pipeline totals). Moved
server-side so the frontend only renders it."""

from datetime import UTC, datetime, timedelta

from app.domains.analytics.repository import AnalyticsRepository
from tests.integration.factories import make_application, make_job_post, make_user


async def test_ranks_top_turnout_and_engagement(db_session):
    quiet = await make_job_post(db_session, status="published")
    quiet.published_at = datetime.now(UTC) - timedelta(days=5)
    busy = await make_job_post(db_session, status="published")
    busy.published_at = datetime.now(UTC) - timedelta(days=5)
    await db_session.flush()

    a1 = await make_user(db_session, role="applicant")
    a2 = await make_user(db_session, role="applicant")
    a3 = await make_user(db_session, role="applicant")

    await make_application(db_session, job_post=quiet, applicant=a1)
    await make_application(db_session, job_post=busy, applicant=a2)
    await make_application(db_session, job_post=busy, applicant=a3)
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    insights = await repo.recruitment_insights(position_id=None)

    assert insights["top_turnout"][0]["id"] == busy.id
    assert insights["top_turnout"][0]["value"] == 2
    assert insights["total_applied"] == 3


async def test_strongest_recommendation_prefers_close_over_others(db_session):
    # A post with >=3 passed candidates gets the "close" recommendation —
    # the highest-priority recommendation per _recommend()'s rule order.
    jp = await make_job_post(db_session, status="published")
    jp.published_at = datetime.now(UTC) - timedelta(days=1)
    await db_session.flush()

    for _ in range(3):
        applicant = await make_user(db_session, role="applicant")
        await make_application(
            db_session, job_post=jp, applicant=applicant, status="interview"
        )
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    insights = await repo.recruitment_insights(position_id=None)

    assert insights["strongest_recommendation"]["id"] == jp.id
    assert (
        insights["strongest_recommendation"]["recommendation"]
        == "Close the posting after sufficient qualified applicants are identified"
    )


async def test_recommendation_distribution_and_totals(db_session):
    await make_job_post(db_session, status="draft")
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    insights = await repo.recruitment_insights(position_id=None)

    # A draft post has no recommendation at all — excluded from the
    # distribution and from being "strongest."
    assert insights["strongest_recommendation"] is None
    assert insights["recommendation_distribution"] == []
    assert insights["total_applied"] == 0
    assert insights["candidates_passed_rate"] == 0.0
