from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .base import CacheBackend


@dataclass
class TieredCacheBackend(CacheBackend):
    """
    Two-tier cache backend with fast L1 and persistent L2.
    
    L1: Fast in-memory cache (e.g., MemoryCacheBackend)
    L2: Persistent cache (e.g., RedisCacheBackend)
    
    Read flow:
    1. Check L1 (fast)
    2. If miss, check L2
    3. If L2 hit, promote to L1
    
    Write flow:
    1. Write to L1 with shorter TTL
    2. Write to L2 with full TTL
    """
    
    l1: CacheBackend  # Fast tier (memory)
    l2: CacheBackend  # Persistent tier (Redis)
    
    def __init__(self, l1: CacheBackend, l2: CacheBackend, l1_ttl_ratio: float = 0.1):
        self.l1 = l1
        self.l2 = l2
        self.l1_ttl_ratio = l1_ttl_ratio
        
        # If L2 supports invalidation (e.g. Redis), subscribe to it to clear L1
        if hasattr(self.l2, "start_invalidation_listener"):
            self.l2.start_invalidation_listener(self._on_invalidation)  # type: ignore

    def _on_invalidation(self, pattern: str) -> None:
        """Handle invalidation message from L2."""
        # For now, we just clear L1 if we receive any invalidation
        # Ideally we would match the pattern, but MemoryCacheBackend doesn't support pattern delete efficiently yet
        # unless we iterate.
        # If pattern is "*", clear all.
        if pattern == "*":
            self.l1.clear()
        else:
            # Try to delete specific key if it's not a glob
            if "*" not in pattern:
                self.l1.delete(pattern)
            else:
                # Fallback to clear for safety, or implement pattern matching in MemoryBackend
                self.l1.clear()

    def get(self, key: str) -> Optional[bytes]:
        """Get from L1, fallback to L2, promote on L2 hit."""
        # Try L1
        val = self.l1.get(key)
        if val is not None:
            return val
            
        # Try L2
        val = self.l2.get(key)
        if val is not None:
            # Promote to L1 with error handling
            try:
                self.l1.set(key, val, ttl_seconds=60)  # Default 60s promotion
            except Exception as e:
                # Log but don't fail - we have the value from L2
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to promote key to L1: {e}")
            return val
            
        return None
    
    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        """Write to both L1 and L2."""
        # L1 gets shorter TTL to reduce memory pressure
        l1_ttl = max(60, int(ttl_seconds * self.l1_ttl_ratio))
        self.l1.set(key, value, ttl_seconds=l1_ttl)
        self.l2.set(key, value, ttl_seconds=ttl_seconds)
        
        # Publish invalidation if L2 supports it
        if hasattr(self.l2, "publish_invalidation"):
            self.l2.publish_invalidation(key)  # type: ignore
    
    def delete(self, key: str) -> None:
        """Delete from both tiers."""
        self.l1.delete(key)
        self.l2.delete(key)
        
        if hasattr(self.l2, "publish_invalidation"):
            self.l2.publish_invalidation(key)  # type: ignore

    def health_check(self) -> bool:
        """Check health of both tiers."""
        return self.l1.health_check() and self.l2.health_check()
    
    def clear_l1(self) -> None:
        """Clear L1 cache only."""
        if hasattr(self.l1, 'clear'):
            self.l1.clear()  # type: ignore
    
    def clear_l2(self) -> None:
        """Clear L2 cache only."""
        if hasattr(self.l2, 'clear'):
            self.l2.clear()  # type: ignore
