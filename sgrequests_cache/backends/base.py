from __future__ import annotations

from typing import Optional, Protocol


class CacheBackend(Protocol):
    """Interface for cache backends."""

    def get(self, key: str) -> Optional[bytes]:
        """Retrieve a value from the cache."""
        ...

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        """Set a value in the cache with a TTL."""
        ...

    def delete(self, key: str) -> None:
        """Delete a value from the cache."""
        ...

    def health_check(self) -> bool:
        """Check if the backend is healthy."""
        ...
