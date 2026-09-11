import io

import pytest
from fastapi import HTTPException, UploadFile

from app.core.uploads import read_upload_bounded


def _upload(data: bytes) -> UploadFile:
    return UploadFile(filename="f.bin", file=io.BytesIO(data))


async def test_returns_full_content_within_limit():
    data = b"x" * 1000
    assert await read_upload_bounded(_upload(data), 5000) == data


async def test_aborts_over_the_limit_with_413():
    with pytest.raises(HTTPException) as exc:
        await read_upload_bounded(_upload(b"y" * 200_000), 100_000)
    assert exc.value.status_code == 413
