"""drop per-question instructions

Per-question `instructions` is redundant with the template-level `instructions`
(shown to the applicant before the attempt starts). Dropped from all 3 question
tables; template-level `instructions` is untouched.

Revision ID: ffd55849b8a5
Revises: 449cadbbefb7
Create Date: 2026-09-07 17:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "ffd55849b8a5"
down_revision: Union[str, Sequence[str], None] = "449cadbbefb7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "pre_assessment_questions",
    "culture_fit_questions",
    "technical_assessment_questions",
)


def upgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "instructions")


def downgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column("instructions", sa.String(length=1000), nullable=True),
        )
