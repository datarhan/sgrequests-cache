from __future__ import annotations

import fnmatch
import re
from typing import List


class URLMatcher:
    """URL pattern matcher for selective caching."""
    
    def __init__(self, include_patterns: List[str] = None, exclude_patterns: List[str] = None):
        """
        Initialize URL matcher with include/exclude patterns.
        
        Patterns support glob-style wildcards:
        - * matches any characters
        - ? matches single character
        - [abc] matches any character in brackets
        
        Examples:
        - "*/api/*" matches any URL with /api/ in path
        - "https://example.com/*" matches all URLs on example.com
        - "*/products/*/details" matches product detail pages
        
        Args:
            include_patterns: List of patterns to include (cache). Empty = include all.
            exclude_patterns: List of patterns to exclude (don't cache). Takes precedence.
        """
        self.include_patterns = include_patterns or []
        self.exclude_patterns = exclude_patterns or []
        
        # Compile patterns to regex for performance
        self.include_regex = [self._compile_pattern(p) for p in self.include_patterns]
        self.exclude_regex = [self._compile_pattern(p) for p in self.exclude_patterns]
    
    def should_cache(self, url: str) -> bool:
        """
        Determine if URL should be cached based on patterns.
        
        Logic:
        1. If URL matches any exclude pattern -> don't cache
        2. If no include patterns specified -> cache (except excluded)
        3. If URL matches any include pattern -> cache
        4. Otherwise -> don't cache
        
        Args:
            url: URL to check
            
        Returns:
            True if URL should be cached, False otherwise
        """
        # Exclude takes precedence
        if any(pattern.match(url) for pattern in self.exclude_regex):
            return False
        
        # If no include patterns specified, cache all (except excluded)
        if not self.include_regex:
            return True
        
        # Check if matches any include pattern
        return any(pattern.match(url) for pattern in self.include_regex)
    
    def _compile_pattern(self, pattern: str) -> re.Pattern:
        """
        Convert glob-style pattern to compiled regex.
        
        Args:
            pattern: Glob-style pattern
            
        Returns:
            Compiled regex pattern
        """
        # fnmatch.translate converts glob to regex
        regex = fnmatch.translate(pattern)
        return re.compile(regex)
