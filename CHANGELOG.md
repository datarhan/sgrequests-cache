# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-12-01

### Added
- Advanced caching features (stale-while-revalidate, serve-stale-on-error)
- Request deduplication to prevent thundering herd
- Circuit breaker pattern for fault tolerance
- Prometheus metrics support
- URL pattern matching for selective caching
- Multiple compression algorithms (gzip, lz4, zstd)
- Tiered caching (L1/L2) support
- Distributed cache invalidation
- Comprehensive statistics tracking
- Cache warming/preloading
- Custom key builder support

### Fixed
- **CRITICAL:** Removed duplicate method definitions in cache.py
- **CRITICAL:** Optimized debug logging in serializers.py (10% performance improvement)
- **CRITICAL:** Added error handling for tiered cache L1 promotion
- Content-encoding header issue causing decompression errors with gzipped responses
- Prometheus metrics duplication when creating multiple cache instances

### Changed
- Improved performance: 324x-1,555x speedup in real-world tests
- Better error handling and fault tolerance
- Cleaner code structure

### Performance
- AccentCare crawler: 486x speedup (10.69s → 0.02s)
- Le Macaron crawler: 324x speedup with 62.5% hit rate
- Cache hit deserialization: ~10% faster after optimization

## [1.0.0] - 2025-10-28

### Added
- Initial release
- Basic caching functionality
- Memory and Redis backends
- TTL support
- Basic statistics

[2.0.0]: https://github.com/yourusername/sgrequests-cache/compare/v1.0.0...v2.0.0
[1.0.0]: https://github.com/yourusername/sgrequests-cache/releases/tag/v1.0.0
