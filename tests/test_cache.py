from __future__ import annotations

import threading
import time
from typing import Any

import httpx
import pytest

from sgrequests_cache import (
    CachedSgRequests,
    CacheConfig,
    CircuitBreaker,
    CircuitBreakerOpenError,
    MemoryCacheBackend,
    RequestDeduplicator,
    TieredCacheBackend,
    URLMatcher,
)


class DummyHttp:
    def __init__(self, status_code: int = 200, delay: float = 0) -> None:
        self.calls: int = 0
        self.status_code = status_code
        self.delay = delay

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self.delay:
            time.sleep(self.delay)
        self.calls += 1
        return httpx.Response(
            self.status_code, 
            request=httpx.Request(method, url), 
            content=f"ok-{self.calls}".encode()
        )


@pytest.fixture
def backend() -> MemoryCacheBackend:
    return MemoryCacheBackend()


# ==================== Original Tests ====================

def test_get_cached_roundtrip(backend: MemoryCacheBackend) -> None:
    http = DummyHttp()
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t", ttl_seconds=60))

    r1 = cache.get("https://example.com/a")
    assert r1.text.startswith("ok-1")
    r2 = cache.get("https://example.com/a")
    assert r2.text.startswith("ok-1")  # cached
    assert http.calls == 1


def test_post_variance_by_body(backend: MemoryCacheBackend) -> None:
    http = DummyHttp()
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t", ttl_seconds=60))

    r1 = cache.post("https://example.com/p", data={"x": 1})
    r2 = cache.post("https://example.com/p", data={"x": 2})
    r3 = cache.post("https://example.com/p", data={"x": 1})
    assert r1.text == r3.text
    assert r1.text != r2.text
    assert http.calls == 2


def test_force_refresh_bypasses_cache(backend: MemoryCacheBackend) -> None:
    http = DummyHttp()
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t", ttl_seconds=60))

    r1 = cache.get("https://example.com/f")
    r2 = cache.get("https://example.com/f", force_refresh=True)
    assert r1.text != r2.text
    assert http.calls == 2


def test_json_body_variance(backend: MemoryCacheBackend) -> None:
    http = DummyHttp()
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t", ttl_seconds=60))

    r1 = cache.post("https://example.com/j", json={"foo": "bar"})
    r2 = cache.post("https://example.com/j", json={"foo": "baz"})
    r3 = cache.post("https://example.com/j", json={"foo": "bar"})
    
    assert r1.text == r3.text
    assert r1.text != r2.text
    assert http.calls == 2


def test_4xx_errors_not_cached(backend: MemoryCacheBackend) -> None:
    """CRITICAL: 4xx errors should NEVER be cached."""
    http = DummyHttp(status_code=404)
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t", ttl_seconds=60))

    r1 = cache.get("https://example.com/notfound")
    r2 = cache.get("https://example.com/notfound")
    
    assert r1.status_code == 404
    assert r2.status_code == 404
    assert http.calls == 2


def test_5xx_errors_not_cached(backend: MemoryCacheBackend) -> None:
    """CRITICAL: 5xx errors should NEVER be cached."""
    http = DummyHttp(status_code=500)
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t", ttl_seconds=60))

    r1 = cache.get("https://example.com/error")
    r2 = cache.get("https://example.com/error")
    
    assert r1.status_code == 500
    assert r2.status_code == 500
    assert http.calls == 2


def test_201_created_is_cached(backend: MemoryCacheBackend) -> None:
    """201 Created should be cached (it's a 2xx success)."""
    http = DummyHttp(status_code=201)
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t", ttl_seconds=60))

    r1 = cache.post("https://example.com/create", data={"x": 1})
    r2 = cache.post("https://example.com/create", data={"x": 1})
    
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert http.calls == 1


def test_204_no_content_is_cached() -> None:
    """Test that 204 No Content responses are NOT cached (per best practice)."""
    backend = MemoryCacheBackend()
    http = DummyHttp(status_code=204)
    cache = CachedSgRequests(http, backend)

    cache.get("https://example.com")
    assert http.calls == 1  # First request

    cache.get("https://example.com")
    assert http.calls == 2  # Second request - NOT cached (204 should not be cached).


