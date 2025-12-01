from __future__ import annotations

import gzip
import io
import logging
import time
from typing import Any, Dict, Optional, Tuple

import httpx
import msgpack

logger = logging.getLogger(__name__)

# Optional compression libraries
try:
    import lz4.frame
    HAS_LZ4 = True
except ImportError:
    HAS_LZ4 = False

try:
    import zstandard as zstd
    HAS_ZSTD = True
except ImportError:
    HAS_ZSTD = False


def _gzip_compress(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(data)
    return buf.getvalue()


def _gzip_decompress(data: bytes) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as gz:
        return gz.read()


def _lz4_compress(data: bytes) -> bytes:
    if not HAS_LZ4:
        raise ImportError("lz4 not installed")
    return lz4.frame.compress(data)


def _lz4_decompress(data: bytes) -> bytes:
    if not HAS_LZ4:
        raise ImportError("lz4 not installed")
    return lz4.frame.decompress(data)


def _zstd_compress(data: bytes) -> bytes:
    if not HAS_ZSTD:
        raise ImportError("zstandard not installed")
    cctx = zstd.ZstdCompressor()
    return cctx.compress(data)


def _zstd_decompress(data: bytes) -> bytes:
    if not HAS_ZSTD:
        raise ImportError("zstandard not installed")
    dctx = zstd.ZstdDecompressor()
    return dctx.decompress(data)


COMPRESSORS = {
    "gzip": (_gzip_compress, _gzip_decompress),
    "lz4": (_lz4_compress, _lz4_decompress),
    "zstd": (_zstd_compress, _zstd_decompress),
    "none": (lambda x: x, lambda x: x),
}


def serialize_response(resp: httpx.Response, compression: str = "gzip") -> bytes:
    """Serialize an httpx.Response into a compact binary blob.

    Stores minimal fields needed to reconstruct an equivalent Response.
    Body is compressed to reduce cache size.
    """
    headers: Dict[str, str] = {
        k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
        for k, v in resp.headers.items()
    }
    
    # Remove headers that can cause issues with cached responses
    # content-encoding: The body in resp.content is already decoded by httpx
    # content-length: May not match after caching
    headers.pop('content-encoding', None)
    headers.pop('content-length', None)
    
    compress_fn = COMPRESSORS.get(compression, COMPRESSORS["gzip"])[0]
    
    payload: Dict[str, Any] = {
        "status": resp.status_code,
        "url": str(resp.request.url if resp.request else resp.url),
        "http_version": getattr(resp, "http_version", "HTTP/1.1"),
        "reason": resp.reason_phrase,
        "headers": headers,
        "encoding": resp.encoding,
        "cached_at": time.time(),
        "compression": compression,
        "body_compressed": compress_fn(resp.content),
    }
    return msgpack.packb(payload, use_bin_type=True)


def deserialize_response(data: bytes) -> Tuple[httpx.Response, float]:
    """Reconstruct an httpx.Response from the serialized blob.
    
    Returns:
        Tuple of (response, cached_at_timestamp)
    """
    payload: Dict[str, Any] = msgpack.unpackb(data, raw=False)
    
    # Handle legacy format (body_gzip) vs new format (body_compressed + compression)
    if "body_compressed" in payload:
        compression = payload.get("compression", "gzip")
        decompress_fn = COMPRESSORS.get(compression, COMPRESSORS["gzip"])[1]
        body = decompress_fn(payload["body_compressed"])
    else:
        # Legacy fallback
        body = _gzip_decompress(payload["body_gzip"])

    request = httpx.Request("GET", payload["url"])  # method is not critical for cached body
    response = httpx.Response(
        status_code=int(payload["status"]),
        request=request,
        headers=payload.get("headers", {}),
        content=body,
    )
    # Set optional attributes when available
    if payload.get("encoding"):
        response.encoding = payload["encoding"]
        
    cached_at = payload.get("cached_at", 0.0)
    return response, cached_at
