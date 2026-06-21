"""MinIO object storage adapter for original knowledge-base documents."""

from functools import lru_cache
from pathlib import Path

from minio import Minio

from app.rag.config import get_rag_settings


@lru_cache(maxsize=1)
def get_minio_client() -> Minio:
    settings = get_rag_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )


def ensure_bucket() -> None:
    settings = get_rag_settings()
    client = get_minio_client()
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def upload_path(path: Path, object_key: str, content_type: str) -> None:
    ensure_bucket()
    settings = get_rag_settings()
    get_minio_client().fput_object(
        settings.minio_bucket, object_key, str(path), content_type=content_type
    )


def download_path(object_key: str, destination: Path) -> None:
    settings = get_rag_settings()
    get_minio_client().fget_object(settings.minio_bucket, object_key, str(destination))


def delete_object(object_key: str) -> None:
    settings = get_rag_settings()
    get_minio_client().remove_object(settings.minio_bucket, object_key)

