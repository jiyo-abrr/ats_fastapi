"""add interview date overrides

Revision ID: a1c7e2f4d8b3
Revises: 03fb6481126a
Create Date: 2026-09-10 09:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "a1c7e2f4d8b3"
down_revision: Union[str, Sequence[str], None] = "03fb6481126a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_date_overrides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_post_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_posts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "is_unavailable",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column("start_minute", sa.Integer(), nullable=True),
        sa.Column("end_minute", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_date >= start_date",
            name="ck_interview_date_overrides_range",
        ),
        sa.CheckConstraint(
            "is_unavailable OR ("
            "start_minute IS NOT NULL AND end_minute IS NOT NULL "
            "AND start_minute >= 0 AND end_minute <= 1440 "
            "AND end_minute > start_minute)",
            name="ck_interview_date_overrides_hours",
        ),
    )
    op.create_index(
        "ix_interview_date_overrides_job_post_id",
        "interview_date_overrides",
        ["job_post_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_date_overrides_job_post_id",
        table_name="interview_date_overrides",
    )
    op.drop_table("interview_date_overrides")
