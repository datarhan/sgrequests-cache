from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from .backends.base import CacheBackend
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from .deduplication import RequestDeduplicator
from .patterns import URLMatcher
from .serializers import deserialize_response, serialize_response
from .stats import CacheStats

logger = logging.getLogger(__name__)


def _hash_bytes(data: Optional[bytes]) -> str:
    if not data:
        return ""
    return hashlib.sha256(data).hexdigest()


def _sorted_query(url: httpx.URL) -> str:
    if not url.query:
        return ""
    params = httpx.QueryParams(url.query)
    return json.dumps(sorted(params.multi_items()), separators=(",", ":"))


def _calculate_adaptive_ttl(resp: httpx.Response, default_ttl: int, min_ttl: int, max_ttl: int) -> int:
    """Calculate TTL based on response headers (Cache-Control, Expires)."""
    # Check Cache-Control header
    cache_control = resp.headers.get("cache-control", "")
    if "max-age=" in cache_control:
        match = re.search(r"max-age=(\d+)", cache_control)
        if match:
            ttl = int(match.group(1))
            return max(min_ttl, min(ttl, max_ttl))
    
    # Check Expires header
    expires = resp.headers.get("expires")
    if expires:
        try:
            expires_dt = parsedate_to_datetime(expires)
            ttl = int((expires_dt - datetime.now(timezone.utc)).total_seconds())
            return max(min_ttl, min(ttl, max_ttl))
        except Exception:
            pass
    
    return default_ttl


@dataclass
class CacheConfig:
    namespace: str = os.environ.get("SGCACHE_NAMESPACE", "default")
    ttl_seconds: int = int(os.environ.get("SGCACHE_TTL", "86400"))
    max_bytes: int = int(os.environ.get("SGCACHE_MAX_BYTES", str(2 * 1024 * 1024)))
    vary_user_agent: bool = os.environ.get("SGCACHE_VARY_UA", "false").lower() == "true"
    vary_cookies: bool = os.environ.get("SGCACHE_VARY_COOKIES", "false").lower() == "true"
    enable_logging: bool = os.environ.get("SGCACHE_LOGGING", "false").lower() == "true"
    cache_by_default: bool = os.environ.get("SGCACHE_BY_DEFAULT", "true").lower() == "true"
    
    # Advanced features
    cache_version: str = "v1"
    cache_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)
    enable_request_deduplication: bool = True
    deduplication_timeout_seconds: int = 10  # Timeout for waiting on concurrent requests
    stale_while_revalidate_seconds: int = 0  # 0 = disabled
    serve_stale_on_error: bool = False
    max_stale_age_seconds: int = 86400  # 24 hours
    respect_cache_headers: bool = False
    min_ttl: int = 60
    max_ttl: int = 86400 * 7  # 7 days
    enable_circuit_breaker: bool = True
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 30
    key_builder: Optional[Callable] = None
    compression: str = "gzip"  # gzip, lz4, zstd, none
    
    # Only cache successful responses (2xx). Never cache errors (4xx, 5xx)
    cacheable_status_codes: set[int] = None  # type: ignore
    
    def __post_init__(self) -> None:
        if self.cacheable_status_codes is None:
            # Default to all 2xx status codes
            object.__setattr__(self, "cacheable_status_codes", set(range(200, 300)))
        
        # Validate configuration
        if self.ttl_seconds < 0:
            raise ValueError(f"ttl_seconds must be >= 0, got {self.ttl_seconds}")
        
        if self.max_bytes < 0:
            raise ValueError(f"max_bytes must be >= 0, got {self.max_bytes}")
        
        from .serializers import COMPRESSORS
        if self.compression not in COMPRESSORS:
            valid = ", ".join(COMPRESSORS.keys())
            raise ValueError(f"Invalid compression '{self.compression}'. Valid options: {valid}")
        
        if self.min_ttl < 0 or self.max_ttl < 0:
            raise ValueError(f"min_ttl and max_ttl must be >= 0")
        
        if self.min_ttl > self.max_ttl:
            raise ValueError(f"min_ttl ({self.min_ttl}) cannot be greater than max_ttl ({self.max_ttl})")
        
        if self.circuit_breaker_threshold < 1:
            raise ValueError(f"circuit_breaker_threshold must be >= 1")
        
        if self.deduplication_timeout_seconds < 1:
            raise ValueError(f"deduplication_timeout_seconds must be >= 1")


