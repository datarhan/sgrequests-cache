# Cache Statistics & Metrics

SgRequests Cache provides comprehensive observability into cache performance through built-in statistics and Prometheus metrics integration.

## Built-in Statistics

Access real-time statistics programmatically using `cache.get_stats()`:

```python
stats = cache.get_stats()
print(f"Hit Rate: {stats.hit_rate:.2%}")
print(f"Hits: {stats.hits}")
print(f"Misses: {stats.misses}")
print(f"Bytes Saved: {stats.bytes_saved}")
```

### Available Metrics

| Metric | Description |
|--------|-------------|
| `hits` | Number of requests served from cache |
| `misses` | Number of requests fetched from backend |
| `errors` | Number of cache read/write errors |
| `writes` | Number of new responses written to cache |
| `bytes_saved` | Total bytes served from cache (estimated) |
| `uptime_seconds` | Time since cache initialization |

## Prometheus Integration

Enable Prometheus metrics to export cache telemetry to your monitoring system.

### Configuration

```python
from sgrequests_cache import CacheConfig, CachedSgRequests

config = CacheConfig(
    namespace="my_app",
    # Metrics are enabled automatically if prometheus_client is installed
)
```

### Exported Metrics

| Metric Name | Type | Labels | Description |
|-------------|------|--------|-------------|
| `sgcache_hits_total` | Counter | `namespace`, `status` | Total cache hits |
| `sgcache_misses_total` | Counter | `namespace` | Total cache misses |
| `sgcache_errors_total` | Counter | `namespace`, `type` | Total cache errors |
| `sgcache_writes_total` | Counter | `namespace` | Total cache writes |
| `sgcache_bytes_saved_total` | Counter | `namespace` | Total bytes served from cache |
| `sgcache_latency_seconds` | Histogram | `namespace`, `operation` | Cache operation latency |

### Grafana Dashboard

You can visualize these metrics in Grafana. Key panels to include:
- **Cache Hit Rate**: `rate(sgcache_hits_total[5m]) / (rate(sgcache_hits_total[5m]) + rate(sgcache_misses_total[5m]))`
- **Throughput**: `rate(sgcache_hits_total[5m]) + rate(sgcache_misses_total[5m])`
- **Latency**: `histogram_quantile(0.95, rate(sgcache_latency_seconds_bucket[5m]))`
