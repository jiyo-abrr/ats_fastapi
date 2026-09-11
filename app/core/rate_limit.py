import logging
from collections.abc import Callable, Coroutine

import redis.asyncio as redis
from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

redis_client = redis.from_url(settings.redis_url, decode_responses=True)

# INCR the counter and, only on the first hit of a window, attach the TTL — as
# one atomic server-side step. Doing INCR then a separate EXPIRE leaves a race:
# if the process dies between them the key lives forever with no TTL, and the
# client IP is blocked permanently. Returns the post-increment count.
_INCR_WITH_EXPIRY = """
local count = redis.call('INCR', KEYS[1])
-- Set the TTL on the first hit of a window, and also heal any key that somehow
-- lost its TTL (PTTL == -1) so a stuck counter can't block an IP forever.
if count == 1 or redis.call('PTTL', KEYS[1]) == -1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def rate_limit(
    key_prefix: str, limit: int, window_seconds: int
) -> Callable[[Request], Coroutine[None, None, None]]:
    async def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{key_prefix}:{client_ip}"

        try:
            count = await redis_client.eval(_INCR_WITH_EXPIRY, 1, key, window_seconds)
        except RedisError:
            # Fail open: a rate limiter that hard-fails requests when its
            # backing store is unreachable is worse than a brief window with
            # no limiting. Logged so the outage is visible.
            logger.warning("rate limit check skipped: Redis unavailable", exc_info=True)
            return

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )

    return dependency
