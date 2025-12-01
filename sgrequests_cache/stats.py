from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class CacheStats:
    """Thread-safe cache statistics."""
    
    hits: int = 0
    misses: int = 0
    errors: int = 0
    writes: int = 0
    bytes_saved: int = 0
    bytes_written: int = 0
    total_requests: int = 0
    start_time: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    
    def increment_hit(self, bytes_saved: int = 0) -> None:
        """Increment hit counter (thread-safe)."""
        with self._lock:
            self.hits += 1
            self.bytes_saved += bytes_saved
            self.total_requests += 1
    
    def increment_miss(self) -> None:
        """Increment miss counter (thread-safe)."""
        with self._lock:
            self.misses += 1
            self.total_requests += 1
    
    def increment_error(self) -> None:
        """Increment error counter (thread-safe)."""
        with self._lock:
            self.errors += 1
    
    def increment_write(self, bytes_written: int = 0) -> None:
        """Increment write counter (thread-safe)."""
        with self._lock:
            self.writes += 1
            self.bytes_written += bytes_written
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        with self._lock:
            total = self.hits + self.misses
            return self.hits / total if total > 0 else 0.0
    
    @property
    def miss_rate(self) -> float:
        """Calculate cache miss rate (0.0 to 1.0)."""
        with self._lock:
            return self.misses / self.total_requests if self.total_requests > 0 else 0.0
    
    @property
    def uptime_seconds(self) -> float:
        """Get uptime in seconds."""
        return time.time() - self.start_time
    
    def reset(self) -> None:
        """Reset all statistics."""
        with self._lock:
            self.hits = 0
            self.misses = 0
            self.errors = 0
            self.writes = 0
            self.bytes_saved = 0
            self.bytes_written = 0
            self.total_requests = 0
            self.start_time = time.time()
    
    def to_dict(self) -> dict:
        """Export statistics as dictionary."""
        with self._lock:
            return {
                "hits": self.hits,
                "misses": self.misses,
                "errors": self.errors,
                "writes": self.writes,
                "bytes_saved": self.bytes_saved,
                "bytes_written": self.bytes_written,
                "total_requests": self.total_requests,
                "hit_rate": self.hit_rate,
                "miss_rate": self.miss_rate,
                "uptime_seconds": self.uptime_seconds
            }
