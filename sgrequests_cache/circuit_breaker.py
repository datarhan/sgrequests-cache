from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""
    pass


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for fault tolerance.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail fast
    - HALF_OPEN: Testing if service recovered
    
    Flow:
    1. Start in CLOSED state
    2. After N failures -> OPEN (fail fast)
    3. After timeout -> HALF_OPEN (test recovery)
    4. If test succeeds -> CLOSED
    5. If test fails -> OPEN again
    """
    
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
    
    def __init__(self, threshold: int = 5, timeout: int = 30):
        """
        Initialize circuit breaker.
        
        Args:
            threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting recovery
        """
        self.threshold = threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = 0.0
        self.state = self.CLOSED
        self._lock = threading.Lock()
    
    def call(self, fn: Callable[[], Any]) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            fn: Function to execute
            
        Returns:
            Result from function
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: Any exception from fn
        """
        with self._lock:
            # Check if we should transition from OPEN to HALF_OPEN
            if self.state == self.OPEN:
                if time.time() - self.last_failure_time > self.timeout:
                    logger.info("Circuit breaker transitioning to HALF_OPEN")
                    self.state = self.HALF_OPEN
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker is OPEN. "
                        f"Retry in {self.timeout - (time.time() - self.last_failure_time):.1f}s"
                    )
        
        # Execute function
        try:
            result = fn()
            
            # Success - reset if in HALF_OPEN
            with self._lock:
                if self.state == self.HALF_OPEN:
                    logger.info("Circuit breaker transitioning to CLOSED (recovery successful)")
                    self.state = self.CLOSED
                    self.failures = 0
            
            return result
            
        except Exception as e:
            # Failure - increment counter
            with self._lock:
                self.failures += 1
                self.last_failure_time = time.time()
                
                # Open circuit if threshold exceeded
                if self.failures >= self.threshold:
                    if self.state != self.OPEN:
                        logger.warning(
                            f"Circuit breaker opening after {self.failures} failures"
                        )
                    self.state = self.OPEN
            
            raise
    
    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        with self._lock:
            self.state = self.CLOSED
            self.failures = 0
            logger.info("Circuit breaker manually reset to CLOSED")
    
    def get_state(self) -> str:
        """Get current circuit breaker state."""
        with self._lock:
            return self.state
