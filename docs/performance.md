# Performance Tuning

Optimize SgRequests Cache for high-performance and low-latency applications.

## 1. Compression

Reduce memory usage and network traffic (for distributed caches) by enabling compression.

```python
config = CacheConfig(
    compression="gzip"  # Options: "gzip", "lz4", "zstd", "none"
)
```

- **gzip**: Good balance (default).
- **lz4**: Extremely fast, lower compression ratio. Best for high-throughput.
- **zstd**: High compression ratio, good speed. Best for storage efficiency.
- **none**: No compression. Fastest CPU, highest memory/storage usage.

## 2. Stale-While-Revalidate

Serve stale content immediately while refreshing in the background. This eliminates latency spikes for expired content.

```python
config = CacheConfig(
    stale_while_revalidate_seconds=300  # Serve stale for up to 5 minutes
)
```

## 3. Request Deduplication

Prevent "thundering herd" problems where multiple concurrent requests for the same resource overwhelm the backend.

```python
config = CacheConfig(
    enable_request_deduplication=True  # Default: True
)
```

## 4. Tiered Caching

Use a 2-tier architecture for the best of both worlds:
- **L1 (Memory)**: Microsecond latency, volatile.
- **L2 (Redis)**: Millisecond latency, persistent, shared.

```python
from sgrequests_cache import TieredCacheBackend, MemoryCacheBackend, RedisCacheBackend

backend = TieredCacheBackend(
    l1=MemoryCacheBackend(),
    l2=RedisCacheBackend(redis_url="...")
)
```

## 5. Circuit Breaker

Protect your application from cascading failures if the cache backend (e.g., Redis) goes down.

```python
config = CacheConfig(
    enable_circuit_breaker=True,
    circuit_breaker_threshold=5,  # Open after 5 failures
    circuit_breaker_timeout=30    # Retry after 30 seconds
)
```

## 6. Cache Warming

Preload the cache with frequently accessed resources on startup.

```python
requests = [
    ("GET", "https://api.example.com/config", None),
    ("GET", "https://api.example.com/products", None),
]
cache.warm_cache(requests, concurrency=10)
```
