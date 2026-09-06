import io

from minio import Minio
from minio.error import S3Error

from app.core.config import settings

_client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


def ensure_bucket(bucket: str) -> None:
    try:
        if not _client.bucket_exists(bucket):
            _client.make_bucket(bucket)
    except S3Error as exc:
        raise RuntimeError(
            f"could not ensure MinIO bucket '{bucket}' exists: {exc}"
        ) from exc


def upload_object(
    bucket: str, object_key: str, data: bytes, content_type: str | None
) -> None:
    ensure_bucket(bucket)
    _client.put_object(
        bucket,
        object_key,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type or "application/octet-stream",
    )


class ObjectNotFoundError(RuntimeError):
    """Raised by get_object when the key is missing — callers map it to their
    own domain NotFoundError."""


def get_object(bucket: str, object_key: str) -> tuple[bytes, str]:
    """Return `(bytes, content_type)` for a stored object. Sync (the MinIO SDK
    has no async client) — call via `run_in_threadpool`, same as upload_object."""
    try:
        response = _client.get_object(bucket, object_key)
        try:
            data = response.read()
            content_type = (
                response.headers.get("Content-Type") or "application/octet-stream"
            )
            return data, content_type
        finally:
            response.close()
            response.release_conn()
    except S3Error as exc:
        if exc.code in ("NoSuchKey", "NoSuchBucket"):
            raise ObjectNotFoundError(
                f"object '{object_key}' not found in bucket '{bucket}'"
            ) from exc
        raise
