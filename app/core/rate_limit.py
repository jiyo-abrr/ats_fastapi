from collections.abc import Callable, Coroutine

import redis.asyncio as redis
from fastapi import HTTPException, Request, status

from app.core.config import settings

_redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def rate_limit(
    key_prefix: str, limit: int, window_seconds: int
) -> Callable[[Request], Coroutine[None, None, None]]:
    async def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{key_prefix}:{client_ip}"

        count = await _redis_client.incr(key)
        if count == 1:
            await _redis_client.expire(key, window_seconds)

        if count > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
            )

    return dependency
