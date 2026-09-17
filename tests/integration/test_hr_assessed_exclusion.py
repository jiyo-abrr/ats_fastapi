"""hr_assessed — HR explicitly bypassing AI evaluation for an application
(typically moving prescreening -> interview without one). Excluded from the
evaluation pack export and the evaluations CSV, but still returned by
list_for_review itself (unfiltered) so the Compare tab's AI evaluation
matrix can still list the applicant with a "assessed by HR" note, per
GET /applications/evaluations (evaluations/router.py)."""

from sqlalchemy import select

from app.domains.applications.models import Application
from app.domains.applications.repository import ApplicationRepository
from app.domains.evaluations.repository import EvaluationRepository
from tests.integration.factories import make_application, make_job_post, make_user


async def test_evaluation_csv_rows_exclude_hr_assessed(db_session):
    jp = await make_job_post(db_session)
    normal = await make_user(db_session, role="applicant")
    bypassed = await make_user(db_session, role="applicant")

    await make_application(db_session, job_post=jp, applicant=normal, status="applied")
    bypassed_app = await make_application(
        db_session, job_post=jp, applicant=bypassed, status="interview"
    )
    bypassed_app.hr_assessed = True
    await db_session.commit()

    repo = EvaluationRepository(db_session)
    rows = await repo.application_rows_for_job_post(jp.id)

    assert len(rows) == 1
    assert rows[0].email == normal.email


async def test_export_style_query_excludes_hr_assessed(db_session):
    """Mirrors the extra `.where(Application.hr_assessed.is_(False))` the
    evaluation pack export routes (sync + async worker) chain onto
    list_for_review's query."""
    jp = await make_job_post(db_session)
    normal = await make_user(db_session, role="applicant")
    bypassed = await make_user(db_session, role="applicant")

    await make_application(db_session, job_post=jp, applicant=normal, status="applied")
    bypassed_app = await make_application(
        db_session, job_post=jp, applicant=bypassed, status="interview"
    )
    bypassed_app.hr_assessed = True
    await db_session.commit()

    repo = ApplicationRepository(db_session)
    query = (await repo.list_for_review(job_post_id=jp.id, statuses=None)).where(
        Application.hr_assessed.is_(False)
    )
    rows = (await db_session.execute(query)).all()

    assert {r.applicant_id for r in rows} == {normal.id}


async def test_plain_list_for_review_still_includes_hr_assessed(db_session):
    """The Compare tab's AI evaluation matrix (job_evaluations) does NOT
    chain the hr_assessed exclusion — it needs the row to still show a note
    in place of the evaluation, not disappear entirely."""
    jp = await make_job_post(db_session)
    bypassed = await make_user(db_session, role="applicant")
    bypassed_app = await make_application(
        db_session, job_post=jp, applicant=bypassed, status="interview"
    )
    bypassed_app.hr_assessed = True
    await db_session.commit()

    repo = ApplicationRepository(db_session)
    query = await repo.list_for_review(job_post_id=jp.id, statuses=None)
    rows = (await db_session.execute(query)).all()

    assert len(rows) == 1
    assert rows[0].hr_assessed is True


async def test_set_hr_assessed_is_reversible(db_session):
    jp = await make_job_post(db_session)
    applicant = await make_user(db_session, role="applicant")
    app = await make_application(db_session, job_post=jp, applicant=applicant)
    await db_session.flush()

    async def _current_value() -> bool:
        return (
            await db_session.execute(
                select(Application.hr_assessed).where(Application.id == app.id)
            )
        ).scalar_one()

    repo = ApplicationRepository(db_session)
    await repo.set_hr_assessed(app.id, True)
    await db_session.flush()
    assert await _current_value() is True

    await repo.set_hr_assessed(app.id, False)
    await db_session.flush()
    assert await _current_value() is False
