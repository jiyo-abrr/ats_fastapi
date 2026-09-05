import uuid
from unittest.mock import MagicMock

import pytest

from app.domains.rbac import entities
from app.domains.rbac.exceptions import PermissionNotFoundError, RoleNotFoundError
from app.domains.rbac.service import RBACService


def make_service():
    roles = MagicMock()
    permissions = MagicMock()
    role_permissions = MagicMock()
    uow = MagicMock()
    service = RBACService(roles, permissions, role_permissions, uow)
    return service, roles, permissions, role_permissions, uow


def make_role(name="hr") -> entities.Role:
    return entities.Role(id=uuid.uuid4(), name=name, description=None)


def make_permission(key="manage_hr_accounts") -> entities.Permission:
    return entities.Permission(id=uuid.uuid4(), key=key, description=None)


class TestGrant:
    def test_raises_when_role_missing(self):
        service, roles, permissions, role_permissions, uow = make_service()
        roles.get_by_name.return_value = None

        with pytest.raises(RoleNotFoundError):
            service.grant("ghost", "manage_hr_accounts")

        role_permissions.grant.assert_not_called()
        uow.commit.assert_not_called()

    def test_raises_when_permission_missing(self):
        service, roles, permissions, role_permissions, uow = make_service()
        roles.get_by_name.return_value = make_role()
        permissions.get_by_key.return_value = None

        with pytest.raises(PermissionNotFoundError):
            service.grant("hr", "ghost_permission")

        role_permissions.grant.assert_not_called()
        uow.commit.assert_not_called()

    def test_grants_and_commits(self):
        service, roles, permissions, role_permissions, uow = make_service()
        role = make_role()
        permission = make_permission()
        roles.get_by_name.return_value = role
        permissions.get_by_key.return_value = permission

        service.grant("hr", "manage_hr_accounts")

        role_permissions.grant.assert_called_once_with(role.id, permission.id)
        uow.commit.assert_called_once()


class TestRevoke:
    def test_revokes_and_commits(self):
        service, roles, permissions, role_permissions, uow = make_service()
        role = make_role()
        permission = make_permission()
        roles.get_by_name.return_value = role
        permissions.get_by_key.return_value = permission

        service.revoke("hr", "manage_hr_accounts")

        role_permissions.revoke.assert_called_once_with(role.id, permission.id)
        uow.commit.assert_called_once()


class TestListRoles:
    def test_lists_roles_with_their_permissions(self):
        service, roles, permissions, role_permissions, uow = make_service()
        role = make_role("admin")
        roles.list_all.return_value = [role]
        role_permissions.list_for_role.return_value = [make_permission("manage_rbac")]

        result = service.list_roles()

        assert len(result) == 1
        assert result[0].name == "admin"
        assert result[0].permissions[0].key == "manage_rbac"


class TestListPermissions:
    def test_lists_all_permissions(self):
        service, roles, permissions, role_permissions, uow = make_service()
        permissions.list_all.return_value = [make_permission("manage_own_profile")]

        result = service.list_permissions()

        assert len(result) == 1
        assert result[0].key == "manage_own_profile"
