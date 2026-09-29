from dataclasses import is_dataclass

from app.domains.applications.enums import EVALUATION_ELIGIBLE_STATUSES
from app.domains.evaluations.export_repository import EvaluationExportRepository
from app.domains.interviews.availability_repository import (
    InterviewAvailabilityRepository,
)
from app.domains.interviews.models import InterviewRequest
from app.domains.interviews.repository import InterviewRepository
from tests.integration.factories import make_application, make_job_post, make_user


async def test_interview_reads_return_detached_plain_data(db_session):
    job = await make_job_post(db_session)
    applicant = await make_user(db_session)
    hr = await make_user(db_session, role="hr")
    application = await make_application(db_session, job_post=job, applicant=applicant)
    request = InterviewRequest(
        application_id=application.id,
        created_by_user_id=hr.id,
        mode="video",
        duration_minutes=45,
        self_scheduled=True,
    )
    db_session.add(request)
    repo = InterviewAvailabilityRepository(db_session)
    await repo.replace_interviewers(job.id, [hr.id])
    await db_session.flush()
    scheduling = InterviewRepository(db_session)
    outputs = [
        await scheduling.get_application(application.id),
        await scheduling.get_company_address(job.company_address_id),
        await repo.get_application(application.id),
        await repo.get_job_post(job.id),
        await repo.get_request_for_application(application.id),
        *(await repo.company_addresses_by_id({job.company_address_id})).values(),
        *(await repo.list_staff()),
        *(await repo.interviewers(job.id)),
    ]
    assert outputs
    assert all(is_dataclass(obj) for obj in outputs)
    db_session.expunge_all()
    assert outputs[0].status == "applied"
    assert outputs[1].city == "Manila"
    assert outputs[4].duration_minutes == 45
    assert outputs[-1].email == hr.email


async def test_shared_export_query_enforces_eligibility_and_hr_exclusion(db_session):
    job = await make_job_post(db_session)
    rows = []
    for status, assessed in [
        ("applied", False),
        ("withdrawn", False),
        ("interview", True),
    ]:
        applicant = await make_user(db_session)
        row = await make_application(
            db_session, job_post=job, applicant=applicant, status=status
        )
        row.hr_assessed = assessed
        rows.append(row)
    await db_session.flush()
    repo = EvaluationExportRepository(db_session)
    selected = await repo.applicants(
        job.id, statuses=EVALUATION_ELIGIBLE_STATUSES, limit=10
    )
    assert [r.id for r in selected] == [rows[0].id]
    assert selected[0].resume_object_key == "applicant_resume/x/r.pdf"
    explicit = await repo.applicants(
        job.id, statuses=["withdrawn", "interview"], limit=10
    )
    assert [r.id for r in explicit] == [rows[1].id]


async def test_geocoding_cache_roundtrip_and_duplicate_store(db_session):
    from app.domains.analytics.geocoding_repository import GeocodingCacheRepository

    cache = GeocodingCacheRepository(db_session)
    await cache.store("manila", (14.6, 121.0, "Manila"))
    await cache.store("manila", (0.0, 0.0, "Duplicate"))
    await cache.store("unknown place", None)
    await db_session.commit()
    assert await cache.get_many(["manila", "unknown place", "not cached"]) == {
        "manila": (14.6, 121.0),
        "unknown place": None,
    }
