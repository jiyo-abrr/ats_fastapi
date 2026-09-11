import uuid
from unittest.mock import AsyncMock

import pytest

from app.domains.job_posts.exceptions import JobPostInUseError
from app.use_cases.delete_job_post import DeleteJobPost


def _make():
    job_posts = AsyncMock()
    applications = AsyncMock()
    return DeleteJobPost(job_posts, applications), job_posts, applications


async def test_deletes_when_no_applications():
    use_case, job_posts, applications = _make()
    applications.job_post_has_applications.return_value = False
    jp_id = uuid.uuid4()

    await use_case.execute(jp_id)

    job_posts.delete.assert_awaited_once_with(jp_id)


async def test_refuses_when_applications_exist():
    use_case, job_posts, applications = _make()
    applications.job_post_has_applications.return_value = True

    with pytest.raises(JobPostInUseError):
        await use_case.execute(uuid.uuid4())

    job_posts.delete.assert_not_called()


async def test_missing_job_post_propagates_before_the_check():
    use_case, job_posts, applications = _make()
    job_posts.get.side_effect = RuntimeError("not found")

    with pytest.raises(RuntimeError):
        await use_case.execute(uuid.uuid4())

    applications.job_post_has_applications.assert_not_called()
