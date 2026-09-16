"""add show_salary and show_tags to job_posts

Revision ID: 1f2b3c4d5e6a
Revises: 7fdaa0e92d36
Create Date: 2026-09-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "1f2b3c4d5e6a"
down_revision: Union[str, Sequence[str], None] = "7fdaa0e92d36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_posts",
        sa.Column(
            "show_salary",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "job_posts",
        sa.Column(
            "show_tags",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("job_posts", "show_tags")
    op.drop_column("job_posts", "show_salary")
