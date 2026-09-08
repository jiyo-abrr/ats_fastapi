import uuid
from datetime import UTC, datetime, timedelta
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
    InvalidAssessmentDeadlineExtensionError,
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
        assessment_window_days=4,
        excluded_job_post_ids=[],
    )
    defaults.update(overrides)
    return job_post_entities.JobPost(**defaults)


def make_application(**overrides) -> entities.Application:
    defaults = dict(
        id=uuid.uuid4(),
        job_post_id=uuid.uuid4(),
        applicant_id=uuid.uuid4(),
        status=ApplicationStatus.APPLIED,
        resume_object_key="applicant_resume/x/resume.pdf",
        assessment_deadline=datetime.now(UTC) + timedelta(days=4),
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

    async def test_happy_path_snapshots_resume_sets_deadline_and_commits(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        job_post = make_job_post(assessment_window_days=4)
        job_posts.get_by_id.return_value = job_post
        applications.has_any_application_for.return_value = False
        user = make_user(resume_object_key="applicant_resume/x/latest.pdf")

        added = {}
        applications.add.side_effect = lambda entity: added.update(entity=entity)
        applications.get_by_id.side_effect = lambda application_id: added["entity"]

        before = datetime.now(UTC)
        result = await service.create(job_post_id=job_post.id, current_user=user)
        after = datetime.now(UTC)

        assert added["entity"].applicant_id == user.id
        assert added["entity"].resume_object_key == "applicant_resume/x/latest.pdf"
        assert added["entity"].status == ApplicationStatus.APPLIED
        assert (
            before + timedelta(days=4)
            <= added["entity"].assessment_deadline
            <= after + timedelta(days=4)
        )
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
            applicant_id=user.id, status=ApplicationStatus.APPLIED
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
            applicant_id=user.id, status=ApplicationStatus.SUCCESS
        )
        applications.get_by_id.return_value = application

        with pytest.raises(InvalidApplicationStatusTransitionError):
            await service.withdraw(application.id, user)


class TestUpdateStatus:
    async def test_allows_applied_to_prescreening(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.APPLIED)
        applications.get_by_id.return_value = application

        await service.update_status(application.id, ApplicationStatus.PRESCREENING)

        applications.update_status.assert_called_once_with(
            application.id, ApplicationStatus.PRESCREENING
        )
        uow.commit.assert_called_once()

    async def test_allows_applied_to_denied_directly(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.APPLIED)
        applications.get_by_id.return_value = application

        await service.update_status(application.id, ApplicationStatus.DENIED)

        applications.update_status.assert_called_once_with(
            application.id, ApplicationStatus.DENIED
        )

    async def test_allows_prescreening_to_interview(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.PRESCREENING)
        applications.get_by_id.return_value = application

        await service.update_status(application.id, ApplicationStatus.INTERVIEW)

        applications.update_status.assert_called_once_with(
            application.id, ApplicationStatus.INTERVIEW
        )

    async def test_allows_interview_to_success_or_failed(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.INTERVIEW)
        applications.get_by_id.return_value = application

        await service.update_status(application.id, ApplicationStatus.SUCCESS)

        applications.update_status.assert_called_once_with(
            application.id, ApplicationStatus.SUCCESS
        )

    async def test_rejects_backwards_transition(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.SUCCESS)
        applications.get_by_id.return_value = application

        with pytest.raises(InvalidApplicationStatusTransitionError):
            await service.update_status(application.id, ApplicationStatus.INTERVIEW)

    async def test_rejects_hr_setting_withdrawn(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.APPLIED)
        applications.get_by_id.return_value = application

        with pytest.raises(InvalidApplicationStatusTransitionError):
            await service.update_status(application.id, ApplicationStatus.WITHDRAWN)

    async def test_rejects_hr_setting_disqualified(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.APPLIED)
        applications.get_by_id.return_value = application

        with pytest.raises(InvalidApplicationStatusTransitionError):
            await service.update_status(
                application.id, ApplicationStatus.DISQUALIFIED
            )


class TestExtendAssessmentDeadline:
    async def test_extends_with_absolute_new_deadline(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.APPLIED)
        applications.get_by_id.return_value = application
        new_deadline = datetime.now(UTC) + timedelta(days=10)

        await service.extend_assessment_deadline(
            application.id,
            new_deadline=new_deadline,
            extend_by_days=None,
            reason="Applicant requested more time",
            current_user=make_user(role="hr"),
        )

        applications.set_assessment_deadline.assert_called_once_with(
            application.id, new_deadline
        )
        applications.add_deadline_extension.assert_called_once()
        uow.commit.assert_called_once()

    async def test_extends_with_relative_days_from_current_deadline(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        current_deadline = datetime.now(UTC) + timedelta(days=1)
        application = make_application(
            status=ApplicationStatus.APPLIED, assessment_deadline=current_deadline
        )
        applications.get_by_id.return_value = application

        await service.extend_assessment_deadline(
            application.id,
            new_deadline=None,
            extend_by_days=2,
            reason="Extension requested",
            current_user=make_user(role="hr"),
        )

        applications.set_assessment_deadline.assert_called_once_with(
            application.id, current_deadline + timedelta(days=2)
        )

    async def test_reviving_a_disqualified_application_sets_status_back_to_applied(
        self,
    ):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.DISQUALIFIED)
        applications.get_by_id.return_value = application

        await service.extend_assessment_deadline(
            application.id,
            new_deadline=datetime.now(UTC) + timedelta(days=4),
            extend_by_days=None,
            reason="System outage during assessment window",
            current_user=make_user(role="hr"),
        )

        applications.update_status.assert_called_once_with(
            application.id, ApplicationStatus.APPLIED
        )

    async def test_rejects_extension_for_decided_application(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.PRESCREENING)
        applications.get_by_id.return_value = application

        with pytest.raises(InvalidAssessmentDeadlineExtensionError):
            await service.extend_assessment_deadline(
                application.id,
                new_deadline=datetime.now(UTC) + timedelta(days=4),
                extend_by_days=None,
                reason="reason",
                current_user=make_user(role="hr"),
            )


class TestDisqualify:
    async def test_disqualifies_an_applied_application(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.APPLIED)
        applications.get_by_id.return_value = application

        await service.disqualify(application.id)

        applications.update_status.assert_called_once_with(
            application.id, ApplicationStatus.DISQUALIFIED
        )
        uow.commit.assert_called_once()

    async def test_idempotent_noop_if_already_moved_past_applied(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(status=ApplicationStatus.PRESCREENING)
        applications.get_by_id.return_value = application

        await service.disqualify(application.id)

        applications.update_status.assert_not_called()
        uow.commit.assert_not_called()

    async def test_noop_if_application_missing(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        applications.get_by_id.return_value = None

        await service.disqualify(uuid.uuid4())

        applications.update_status.assert_not_called()


class TestStats:
    async def test_zero_fills_all_statuses_and_totals(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        applications.status_counts.return_value = {"applied": 3, "denied": 1}

        result = await service.stats()

        assert result["by_status"]["applied"] == 3
        assert result["by_status"]["denied"] == 1
        assert result["by_status"]["interview"] == 0
        assert set(result["by_status"]) == {s.value for s in ApplicationStatus}
        assert result["total"] == 4

    async def test_passes_job_post_scope_through(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        applications.status_counts.return_value = {}
        job_post_id = uuid.uuid4()

        await service.stats(job_post_id)

        applications.status_counts.assert_called_once_with(job_post_id)


class TestListForApplicant:
    async def test_forwards_job_post_filter(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        applicant_id, job_post_id = uuid.uuid4(), uuid.uuid4()

        await service.list_for_applicant(applicant_id, job_post_id=job_post_id)

        applications.list_for_applicant.assert_called_once_with(
            applicant_id, job_post_id=job_post_id
        )


class TestListApplicants:
    async def test_forwards_search(self):
        service, applications, job_posts, role_permissions, uow = make_service()

        await service.list_applicants(search="ana")

        applications.list_applicants.assert_called_once_with(search="ana")

    async def test_forwards_none_search(self):
        service, applications, job_posts, role_permissions, uow = make_service()

        await service.list_applicants(search=None)

        applications.list_applicants.assert_called_once_with(search=None)


class TestListForReview:
    async def test_forwards_applicant_id_filter(self):
        service, applications, job_posts, role_permissions, uow = make_service()
        applicant_id = uuid.uuid4()

        await service.list_for_review(
            job_post_id=None, status=None, applicant_id=applicant_id
        )

        applications.list_for_review.assert_called_once_with(
            job_post_id=None, status=None, applicant_id=applicant_id
        )


class TestGetResume:
    async def test_returns_bytes_content_type_and_filename(self, monkeypatch):
        service, applications, job_posts, role_permissions, uow = make_service()
        user = make_user()
        application = make_application(
            applicant_id=user.id,
            resume_object_key="applicant_resume/u/1234_cv.pdf",
        )
        applications.get_by_id.return_value = application

        monkeypatch.setattr(
            "app.domains.applications.service.get_object",
            lambda bucket, key: (b"%PDF-1.4", "application/pdf"),
        )

        data, content_type, filename = await service.get_resume(
            application.id, user
        )

        assert data == b"%PDF-1.4"
        assert content_type == "application/pdf"
        assert filename == "1234_cv.pdf"

    async def test_missing_object_raises_resume_unavailable(self, monkeypatch):
        from app.core.storage import ObjectNotFoundError
        from app.domains.applications.exceptions import ResumeUnavailableError

        service, applications, job_posts, role_permissions, uow = make_service()
        user = make_user()
        application = make_application(applicant_id=user.id)
        applications.get_by_id.return_value = application

        def boom(bucket, key):
            raise ObjectNotFoundError("gone")

        monkeypatch.setattr(
            "app.domains.applications.service.get_object", boom
        )

        with pytest.raises(ResumeUnavailableError):
            await service.get_resume(application.id, user)

    async def test_rejects_other_users_application(self, monkeypatch):
        service, applications, job_posts, role_permissions, uow = make_service()
        application = make_application(applicant_id=uuid.uuid4())
        applications.get_by_id.return_value = application
        role_permissions.has_permission.return_value = False

        with pytest.raises(ApplicationNotFoundError):
            await service.get_resume(application.id, make_user())
