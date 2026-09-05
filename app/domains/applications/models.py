import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.domains.applications.enums import ApplicationStatus


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s.value}'" for s in ApplicationStatus) + ")",
            name="ck_applications_status",
        ),
        # One *active* application per applicant per job post — withdrawn
        # applications don't count, so withdrawing frees the slot but a
        # rejected application stays blocking (rejected is terminal).
        Index(
            "ux_applications_active_per_job_post",
            "job_post_id",
            "applicant_id",
            unique=True,
            postgresql_where=text("status != 'withdrawn'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Plain FK columns, no relationship() — job_post/applicant data needed by
    # the list endpoints is composed via explicit projection queries (see
    # ApplicationRepository.list_for_review/list_for_applicant) rather than
    # ORM relationship traversal, since those views only need a few columns
    # from each joined table, not the whole related entity.
    job_post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("job_posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    applicant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ApplicationStatus.SUBMITTED.value
    )
    # Snapshot of the applicant's resume at the time of applying — deliberately
    # not a live reference to User.resume_object_key, which can change later.
    resume_object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
