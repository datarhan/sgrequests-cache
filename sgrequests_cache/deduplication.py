from __future__ import annotations

import threading
from typing import Any, Callable, Dict, Optional


class RequestDeduplicator:
    """
    Deduplicates concurrent requests to the same resource.
    
    When multiple threads request the same resource simultaneously,
    only one request is made to the backend. Other threads wait
    for the result and receive the same response.
    
    This prevents "thundering herd" problems during cache misses.
    """
    
    def __init__(self, timeout_seconds: int = 10):
        """
        Initialize request deduplicator.
        
        Args:
            timeout_seconds: Maximum time to wait for in-flight request
        """
        self._in_flight: Dict[str, threading.Event] = {}
        self._results: Dict[str, Any] = {}
        self._errors: Dict[str, Optional[Exception]] = {}
        self._lock = threading.Lock()
        self._timeout = timeout_seconds
    
    def get_or_fetch(self, key: str, fetch_fn: Callable[[], Any]) -> Any:
        """
        Get result for key, either from in-flight request or by fetching.
        
        Args:
            key: Unique key for the request
            fetch_fn: Function to call if no in-flight request exists
            
        Returns:
            Result from fetch_fn
            
        Raises:
            Exception: If fetch_fn raised an exception
        """
        # Try to register as the fetcher
        event = None
        should_fetch = False
        
        with self._lock:
            if key not in self._in_flight:
                # We're the first - we'll fetch
                event = threading.Event()
                self._in_flight[key] = event
                should_fetch = True
            else:
                # Someone else is fetching - get their event
                event = self._in_flight[key]
        
        if should_fetch:
            # We're responsible for fetching
            try:
                result = fetch_fn()
                with self._lock:
                    self._results[key] = result
                    self._errors[key] = None
                    # Remove from in_flight immediately so new sequential requests start fresh
                    self._in_flight.pop(key, None)
                return result
            except Exception as e:
                with self._lock:
                    self._errors[key] = e
                    self._in_flight.pop(key, None)
                raise
            finally:
                # Signal completion for any waiters holding the event
                event.set()
                # Clean up results after a short delay to let waiters read them
                threading.Timer(0.05, lambda: self._cleanup(key)).start()
        else:
            # Wait for the fetcher to complete
            event.wait(timeout=self._timeout)
            
            with self._lock:
                # Check for error
                if key in self._errors and self._errors[key] is not None:
                    raise self._errors[key]
                
                # Return result
                if key in self._results:
                    return self._results[key]
                else:
                    # Timeout or other issue - fetch ourselves
                    return fetch_fn()
    
    def _cleanup(self, key: str) -> None:
        """Clean up cached result."""
        with self._lock:
            # _in_flight is already removed
            self._results.pop(key, None)
            self._errors.pop(key, None)
