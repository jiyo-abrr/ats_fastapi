"""add company address links to interview logistics

Revision ID: 877fdc3305ab
Revises: f92afc553688
Create Date: 2026-09-11 13:58:59.010044

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "877fdc3305ab"
down_revision: Union[str, Sequence[str], None] = "f92afc553688"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "interview_logistics_presets",
        "value",
        existing_type=sa.String(length=500),
        nullable=True,
    )
    op.add_column(
        "interview_logistics_presets",
        sa.Column("company_address_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_interview_logistics_presets_company_address_id",
        "interview_logistics_presets",
        "company_addresses",
        ["company_address_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_interview_logistics_presets_address_mode",
        "interview_logistics_presets",
        "company_address_id IS NULL OR mode = 'onsite'",
    )

    op.add_column(
        "interview_requests",
        sa.Column("company_address_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_interview_requests_company_address_id",
        "interview_requests",
        "company_addresses",
        ["company_address_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_interview_requests_address_mode",
        "interview_requests",
        "company_address_id IS NULL OR mode = 'onsite'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_interview_requests_address_mode", "interview_requests", type_="check"
    )
    op.drop_constraint(
        "fk_interview_requests_company_address_id",
        "interview_requests",
        type_="foreignkey",
    )
    op.drop_column("interview_requests", "company_address_id")

    op.drop_constraint(
        "ck_interview_logistics_presets_address_mode",
        "interview_logistics_presets",
        type_="check",
    )
    op.drop_constraint(
        "fk_interview_logistics_presets_company_address_id",
        "interview_logistics_presets",
        type_="foreignkey",
    )
    op.drop_column("interview_logistics_presets", "company_address_id")
    op.alter_column(
        "interview_logistics_presets",
        "value",
        existing_type=sa.String(length=500),
        nullable=False,
    )
