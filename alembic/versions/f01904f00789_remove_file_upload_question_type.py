"""remove file_upload question type

Revision ID: f01904f00789
Revises: f4d2d1f8394c
Create Date: 2026-09-06 06:58:25.143630

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f01904f00789'
down_revision: Union[str, Sequence[str], None] = 'f4d2d1f8394c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # file_upload was dropped from QuestionType — not needed for assessments.
    # No existing rows used it (confirmed empty before writing this migration).
    op.drop_constraint(
        'ck_assessment_questions_question_type', 'assessment_questions', type_='check'
    )
    op.create_check_constraint(
        'ck_assessment_questions_question_type',
        'assessment_questions',
        "question_type IN ('text', 'long_text', 'single_choice', "
        "'multiple_choice', 'boolean', 'number', 'rating', 'date')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'ck_assessment_questions_question_type', 'assessment_questions', type_='check'
    )
    op.create_check_constraint(
        'ck_assessment_questions_question_type',
        'assessment_questions',
        "question_type IN ('text', 'long_text', 'single_choice', "
        "'multiple_choice', 'boolean', 'number', 'rating', 'date', "
        "'file_upload')",
    )
