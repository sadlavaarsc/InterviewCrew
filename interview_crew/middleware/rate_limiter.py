"""
Token bucket rate limiter for InterviewCrew.
Provides per-endpoint and per-session rate limiting.
"""

import time
import asyncio
from typing import Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class TokenBucket:
    """Simple in-memory token bucket."""

    def __init__(self, rate: float, capacity: float):
        self.rate = rate          # tokens per second
        self.capacity = capacity  # max tokens
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def consume(self, tokens: float = 1.0) -> bool:
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for rate limiting."""

    def __init__(
        self,
        app,
        global_rate: float = 10.0,      # requests per second globally
        global_capacity: float = 20.0,
        session_rate: float = 1.0,       # requests per second per session
        session_capacity: float = 5.0,
    ):
        super().__init__(app)
        self.global_bucket = TokenBucket(global_rate, global_capacity)
        self.session_buckets: dict[str, TokenBucket] = {}
        self.session_rate = session_rate
        self.session_capacity = session_capacity

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health and static files
        path = request.url.path
        if path in ("/health", "/", "/metrics") or path.startswith("/static"):
            return await call_next(request)

        # Global rate limit
        if not await self.global_bucket.consume():
            return Response(
                content='{"detail":"Global rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
            )

        # Per-session rate limit (for /step and /stream endpoints)
        if path.startswith("/sessions/") and path != "/sessions":
            session_id = path.split("/")[2]
            if session_id not in self.session_buckets:
                self.session_buckets[session_id] = TokenBucket(
                    self.session_rate, self.session_capacity
                )
            if not await self.session_buckets[session_id].consume():
                return Response(
                    content='{"detail":"Session rate limit exceeded"}',
                    status_code=429,
                    media_type="application/json",
                )

        return await call_next(request)
