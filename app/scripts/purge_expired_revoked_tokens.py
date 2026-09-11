import asyncio
import logging
import selectors
from datetime import UTC, datetime

from app.core.database import AsyncSessionLocal
from app.core.unit_of_work import UnitOfWork
from app.domains.auth.repository import RevokedRefreshTokenRepository

# Housekeeping, not part of the assessment sweep — split out from
# app/core/scheduler.py (review D06 / the Airflow migration, decision 2f in
# docs/plans/rabbitmq-airflow-migration.md) into its own script/DAG task,
# rather than carrying over its old coincidental coupling to the sweep's
# timer just because that's how it happened to be wired before. No shared
# advisory lock — a `DELETE ... WHERE expires_at < now` is naturally
# idempotent, so two overlapping runs aren't a correctness problem the way
# the sweep's read-then-write logic is.

logger = logging.getLogger(__name__)


async def run() -> int:
    """Drop revoked-refresh-token denylist rows whose token has already
    expired on its own merits (dead weight — see
    RevokedRefreshTokenRepository.delete_expired's own docstring). Returns
    the number removed (used by `app.cli`'s `--json` output)."""
    async with AsyncSessionLocal() as db:
        uow = UnitOfWork(db)
        removed = await RevokedRefreshTokenRepository(db).delete_expired(
            datetime.now(UTC)
        )
        await uow.commit()
        if removed:
            logger.info("purged %s expired revoked-token row(s)", removed)
        print(f"Purged {removed} expired revoked-token row(s)")
        return removed


async def main() -> int:
    """CLI / task-runner entry point — no lock needed, see module docstring."""
    return await run()


if __name__ == "__main__":
    # psycopg's async driver can't run under Windows' default ProactorEventLoop
    # (asyncio.run()'s default there) — force the selector-based loop instead.
    asyncio.run(
        main(),
        loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()),
    )
