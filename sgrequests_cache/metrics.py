from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Dummy metric class for fallback
class DummyMetric:
    def __init__(self, *args, **kwargs): pass
    def inc(self, *args, **kwargs): pass
    def set(self, *args, **kwargs): pass
    def observe(self, *args, **kwargs): pass
    def labels(self, *args, **kwargs): return self

try:
    from prometheus_client import Counter, Gauge, Histogram
    HAS_PROMETHEUS = True
except ImportError:
    HAS_PROMETHEUS = False
    # Use dummy classes if prometheus_client is not installed
    Counter = Gauge = Histogram = DummyMetric  # type: ignore


class CacheMetrics:
    """Prometheus metrics for cache operations."""
    
    # Class-level cache for metrics to avoid duplication
    _metrics_cache: Dict[str, Any] = {}
    
    def __init__(self, namespace: str = "default"):
        self.namespace = namespace
        
        # Use cached metrics if available, otherwise create new ones
        cache_key = f"metrics_{namespace}"
        
        if cache_key in self._metrics_cache:
            cached = self._metrics_cache[cache_key]
            self.hits = cached['hits']
            self.misses = cached['misses']
            self.errors = cached['errors']
            self.latency = cached['latency']
            self.writes = cached['writes']
            self.bytes_saved = cached['bytes_saved']
        else:
            # Define metrics
            try:
                self.hits = Counter(
                    'sgcache_hits_total',
                    'Total cache hits',
                    ['namespace', 'status']
                )
                self.misses = Counter(
                    'sgcache_misses_total',
                    'Total cache misses',
                    ['namespace']
                )
                self.errors = Counter(
                    'sgcache_errors_total',
                    'Total cache errors',
                    ['namespace', 'type']
                )
                self.latency = Histogram(
                    'sgcache_latency_seconds',
                    'Cache operation latency',
                    ['namespace', 'operation']
                )
                self.writes = Counter(
                    'sgcache_writes_total',
                    'Total cache writes',
                    ['namespace']
                )
                self.bytes_saved = Counter(
                    'sgcache_bytes_saved_total',
                    'Total bytes served from cache',
                    ['namespace']
                )
                
                # Cache the metrics
                self._metrics_cache[cache_key] = {
                    'hits': self.hits,
                    'misses': self.misses,
                    'errors': self.errors,
                    'latency': self.latency,
                    'writes': self.writes,
                    'bytes_saved': self.bytes_saved,
                }
            except Exception as e:
                logger.warning(f"Failed to create prometheus metrics: {e}. Using dummy metrics.")
                # Fall back to dummy metrics
                self.hits = DummyMetric()
                self.misses = DummyMetric()
                self.errors = DummyMetric()
                self.latency = DummyMetric()
                self.writes = DummyMetric()
                self.bytes_saved = DummyMetric()

    def record_hit(self, status_code: int, bytes_saved: int) -> None:
        if not HAS_PROMETHEUS: return
        self.hits.labels(namespace=self.namespace, status=str(status_code)).inc()
        self.bytes_saved.labels(namespace=self.namespace).inc(bytes_saved)

    def record_miss(self) -> None:
        if not HAS_PROMETHEUS: return
        self.misses.labels(namespace=self.namespace).inc()

    def record_error(self, error_type: str) -> None:
        if not HAS_PROMETHEUS: return
        self.errors.labels(namespace=self.namespace, type=error_type).inc()

    def record_write(self) -> None:
        if not HAS_PROMETHEUS: return
        self.writes.labels(namespace=self.namespace).inc()

    def observe_latency(self, operation: str, seconds: float) -> None:
        if not HAS_PROMETHEUS: return
        self.latency.labels(namespace=self.namespace, operation=operation).observe(seconds)
