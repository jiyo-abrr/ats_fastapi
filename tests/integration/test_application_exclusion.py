"""`excluded_job_post_ids` (review: block re-applying elsewhere after
applying to a given job post) — `ApplicationRepository.has_any_application_for`
against a real database, specifically the withdrawn-doesn't-count rule."""

from app.domains.applications.repository import ApplicationRepository
from tests.integration.factories import make_application, make_job_post, make_user


async def test_withdrawn_application_does_not_count_as_excluded(db_session):
    applicant = await make_user(db_session, role="applicant")
    job_post = await make_job_post(db_session)
    await make_application(
        db_session, job_post=job_post, applicant=applicant, status="withdrawn"
    )
    repo = ApplicationRepository(db_session)

    assert await repo.has_any_application_for(applicant.id, job_post.id) is False


async def test_non_withdrawn_application_counts_as_excluded(db_session):
    applicant = await make_user(db_session, role="applicant")
    job_post = await make_job_post(db_session)
    await make_application(
        db_session, job_post=job_post, applicant=applicant, status="applied"
    )
    repo = ApplicationRepository(db_session)

    assert await repo.has_any_application_for(applicant.id, job_post.id) is True
