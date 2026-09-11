"""add interview logistics presets

Revision ID: f92afc553688
Revises: 3cbb0fb36c68
Create Date: 2026-09-11 13:31:19.103251

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "f92afc553688"
down_revision: Union[str, Sequence[str], None] = "3cbb0fb36c68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_config = sa.table(
    "interview_config",
    sa.column("id", sa.Integer()),
    sa.column("default_video_link", sa.String()),
    sa.column("default_onsite_address", sa.String()),
)
_presets = sa.table(
    "interview_logistics_presets",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("job_post_id", UUID(as_uuid=True)),
    sa.column("mode", sa.String()),
    sa.column("label", sa.String()),
    sa.column("value", sa.String()),
)


def upgrade() -> None:
    op.create_table(
        "interview_logistics_presets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_post_id",
            UUID(as_uuid=True),
            sa.ForeignKey("job_posts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("mode", sa.String(length=10), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('video', 'onsite')",
            name="ck_interview_logistics_presets_mode",
        ),
    )
    op.create_index(
        "ix_interview_logistics_presets_job_post_id",
        "interview_logistics_presets",
        ["job_post_id"],
    )

    # Carry forward whatever was already set as the single global default —
    # each becomes a "Default" preset for its mode rather than being dropped.
    conn = op.get_bind()
    row = conn.execute(
        sa.select(
            _config.c.default_video_link, _config.c.default_onsite_address
        ).where(_config.c.id == 1)
    ).first()
    if row is not None:
        if row.default_video_link:
            conn.execute(
                _presets.insert().values(
                    id=uuid.uuid4(),
                    job_post_id=None,
                    mode="video",
                    label="Default",
                    value=row.default_video_link,
                )
            )
        if row.default_onsite_address:
            conn.execute(
                _presets.insert().values(
                    id=uuid.uuid4(),
                    job_post_id=None,
                    mode="onsite",
                    label="Default",
                    value=row.default_onsite_address,
                )
            )

    op.drop_column("interview_config", "default_video_link")
    op.drop_column("interview_config", "default_onsite_address")


def downgrade() -> None:
    op.add_column(
        "interview_config",
        sa.Column("default_onsite_address", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "interview_config",
        sa.Column("default_video_link", sa.String(length=500), nullable=True),
    )
    op.drop_index(
        "ix_interview_logistics_presets_job_post_id",
        table_name="interview_logistics_presets",
    )
    op.drop_table("interview_logistics_presets")
