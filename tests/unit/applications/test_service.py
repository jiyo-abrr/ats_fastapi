import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.domains.applications import entities
from app.domains.applications.enums import ApplicationStatus
from app.domains.applications.exceptions import (
    ApplicantExcludedError,
    ApplicationNotFoundError,
    DuplicateApplicationError,
    InvalidApplicationStatusTransitionError,
    JobPostNotAcceptingApplicationsError,
    OnlyApplicantsCanApplyError,
)
from app.domains.applications.service import ApplicationService
from app.domains.auth import entities as auth_entities
from app.domains.job_posts import entities as job_post_entities
from app.domains.job_posts.enums import JobPostStatus
from app.domains.job_posts.exceptions import JobPostNotFoundError


def make_service():
    applications = AsyncMock()
    job_posts = AsyncMock()
    role_permissions = AsyncMock()
    uow = AsyncMock()
    service = ApplicationService(applications, job_posts, role_permissions, uow)
    return service, applications, job_posts, role_permissions, uow


def make_user(**overrides) -> auth_entities.User:
    defaults = dict(
        id=uuid.uuid4(),
        first_name="Ana",
        middle_initial=None,
        last_name="Applicant",
        contact_number="123",
        email="ana@example.com",
        password_hash="hashed",
        role_id=uuid.uuid4(),
        role="applicant",
        resume_object_key="applicant_resume/x/resume.pdf",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return auth_entities.User(**defaults)


def make_job_post(**overrides) -> job_post_entities.JobPost:
    defaults = dict(
        id=uuid.uuid4(),
        job_title="Backend Engineer",
        description="desc",
        requirements="req",
        qualifications="qual",
        salary_min=None,
        salary_max=None,
        employment_type="full_time",
        status=JobPostStatus.PUBLISHED,
        company_address_id=uuid.uuid4(),
        company_address_label="HQ",
        position_id=uuid.uuid4(),
        position_title="Backend Engineer",
        excluded_job_post_ids=[],
    )
    defaults.update(overrides)
    return job_post_entities.JobPost(**defaults)


def make_application(**overrides) -> entities.Application:
    defaults = dict(
        id=uuid.uuid4(),
        job_post_id=uuid.uuid4(),
        applicant_id=uuid.uuid4(),
        status=ApplicationStatus.SUBMITTED,
        resume_object_key="applicant_resume/x/resume.pdf",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return entities.Application(**defaults)


class TestCreate:
    async def test_rejects_non_applicant(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        hr_user = make_user(role="hr")

        with pytest.raises(OnlyApplicantsCanApplyError):
            await service.create(job_post_id=uuid.uuid4(), current_user=hr_user)

        job_posts.get_by_id.assert_not_called()

    async def test_rejects_nonexistent_job_post(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        job_posts.get_by_id.return_value = None

        with pytest.raises(JobPostNotFoundError):
            await service.create(job_post_id=uuid.uuid4(), current_user=make_user())

    async def test_rejects_job_post_not_published(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        job_posts.get_by_id.return_value = make_job_post(status=JobPostStatus.DRAFT)

        with pytest.raises(JobPostNotAcceptingApplicationsError):
            await service.create(job_post_id=uuid.uuid4(), current_user=make_user())

    async def test_rejects_excluded_applicant_with_job_title_in_message(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        excluded_id = uuid.uuid4()
        job_post = make_job_post(excluded_job_post_ids=[excluded_id])
        excluded_job_post = make_job_post(id=excluded_id, job_title="Frontend Engineer")

        async def get_by_id(job_post_id):
            return excluded_job_post if job_post_id == excluded_id else job_post

        job_posts.get_by_id.side_effect = get_by_id
        applications.has_any_application_for.return_value = True

        with pytest.raises(ApplicantExcludedError, match="Frontend Engineer"):
            await service.create(job_post_id=job_post.id, current_user=make_user())

        applications.add.assert_not_called()

    async def test_rejects_duplicate_active_application(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        job_posts.get_by_id.return_value = make_job_post()
        applications.has_any_application_for.return_value = False
        uow.commit.side_effect = IntegrityError("dup", None, None)

        with pytest.raises(DuplicateApplicationError):
            await service.create(job_post_id=uuid.uuid4(), current_user=make_user())

        uow.rollback.assert_called_once()

    async def test_happy_path_snapshots_resume_and_commits(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        job_post = make_job_post()
        job_posts.get_by_id.return_value = job_post
        applications.has_any_application_for.return_value = False
        user = make_user(resume_object_key="applicant_resume/x/latest.pdf")

        added = {}
        applications.add.side_effect = lambda entity: added.update(entity=entity)
        applications.get_by_id.side_effect = lambda application_id: added["entity"]

        result = await service.create(job_post_id=job_post.id, current_user=user)

        assert added["entity"].applicant_id == user.id
        assert added["entity"].resume_object_key == "applicant_resume/x/latest.pdf"
        assert added["entity"].status == ApplicationStatus.SUBMITTED
        uow.commit.assert_called_once()
        assert result is added["entity"]


class TestGet:
    async def test_raises_not_found_when_missing(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        applications.get_by_id.return_value = None

        with pytest.raises(ApplicationNotFoundError):
            await service.get(uuid.uuid4(), make_user())

    async def test_owner_can_view(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        user = make_user()
        application = make_application(applicant_id=user.id)
        applications.get_by_id.return_value = application

        result = await service.get(application.id, user)

        assert result is application
        role_permissions.has_permission.assert_not_called()

    async def test_non_owner_without_permission_gets_not_found_not_forbidden(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application()
        applications.get_by_id.return_value = application
        role_permissions.has_permission.return_value = False

        with pytest.raises(ApplicationNotFoundError):
            await service.get(application.id, make_user())

    async def test_non_owner_with_manage_applications_permission_can_view(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application()
        applications.get_by_id.return_value = application
        role_permissions.has_permission.return_value = True

        result = await service.get(application.id, make_user(role="hr"))

        assert result is application


class TestWithdraw:
    async def test_owner_can_withdraw(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        user = make_user()
        application = make_application(
            applicant_id=user.id, status=ApplicationStatus.SUBMITTED
        )
        applications.get_by_id.return_value = application

        await service.withdraw(application.id, user)

        applications.update_status.assert_called_once_with(
            application.id, ApplicationStatus.WITHDRAWN
        )
        uow.commit.assert_called_once()

    async def test_non_owner_gets_not_found(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application()
        applications.get_by_id.return_value = application

        with pytest.raises(ApplicationNotFoundError):
            await service.withdraw(application.id, make_user())

        applications.update_status.assert_not_called()

    async def test_rejects_withdrawing_a_decided_application(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        user = make_user()
        application = make_application(
            applicant_id=user.id, status=ApplicationStatus.ACCEPTED
        )
        applications.get_by_id.return_value = application

        with pytest.raises(InvalidApplicationStatusTransitionError):
            await service.withdraw(application.id, user)


class TestUpdateStatus:
    async def test_allows_submitted_to_under_review(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.SUBMITTED)
        applications.get_by_id.return_value = application

        await service.update_status(application.id, ApplicationStatus.UNDER_REVIEW)

        applications.update_status.assert_called_once_with(
            application.id, ApplicationStatus.UNDER_REVIEW
        )
        uow.commit.assert_called_once()

    async def test_rejects_backwards_transition(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.ACCEPTED)
        applications.get_by_id.return_value = application

        with pytest.raises(InvalidApplicationStatusTransitionError):
            await service.update_status(application.id, ApplicationStatus.UNDER_REVIEW)

    async def test_rejects_hr_setting_withdrawn(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.SUBMITTED)
        applications.get_by_id.return_value = application

        with pytest.raises(InvalidApplicationStatusTransitionError):
            await service.update_status(application.id, ApplicationStatus.WITHDRAWN)
