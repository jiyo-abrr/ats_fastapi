"""Application-activity zero-fill (analytics/repository.py's `_hiring`) — a
bounded granularity (daily/weekly/monthly) must return one point per bucket
across its whole window, including zero-count buckets, not just the buckets
that actually had an application."""

from datetime import UTC, datetime, timedelta

from app.domains.analytics.aggregation import bucket_for, bucket_starts, period_start
from app.domains.analytics.repository import AnalyticsRepository
from tests.integration.factories import make_application, make_job_post, make_user


async def test_weekly_granularity_is_zero_filled(db_session):
    jp = await make_job_post(db_session)
    applicant_a = await make_user(db_session, role="applicant")
    applicant_b = await make_user(db_session, role="applicant")

    now = datetime.now(UTC)
    await make_application(
        db_session,
        job_post=jp,
        applicant=applicant_a,
        created_at=now - timedelta(days=4),
    )
    await make_application(
        db_session,
        job_post=jp,
        applicant=applicant_b,
        created_at=now,
    )
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    filters = repo._application_filters(period="weekly", position_id=None)
    hiring = await repo._hiring(filters=filters, period="weekly")
    activity = hiring["application_activity"]

    expected_dates = bucket_starts(
        period_start("weekly", now).date(), now.date(), bucket_for("weekly")
    )
    assert [p["date"] for p in activity] == expected_dates

    total = sum(p["count"] for p in activity)
    assert total == 2
    # Both applications are within the last 4 days, so — regardless of
    # exactly which week-of-the-year boundary "now" falls on — they land in
    # one of the last two buckets, not spread further back.
    assert sum(p["count"] for p in activity[-2:]) == 2
    # The very first week in the 12-week window is well clear of both
    # applications and must be present with an explicit zero, not absent.
    assert activity[0]["count"] == 0


async def test_yearly_granularity_stays_sparse(db_session):
    """ "yearly" has no lower bound to enumerate years from, so it keeps the
    old sparse behavior: only years that actually had an application."""
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session, role="applicant")
    await make_application(db_session, job_post=jp, applicant=applicant)
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    filters = repo._application_filters(period="yearly", position_id=None)
    hiring = await repo._hiring(filters=filters, period="yearly")

    assert len(hiring["application_activity"]) == 1
