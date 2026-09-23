"""Storage package: ObjectStorage abstraction and MinIO implementation."""
from functools import lru_cache

from app.storage.base import ObjectStorage
from app.storage.minio import MinIOObjectStorage

__all__ = ["ObjectStorage", "MinIOObjectStorage", "get_storage"]


@lru_cache
def get_storage() -> ObjectStorage:
    return MinIOObjectStorage()
