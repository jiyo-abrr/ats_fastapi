"""add default interview mode to job posts and interview config

Revision ID: 9894d1bbb660
Revises: e5f6a7b8c9d0
Create Date: 2026-09-16 13:38:25.381645

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9894d1bbb660'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'interview_config',
        sa.Column(
            'default_mode', sa.String(length=10), nullable=False,
            server_default='onsite',
        ),
    )
    op.alter_column('interview_config', 'default_mode', server_default=None)
    op.create_check_constraint(
        'ck_interview_config_default_mode',
        'interview_config',
        "default_mode IN ('video', 'onsite', 'phone')",
    )
    op.add_column(
        'job_posts',
        sa.Column('default_interview_mode', sa.String(length=10), nullable=True),
    )
    op.create_check_constraint(
        'ck_job_posts_default_interview_mode',
        'job_posts',
        "default_interview_mode IS NULL OR "
        "default_interview_mode IN ('video', 'onsite', 'phone')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_job_posts_default_interview_mode', 'job_posts', type_='check')
    op.drop_column('job_posts', 'default_interview_mode')
    op.drop_constraint('ck_interview_config_default_mode', 'interview_config', type_='check')
    op.drop_column('interview_config', 'default_mode')
