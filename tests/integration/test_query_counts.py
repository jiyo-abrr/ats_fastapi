"""F08 — `JobPostRepository.map_many` (the paginated-list transformer) must
run a fixed number of queries regardless of page size."""

import contextlib

from sqlalchemy import event, select
from sqlalchemy.orm import selectinload

from app.domains.job_posts.models import JobPost as JobPostModel
from app.domains.job_posts.repository import JobPostRepository
from tests.integration.factories import make_job_post


@contextlib.contextmanager
def count_queries(session):
    counter = {"n": 0}
    # AsyncSession.get_bind() returns the underlying sync Connection, which is
    # itself a valid `before_cursor_execute` event target.
    target = session.get_bind()

    def _before(*_a, **_k):
        counter["n"] += 1

    event.listen(target, "before_cursor_execute", _before)
    try:
        yield counter
    finally:
        event.remove(target, "before_cursor_execute", _before)


async def test_map_many_query_count_is_flat(db_session):
    for _ in range(12):
        await make_job_post(db_session)
    await db_session.flush()

    rows = (
        (
            await db_session.execute(
                select(JobPostModel).options(
                    selectinload(JobPostModel.company_address),
                    selectinload(JobPostModel.position),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 12

    repo = JobPostRepository(db_session)
    with count_queries(db_session) as c:
        entities = await repo.map_many(rows)

    assert len(entities) == 12
    # tags + exclusions + 3 template tables = 5, independent of row count.
    assert c["n"] <= 5, f"map_many ran {c['n']} queries for 12 rows (expected <= 5)"
