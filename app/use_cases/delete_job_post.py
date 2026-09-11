"""`delete_job_post` — refuses to delete a job post that has applications.

`DELETE /job-posts/{id}` used to cascade straight through
`applications → assessments / interviews / evaluations / audit rows`, so one
call could erase an entire hiring history. Those records outlive the
requisition (docs/decisions/D04). This use case blocks the delete when any
application exists; a post with none can still be removed.

It lives in `app/use_cases/` because `job_posts` must not import
`applications` (that domain already depends one-way on `job_posts`).
"""

import uuid

from app.domains.applications.repository import ApplicationRepository
from app.domains.job_posts.exceptions import JobPostInUseError
from app.domains.job_posts.service import JobPostService


class DeleteJobPost:
    def __init__(
        self,
        job_posts: JobPostService,
        applications: ApplicationRepository,
    ):
        self.job_posts = job_posts
        self.applications = applications

    async def execute(self, job_post_id: uuid.UUID) -> None:
        await self.job_posts.get(job_post_id)  # 404 if missing
        if await self.applications.job_post_has_applications(job_post_id):
            raise JobPostInUseError(
                "This job post has applications and can't be deleted. Close it "
                "instead to stop accepting new applications."
            )
        await self.job_posts.delete(job_post_id)
