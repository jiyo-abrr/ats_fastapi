"""F02 — a status transition reads the application, validates, then writes.
`compare_and_set_status` makes that write conditional on the status that was
read, so two interleaved transitions can't both succeed (the old
`obj.status = new` was an unconditional UPDATE — a silent lost update)."""

import pytest
from sqlalchemy import select

from app.core.unit_of_work import UnitOfWork
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.models import Application
from app.domains.applications.repository import ApplicationRepository
from app.domains.applications.service import ApplicationService
from app.domains.job_posts.repository import JobPostRepository
from app.domains.rbac.repository import RolePermissionRepository
from tests.integration.factories import make_application, make_job_post, make_user


def _service(db) -> ApplicationService:
    return ApplicationService(
        ApplicationRepository(db),
        JobPostRepository(db),
        RolePermissionRepository(db),
        UnitOfWork(db),
    )


async def _status(db, app_id) -> str:
    return (
        await db.execute(select(Application.status).where(Application.id == app_id))
    ).scalar_one()


async def _seed_applied(committing_session):
    db = committing_session()
    jp = await make_job_post(db)
    applicant = await make_user(db)
    app = await make_application(db, job_post=jp, applicant=applicant, status="applied")
    await db.commit()
    return app, applicant


async def test_interleaved_transitions_the_second_writer_is_rejected(
    committing_session,
):
    app, _ = await _seed_applied(committing_session)

    session_a = ApplicationRepository(committing_session())
    session_b = ApplicationRepository(committing_session())

    # Both transactions read the application as `applied`.
    assert (await session_a.get_by_id(app.id)).status == "applied"
    assert (await session_b.get_by_id(app.id)).status == "applied"

    # A advances it and commits.
    assert await session_a.compare_and_set_status(
        app.id, expected="applied", new="prescreening"
    )
    await session_a.db.commit()

    # B, still holding its `applied` view, tries its own advance — the
    # conditional UPDATE now matches no row.
    assert (
        await session_b.compare_and_set_status(app.id, expected="applied", new="denied")
        is False
    )
    await session_b.db.rollback()

    assert await _status(committing_session(), app.id) == "prescreening"


async def test_advance_after_a_committed_withdraw_is_a_clean_domain_error(
    committing_session,
):
    """End to end: once another session has committed a withdrawal, an advance
    fails with a domain error (400/409) and leaves the row untouched — never a
    lost update, never a 500."""
    from app.core.exceptions import DomainError

    app, applicant = await _seed_applied(committing_session)

    await _service(committing_session()).withdraw(app.id, applicant)

    with pytest.raises(DomainError):
        await _service(committing_session()).update_status(
            app.id, ApplicationStatus.PRESCREENING
        )

    assert await _status(committing_session(), app.id) == "withdrawn"
