"""add is_active to users

Revision ID: bb2229b90efd
Revises: ffd55849b8a5
Create Date: 2026-09-08 10:19:06.293783

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'bb2229b90efd'
down_revision: Union[str, Sequence[str], None] = 'ffd55849b8a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column(
            'is_active', sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'is_active')
