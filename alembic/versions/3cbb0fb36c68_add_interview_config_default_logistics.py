"""add interview config default logistics

Revision ID: 3cbb0fb36c68
Revises: bab3745597ee
Create Date: 2026-09-11 13:15:10.033937

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "3cbb0fb36c68"
down_revision: Union[str, Sequence[str], None] = "bab3745597ee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "interview_config",
        sa.Column("default_video_link", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "interview_config",
        sa.Column("default_onsite_address", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_config", "default_onsite_address")
    op.drop_column("interview_config", "default_video_link")
