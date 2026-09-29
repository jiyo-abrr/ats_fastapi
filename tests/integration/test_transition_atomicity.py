"""The HTTP status transition persists all interview state or none of it."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.core.unit_of_work import UnitOfWork
from app.domains.applications.models import Application
from app.domains.applications.service import ApplicationService
from app.domains.auth.dependencies import get_current_user
from app.domains.auth.repository import UserRepository
from app.domains.interviews.models import InterviewRequest
from app.domains.interviews.scheduling_service import InterviewService
from app.main import app
from tests.integration.factories import make_application, make_job_post, make_user


@pytest.mark.parametrize("failure", [None, "request", "deadline", "commit"])
async def test_status_endpoint_is_atomic(client, db_session, failure):
    job = await make_job_post(db_session)
    applicant = await make_user(db_session)
    hr = await make_user(db_session, role="hr")
    application = await make_application(
        db_session, job_post=job, applicant=applicant, status="prescreening"
    )
    application_id = application.id
    await db_session.commit()
    current_user = await UserRepository(db_session).get_by_id(hr.id)

    async def user():
        return current_user

    app.dependency_overrides[get_current_user] = user
    targets = {
        "request": (InterviewService, "ensure_default_request"),
        "deadline": (
            ApplicationService,
            "set_interview_booking_deadline_for_transition",
        ),
        "commit": (UnitOfWork, "commit"),
    }
    try:
        if failure:
            owner, method = targets[failure]
            with patch.object(
                owner, method, new=AsyncMock(side_effect=RuntimeError(failure))
            ):
                with pytest.raises(RuntimeError, match=failure):
                    await client.patch(
                        f"/api/v1/applications/{application_id}/status",
                        json={"status": "interview", "hr_assessed": True},
                    )
        else:
            response = await client.patch(
                f"/api/v1/applications/{application_id}/status",
                json={"status": "interview", "hr_assessed": True},
            )
            assert response.status_code == 200, response.text
            assert response.json()["interview_booking_deadline"] is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    # Read scalar columns afresh; never trust an ORM identity-map value after rollback.
    status, assessed, deadline = (
        await db_session.execute(
            select(
                Application.status,
                Application.hr_assessed,
                Application.interview_booking_deadline,
            ).where(Application.id == application_id)
        )
    ).one()
    request = (
        await db_session.execute(
            select(InterviewRequest.id).where(
                InterviewRequest.application_id == application_id
            )
        )
    ).scalar_one_or_none()
    if failure:
        assert status == "prescreening"
        assert assessed is False
        assert deadline is None
        assert request is None
    else:
        assert status == "interview"
        assert assessed is True
        assert deadline is not None
        assert request is not None
