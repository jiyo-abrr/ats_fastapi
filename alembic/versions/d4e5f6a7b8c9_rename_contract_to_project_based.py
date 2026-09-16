"""rename job_posts employment_type 'contract' to 'project_based'

Revision ID: d4e5f6a7b8c9
Revises: ce3afa1f8273
Create Date: 2026-09-17 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "ce3afa1f8273"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_CHECK = (
    "employment_type IN ('full_time', 'part_time', 'contract', "
    "'internship', 'temporary')"
)
_NEW_CHECK = (
    "employment_type IN ('full_time', 'part_time', 'project_based', "
    "'internship', 'temporary')"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_job_posts_employment_type", "job_posts", type_="check"
    )
    op.execute(
        "UPDATE job_posts SET employment_type = 'project_based' "
        "WHERE employment_type = 'contract'"
    )
    op.create_check_constraint(
        "ck_job_posts_employment_type", "job_posts", _NEW_CHECK
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_job_posts_employment_type", "job_posts", type_="check"
    )
    op.execute(
        "UPDATE job_posts SET employment_type = 'contract' "
        "WHERE employment_type = 'project_based'"
    )
    op.create_check_constraint(
        "ck_job_posts_employment_type", "job_posts", _OLD_CHECK
    )
