"""Bounded reading of an UploadFile.

`await upload.read()` pulls the whole body into memory before any size check
can run. `read_upload_bounded` streams it in chunks and aborts as soon as it
crosses the limit, so an oversized upload costs `max_bytes`, not the full
payload (review F12).
"""

from fastapi import HTTPException, UploadFile, status

_CHUNK = 64 * 1024


async def read_upload_bounded(upload: UploadFile, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(_CHUNK):
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(f"File exceeds the {max_bytes // (1024 * 1024)} MB limit."),
            )
        chunks.append(chunk)
    return b"".join(chunks)
