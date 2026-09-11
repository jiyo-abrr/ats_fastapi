import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.applications.exceptions import DuplicateApplicationError
from app.use_cases.apply_to_job import ApplyToJob


def _integrity_error(constraint_name: str) -> IntegrityError:
    err = IntegrityError("stmt", {}, Exception("violation"))
    err.orig = SimpleNamespace(diag=SimpleNamespace(constraint_name=constraint_name))
    return err


def _make():
    applications = AsyncMock()
    assessments = AsyncMock()
    uow = AsyncMock()
    application = AsyncMock(id=uuid.uuid4())
    applications.create.return_value = application
    use_case = ApplyToJob(applications, assessments, uow)
    return use_case, applications, assessments, uow, application


async def test_stages_both_then_commits_once():
    use_case, applications, assessments, uow, application = _make()
    job_post_id = uuid.uuid4()
    user = AsyncMock()

    result = await use_case.execute(job_post_id=job_post_id, current_user=user)

    applications.create.assert_awaited_once_with(
        job_post_id=job_post_id, current_user=user, commit=False
    )
    assessments.create_attempts_for_application.assert_awaited_once_with(
        application.id, job_post_id, commit=False
    )
    uow.commit.assert_awaited_once()
    uow.rollback.assert_not_called()
    assert result is application


async def test_attempt_staging_failure_rolls_back_and_does_not_commit():
    use_case, applications, assessments, uow, _ = _make()
    assessments.create_attempts_for_application.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await use_case.execute(job_post_id=uuid.uuid4(), current_user=AsyncMock())

    uow.commit.assert_not_called()
    uow.rollback.assert_awaited_once()


async def test_active_application_conflict_at_commit_becomes_duplicate_error():
    use_case, applications, assessments, uow, _ = _make()
    uow.commit.side_effect = _integrity_error("ux_applications_active_per_job_post")

    with pytest.raises(DuplicateApplicationError):
        await use_case.execute(job_post_id=uuid.uuid4(), current_user=AsyncMock())

    uow.rollback.assert_awaited_once()


async def test_unrelated_integrity_error_is_reraised_not_masked():
    use_case, applications, assessments, uow, _ = _make()
    uow.commit.side_effect = _integrity_error("assessment_attempts_some_fk")

    with pytest.raises(IntegrityError):
        await use_case.execute(job_post_id=uuid.uuid4(), current_user=AsyncMock())

    uow.rollback.assert_awaited_once()
