# SgRequests Redis Cache Wrapper

A robust Redis-backed caching layer for SgRequests HTTP client with comprehensive error handling and logging.

## Features

- **Smart Caching**: Only caches successful responses (2xx by default), never caches errors (4xx, 5xx)
- **Redis-backed persistence** across crawler restarts
- **POST request body-aware** cache keys (SHA256 digest)
- **TTL-based expiration** (default 24h)
- **Optional per-request bypass** flags

## SgRequests Cache

A high-performance, feature-rich caching layer for `sgrequests` (and `httpx`), designed for production-grade applications.

## Features

- 🚀 **Backend Support**: In-memory, Redis, and Tiered (L1/L2) caching.
- ⚡ **Performance**: Request deduplication, compression (gzip/lz4/zstd), and Stale-While-Revalidate.
- 🛡️ **Reliability**: Circuit breaker, health checks, and "Serve Stale on Error" fallback.
- 🎯 **Control**: URL pattern matching, adaptive TTL (Cache-Control/Expires), and custom key builders.
- 📊 **Observability**: Prometheus metrics, structured logging, and detailed statistics.
- 🔄 **Distributed**: Pub/Sub cache invalidation for multi-instance deployments.

## Installation

```bash
pip install sgrequests-cache
# Optional dependencies
pip install sgrequests-cache[redis,compression,metrics]
```

## Quick Start

```python
from sgrequests_cache import CachedSgRequests, CacheConfig, MemoryCacheBackend
import httpx

# 1. Configure
config = CacheConfig(
    ttl_seconds=300,
    stale_while_revalidate_seconds=60,
    compression="gzip"
)

# 2. Initialize
backend = MemoryCacheBackend()
client = httpx.Client()
cache = CachedSgRequests(client, backend, config)

# 3. Use
response = cache.get("https://api.example.com/data")
```

## Documentation

- [Statistics & Metrics](docs/statistics.md)
- [URL Patterns](docs/patterns.md)
- [Performance Tuning](docs/performance.md)
- [Production Guide](docs/production.md)

## Advanced Usage

### Tiered Caching (Memory + Redis)

```python
from sgrequests_cache import TieredCacheBackend, RedisCacheBackend, MemoryCacheBackend

backend = TieredCacheBackend(
    l1=MemoryCacheBackend(),
    l2=RedisCacheBackend(redis_url="redis://localhost:6379")
)
```

### Stale-While-Revalidate

Serve stale content immediately while refreshing in the background:

```python
config = CacheConfig(
    ttl_seconds=60,
    stale_while_revalidate_seconds=300
)
```

### Distributed Invalidation

Automatically sync L1 caches across multiple instances using Redis Pub/Sub:

```python
# When you delete a key on one instance:
cache.delete("https://api.example.com/resource")
# It is automatically removed from all other instances' memory cache.
```

## License

MIT

### Configuration Options

```python
config = CacheConfig(
    namespace="my_crawler",           # Cache namespace
    ttl_seconds=86400,                # 24 hours
    max_bytes=2*1024*1024,            # Max response size to cache (2MB)
    vary_user_agent=False,            # Include User-Agent in cache key
    vary_cookies=False,               # Include cookies in cache key
    enable_logging=True,              # Enable cache hit/miss logging
    cache_by_default=True,            # Cache all requests by default (opt-out)
    cacheable_status_codes=set(range(200, 300))  # Only cache 2xx responses
)
```

### Opt-In vs Opt-Out Caching

**Opt-Out (Default)**: All requests are cached unless you explicitly disable it
```python
config = CacheConfig(cache_by_default=True)  # Default
cache = CachedSgRequests(http, backend, config)

# This will be cached
r = cache.get(url)

# Explicitly disable caching for this request
r = cache.get(url, cache_write=False)
```

**Opt-In**: No requests are cached unless you explicitly enable it
```python
config = CacheConfig(cache_by_default=False)
cache = CachedSgRequests(http, backend, config)

# This will NOT be cached
r = cache.get(url)

# Explicitly enable caching for this request
r = cache.get(url, cache_write=True, cache_read=True)
```

### Enable Logging

```python
import logging
logging.basicConfig(level=logging.INFO)

config = CacheConfig(enable_logging=True)
# Now you'll see cache hits/misses in logs
```

### Cache Management

```python
backend = RedisCacheBackend()

# Clear all cache entries for this prefix
backend.clear()

# Delete specific pattern
backend.delete_pattern("*example.com*")

# Close connection when done
backend.close()
```

### Per-Request Control

```python
# Force refresh (bypass cache read)
r = http.get(url, force_refresh=True)

# Don't read from cache
r = http.get(url, cache_read=False)

# Don't write to cache
r = http.get(url, cache_write=False)
```

## Run Tests

```bash
pip install -r requirements.txt
PYTHONPATH=. pytest tests/ -v
```

## Environment Variables

- `REDIS_URL`: Redis connection URL (default: `redis://localhost:6379/0`)
- `SGCACHE_PREFIX`: Key prefix (default: `sgcache:`)
- `SGCACHE_NAMESPACE`: Cache namespace (default: `default`)
- `SGCACHE_TTL`: TTL in seconds (default: `86400`)
- `SGCACHE_MAX_BYTES`: Max response size (default: `2097152`)
- `SGCACHE_LOGGING`: Enable logging (default: `false`)
- `SGCACHE_BY_DEFAULT`: Cache by default (default: `true`)
- `SGCACHE_VARY_UA`: Vary by User-Agent (default: `false`)
- `SGCACHE_VARY_COOKIES`: Vary by cookies (default: `false`)

## Project Structure

```
sgrequests-cache/
├── sgrequests_cache/
│   ├── __init__.py
│   ├── cache.py              # Main caching wrapper
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── base.py           # Backend interface
│   │   ├── redis.py          # Redis backend
│   │   └── memory.py         # Memory backend (for testing)
│   └── serializers.py        # MessagePack + Gzip serialization
├── tests/
│   └── test_cache.py         # Comprehensive test suite
├── README.md
└── requirements.txt
```

## Important Notes

⚠️ **Error Responses**: By default, only 2xx responses are cached. 4xx and 5xx errors are NEVER cached to avoid propagating temporary failures.

💡 **Custom Status Codes**: You can customize which status codes to cache via `cacheable_status_codes` in `CacheConfig`.