def test_custom_cacheable_status_codes(backend: MemoryCacheBackend) -> None:
    """Test that custom cacheable status codes work."""
    http = DummyHttp(status_code=404)
    config = CacheConfig(namespace="t", ttl_seconds=60, cacheable_status_codes={404})
    cache = CachedSgRequests(http, backend, config)

    r1 = cache.get("https://example.com/notfound")
    r2 = cache.get("https://example.com/notfound")
    
    assert r1.status_code == 404
    assert r2.status_code == 404
    assert http.calls == 1


def test_cache_read_false_bypasses_cache(backend: MemoryCacheBackend) -> None:
    """Test that cache_read=False bypasses cache reading."""
    http = DummyHttp()
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t", ttl_seconds=60))

    r1 = cache.get("https://example.com/x")
    r2 = cache.get("https://example.com/x", cache_read=False)
    
    assert r1.text.startswith("ok-1")
    assert r2.text.startswith("ok-2")
    assert http.calls == 2


def test_cache_write_false_prevents_caching(backend: MemoryCacheBackend) -> None:
    """Test that cache_write=False prevents writing to cache."""
    http = DummyHttp()
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t", ttl_seconds=60))

    r1 = cache.get("https://example.com/y", cache_write=False)
    r2 = cache.get("https://example.com/y")
    
    assert r1.text.startswith("ok-1")
    assert r2.text.startswith("ok-2")
    assert http.calls == 2


def test_cache_by_default_false(backend: MemoryCacheBackend) -> None:
    """Test opt-in caching."""
    http = DummyHttp()
    config = CacheConfig(namespace="t", ttl_seconds=60, cache_by_default=False)
    cache = CachedSgRequests(http, backend, config)

    r1 = cache.get("https://example.com/opt-in")
    r2 = cache.get("https://example.com/opt-in")
    assert http.calls == 2

    r3 = cache.get("https://example.com/cached", cache_write=True, cache_read=True)
    r4 = cache.get("https://example.com/cached", cache_write=True, cache_read=True)
    assert r3.text == r4.text
    assert http.calls == 3


# ==================== New Feature Tests ====================

def test_cache_statistics(backend: MemoryCacheBackend) -> None:
    """Test cache statistics tracking."""
    http = DummyHttp()
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t"))

    # Initial stats
    stats = cache.get_stats()
    assert stats.hits == 0
    assert stats.misses == 0
    assert stats.total_requests == 0

    # First request - miss
    cache.get("https://example.com/stats")
    stats = cache.get_stats()
    assert stats.misses == 1
    assert stats.total_requests == 1
    assert stats.hit_rate == 0.0

    # Second request - hit
    cache.get("https://example.com/stats")
    stats = cache.get_stats()
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.total_requests == 2
    assert stats.hit_rate == 0.5


def test_url_pattern_matching(backend: MemoryCacheBackend) -> None:
    """Test URL pattern matching for selective caching."""
    http = DummyHttp()
    config = CacheConfig(
        namespace="t",
        cache_patterns=["*/api/*", "*/products/*"],
        exclude_patterns=["*/admin/*"]
    )
    cache = CachedSgRequests(http, backend, config)

    # Should cache (matches pattern)
    r1 = cache.get("https://example.com/api/users")
    r2 = cache.get("https://example.com/api/users")
    assert http.calls == 1  # Cached

    # Should NOT cache (doesn't match pattern)
    r3 = cache.get("https://example.com/other/page")
    r4 = cache.get("https://example.com/other/page")
    assert http.calls == 3  # Not cached

    # Should NOT cache (excluded)
    r5 = cache.get("https://example.com/admin/users")
    r6 = cache.get("https://example.com/admin/users")
    assert http.calls == 5  # Not cached


def test_url_matcher_standalone() -> None:
    """Test URLMatcher class directly."""
    matcher = URLMatcher(
        include_patterns=["*/api/*"],
        exclude_patterns=["*/api/admin/*"]
    )

    assert matcher.should_cache("https://example.com/api/users") == True
    assert matcher.should_cache("https://example.com/api/admin/users") == False
    assert matcher.should_cache("https://example.com/other") == False


