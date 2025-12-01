# Production Deployment Guide

Best practices for deploying SgRequests Cache in production environments.

## 1. Backend Selection

- **Single Instance**: Use `MemoryCacheBackend` for simplicity and speed.
- **Distributed/Microservices**: Use `RedisCacheBackend` to share cache across instances.
- **High Performance**: Use `TieredCacheBackend` (Memory + Redis) to minimize Redis network round-trips.

## 2. Redis Configuration

Ensure your Redis instance is configured for caching:
- **Eviction Policy**: Set `maxmemory-policy allkeys-lru` or `volatile-lru`.
- **Persistence**: RDB/AOF are optional for cache, but recommended if warming is expensive.

## 3. Distributed Invalidation

When using `TieredCacheBackend` or multiple instances with local cache, enable distributed invalidation to keep caches in sync.

```python
# Automatically handled by RedisCacheBackend and TieredCacheBackend
# when using delete() or clear()
cache.delete("https://api.example.com/resource")
```

This publishes an invalidation message via Redis Pub/Sub, clearing the key from all other instances' L1 memory cache.

## 4. Health Checks

Implement readiness/liveness probes using the `health_check()` method.

```python
@app.route("/health")
def health():
    if not cache.backend.health_check():
        return "Cache Down", 503
    return "OK", 200
```

## 5. Error Handling

Configure `serve_stale_on_error` to improve resilience. If the upstream API fails, the cache can serve the last known good response.

```python
config = CacheConfig(
    serve_stale_on_error=True,
    max_stale_age_seconds=86400  # Serve stale for up to 24 hours
)
```

## 6. Security

- **Vary Headers**: Use `vary_cookies` and `vary_user_agent` carefully.
- **Sensitive Data**: Avoid caching endpoints with PII or use `exclude_patterns`.
- **Redis Auth**: Always use password/ACLs for Redis in production.

```python
RedisCacheBackend(redis_url="redis://:password@host:6379/0")
```
