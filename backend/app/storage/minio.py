"""MinIO implementation of the ObjectStorage abstraction."""
from io import BytesIO

from minio import Minio
from minio.error import S3Error

from app.config import get_settings
from app.storage.base import ObjectStorage


class MinIOObjectStorage(ObjectStorage):
    def __init__(self) -> None:
        settings = get_settings()
        # The platform injects endpoints like http://minio.dkubex.svc:9000;
        # the minio client wants host:port and takes secure separately.
        endpoint = settings.minio_endpoint.split("://", 1)[-1]
        self._client = Minio(
            endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def upload(self, bucket: str, key: str, data: bytes) -> None:
        self._client.put_object(bucket, key, BytesIO(data), length=len(data))

    def download(self, bucket: str, key: str) -> bytes:
        response = self._client.get_object(bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, bucket: str, key: str) -> None:
        self._client.remove_object(bucket, key)

    def exists(self, bucket: str, key: str) -> bool:
        try:
            self._client.stat_object(bucket, key)
            return True
        except S3Error as exc:
            if exc.code == "NoSuchKey":
                return False
            raise

    def ensure_bucket(self, bucket: str) -> None:
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)