def _build_key(method: str, url: str, content: Optional[bytes], headers: Optional[Any], cfg: CacheConfig) -> str:
    u = httpx.URL(url)
    normalized = f"{u.scheme}://{u.host}{u.path}"
    q = _sorted_query(u)
    
    # Only hash body for methods that typically have one
    body_hash = ""
    if method in {"POST", "PUT", "PATCH"} and content:
        body_hash = _hash_bytes(content)
        
    # Optional variance
    ua = ""
    ck = ""
    if headers:
        # headers can be dict or httpx.Headers
        h_get = headers.get if hasattr(headers, "get") else headers.__getitem__
        if cfg.vary_user_agent:
            ua = h_get("user-agent", "") or ""
        if cfg.vary_cookies:
            ck = h_get("cookie", "") or ""

    parts = [
        f"ver:{cfg.cache_version}",
        f"ns:{cfg.namespace}",
        f"m:{method}",
        f"u:{normalized}",
        f"q:{q}",
        f"b:{body_hash}",
        f"ua:{ua}",
        f"ck:{ck}",
    ]
    return "|".join(parts)


def _is_cacheable(resp: httpx.Response, config: CacheConfig) -> bool:
    """Check if response should be cached."""
    # CRITICAL: Never cache error responses (4xx, 5xx)
    if resp.status_code not in config.cacheable_status_codes:
        return False
    
    # Don't cache 204 No Content
    if resp.status_code == 204:
        return False
    
    ctype = resp.headers.get("content-type", "").lower()
    if ctype:
        if not (ctype.startswith("text/") or ctype.startswith("application/json") or ctype.startswith("application/xhtml")):
            return False
    # If no content-type, allow caching for small bodies (conservative default)
    if len(resp.content) > config.max_bytes:
        return False
    return True


