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
