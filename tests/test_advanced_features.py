from __future__ import annotations

import time
import threading
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from sgrequests_cache import (
    CachedSgRequests,
    CacheConfig,
    MemoryCacheBackend,
    RedisCacheBackend,
    TieredCacheBackend,
)
from sgrequests_cache.serializers import serialize_response, deserialize_response


class DummyHttp:
    def __init__(self, status_code: int = 200, delay: float = 0) -> None:
        self.calls: int = 0
        self.status_code = status_code
        self.delay = delay
        self.last_url = ""

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self.delay:
            time.sleep(self.delay)
        self.calls += 1
        self.last_url = url
        return httpx.Response(
            self.status_code, 
            request=httpx.Request(method, url), 
            content=f"ok-{self.calls}".encode()
        )


@pytest.fixture
def backend() -> MemoryCacheBackend:
    return MemoryCacheBackend()


def test_stale_while_revalidate(backend: MemoryCacheBackend) -> None:
    """Test Stale-While-Revalidate behavior."""
    http = DummyHttp()
    config = CacheConfig(
        namespace="t",
        ttl_seconds=1,  # Short TTL
        stale_while_revalidate_seconds=5  # Longer SWR window
    )
    cache = CachedSgRequests(http, backend, config)

    # 1. Initial request - miss
    r1 = cache.get("https://example.com/swr")
    assert r1.text == "ok-1"
    assert http.calls == 1

    # 2. Immediate request - hit (fresh)
    r2 = cache.get("https://example.com/swr")
    assert r2.text == "ok-1"
    assert http.calls == 1

    # 3. Wait for TTL to expire (1s) but within SWR (5s)
    time.sleep(1.1)

    # 4. Request - should get stale response immediately AND trigger background refresh
    r3 = cache.get("https://example.com/swr")
    assert r3.text == "ok-1"  # Stale response
    
    # Wait for background thread to complete
    time.sleep(0.5)
    
    # Backend should have been called again (background refresh)
    assert http.calls == 2

    # 5. Request again - should get NEW response (refreshed)
    r4 = cache.get("https://example.com/swr")
    assert r4.text == "ok-2"  # New response
    assert http.calls == 2  # No new call needed


def test_compression_gzip(backend: MemoryCacheBackend) -> None:
    """Test GZIP compression."""
    http = DummyHttp()
    config = CacheConfig(namespace="t", compression="gzip")
    cache = CachedSgRequests(http, backend, config)

    # Cache a large response
    large_content = b"x" * 1000
    # Add content-type to ensure it's cacheable
    resp = httpx.Response(
        200, 
        content=large_content, 
        headers={"content-type": "text/plain"},
        request=httpx.Request("GET", "https://example.com/gzip")
    )
    with patch.object(http, 'request', return_value=resp):
        cache.get("https://example.com/gzip")
    
    # Check backend storage
    # We need to find the key. Since we don't know the exact key hash, we iterate.
    keys = list(backend._data.keys())
    assert len(keys) == 1
    value_tuple = backend._data[keys[0]]
    blob, _ = value_tuple  # Unpack (value, expiry_timestamp)
    
    # Blob should be smaller than content due to compression + overhead
    # 1000 bytes of 'x' compresses very well
    assert len(blob) < 1000
    
    # Read back
    r2 = cache.get("https://example.com/gzip")
    assert r2.content == large_content


def test_compression_none(backend: MemoryCacheBackend) -> None:
    """Test no compression."""
    http = DummyHttp()
    config = CacheConfig(namespace="t", compression="none")
    cache = CachedSgRequests(http, backend, config)

    # Cache a response
    content = b"x" * 100
    resp = httpx.Response(
        200, 
        content=content, 
        headers={"content-type": "text/plain"},
        request=httpx.Request("GET", "https://example.com/none")
    )
    with patch.object(http, 'request', return_value=resp):
        cache.get("https://example.com/none")
    
    keys = list(backend._data.keys())
    value_tuple = backend._data[keys[0]]
    blob, _ = value_tuple  # Unpack (value, expiry_timestamp)
    
    # Blob should be larger than content (overhead)
    assert len(blob) > 100


def test_metrics_calls(backend: MemoryCacheBackend) -> None:
    """Test that metrics are recorded."""
    http = DummyHttp()
    cache = CachedSgRequests(http, backend, CacheConfig(namespace="t"))
    
    # Mock the metrics object
    cache.metrics = MagicMock()
    
    # Miss
    cache.get("https://example.com/m")
    cache.metrics.record_miss.assert_called_once()
    cache.metrics.record_write.assert_called_once()
    
    # Hit
    cache.get("https://example.com/m")
    cache.metrics.record_hit.assert_called_once()


def test_health_checks() -> None:
    """Test health check methods."""
    mem = MemoryCacheBackend()
    assert mem.health_check() is True
    
    tiered = TieredCacheBackend(mem, mem)
    assert tiered.health_check() is True
    
    # Redis health check (mocked)
    # Patch the redis module where it is imported in the backend module
    with patch("sgrequests_cache.backends.redis.redis") as mock_redis_module:
        mock_client = MagicMock()
        mock_redis_module.from_url.return_value = mock_client
        mock_client.ping.return_value = True
        
        redis_backend = RedisCacheBackend()
        assert redis_backend.health_check() is True
        
        mock_client.ping.side_effect = Exception("Down")
        assert redis_backend.health_check() is False


def test_distributed_invalidation_integration() -> None:
    """Test that TieredCacheBackend subscribes to invalidation."""
    l1 = MagicMock(spec=MemoryCacheBackend)
    l2 = MagicMock(spec=RedisCacheBackend)
    
    # Mock l2 having invalidation methods
    l2.start_invalidation_listener = MagicMock()
    l2.publish_invalidation = MagicMock()
    
    tiered = TieredCacheBackend(l1, l2)
    
    # Check subscription
    l2.start_invalidation_listener.assert_called_once()
    
    # Get the callback passed to listener
    callback = l2.start_invalidation_listener.call_args[0][0]
    
    # Simulate invalidation message
    callback("some-key")
    l1.delete.assert_called_with("some-key")
    
    callback("*")
    l1.clear.assert_called_once()
    
    # Check publication on set/delete
    tiered.set("k", b"v", 60)
    l2.publish_invalidation.assert_called_with("k")
    
    tiered.delete("k2")
    l2.publish_invalidation.assert_called_with("k2")
