"""AuthService.change_password() against a real DB — verifies the new
password hash actually replaces the old one and the old password stops
working, not just that a mocked repository method was called."""

import pytest

from app.core.security import hash_password, verify_password
from app.core.unit_of_work import UnitOfWork
from app.domains.auth.exceptions import (
    InvalidCredentialsError,
    NewPasswordMatchesCurrentError,
    PasswordTooWeakError,
)
from app.domains.auth.repository import RevokedRefreshTokenRepository, UserRepository
from app.domains.auth.service import AuthService
from app.domains.rbac.repository import RoleRepository
from tests.integration.factories import make_user

_OLD_PASSWORD = "OldPassw0rd!"
_NEW_PASSWORD = "NewPassw0rd!"


def _make_service(db_session):
    return AuthService(
        UserRepository(db_session),
        RoleRepository(db_session),
        RevokedRefreshTokenRepository(db_session),
        UnitOfWork(db_session),
    )


async def test_updates_the_hash_for_real(db_session):
    user = await make_user(db_session, role="applicant")
    user.password_hash = hash_password(_OLD_PASSWORD)
    await db_session.flush()

    service = _make_service(db_session)
    await service.change_password(
        user.id, current_password=_OLD_PASSWORD, new_password=_NEW_PASSWORD
    )

    assert verify_password(_NEW_PASSWORD, user.password_hash)
    assert not verify_password(_OLD_PASSWORD, user.password_hash)


async def test_rejects_wrong_current_password(db_session):
    user = await make_user(db_session, role="applicant")
    user.password_hash = hash_password(_OLD_PASSWORD)
    await db_session.flush()
    original_hash = user.password_hash

    service = _make_service(db_session)
    with pytest.raises(InvalidCredentialsError):
        await service.change_password(
            user.id, current_password="totally-wrong", new_password=_NEW_PASSWORD
        )

    assert user.password_hash == original_hash


async def test_rejects_new_password_matching_current(db_session):
    user = await make_user(db_session, role="applicant")
    user.password_hash = hash_password(_OLD_PASSWORD)
    await db_session.flush()

    service = _make_service(db_session)
    with pytest.raises(NewPasswordMatchesCurrentError):
        await service.change_password(
            user.id, current_password=_OLD_PASSWORD, new_password=_OLD_PASSWORD
        )


async def test_rejects_weak_new_password(db_session):
    user = await make_user(db_session, role="applicant")
    user.password_hash = hash_password(_OLD_PASSWORD)
    await db_session.flush()
    original_hash = user.password_hash

    service = _make_service(db_session)
    with pytest.raises(PasswordTooWeakError):
        await service.change_password(
            user.id, current_password=_OLD_PASSWORD, new_password="weakpassword"
        )

    assert user.password_hash == original_hash
