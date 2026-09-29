import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domains.applications.enums import ApplicationStatus
from app.use_cases.transition_application import TransitionApplication


def setup():
    applications, interviews, uow = AsyncMock(), AsyncMock(), AsyncMock()
    interviews.get_config.return_value = SimpleNamespace(interview_booking_days=21)
    kwargs = dict(
        application_id=uuid.uuid4(),
        status=ApplicationStatus.INTERVIEW,
        hr_assessed=True,
        current_user=SimpleNamespace(id=uuid.uuid4()),
    )
    return TransitionApplication(applications, interviews, uow), kwargs


async def test_interview_changes_share_one_commit():
    use_case, kwargs = setup()
    result = await use_case.execute(**kwargs)
    use_case.applications.update_status.assert_awaited_once_with(
        kwargs["application_id"],
        ApplicationStatus.INTERVIEW,
        hr_assessed=True,
        commit=False,
    )
    use_case.interviews.ensure_default_request.assert_awaited_once_with(
        kwargs["application_id"],
        created_by_user_id=kwargs["current_user"].id,
        commit=False,
    )
    deadline = use_case.applications.set_interview_booking_deadline_for_transition
    deadline.assert_awaited_once_with(
        kwargs["application_id"],
        default_days=21,
        commit=False,
    )
    use_case.uow.commit.assert_awaited_once()
    use_case.uow.rollback.assert_not_awaited()
    assert result is use_case.applications.get.return_value


@pytest.mark.parametrize("failure", ["status", "request", "deadline", "commit"])
async def test_failure_rolls_back_entire_transition(failure):
    use_case, kwargs = setup()
    targets = {
        "status": use_case.applications.update_status,
        "request": use_case.interviews.ensure_default_request,
        "deadline": use_case.applications.set_interview_booking_deadline_for_transition,
        "commit": use_case.uow.commit,
    }
    targets[failure].side_effect = RuntimeError(failure)
    with pytest.raises(RuntimeError, match=failure):
        await use_case.execute(**kwargs)
    use_case.uow.rollback.assert_awaited_once()
    if failure != "commit":
        use_case.uow.commit.assert_not_awaited()


async def test_other_transitions_do_not_create_interviews():
    use_case, kwargs = setup()
    kwargs["status"] = ApplicationStatus.DENIED
    await use_case.execute(**kwargs)
    use_case.interviews.ensure_default_request.assert_not_awaited()
    deadline = use_case.applications.set_interview_booking_deadline_for_transition
    deadline.assert_not_awaited()
    use_case.uow.commit.assert_awaited_once()
