"""Request-correlation IDs (review F21).

Every request gets an ID — the caller's `X-Request-ID` if it sent one,
otherwise a generated UUID4 — available as `request.state.request_id`,
echoed back in the response header, and included in the generic-500 body so a
user-reported error can be matched to server logs. Deliberately small: no
metrics/tracing framework, just the one correlation primitive that makes
"here's what broke" support requests answerable.
"""

import uuid
from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import Response

HEADER_NAME = "X-Request-ID"


async def request_id_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get(HEADER_NAME) or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers[HEADER_NAME] = request_id
    return response
