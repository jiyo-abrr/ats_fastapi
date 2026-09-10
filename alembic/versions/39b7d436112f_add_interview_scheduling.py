"""add interview scheduling

Revision ID: 39b7d436112f
Revises: d6b68d63e22a
Create Date: 2026-09-09 14:11:36.891564

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "39b7d436112f"
down_revision: Union[str, Sequence[str], None] = "d6b68d63e22a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "interview_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("location_or_link", sa.String(length=500), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column(
            "self_scheduled",
            sa.Boolean(),
            server_default=sa.true(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('video', 'onsite', 'phone')",
            name="ck_interview_requests_mode",
        ),
        sa.CheckConstraint(
            "duration_minutes > 0 AND duration_minutes <= 480",
            name="ck_interview_requests_duration",
        ),
    )
    op.create_index(
        "ux_interview_requests_application_id",
        "interview_requests",
        ["application_id"],
        unique=True,
    )

    op.create_table(
        "interview_slots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("interview_requests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_interview_slots_request_id",
        "interview_slots",
        ["request_id"],
    )
    op.create_index(
        "ux_interview_slots_one_selected",
        "interview_slots",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("selected_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_table("interview_slots")
    op.drop_table("interview_requests")
