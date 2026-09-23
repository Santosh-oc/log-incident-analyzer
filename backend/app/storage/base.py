"""Object storage abstraction. Services depend on this, not the MinIO client."""
from abc import ABC, abstractmethod
from io import BytesIO


class ObjectStorage(ABC):
    @abstractmethod
    def upload(self, bucket: str, key: str, data: bytes) -> None:
        """Store object data at bucket/key, overwriting any existing object."""

    @abstractmethod
    def download(self, bucket: str, key: str) -> bytes:
        """Return the full object content."""

    @abstractmethod
    def delete(self, bucket: str, key: str) -> None:
        """Delete the object. No-op if it does not exist."""

    @abstractmethod
    def exists(self, bucket: str, key: str) -> bool:
        """Return True if the object exists."""

    @abstractmethod
    def ensure_bucket(self, bucket: str) -> None:
        """Create the bucket if it does not exist."""