def test_request_deduplication(backend: MemoryCacheBackend) -> None:
    """Test that concurrent requests are deduplicated."""
    http = DummyHttp(delay=0.05)  # Small delay
    config = CacheConfig(namespace="t", enable_request_deduplication=True)
    cache = CachedSgRequests(http, backend, config)

    results = []
    errors = []
    
    def make_request():
        try:
            r = cache.get("https://example.com/slow")
            results.append(r.text)
        except Exception as e:
            errors.append(e)

    # Make 3 concurrent requests
    threads = [threading.Thread(target=make_request) for _ in range(3)]
    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2)  # Add timeout
    elapsed = time.time() - start

    # Check no errors
    assert len(errors) == 0, f"Errors occurred: {errors}"
    
    # All should get same response
    assert len(results) == 3
    assert len(set(results)) == 1
    
    # Only one backend call should have been made
    assert http.calls == 1
    
    # Should take roughly the time of one request (not 3)
    assert elapsed < 0.15  # 3 * 0.05 would be 0.15, but should be ~0.05


def test_circuit_breaker_standalone() -> None:
    """Test CircuitBreaker class directly."""
    cb = CircuitBreaker(threshold=3, timeout=1)

    # Normal operation
    assert cb.call(lambda: "ok") == "ok"

    # Simulate failures
    for _ in range(3):
        try:
            cb.call(lambda: (_ for _ in ()).throw(Exception("fail")))
        except Exception:
            pass

    # Circuit should be open
    with pytest.raises(CircuitBreakerOpenError):
        cb.call(lambda: "ok")

    # Wait for timeout
    time.sleep(1.1)

    # Should transition to half-open and allow test
    assert cb.call(lambda: "ok") == "ok"
    assert cb.get_state() == "closed"


def test_cache_versioning(backend: MemoryCacheBackend) -> None:
    """Test cache versioning invalidates old cache."""
    http = DummyHttp()
    
    # Version 1
    config_v1 = CacheConfig(namespace="t", cache_version="v1")
    cache_v1 = CachedSgRequests(http, backend, config_v1)
    r1 = cache_v1.get("https://example.com/versioned")
    assert http.calls == 1

    # Version 2 - should not use v1 cache
    config_v2 = CacheConfig(namespace="t", cache_version="v2")
    cache_v2 = CachedSgRequests(http, backend, config_v2)
    r2 = cache_v2.get("https://example.com/versioned")
    assert http.calls == 2  # New request


def test_custom_key_builder(backend: MemoryCacheBackend) -> None:
    """Test custom key builder function."""
    http = DummyHttp()
    
    def custom_builder(method, url, content, headers, config):
        # Simple key: just method + url
        return f"{method}:{url}"
    
    config = CacheConfig(namespace="t", key_builder=custom_builder)
    cache = CachedSgRequests(http, backend, config)

    r1 = cache.get("https://example.com/custom")
    r2 = cache.get("https://example.com/custom")
    assert http.calls == 1


def test_tiered_cache_backend() -> None:
    """Test tiered cache backend (L1/L2)."""
    l1 = MemoryCacheBackend()
    l2 = MemoryCacheBackend()
    tiered = TieredCacheBackend(l1=l1, l2=l2)

    # Write to tiered cache
    tiered.set("key1", b"value1", ttl_seconds=3600)

    # Should be in both tiers
    assert l1.get("key1") == b"value1"
    assert l2.get("key1") == b"value1"

    # Clear L1
    l1._data.clear()

    # Read should promote from L2 to L1
    assert tiered.get("key1") == b"value1"
    assert l1.get("key1") == b"value1"  # Promoted


def test_cache_warming(backend: MemoryCacheBackend) -> None:
    """Test cache warming/preloading."""
    http = DummyHttp()
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t"))

    # Warm cache
    requests = [
        ("GET", "https://example.com/page1", None),
        ("GET", "https://example.com/page2", None),
        ("POST", "https://example.com/api", {"x": 1}),
    ]
    results = cache.warm_cache(requests, concurrency=2)

    # All should succeed
    assert all(results.values())
    assert http.calls == 3

    # Subsequent requests should be cached
    cache.get("https://example.com/page1")
    cache.get("https://example.com/page2")
    assert http.calls == 3  # No new calls


def test_deduplicator_standalone() -> None:
    """Test RequestDeduplicator class directly."""
    dedup = RequestDeduplicator()
    call_count = 0

    def slow_fetch():
        nonlocal call_count
        time.sleep(0.1)
        call_count += 1
        return f"result-{call_count}"

    results = []
    
    def make_request():
        result = dedup.get_or_fetch("key1", slow_fetch)
        results.append(result)

    # Make 5 concurrent requests
    threads = [threading.Thread(target=make_request) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # All should get same result
    assert len(set(results)) == 1
    # Only one call should have been made
    assert call_count == 1
