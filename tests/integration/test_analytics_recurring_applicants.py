"""recurring_applicants() — the detail list behind the recruitment report's
"recurring applicants" insight card: applicants with more than one
application anywhere in the system, plus their full application history."""

from app.domains.analytics.repository import AnalyticsRepository
from tests.integration.factories import make_application, make_job_post, make_user


async def test_only_applicants_with_more_than_one_application_are_listed(db_session):
    jp1 = await make_job_post(db_session)
    jp2 = await make_job_post(db_session)
    recurring = await make_user(db_session, role="applicant")
    single = await make_user(db_session, role="applicant")

    await make_application(db_session, job_post=jp1, applicant=recurring)
    await make_application(db_session, job_post=jp2, applicant=recurring)
    await make_application(db_session, job_post=jp1, applicant=single)
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    rows = await repo.recurring_applicants(position_id=None)

    assert len(rows) == 1
    row = rows[0]
    assert row["applicant_id"] == recurring.id
    assert row["application_count"] == 2
    assert {a["job_post_id"] for a in row["applications"]} == {jp1.id, jp2.id}


async def test_position_filter_scopes_by_at_least_one_application_there(db_session):
    jp1 = await make_job_post(db_session)
    jp2 = await make_job_post(db_session)
    applicant = await make_user(db_session, role="applicant")

    await make_application(db_session, job_post=jp1, applicant=applicant)
    await make_application(db_session, job_post=jp2, applicant=applicant)
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    rows = await repo.recurring_applicants(position_id=jp1.position_id)

    assert len(rows) == 1
    # Full application history is still returned, not just jp1's.
    assert len(rows[0]["applications"]) == 2

    other_position_rows = await repo.recurring_applicants(
        position_id=(await make_job_post(db_session)).position_id
    )
    assert other_position_rows == []


async def test_no_recurring_applicants_returns_empty_list(db_session):
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session, role="applicant")
    await make_application(db_session, job_post=jp, applicant=applicant)
    await db_session.commit()

    repo = AnalyticsRepository(db_session)
    assert await repo.recurring_applicants(position_id=None) == []
