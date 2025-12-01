from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class DistributedInvalidator:
    """
    Handles distributed cache invalidation using Redis Pub/Sub.
    
    When one instance invalidates a cache pattern, it publishes a message.
    Other instances subscribe to these messages and invalidate their local caches (L1).
    """
    
    CHANNEL = "sgcache:invalidate"
    
    def __init__(self, redis_client: Any, callback: Callable[[str], None]):
        """
        Initialize invalidator.
        
        Args:
            redis_client: Redis client instance
            callback: Function to call when invalidation message is received
                      Signature: callback(pattern: str) -> None
        """
        self.redis = redis_client
        self.callback = callback
        self.pubsub = self.redis.pubsub()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        
    def start(self) -> None:
        """Start listening for invalidation messages."""
        if self._running:
            return
            
        try:
            self.pubsub.subscribe(**{self.CHANNEL: self._handle_message})
            self._thread = self.pubsub.run_in_thread(sleep_time=0.1, daemon=True)
            self._running = True
            logger.info("Started distributed invalidation listener")
        except Exception as e:
            logger.error(f"Failed to start invalidation listener: {e}")

    def stop(self) -> None:
        """Stop listening."""
        if self._thread:
            self._thread.stop()
            self._thread = None
        self.pubsub.close()
        self._running = False

    def invalidate(self, pattern: str) -> None:
        """Publish invalidation message to other instances."""
        try:
            self.redis.publish(self.CHANNEL, pattern)
        except Exception as e:
            logger.error(f"Failed to publish invalidation message: {e}")

    def _handle_message(self, message: dict) -> None:
        """Handle received invalidation message."""
        if message['type'] == 'message':
            pattern = message['data']
            if isinstance(pattern, bytes):
                pattern = pattern.decode()
            
            logger.debug(f"Received invalidation signal for pattern: {pattern}")
            try:
                self.callback(pattern)
            except Exception as e:
                logger.error(f"Error in invalidation callback: {e}")
