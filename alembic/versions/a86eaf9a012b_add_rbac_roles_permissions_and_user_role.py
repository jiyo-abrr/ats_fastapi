"""add rbac roles/permissions and user role

Revision ID: a86eaf9a012b
Revises: c61a17bd8f25
Create Date: 2026-09-05 16:03:58.587026

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import column, table


# revision identifiers, used by Alembic.
revision: str = 'a86eaf9a012b'
down_revision: Union[str, Sequence[str], None] = 'c61a17bd8f25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'permissions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    op.create_table(
        'roles',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_table(
        'role_permissions',
        sa.Column('role_id', sa.UUID(), nullable=False),
        sa.Column('permission_id', sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id']),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id']),
        sa.PrimaryKeyConstraint('role_id', 'permission_id'),
    )

    roles_table = table(
        "roles",
        column("id", sa.UUID()),
        column("name", sa.String()),
        column("description", sa.String()),
    )
    permissions_table = table(
        "permissions",
        column("id", sa.UUID()),
        column("key", sa.String()),
        column("description", sa.String()),
    )
    role_permissions_table = table(
        "role_permissions",
        column("role_id", sa.UUID()),
        column("permission_id", sa.UUID()),
    )

    admin_id = uuid.uuid4()
    hr_id = uuid.uuid4()
    applicant_id = uuid.uuid4()

    manage_hr_accounts_id = uuid.uuid4()
    manage_rbac_id = uuid.uuid4()
    manage_own_profile_id = uuid.uuid4()

    op.bulk_insert(
        roles_table,
        [
            {
                "id": admin_id,
                "name": "admin",
                "description": "Full access, including account management",
            },
            {
                "id": hr_id,
                "name": "hr",
                "description": "Operational access, excluding account management",
            },
            {
                "id": applicant_id,
                "name": "applicant",
                "description": "Self-service access to own data only",
            },
        ],
    )

    op.bulk_insert(
        permissions_table,
        [
            {
                "id": manage_hr_accounts_id,
                "key": "manage_hr_accounts",
                "description": "Create HR user accounts",
            },
            {
                "id": manage_rbac_id,
                "key": "manage_rbac",
                "description": "Grant/revoke role permissions",
            },
            {
                "id": manage_own_profile_id,
                "key": "manage_own_profile",
                "description": "View/edit own profile",
            },
        ],
    )

    op.bulk_insert(
        role_permissions_table,
        [
            {"role_id": admin_id, "permission_id": manage_hr_accounts_id},
            {"role_id": admin_id, "permission_id": manage_rbac_id},
            {"role_id": admin_id, "permission_id": manage_own_profile_id},
            {"role_id": hr_id, "permission_id": manage_own_profile_id},
            {"role_id": applicant_id, "permission_id": manage_own_profile_id},
        ],
    )

    op.add_column('users', sa.Column('role_id', sa.UUID(), nullable=True))

    users_table = table("users", column("role_id", sa.UUID()))
    op.execute(users_table.update().values(role_id=applicant_id))

    op.alter_column('users', 'role_id', nullable=False)
    op.create_foreign_key(
        'fk_users_role_id_roles', 'users', 'roles', ['role_id'], ['id']
    )
    op.alter_column(
        'users',
        'resume_object_key',
        existing_type=sa.VARCHAR(length=500),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'users',
        'resume_object_key',
        existing_type=sa.VARCHAR(length=500),
        nullable=False,
    )
    op.drop_constraint('fk_users_role_id_roles', 'users', type_='foreignkey')
    op.drop_column('users', 'role_id')
    op.drop_table('role_permissions')
    op.drop_table('roles')
    op.drop_table('permissions')
