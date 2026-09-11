"""arq (Redis-backed) job queue plumbing shared by the FastAPI process (which
enqueues) and `app/workers/` (which consumes) — review F09/F26. arq reuses the
`REDIS_URL` the app already depends on for rate limiting, rather than adding a
second broker.
"""

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import settings

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def get_arq_pool() -> ArqRedis:
    """Lazily-created, process-wide pool (same shape as `rate_limit.redis_client`)
    — reused across requests rather than opened per call. Closed in `main.py`'s
    lifespan alongside the rate-limit client."""
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


async def close_arq_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None
