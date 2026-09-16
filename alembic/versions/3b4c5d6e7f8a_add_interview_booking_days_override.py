"""add per-job-post interview_booking_days override

Revision ID: 3b4c5d6e7f8a
Revises: 2a3b4c5d6e7f
Create Date: 2026-09-15 00:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "3b4c5d6e7f8a"
down_revision: Union[str, Sequence[str], None] = "2a3b4c5d6e7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "job_posts",
        sa.Column("interview_booking_days", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_job_posts_interview_booking_days",
        "job_posts",
        "interview_booking_days IS NULL OR "
        "(interview_booking_days >= 1 AND interview_booking_days <= 120)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_job_posts_interview_booking_days", "job_posts", type_="check"
    )
    op.drop_column("job_posts", "interview_booking_days")
