from __future__ import annotations

import time
from typing import Dict, Optional, Tuple

from .base import CacheBackend


class MemoryCacheBackend(CacheBackend):
    """In-memory cache backend with TTL support."""
    
    def __init__(self) -> None:
        # Store tuples of (value, expiry_timestamp)
        self._data: Dict[str, Tuple[bytes, float]] = {}

    def get(self, key: str) -> Optional[bytes]:
        """
        Get value from cache.
        
        Returns the value even if expired - caller is responsible for checking freshness.
        This allows for stale-while-revalidate and serve-stale-on-error patterns.
        """
        if key in self._data:
            value, expires_at = self._data[key]
            return value
        return None
    
    def is_expired(self, key: str) -> bool:
        """Check if key is expired (without deleting it)."""
        if key in self._data:
            _, expires_at = self._data[key]
            return time.time() >= expires_at
        return True

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        expires_at = time.time() + ttl_seconds
        self._data[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def health_check(self) -> bool:
        return True

    def clear(self) -> None:
        self._data.clear()
    
    def cleanup_expired(self) -> int:
        """Remove expired entries. Returns number of entries removed."""
        now = time.time()
        expired_keys = [k for k, (_, exp) in self._data.items() if now >= exp]
        for key in expired_keys:
            del self._data[key]
        return len(expired_keys)
