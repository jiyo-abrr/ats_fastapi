"""add interview availability

Revision ID: 03fb6481126a
Revises: 39b7d436112f
Create Date: 2026-09-09 15:31:30.120979

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "03fb6481126a"
down_revision: Union[str, Sequence[str], None] = "39b7d436112f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slot_minutes", sa.Integer(), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("min_notice_hours", sa.Integer(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_interview_config_singleton"),
        sa.CheckConstraint(
            "slot_minutes > 0 AND slot_minutes <= 480",
            name="ck_interview_config_slot_minutes",
        ),
        sa.CheckConstraint(
            "horizon_days >= 1 AND horizon_days <= 120",
            name="ck_interview_config_horizon_days",
        ),
        sa.CheckConstraint(
            "min_notice_hours >= 0 AND min_notice_hours <= 336",
            name="ck_interview_config_min_notice_hours",
        ),
    )
    op.execute(
        "INSERT INTO interview_config "
        "(id, slot_minutes, horizon_days, min_notice_hours, timezone) "
        "VALUES (1, 45, 21, 12, 'Asia/Manila')"
    )

    op.create_table(
        "interview_availability_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_post_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_posts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_minute", sa.Integer(), nullable=False),
        sa.Column("end_minute", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "weekday >= 0 AND weekday <= 6",
            name="ck_interview_availability_rules_weekday",
        ),
        sa.CheckConstraint(
            "start_minute >= 0 AND end_minute <= 1440 "
            "AND end_minute > start_minute",
            name="ck_interview_availability_rules_span",
        ),
    )
    op.create_index(
        "ix_interview_availability_rules_job_post_id",
        "interview_availability_rules",
        ["job_post_id"],
    )

    op.create_table(
        "job_post_interviewers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_post_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_posts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ux_job_post_interviewers",
        "job_post_interviewers",
        ["job_post_id", "user_id"],
        unique=True,
    )

    op.create_index(
        "ix_interview_slots_starts_at", "interview_slots", ["starts_at"]
    )
    op.create_index(
        "ux_interview_slots_booked_time",
        "interview_slots",
        ["starts_at"],
        unique=True,
        postgresql_where=sa.text("selected_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_interview_slots_booked_time", table_name="interview_slots")
    op.drop_index("ix_interview_slots_starts_at", table_name="interview_slots")
    op.drop_table("job_post_interviewers")
    op.drop_table("interview_availability_rules")
    op.drop_table("interview_config")
