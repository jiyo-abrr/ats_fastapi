import uuid
from unittest.mock import AsyncMock

import pytest

from app.domains.job_posts import entities
from app.domains.job_posts.enums import JobPostStatus
from app.domains.job_posts.exceptions import JobPostAssessmentsIncompleteError
from app.domains.job_posts.service import JobPostService

pytestmark = pytest.mark.asyncio


def make_service():
    job_posts = AsyncMock()
    positions = AsyncMock()
    addresses = AsyncMock()
    tags = AsyncMock()
    pre = AsyncMock()
    culture = AsyncMock()
    technical = AsyncMock()
    uow = AsyncMock()
    service = JobPostService(
        job_posts, positions, addresses, tags, pre, culture, technical, uow
    )
    positions.get_by_id.return_value = AsyncMock(title="Engineer")
    addresses.get_by_id.return_value = AsyncMock(label="HQ")
    return service, job_posts


def make_job_post(**overrides) -> entities.JobPost:
    defaults = dict(
        id=uuid.uuid4(),
        job_title="Backend Engineer",
        description="d",
        requirements="r",
        qualifications="q",
        salary_min=None,
        salary_max=None,
        employment_type="full_time",
        status=JobPostStatus.DRAFT,
        company_address_id=uuid.uuid4(),
        company_address_label="HQ",
        position_id=uuid.uuid4(),
        position_title="Engineer",
    )
    defaults.update(overrides)
    return entities.JobPost(**defaults)


BASE = dict(
    job_title="Backend Engineer",
    description="d",
    requirements="r",
    qualifications="q",
    salary_min=None,
    salary_max=None,
    currency="PHP",
    employment_type="full_time",
    company_address_id=uuid.uuid4(),
    position_id=uuid.uuid4(),
)


class TestCreatePublishGate:
    async def test_rejects_publishing_without_all_three_assessments(self):
        service, _ = make_service()
        with pytest.raises(JobPostAssessmentsIncompleteError):
            await service.create(
                **BASE,
                status=JobPostStatus.PUBLISHED,
                tag_ids=[],
                excluded_job_post_ids=[],
                pre_assessment_template_id=uuid.uuid4(),
                culture_fit_template_id=None,
                technical_assessment_template_id=uuid.uuid4(),
            )

    async def test_allows_draft_without_assessments(self):
        service, job_posts = make_service()
        job_posts.get_by_id.return_value = make_job_post()
        await service.create(
            **BASE,
            status=JobPostStatus.DRAFT,
            tag_ids=[],
            excluded_job_post_ids=[],
        )


class TestUpdatePublishGate:
    async def test_rejects_publishing_when_assessments_incomplete(self):
        service, job_posts = make_service()
        job_posts.get_by_id.return_value = make_job_post(
            pre_assessment_template_id=uuid.uuid4(),
            culture_fit_template_id=uuid.uuid4(),
            technical_assessment_template_id=None,
        )
        with pytest.raises(JobPostAssessmentsIncompleteError):
            await service.update(
                make_job_post().id,
                job_title="x",
                description="d",
                requirements="r",
                qualifications="q",
                salary_min=None,
                salary_max=None,
                currency="PHP",
                employment_type="full_time",
                status=JobPostStatus.PUBLISHED,
                company_address_id=uuid.uuid4(),
                position_id=uuid.uuid4(),
            )

    async def test_allows_publishing_when_all_three_attached(self):
        service, job_posts = make_service()
        job_posts.get_by_id.return_value = make_job_post(
            pre_assessment_template_id=uuid.uuid4(),
            culture_fit_template_id=uuid.uuid4(),
            technical_assessment_template_id=uuid.uuid4(),
        )
        await service.update(
            make_job_post().id,
            job_title="x",
            description="d",
            requirements="r",
            qualifications="q",
            salary_min=None,
            salary_max=None,
            currency="PHP",
            employment_type="full_time",
            status=JobPostStatus.PUBLISHED,
            company_address_id=uuid.uuid4(),
            position_id=uuid.uuid4(),
        )


class TestDetachGuard:
    async def test_cannot_detach_from_published_job_post(self):
        service, job_posts = make_service()
        job_posts.get_by_id.return_value = make_job_post(status=JobPostStatus.PUBLISHED)
        with pytest.raises(JobPostAssessmentsIncompleteError):
            await service.remove_culture_fit_template(uuid.uuid4())

    async def test_can_detach_from_draft_job_post(self):
        service, job_posts = make_service()
        job_posts.get_by_id.return_value = make_job_post(status=JobPostStatus.DRAFT)
        await service.remove_culture_fit_template(uuid.uuid4())
