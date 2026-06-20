"""Unit tests for rate limiting middleware."""

import time
import asyncio
import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interview_crew.middleware.rate_limiter import TokenBucket, RateLimitMiddleware


def _run_async(coro):
    """Run an async coroutine synchronously using a fresh event loop."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# TokenBucket tests
# ---------------------------------------------------------------------------

class TestTokenBucket:
    """Tests for the TokenBucket class."""

    def test_consume_returns_true_when_tokens_available(self):
        """consume() should return True when tokens are available."""
        bucket = TokenBucket(rate=10.0, capacity=5.0)
        result = _run_async(bucket.consume())
        assert result is True

    def test_consume_returns_false_when_capacity_exhausted(self):
        """consume() should return False after all tokens are consumed."""
        bucket = TokenBucket(rate=10.0, capacity=3.0)
        # Consume all 3 tokens
        assert _run_async(bucket.consume()) is True
        assert _run_async(bucket.consume()) is True
        assert _run_async(bucket.consume()) is True
        # 4th consume should fail
        assert _run_async(bucket.consume()) is False

    def test_tokens_refill_over_time(self):
        """Tokens should refill over time based on rate."""
        bucket = TokenBucket(rate=10.0, capacity=5.0)
        # Consume all tokens
        for _ in range(5):
            assert _run_async(bucket.consume()) is True
        assert _run_async(bucket.consume()) is False

        # Wait for refill (at rate 10.0, 1 token refills in 0.1s)
        time.sleep(0.15)
        assert _run_async(bucket.consume()) is True

    def test_tokens_refill_with_monotonic_patching(self):
        """Tokens refill can be tested by patching time.time."""
        bucket = TokenBucket(rate=10.0, capacity=2.0)
        # Consume all tokens
        assert _run_async(bucket.consume()) is True
        assert _run_async(bucket.consume()) is True
        assert _run_async(bucket.consume()) is False

        # Patch time.time to simulate 0.2 seconds passing (2 tokens refill at rate 10)
        with patch.object(time, "time", return_value=bucket.last_update + 0.2):
            assert _run_async(bucket.consume()) is True
            assert _run_async(bucket.consume()) is True
            assert _run_async(bucket.consume()) is False

    def test_per_request_token_consumption(self):
        """consume() with custom token count."""
        bucket = TokenBucket(rate=10.0, capacity=5.0)
        # Consume 3 tokens at once
        assert _run_async(bucket.consume(tokens=3.0)) is True
        # 2 tokens left
        assert _run_async(bucket.consume(tokens=2.0)) is True
        # 0 tokens left
        assert _run_async(bucket.consume(tokens=1.0)) is False

    def test_capacity_never_exceeds_max(self):
        """Token count should never exceed capacity even after long wait."""
        bucket = TokenBucket(rate=10.0, capacity=3.0)
        # Consume all tokens
        for _ in range(3):
            assert _run_async(bucket.consume()) is True

        # Wait a long time (would refill more than capacity)
        time.sleep(0.5)
        # Should still only have capacity tokens
        assert _run_async(bucket.consume()) is True
        assert _run_async(bucket.consume()) is True
        assert _run_async(bucket.consume()) is True
        assert _run_async(bucket.consume()) is False

    def test_token_bucket_concurrent_access(self):
        """TokenBucket should handle concurrent access safely."""
        bucket = TokenBucket(rate=100.0, capacity=5.0)

        async def try_consume():
            return await bucket.consume()

        async def run_all():
            return await asyncio.gather(*[try_consume() for _ in range(10)])

        # Launch 10 concurrent consume attempts
        results = _run_async(run_all())

        # Only 5 should succeed (capacity)
        assert sum(results) == 5
        assert results.count(False) == 5


# ---------------------------------------------------------------------------
# RateLimitMiddleware tests
# ---------------------------------------------------------------------------

@pytest.fixture
def test_app():
    """Create a minimal FastAPI app with RateLimitMiddleware for testing."""
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        global_rate=100.0,      # high global rate to avoid global limits
        global_capacity=1000.0,
        session_rate=100.0,     # high session rate for most tests
        session_capacity=1000.0,
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics():
        return {"metrics": "data"}

    @app.get("/")
    def root():
        return {"message": "root"}

    @app.get("/static/test.css")
    def static_file():
        return {"css": "body{}"}

    @app.post("/sessions/{session_id}/step")
    def step(session_id: str):
        return {"agent": "tech1", "question": "test?"}

    @app.get("/sessions/{session_id}")
    def get_session(session_id: str):
        return {"session_id": session_id}

    return app


class TestRateLimitMiddlewareWhitelist:
    """Tests for whitelisted paths that bypass rate limiting."""

    def test_health_not_rate_limited(self, test_app):
        """/health should not be rate limited."""
        client = TestClient(test_app)
        # Make many requests quickly
        for _ in range(50):
            response = client.get("/health")
            assert response.status_code == 200

    def test_metrics_not_rate_limited(self, test_app):
        """/metrics should not be rate limited."""
        client = TestClient(test_app)
        for _ in range(50):
            response = client.get("/metrics")
            assert response.status_code == 200

    def test_root_not_rate_limited(self, test_app):
        """/ (root) should not be rate limited."""
        client = TestClient(test_app)
        for _ in range(50):
            response = client.get("/")
            assert response.status_code == 200

    def test_static_not_rate_limited(self, test_app):
        """Paths starting with /static should not be rate limited."""
        client = TestClient(test_app)
        for _ in range(50):
            response = client.get("/static/test.css")
            assert response.status_code == 200


@pytest.fixture
def limited_app():
    """App with very low session rate limits for testing 429 responses."""
    app = FastAPI()
    app.add_middleware(
        RateLimitMiddleware,
        global_rate=1000.0,     # very high global rate
        global_capacity=10000.0,
        session_rate=0.0,      # no refill for deterministic burst testing
        session_capacity=3.0,   # only 3 burst requests allowed
    )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/sessions/{session_id}/step")
    def step(session_id: str):
        return {"agent": "tech1", "question": "test?"}

    @app.get("/sessions/{session_id}")
    def get_session(session_id: str):
        return {"session_id": session_id}

    return app


class TestRateLimitMiddlewareSession:
    """Tests for per-session rate limiting on /sessions/{id}/step."""

    def test_session_step_returns_429_after_burst(self, limited_app):
        """Rapid requests to /sessions/{id}/step should return 429 after burst."""
        client = TestClient(limited_app)
        session_id = "test-session-123"

        # First 3 requests should succeed (capacity=3)
        for _ in range(3):
            response = client.post(f"/sessions/{session_id}/step")
            assert response.status_code == 200

        # 4th request should be rate limited
        response = client.post(f"/sessions/{session_id}/step")
        assert response.status_code == 429
        assert "Session rate limit exceeded" in response.text

    def test_per_session_isolation(self, limited_app):
        """Session A being throttled should not throttle session B."""
        client = TestClient(limited_app)
        session_a = "session-a"
        session_b = "session-b"

        # Exhaust session A's capacity
        for _ in range(3):
            response = client.post(f"/sessions/{session_a}/step")
            assert response.status_code == 200

        # Session A should now be throttled
        assert client.post(f"/sessions/{session_a}/step").status_code == 429

        # Session B should still work fine
        for _ in range(3):
            response = client.post(f"/sessions/{session_b}/step")
            assert response.status_code == 200

        # Session B should also be throttled after 3 requests
        assert client.post(f"/sessions/{session_b}/step").status_code == 429

    def test_session_get_shares_session_bucket(self, limited_app):
        """GET /sessions/{id} shares the same per-session bucket as POST /step."""
        client = TestClient(limited_app)
        session_id = "test-session-123"

        # POST 3 times to exhaust session capacity
        for _ in range(3):
            response = client.post(f"/sessions/{session_id}/step")
            assert response.status_code == 200

        # GET should also be throttled (shares same session bucket)
        response = client.get(f"/sessions/{session_id}")
        assert response.status_code == 429
        assert "Session rate limit exceeded" in response.text

    def test_global_rate_limit_429(self):
        """Global rate limit should return 429 when exceeded."""
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            global_rate=0.0,      # no refill for deterministic burst testing
            global_capacity=2.0,  # Only 2 burst globally
            session_rate=1000.0,
            session_capacity=1000.0,
        )

        @app.post("/some-endpoint")
        def some_endpoint():
            return {"ok": True}

        client = TestClient(app)

        # First 2 requests succeed
        assert client.post("/some-endpoint").status_code == 200
        assert client.post("/some-endpoint").status_code == 200

        # 3rd request hits global limit
        response = client.post("/some-endpoint")
        assert response.status_code == 429
        assert "Global rate limit exceeded" in response.text

    def test_rate_limit_response_format(self, limited_app):
        """429 responses should have correct JSON format."""
        client = TestClient(limited_app)
        session_id = "test-session-123"

        # Exhaust capacity
        for _ in range(3):
            client.post(f"/sessions/{session_id}/step")

        response = client.post(f"/sessions/{session_id}/step")
        assert response.status_code == 429
        assert response.headers["content-type"] == "application/json"


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------

class TestRateLimitEdgeCases:
    """Edge case tests for rate limiter."""

    def test_sessions_root_path_not_session_limited(self):
        """POST /sessions (without id) should not trigger per-session limit."""
        app = FastAPI()
        app.add_middleware(
            RateLimitMiddleware,
            global_rate=1000.0,
            global_capacity=1000.0,
            session_rate=1000.0,
            session_capacity=3.0,
        )

        @app.post("/sessions")
        def create_session():
            return {"session_id": "new"}

        client = TestClient(app)
        # Many requests to /sessions should not be session-limited
        for _ in range(10):
            response = client.post("/sessions")
            assert response.status_code == 200

    def test_token_bucket_concurrent_access(self):
        """TokenBucket should handle concurrent access safely."""
        bucket = TokenBucket(rate=100.0, capacity=5.0)

        async def try_consume():
            return await bucket.consume()

        async def run_all():
            return await asyncio.gather(*[try_consume() for _ in range(10)])

        # Launch 10 concurrent consume attempts
        results = _run_async(run_all())

        # Only 5 should succeed (capacity)
        assert sum(results) == 5
        assert results.count(False) == 5

    def test_different_session_ids_create_different_buckets(self, limited_app):
        """Each unique session ID should get its own TokenBucket."""
        client = TestClient(limited_app)

        # Create many sessions and use 1 request each
        for i in range(10):
            session_id = f"session-{i}"
            response = client.post(f"/sessions/{session_id}/step")
            assert response.status_code == 200

        # All should still have 2 more requests each
        for i in range(10):
            session_id = f"session-{i}"
            response = client.post(f"/sessions/{session_id}/step")
            assert response.status_code == 200
            response = client.post(f"/sessions/{session_id}/step")
            assert response.status_code == 200
            # 4th should fail
            response = client.post(f"/sessions/{session_id}/step")
            assert response.status_code == 429
