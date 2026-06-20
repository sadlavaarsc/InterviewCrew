"""
Session storage abstraction for InterviewCrew.
Supports Redis (production) and in-memory (dev/fallback) backends.
"""

import json
import time
from abc import ABC, abstractmethod
from typing import Optional

import redis as redis_lib

from interview_crew.config import settings


class SessionStore(ABC):
    """Abstract session storage interface."""

    @abstractmethod
    def save(self, session_id: str, state_json: str) -> None:
        """Save session state."""
        raise NotImplementedError

    @abstractmethod
    def load(self, session_id: str) -> Optional[str]:
        """Load session state. Returns None if not found."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, session_id: str) -> None:
        """Delete session state."""
        raise NotImplementedError

    @abstractmethod
    def list_active(self) -> list[str]:
        """List all active session IDs."""
        raise NotImplementedError

    @abstractmethod
    def cleanup_expired(self, max_age_seconds: int = 86400) -> int:
        """Remove sessions older than max_age_seconds. Returns count removed."""
        raise NotImplementedError


class MemorySessionStore(SessionStore):
    """In-memory session store (backward compatible)."""

    def __init__(self):
        self._data: dict[str, tuple[str, float]] = {}

    def save(self, session_id: str, state_json: str) -> None:
        self._data[session_id] = (state_json, time.time())

    def load(self, session_id: str) -> Optional[str]:
        item = self._data.get(session_id)
        return item[0] if item else None

    def delete(self, session_id: str) -> None:
        self._data.pop(session_id, None)

    def list_active(self) -> list[str]:
        return list(self._data.keys())

    def cleanup_expired(self, max_age_seconds: int = 86400) -> int:
        now = time.time()
        expired = [
            sid for sid, (_, created_at) in self._data.items()
            if now - created_at > max_age_seconds
        ]
        for sid in expired:
            self._data.pop(sid, None)
        return len(expired)


class RedisSessionStore(SessionStore):
    """Redis-backed session store with TTL."""

    TTL_SECONDS = 86400  # 24 hours

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        import redis
        self._client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        self._prefix = "interview_crew:session:"

    def save(self, session_id: str, state_json: str) -> None:
        key = f"{self._prefix}{session_id}"
        self._client.setex(key, self.TTL_SECONDS, state_json)

    def load(self, session_id: str) -> Optional[str]:
        key = f"{self._prefix}{session_id}"
        return self._client.get(key)

    def delete(self, session_id: str) -> None:
        key = f"{self._prefix}{session_id}"
        self._client.delete(key)

    def list_active(self) -> list[str]:
        pattern = f"{self._prefix}*"
        keys = self._client.keys(pattern)
        return [k.replace(self._prefix, "") for k in keys]

    def cleanup_expired(self, max_age_seconds: int = 86400) -> int:
        # Redis uses TTL per key; no manual cleanup required.
        return 0


# Singleton instance
_session_store_instance: Optional[SessionStore] = None


def get_session_store() -> SessionStore:
    """Get or create the global session store instance.

    Tries Redis first, falls back to memory if Redis is unavailable.
    """
    global _session_store_instance
    if _session_store_instance is not None:
        return _session_store_instance

    # Try Redis if configured
    redis_url = getattr(settings, "redis_url", None)
    if redis_url:
        try:
            parsed = redis_lib.from_url(redis_url)
            _session_store_instance = RedisSessionStore(
                host=getattr(parsed, "host", "localhost"),
                port=getattr(parsed, "port", 6379),
                db=getattr(parsed, "db", 0),
            )
            return _session_store_instance
        except Exception:
            pass  # Fall through to memory

    _session_store_instance = MemorySessionStore()
    return _session_store_instance


def set_session_store(store: SessionStore) -> None:
    """Override the global session store (useful for testing)."""
    global _session_store_instance
    _session_store_instance = store