class CachedSgRequests:
    def __init__(self, inner: Any, backend: CacheBackend, config: Optional[CacheConfig] = None) -> None:
        self.inner = inner
        self.backend = backend
        self.config = config or CacheConfig()
        self.stats = CacheStats()
        
        # Initialize metrics
        from .metrics import CacheMetrics
        self.metrics = CacheMetrics(namespace=self.config.namespace)
        
        # Initialize URL matcher
        self.url_matcher = URLMatcher(
            include_patterns=self.config.cache_patterns,
            exclude_patterns=self.config.exclude_patterns
        )
        
        # Initialize request deduplicator
        self.deduplicator = RequestDeduplicator(
            timeout_seconds=self.config.deduplication_timeout_seconds
        ) if self.config.enable_request_deduplication else None
        
        # Initialize circuit breaker
        self.circuit_breaker = CircuitBreaker(
            threshold=self.config.circuit_breaker_threshold,
            timeout=self.config.circuit_breaker_timeout
        ) if self.config.enable_circuit_breaker else None

    def __enter__(self) -> "CachedSgRequests":
        if hasattr(self.inner, "__enter__"):
            self.inner.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        if hasattr(self.inner, "__exit__"):
            self.inner.__exit__(exc_type, exc, tb)

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self.stats

    def warm_cache(
        self,
        requests: List[Tuple[str, str, Optional[Dict]]],
        concurrency: int = 5
    ) -> Dict[str, bool]:
        """
        Preload cache with common requests.
        
        Args:
            requests: List of (method, url, data) tuples
            concurrency: Number of concurrent requests
            
        Returns:
            Dict mapping request to success status
        """
        results = {}
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {}
            for method, url, data in requests:
                future = executor.submit(self.request, method, url, data=data)
                futures[future] = (method, url)
            
            for future in as_completed(futures):
                method, url = futures[future]
                try:
                    future.result()
                    results[f"{method} {url}"] = True
                except Exception:
                    results[f"{method} {url}"] = False
        
        return results

    def request(self, method: str, url: str, *, cache_read: bool = None, cache_write: bool = None, force_refresh: bool = False, **kwargs: Any) -> httpx.Response:
        start_time = time.time()
        method = method.upper()
        
        # Apply defaults from config if not explicitly set
        if cache_read is None:
            cache_read = self.config.cache_by_default
        if cache_write is None:
            cache_write = self.config.cache_by_default
        
        # Check URL patterns
        if not self.url_matcher.should_cache(url):
            cache_read = False
            cache_write = False
        
        # Extract content for key generation
        content_bytes: Optional[bytes] = None
        if method in {"POST", "PUT", "PATCH"}:
            if "content" in kwargs and kwargs["content"]:
                content_bytes = kwargs["content"]
            elif "data" in kwargs or "json" in kwargs:
                 temp_req = httpx.Request(method, url, headers=kwargs.get("headers"), data=kwargs.get("data"), json=kwargs.get("json"))
                 content_bytes = temp_req.read()
        
        # Build cache key
        if self.config.key_builder:
            key = self.config.key_builder(method, url, content_bytes, kwargs.get("headers"), self.config)
        else:
            key = _build_key(method, url, content_bytes, kwargs.get("headers"), self.config)

        # Try cache read
        if cache_read and not force_refresh:
            blob = self._get_from_cache(key)
            if blob:
                try:
                    resp, cached_at = deserialize_response(blob)
                    age = time.time() - cached_at
                    ttl = self.config.ttl_seconds
                    
                    # Check if fresh
                    if age <= ttl:
                        self.stats.increment_hit(bytes_saved=len(blob))
                        self.metrics.record_hit(resp.status_code, len(blob))
                        self.metrics.observe_latency("hit", time.time() - start_time)
                        if self.config.enable_logging:
                            logger.info(
                                "cache_hit",
                                extra={
                                    "event": "cache_hit",
                                    "method": method,
                                    "url": url,
                                    "status_code": resp.status_code,
                                    "age": age,
                                    "namespace": self.config.namespace
                                }
                            )
                        return resp
                    
                    # Check if stale-while-revalidate
                    if self.config.stale_while_revalidate_seconds > 0 and age <= (ttl + self.config.stale_while_revalidate_seconds):
                        self.stats.increment_hit(bytes_saved=len(blob))
                        self.metrics.record_hit(resp.status_code, len(blob))
                        self.metrics.observe_latency("hit_stale", time.time() - start_time)
                        if self.config.enable_logging:
                            logger.info(
                                "cache_hit_stale",
                                extra={
                                    "event": "cache_hit_stale",
                                    "method": method,
                                    "url": url,
                                    "status_code": resp.status_code,
                                    "age": age,
                                    "namespace": self.config.namespace
                                }
                            )
                        
                        # Trigger background refresh
                        threading.Thread(
                            target=self._background_refresh,
                            args=(method, url, key, kwargs)
                        ).start()
                        
                        return resp
                        
                except Exception as e:
                    # Corrupt cache entry
                    self.stats.increment_error()
                    self.metrics.record_error("corruption")
                    if self.config.enable_logging:
                        logger.warning(f"Cache corruption for {method} {url}: {e}")
                    self.backend.delete(key)

        # Cache miss - fetch from backend
        self.stats.increment_miss()
        self.metrics.record_miss()
        if self.config.enable_logging:
            logger.debug(f"Cache MISS: {method} {url}")
        
        # Use deduplication if enabled AND caching is active AND not forcing refresh
        if self.deduplicator and (cache_read or cache_write) and not force_refresh:
            resp = self.deduplicator.get_or_fetch(
                key,
                lambda: self._fetch_response(method, url, **kwargs)
            )
        else:
            resp = self._fetch_response(method, url, **kwargs)

        # Write to cache
        if cache_write and _is_cacheable(resp, self.config):
            ttl = self.config.ttl_seconds
            if self.config.respect_cache_headers:
                ttl = _calculate_adaptive_ttl(
                    resp,
                    self.config.ttl_seconds,
                    self.config.min_ttl,
                    self.config.max_ttl
                )
            
            try:
                blob = serialize_response(resp, compression=self.config.compression)
                self._set_to_cache(key, blob, ttl)
                self.stats.increment_write(bytes_written=len(blob))
                self.metrics.record_write()
                if self.config.enable_logging:
                    logger.debug(f"Cached response: {method} {url} (status={resp.status_code}, ttl={ttl}s)")
            except Exception as e:
                self.stats.increment_error()
                self.metrics.record_error("write_failed")
                if self.config.enable_logging:
                    logger.error(f"Failed to cache {method} {url}: {e}")
        elif cache_write and self.config.enable_logging:
            logger.debug(f"Response not cacheable: {method} {url} (status={resp.status_code})")
        
        self.metrics.observe_latency("miss", time.time() - start_time)
        return resp

    def _background_refresh(self, method: str, url: str, key: str, kwargs: Any) -> None:
        """Refresh cache in background."""
        try:
            resp = self._fetch_response(method, url, **kwargs)
            if _is_cacheable(resp, self.config):
                ttl = self.config.ttl_seconds
                if self.config.respect_cache_headers:
                    ttl = _calculate_adaptive_ttl(
                        resp,
                        self.config.ttl_seconds,
                        self.config.min_ttl,
                        self.config.max_ttl
                    )
                blob = serialize_response(resp, compression=self.config.compression)
                self._set_to_cache(key, blob, ttl)
                if self.config.enable_logging:
                    logger.info(f"Background refresh success: {method} {url}")
        except Exception as e:
            if self.config.enable_logging:
                logger.error(f"Background refresh failed for {method} {url}: {e}")

    def _fetch_response(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Fetch response from backend with error handling."""
        try:
            return self.inner.request(method, url, **kwargs)
        except Exception as e:
            # Try to serve stale cache on error
            if self.config.serve_stale_on_error:
                # Build key to look for stale entry
                content_bytes: Optional[bytes] = None
                if method in {"POST", "PUT", "PATCH"}:
                    if "content" in kwargs and kwargs["content"]:
                        content_bytes = kwargs["content"]
                    elif "data" in kwargs or "json" in kwargs:
                        temp_req = httpx.Request(method, url, headers=kwargs.get("headers"), data=kwargs.get("data"), json=kwargs.get("json"))
                        content_bytes = temp_req.read()
                
                key = _build_key(method, url, content_bytes, kwargs.get("headers"), self.config)
                stale_blob = self.backend.get(key)
                
                if stale_blob:
                    try:
                        resp, cached_at = deserialize_response(stale_blob)
                        age = time.time() - cached_at
                        if age <= self.config.max_stale_age_seconds:
                            if self.config.enable_logging:
                                logger.warning(f"Serving stale cache due to error: {e}")
                            return resp
                    except Exception:
                        pass
            
            raise

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def head(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("HEAD", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def _get_from_cache(self, key: str) -> Optional[bytes]:
        """Get from cache with circuit breaker protection."""
        if self.circuit_breaker:
            try:
                return self.circuit_breaker.call(lambda: self.backend.get(key))
            except CircuitBreakerOpenError:
                if self.config.enable_logging:
                    logger.warning("Circuit breaker is OPEN, skipping cache read")
                return None
        else:
            return self.backend.get(key)

    def _set_to_cache(self, key: str, value: bytes, ttl: int) -> None:
        """Set to cache with circuit breaker protection."""
        if self.circuit_breaker:
            try:
                self.circuit_breaker.call(lambda: self.backend.set(key, value, ttl))
            except CircuitBreakerOpenError:
                if self.config.enable_logging:
                    logger.warning("Circuit breaker is OPEN, skipping cache write")
        else:
            self.backend.set(key, value, ttl)
