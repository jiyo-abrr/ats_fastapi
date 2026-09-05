import uuid
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.core.security import create_refresh_token, hash_password
from app.domains.auth import entities
from app.domains.auth.exceptions import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    ResumeTooLargeError,
    UnsupportedResumeTypeError,
)
from app.domains.auth.service import AuthService
from app.domains.rbac import entities as rbac_entities


def make_service():
    users = MagicMock()
    roles = MagicMock()
    revoked_tokens = MagicMock()
    uow = MagicMock()
    service = AuthService(users, roles, revoked_tokens, uow)
    return service, users, roles, revoked_tokens, uow


def make_user(**overrides) -> entities.User:
    defaults = dict(
        id=uuid.uuid4(),
        first_name="Jeo",
        middle_initial=None,
        last_name="Abarre",
        contact_number="123",
        email="jeo@example.com",
        password_hash=hash_password("correct-password"),
        role_id=uuid.uuid4(),
        role="applicant",
        resume_object_key="applicant_resume/x/y.pdf",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return entities.User(**defaults)


def make_role(name: str) -> rbac_entities.Role:
    return rbac_entities.Role(id=uuid.uuid4(), name=name, description=None)


def _as_persisted(entity: entities.User) -> entities.User:
    """Simulate a repository re-fetch after commit, where the DB has filled
    in server-generated columns (created_at/updated_at) the service didn't
    know when it first constructed the entity."""
    now = datetime.now(UTC)
    return replace(entity, created_at=now, updated_at=now)


class TestSignup:
    def test_rejects_duplicate_email(self):
        service, users, roles, revoked_tokens, uow = make_service()
        users.get_by_email.return_value = make_user()

        with pytest.raises(EmailAlreadyRegisteredError):
            service.signup(
                first_name="A",
                middle_initial=None,
                last_name="B",
                contact_number="1",
                email="dup@example.com",
                password="pw",
                resume_filename="resume.pdf",
                resume_content_type="application/pdf",
                resume_bytes=b"data",
            )

    def test_rejects_unsupported_resume_type(self):
        service, users, roles, revoked_tokens, uow = make_service()
        users.get_by_email.return_value = None

        with pytest.raises(UnsupportedResumeTypeError):
            service.signup(
                first_name="A",
                middle_initial=None,
                last_name="B",
                contact_number="1",
                email="new@example.com",
                password="pw",
                resume_filename="resume.txt",
                resume_content_type="text/plain",
                resume_bytes=b"data",
            )

    def test_rejects_oversized_resume(self):
        service, users, roles, revoked_tokens, uow = make_service()
        users.get_by_email.return_value = None

        with pytest.raises(ResumeTooLargeError):
            service.signup(
                first_name="A",
                middle_initial=None,
                last_name="B",
                contact_number="1",
                email="new@example.com",
                password="pw",
                resume_filename="resume.pdf",
                resume_content_type="application/pdf",
                resume_bytes=b"x" * (6 * 1024 * 1024),
            )

    @patch("app.domains.auth.service.upload_object")
    def test_happy_path_uploads_and_creates_applicant(self, mock_upload):
        service, users, roles, revoked_tokens, uow = make_service()
        users.get_by_email.return_value = None
        applicant_role = make_role("applicant")
        roles.get_by_name.return_value = applicant_role

        added = {}
        users.add.side_effect = lambda entity: added.update(entity=entity)
        users.get_by_id.side_effect = lambda user_id: _as_persisted(added["entity"])

        result = service.signup(
            first_name="Jeo",
            middle_initial=None,
            last_name="Abarre",
            contact_number="123",
            email="new@example.com",
            password="pw",
            resume_filename="resume.pdf",
            resume_content_type="application/pdf",
            resume_bytes=b"data",
        )

        mock_upload.assert_called_once()
        uploaded_key = mock_upload.call_args[0][1]
        assert uploaded_key.startswith(f"applicant_resume/{added['entity'].id}/")
        assert added["entity"].role == "applicant"
        uow.commit.assert_called_once()
        assert result.access_token
        assert result.refresh_token
        assert result.user.role == "applicant"


class TestCreateHrAccount:
    def test_rejects_duplicate_email(self):
        service, users, roles, revoked_tokens, uow = make_service()
        users.get_by_email.return_value = make_user()

        with pytest.raises(EmailAlreadyRegisteredError):
            service.create_hr_account(
                first_name="A",
                middle_initial=None,
                last_name="B",
                contact_number="1",
                email="dup@example.com",
                password="pw",
            )

    def test_happy_path_creates_hr_with_no_resume(self):
        service, users, roles, revoked_tokens, uow = make_service()
        users.get_by_email.return_value = None
        hr_role = make_role("hr")
        roles.get_by_name.return_value = hr_role

        added = {}
        users.add.side_effect = lambda entity: added.update(entity=entity)
        users.get_by_id.side_effect = lambda user_id: _as_persisted(added["entity"])

        result = service.create_hr_account(
            first_name="Hana",
            middle_initial=None,
            last_name="Reyes",
            contact_number="456",
            email="hana@example.com",
            password="pw",
        )

        assert added["entity"].role == "hr"
        assert added["entity"].resume_object_key is None
        uow.commit.assert_called_once()
        assert result.role == "hr"


class TestLogin:
    def test_rejects_unknown_email(self):
        service, users, roles, revoked_tokens, uow = make_service()
        users.get_by_email.return_value = None

        with pytest.raises(InvalidCredentialsError):
            service.login("nobody@example.com", "pw")

    def test_rejects_wrong_password(self):
        service, users, roles, revoked_tokens, uow = make_service()
        users.get_by_email.return_value = make_user()

        with pytest.raises(InvalidCredentialsError):
            service.login("jeo@example.com", "wrong-password")

    def test_accepts_correct_password(self):
        service, users, roles, revoked_tokens, uow = make_service()
        users.get_by_email.return_value = make_user()

        result = service.login("jeo@example.com", "correct-password")

        assert result.access_token
        assert result.refresh_token


class TestRefresh:
    def test_rejects_garbage_token(self):
        service, *_ = make_service()
        with pytest.raises(InvalidRefreshTokenError):
            service.refresh("not-a-real-token")

    def test_rejects_revoked_token(self):
        service, users, roles, revoked_tokens, uow = make_service()
        token = create_refresh_token(uuid.uuid4())
        revoked_tokens.is_revoked.return_value = True

        with pytest.raises(InvalidRefreshTokenError):
            service.refresh(token)

    def test_rejects_unknown_user(self):
        service, users, roles, revoked_tokens, uow = make_service()
        token = create_refresh_token(uuid.uuid4())
        revoked_tokens.is_revoked.return_value = False
        users.get_by_id.return_value = None

        with pytest.raises(InvalidRefreshTokenError):
            service.refresh(token)

    def test_issues_new_access_token(self):
        service, users, roles, revoked_tokens, uow = make_service()
        token = create_refresh_token(uuid.uuid4())
        revoked_tokens.is_revoked.return_value = False
        users.get_by_id.return_value = make_user()

        result = service.refresh(token)

        assert result.access_token


class TestLogout:
    def test_idempotent_when_already_revoked(self):
        service, users, roles, revoked_tokens, uow = make_service()
        token = create_refresh_token(uuid.uuid4())
        revoked_tokens.is_revoked.return_value = True

        service.logout(token)

        revoked_tokens.add.assert_not_called()
        uow.commit.assert_not_called()

    def test_revokes_new_token(self):
        service, users, roles, revoked_tokens, uow = make_service()
        token = create_refresh_token(uuid.uuid4())
        revoked_tokens.is_revoked.return_value = False

        service.logout(token)

        revoked_tokens.add.assert_called_once()
        uow.commit.assert_called_once()
