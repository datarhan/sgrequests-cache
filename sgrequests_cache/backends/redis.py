from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import Callable, Optional

import redis
from redis.asyncio import Redis as AsyncRedis

from .base import CacheBackend

logger = logging.getLogger(__name__)


@dataclass
class RedisCacheBackend(CacheBackend):
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    key_prefix: str = os.environ.get("SGCACHE_PREFIX", "sgcache:")

    def __post_init__(self) -> None:
        try:
            self._client = redis.from_url(self.redis_url)
        except Exception as e:
            # Redact password from URL for security
            safe_url = re.sub(r'://:[^@]+@', '://***@', self.redis_url)
            logger.error(f"Failed to connect to Redis at {safe_url}: {e}")
            raise

    def _k(self, key: str) -> str:
        # Ensure keys are reasonably sized
        if len(key) > 512:
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
            return f"{self.key_prefix}{digest}"
        return f"{self.key_prefix}{key}"

    def get(self, key: str) -> Optional[bytes]:
        try:
            data = self._client.get(self._k(key))
            return data if data is not None else None
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        try:
            self._client.set(self._k(key), value, ex=ttl_seconds)
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")

    def delete(self, key: str) -> None:
        try:
            self._client.delete(self._k(key))
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")

    def health_check(self) -> bool:
        """Check if Redis is reachable."""
        try:
            return self._client.ping()
        except Exception:
            return False

    def start_invalidation_listener(self, callback: Callable[[str], None]) -> None:
        """Start listening for invalidation messages."""
        from ..invalidation import DistributedInvalidator
        self._invalidator = DistributedInvalidator(self._client, callback)
        self._invalidator.start()

    def publish_invalidation(self, pattern: str) -> None:
        """Publish invalidation message."""
        if hasattr(self, "_invalidator"):
            self._invalidator.invalidate(pattern)
        else:
            # Create temporary invalidator just to publish
            from ..invalidation import DistributedInvalidator
            DistributedInvalidator(self._client, lambda x: None).invalidate(pattern)

    def close(self) -> None:
        """Close the Redis connection."""
        if hasattr(self, "_invalidator"):
            self._invalidator.stop()
        try:
            self._client.close()
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")

    def clear(self) -> None:
        """Clear all keys with the current prefix."""
        try:
            pattern = f"{self.key_prefix}*"
            keys = self._client.keys(pattern)
            if keys:
                self._client.delete(*keys)
                logger.info(f"Cleared {len(keys)} cache entries")
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")

    def delete_pattern(self, pattern: str) -> None:
        """Delete all keys matching the given pattern (after prefix)."""
        try:
            full_pattern = f"{self.key_prefix}{pattern}"
            keys = self._client.keys(full_pattern)
            if keys:
                self._client.delete(*keys)
                logger.info(f"Deleted {len(keys)} keys matching pattern {pattern}")
        except Exception as e:
            logger.error(f"Error deleting pattern {pattern}: {e}")


@dataclass(frozen=True)
class AsyncRedisCacheBackend:
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    key_prefix: str = os.environ.get("SGCACHE_PREFIX", "sgcache:")

    def __post_init__(self) -> None:
        object.__setattr__(self, "_client", AsyncRedis.from_url(self.redis_url))

    def _k(self, key: str) -> str:
        if len(key) > 512:
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
            return f"{self.key_prefix}{digest}"
        return f"{self.key_prefix}{key}"

    async def get(self, key: str) -> Optional[bytes]:
        try:
            data = await self._client.get(self._k(key))
            return data if data is not None else None
        except Exception:
            return None

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        try:
            await self._client.set(self._k(key), value, ex=ttl_seconds)
        except Exception:
            pass

    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(self._k(key))
        except Exception:
            pass
