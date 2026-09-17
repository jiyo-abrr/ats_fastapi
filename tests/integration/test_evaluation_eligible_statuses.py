"""EVALUATION_ELIGIBLE_STATUSES — withdrawn/disqualified applications are out
of the pipeline and must not surface in the Compare tab's evaluation matrix,
the evaluation pack export, or the evaluation CSV export. All three read
paths ultimately filter through ApplicationRepository.list_for_review()
(or, for the CSV, EvaluationRepository.application_rows_for_job_post()) with
EVALUATION_ELIGIBLE_STATUSES — exercised here directly against a real DB."""

from app.domains.applications.enums import EVALUATION_ELIGIBLE_STATUSES
from app.domains.applications.repository import ApplicationRepository
from app.domains.evaluations.repository import EvaluationRepository
from tests.integration.factories import make_application, make_job_post, make_user


async def test_list_for_review_excludes_withdrawn_and_disqualified(db_session):
    jp = await make_job_post(db_session)
    active = await make_user(db_session, role="applicant")
    withdrawn = await make_user(db_session, role="applicant")
    disqualified = await make_user(db_session, role="applicant")

    await make_application(db_session, job_post=jp, applicant=active, status="applied")
    await make_application(
        db_session, job_post=jp, applicant=withdrawn, status="withdrawn"
    )
    await make_application(
        db_session, job_post=jp, applicant=disqualified, status="disqualified"
    )
    await db_session.commit()

    repo = ApplicationRepository(db_session)
    query = await repo.list_for_review(
        job_post_id=jp.id, statuses=EVALUATION_ELIGIBLE_STATUSES
    )
    rows = (await db_session.execute(query)).all()

    assert {r.applicant_id for r in rows} == {active.id}


async def test_evaluation_csv_rows_exclude_withdrawn_and_disqualified(db_session):
    jp = await make_job_post(db_session)
    active = await make_user(db_session, role="applicant")
    withdrawn = await make_user(db_session, role="applicant")

    await make_application(db_session, job_post=jp, applicant=active, status="applied")
    await make_application(
        db_session, job_post=jp, applicant=withdrawn, status="withdrawn"
    )
    await db_session.commit()

    repo = EvaluationRepository(db_session)
    rows = await repo.application_rows_for_job_post(jp.id)

    assert len(rows) == 1
    assert rows[0].email == active.email
