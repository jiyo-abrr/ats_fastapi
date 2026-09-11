"""One Postgres advisory lock shared by every entry point that runs the
overdue-assessment sweep — the scheduler tick and the standalone
`python -m app.scripts.*` jobs alike — so a manual run can't overlap a
scheduled one (review F29).
"""

import logging
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# "ATSSWEEP" as a bigint advisory-lock key.
SWEEP_LOCK_KEY = 0x4154_5353_5745_4550


@asynccontextmanager
async def sweep_advisory_lock(db: AsyncSession):
    """Yields True if this caller acquired the lock (and must do the work),
    False if another process holds it (and this caller should skip). Releases
    on exit only when it was acquired here."""
    got = (
        await db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": SWEEP_LOCK_KEY})
    ).scalar_one()
    if not got:
        logger.info("sweep skipped: another process holds the advisory lock")
        yield False
        return
    try:
        yield True
    finally:
        await db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": SWEEP_LOCK_KEY})
