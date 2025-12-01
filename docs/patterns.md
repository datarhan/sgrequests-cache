# URL Pattern Matching

SgRequests Cache allows you to selectively cache requests based on URL patterns. This is useful for caching specific API endpoints while excluding others.

## Configuration

Use `cache_patterns` and `exclude_patterns` in `CacheConfig`:

```python
config = CacheConfig(
    cache_patterns=[
        "*/api/v1/products*",
        "*/static/*"
    ],
    exclude_patterns=[
        "*/api/v1/user/*",
        "*/auth/*"
    ]
)
```

## Pattern Syntax

Patterns use glob-style syntax (similar to shell wildcards):

| Symbol | Description | Example | Matches |
|--------|-------------|---------|---------|
| `*` | Matches everything | `*/api/*` | `http://host/api/users` |
| `?` | Matches any single character | `file?.txt` | `file1.txt`, `fileA.txt` |
| `[seq]` | Matches any character in seq | `[a-z]*` | `apple`, `banana` |
| `[!seq]` | Matches any character not in seq | `[!a]*` | `123`, `Banana` |

## Precedence Rules

1. **Exclusions take priority**: If a URL matches any pattern in `exclude_patterns`, it will **not** be cached, even if it also matches `cache_patterns`.
2. **Inclusions are additive**: If `cache_patterns` is provided, only URLs matching at least one pattern will be cached.
3. **Default behavior**: If `cache_patterns` is empty (default), **all** URLs are cached (unless excluded).

## Examples

### Cache Only Static Assets
```python
config = CacheConfig(
    cache_patterns=["*.jpg", "*.png", "*.css", "*.js"]
)
```

### Cache Everything Except Auth
```python
config = CacheConfig(
    exclude_patterns=["*/auth/*", "*/login", "*/logout"]
)
```

### Complex API Rules
Cache public data, exclude user-specific data:
```python
config = CacheConfig(
    cache_patterns=["*/api/public/*"],
    exclude_patterns=["*/api/public/user-specific/*"]
)
```
