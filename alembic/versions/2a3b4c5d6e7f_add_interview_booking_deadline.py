"""add interview_booking_deadline to applications and interview_booking_days to interview_config

Revision ID: 2a3b4c5d6e7f
Revises: 1f2b3c4d5e6a
Create Date: 2026-09-15 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "2a3b4c5d6e7f"
down_revision: Union[str, Sequence[str], None] = "1f2b3c4d5e6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "applications",
        sa.Column(
            "interview_booking_deadline",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "interview_config",
        sa.Column(
            "interview_booking_days",
            sa.Integer(),
            nullable=False,
            server_default="21",
        ),
    )
    op.create_check_constraint(
        "ck_interview_config_interview_booking_days",
        "interview_config",
        "interview_booking_days >= 1 AND interview_booking_days <= 120",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_interview_config_interview_booking_days",
        "interview_config",
        type_="check",
    )
    op.drop_column("interview_config", "interview_booking_days")
    op.drop_column("applications", "interview_booking_deadline")
