"""rename job_posts requirements to responsibilities

Revision ID: 7fdaa0e92d36
Revises: 877fdc3305ab
Create Date: 2026-09-14 13:39:59.552141

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7fdaa0e92d36'
down_revision: Union[str, Sequence[str], None] = '877fdc3305ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column("job_posts", "requirements", new_column_name="responsibilities")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("job_posts", "responsibilities", new_column_name="requirements")
