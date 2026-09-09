"""add application evaluations

Revision ID: d6b68d63e22a
Revises: d91894aa8bed
Create Date: 2026-09-08 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "d6b68d63e22a"
down_revision: Union[str, Sequence[str], None] = "d91894aa8bed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "application_evaluations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "application_id",
            UUID(as_uuid=True),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "imported_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("recommendation", sa.String(length=20), nullable=True),
        sa.Column("fit_score", sa.Integer(), nullable=True),
        sa.Column("seniority_assessed", sa.String(length=50), nullable=True),
        sa.Column("summary", sa.String(length=5000), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("rubric_version", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "recommendation IN ('advance', 'hold', 'reject')",
            name="ck_application_evaluations_recommendation",
        ),
        sa.CheckConstraint(
            "fit_score IS NULL OR (fit_score >= 0 AND fit_score <= 100)",
            name="ck_application_evaluations_fit_score",
        ),
    )
    op.create_index(
        "ix_application_evaluations_application_id",
        "application_evaluations",
        ["application_id"],
    )
    op.create_table(
        "application_evaluation_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "evaluation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("application_evaluations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column("dimension", sa.String(length=60), nullable=False),
        sa.Column("rating", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=2000), nullable=True),
        sa.CheckConstraint(
            "rating IN ('strong', 'qualified', 'below_bar', 'na')",
            name="ck_application_evaluation_scores_rating",
        ),
        sa.CheckConstraint(
            "category IN ('resume', 'assessment')",
            name="ck_application_evaluation_scores_category",
        ),
    )
    op.create_index(
        "ix_application_evaluation_scores_evaluation_id",
        "application_evaluation_scores",
        ["evaluation_id"],
    )


def downgrade() -> None:
    op.drop_table("application_evaluation_scores")
    op.drop_table("application_evaluations")
