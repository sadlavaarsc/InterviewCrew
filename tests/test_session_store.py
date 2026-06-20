"""
Unit and integration tests for session storage backends.

Covers:
- MemorySessionStore (basic CRUD)
- RedisSessionStore via fakeredis (CRUD + TTL)
- get_session_store() fallback logic
- Optional real Redis test (requires REAL_REDIS_URL env var)
"""

import os
import json
import time
import pytest
from unittest.mock import patch, MagicMock

from interview_crew.storage.session_store import (
    SessionStore,
    MemorySessionStore,
    RedisSessionStore,
    get_session_store,
    set_session_store,
    _session_store_instance,
)
from interview_crew.state import InterviewState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_realistic_state(session_id: str = "test-session-123") -> InterviewState:
    """Create an InterviewState with realistic data for round-trip tests."""
    state = InterviewState(
        session_id=session_id,
        turn=3,
        max_turns=8,
        candidate_response="I have 5 years of experience in distributed systems.",
        resume_path="/tmp/resume.md",
        jd_path="/tmp/jd.md",
        resume_text="Experienced backend engineer...",
        jd_text="Looking for senior backend engineer...",
        current_agent="tech1",
        last_question="Tell me about your experience with microservices.",
        status="ongoing",
        total_budget_consumed=1500,
        total_plus_token_consumed=800,
        total_flash_token_consumed=700,
        round_turn_counts={"tech1": 3, "tech2": 0},
        current_round_index=1,
        quota_consumed_agent={"tech1": 3},
        quota_consumed_stage={"tech1": {"chat": 2, "coding": 1}},
        tech1_sub_stage="coding",
        tech2_sub_stage="chat",
        tech1_stage_turns=1,
        tech2_stage_turns=0,
    )
    # Add some history messages
    state.append_agent_history("tech1", {"role": "assistant", "content": "Q1?"})
    state.append_agent_history("tech1", {"role": "user", "content": "A1"})
    state.append_unified({"role": "assistant", "content": "Q1?"})
    state.append_unified({"role": "user", "content": "A1"})
    return state


# ---------------------------------------------------------------------------
# MemorySessionStore tests
# ---------------------------------------------------------------------------

class TestMemorySessionStore:
    def test_save_and_load(self):
        store = MemorySessionStore()
        state = _make_realistic_state("sess-1")
        json_str = state.to_json()

        store.save("sess-1", json_str)
        loaded = store.load("sess-1")

        assert loaded is not None
        assert loaded == json_str
        # Verify round-trip via from_json
        restored = InterviewState.from_json(loaded)
        assert restored.session_id == "sess-1"
        assert restored.turn == 3
        assert restored.current_agent == "tech1"

    def test_load_missing_returns_none(self):
        store = MemorySessionStore()
        assert store.load("nonexistent") is None

    def test_delete(self):
        store = MemorySessionStore()
        store.save("a", "{}")
        store.delete("a")
        assert store.load("a") is None

    def test_delete_missing_no_error(self):
        store = MemorySessionStore()
        store.delete("nonexistent")  # should not raise

    def test_list_active(self):
        store = MemorySessionStore()
        store.save("s1", "{}")
        store.save("s2", "{}")
        active = store.list_active()
        assert sorted(active) == ["s1", "s2"]

    def test_overwrite_existing(self):
        store = MemorySessionStore()
        store.save("s1", "old")
        store.save("s1", "new")
        assert store.load("s1") == "new"

    def test_cleanup_expired_removes_old_sessions(self):
        store = MemorySessionStore()
        store.save("old", "{}")
        store.save("recent", "{}")
        # Manually backdate the 'old' entry
        store._data["old"] = ("{}", time.time() - 90000)  # 25 hours ago
        removed = store.cleanup_expired(max_age_seconds=86400)
        assert removed == 1
        assert store.load("old") is None
        assert store.load("recent") == "{}"

    def test_cleanup_expired_keeps_recent_sessions(self):
        store = MemorySessionStore()
        store.save("s1", "{}")
        removed = store.cleanup_expired(max_age_seconds=86400)
        assert removed == 0
        assert store.load("s1") == "{}"


# ---------------------------------------------------------------------------
# RedisSessionStore tests (fakeredis)
# ---------------------------------------------------------------------------

class TestRedisSessionStore:
    @pytest.fixture(autouse=True)
    def _reset_fakeredis(self):
        """Ensure each test gets a fresh fakeredis instance."""
        # We create a new RedisSessionStore with a fresh fakeredis client per test
        pass

    @pytest.fixture
    def fake_store(self):
        """Return a RedisSessionStore backed by fakeredis."""
        import fakeredis
        fake_client = fakeredis.FakeStrictRedis(decode_responses=True)
        store = RedisSessionStore.__new__(RedisSessionStore)
        store._client = fake_client
        store._prefix = "interview_crew:session:"
        return store

    def test_save_and_load(self, fake_store):
        state = _make_realistic_state("redis-sess-1")
        json_str = state.to_json()

        fake_store.save("redis-sess-1", json_str)
        loaded = fake_store.load("redis-sess-1")

        assert loaded is not None
        assert loaded == json_str
        restored = InterviewState.from_json(loaded)
        assert restored.session_id == "redis-sess-1"
        assert restored.turn == 3

    def test_load_missing_returns_none(self, fake_store):
        assert fake_store.load("nonexistent") is None

    def test_delete(self, fake_store):
        fake_store.save("del-me", "{}")
        fake_store.delete("del-me")
        assert fake_store.load("del-me") is None

    def test_list_active(self, fake_store):
        fake_store.save("r1", "{}")
        fake_store.save("r2", "{}")
        active = fake_store.list_active()
        assert sorted(active) == ["r1", "r2"]

    def test_list_active_empty(self, fake_store):
        assert fake_store.list_active() == []

    def test_overwrite_existing(self, fake_store):
        fake_store.save("s1", "old")
        fake_store.save("s1", "new")
        assert fake_store.load("s1") == "new"

    def test_ttl_expiration(self, fake_store):
        """Verify that keys expire after TTL_SECONDS by manipulating server time."""
        import fakeredis
        # Use a FakeRedis that supports time manipulation
        fake_client = fakeredis.FakeStrictRedis(decode_responses=True)
        store = RedisSessionStore.__new__(RedisSessionStore)
        store._client = fake_client
        store._prefix = "interview_crew:session:"

        # Save with a very short TTL for testing
        original_ttl = RedisSessionStore.TTL_SECONDS
        RedisSessionStore.TTL_SECONDS = 2  # 2 seconds for quick test
        try:
            store.save("ttl-sess", "some-state")
            assert store.load("ttl-sess") == "some-state"

            # Manipulate FakeRedis time to simulate expiration
            # FakeRedis uses time.time() internally; we patch it
            with patch("time.time", return_value=time.time() + 10):
                assert store.load("ttl-sess") is None
        finally:
            RedisSessionStore.TTL_SECONDS = original_ttl

    def test_ttl_via_expire_direct(self, fake_store):
        """Alternative TTL test: use Redis EXPIRE directly and check."""
        fake_store.save("ttl2", "data")
        # Manually set TTL to 1 second using the underlying client
        key = f"{fake_store._prefix}ttl2"
        fake_store._client.expire(key, 1)
        # FakeRedis time manipulation
        with patch("time.time", return_value=time.time() + 5):
            assert fake_store.load("ttl2") is None

    def test_prefix_isolation(self, fake_store):
        """Ensure keys with different prefixes don't collide."""
        fake_store.save("s1", "state1")
        # Directly write a key with different prefix
        fake_store._client.set("other:prefix:s1", "other-state")
        active = fake_store.list_active()
        assert active == ["s1"]
        assert fake_store.load("s1") == "state1"


# ---------------------------------------------------------------------------
# get_session_store() fallback tests
# ---------------------------------------------------------------------------

class TestGetSessionStoreFallback:
    def setup_method(self):
        """Reset global singleton before each test."""
        global _session_store_instance
        set_session_store(None)

    def teardown_method(self):
        """Clean up global singleton after each test."""
        set_session_store(None)

    def test_returns_memory_when_redis_url_not_set(self):
        from interview_crew import storage
        with patch.object(storage.session_store.settings, "redis_url", ""):
            set_session_store(None)
            store = get_session_store()
            assert isinstance(store, MemorySessionStore)

    def test_returns_memory_when_redis_url_invalid(self):
        from interview_crew import storage
        with patch.object(storage.session_store.settings, "redis_url", "redis://invalid_host:9999/0"):
            set_session_store(None)
            with patch.object(storage.session_store, "redis_lib") as fake_redis_lib:
                fake_redis_lib.from_url.side_effect = ConnectionError("connection failed")
                store = get_session_store()
                assert isinstance(store, MemorySessionStore)

    def test_caches_instance(self):
        from interview_crew import storage
        with patch.object(storage.session_store.settings, "redis_url", ""):
            set_session_store(None)
            store1 = get_session_store()
            store2 = get_session_store()
            assert store1 is store2

    def test_returns_redis_when_url_valid(self):
        """Test that a valid redis URL results in RedisSessionStore.

        We patch the module-level redis_lib import so redis_lib.from_url()
        returns a fake client with host/port/db attrs. The fake client must
        also support .info() (used by get_session_store).
        """
        import fakeredis
        from interview_crew import storage
        with patch.object(storage.session_store.settings, "redis_url", "redis://localhost:6379/0"):
            set_session_store(None)
            fake_redis = fakeredis.FakeStrictRedis(decode_responses=True)
            fake_redis.host = "localhost"
            fake_redis.port = 6379
            fake_redis.db = 0
            fake_redis.info = MagicMock(return_value={"redis_version": "7.0.0"})
            fake_redis_module = MagicMock()
            fake_redis_module.from_url.return_value = fake_redis
            with patch.object(storage.session_store, "redis_lib", fake_redis_module):
                store = get_session_store()
                assert isinstance(store, RedisSessionStore)


# ---------------------------------------------------------------------------
# Optional real Redis integration test
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("REAL_REDIS_URL") is None,
    reason="No real Redis available (set REAL_REDIS_URL env var to enable)",
)
class TestRealRedisSessionStore:
    @pytest.fixture
    def real_store(self):
        import redis
        url = os.environ["REAL_REDIS_URL"]
        parsed = redis.from_url(url)
        store = RedisSessionStore(
            host=getattr(parsed, "host", "localhost"),
            port=getattr(parsed, "port", 6379),
            db=getattr(parsed, "db", 0),
        )
        # Clean up any existing test keys
        for key in store._client.keys("interview_crew:session:test-*"):
            store._client.delete(key)
        return store

    def test_save_load_delete(self, real_store):
        state = _make_realistic_state("test-real-001")
        json_str = state.to_json()

        real_store.save("test-real-001", json_str)
        loaded = real_store.load("test-real-001")
        assert loaded == json_str

        real_store.delete("test-real-001")
        assert real_store.load("test-real-001") is None

    def test_list_active(self, real_store):
        real_store.save("test-real-a", "{}")
        real_store.save("test-real-b", "{}")
        active = real_store.list_active()
        assert "test-real-a" in active
        assert "test-real-b" in active
        real_store.delete("test-real-a")
        real_store.delete("test-real-b")

    def test_ttl_expiration_real(self, real_store):
        """Test that keys actually expire on a real Redis server.
        Uses a very short TTL to avoid long waits.
        """
        original_ttl = RedisSessionStore.TTL_SECONDS
        RedisSessionStore.TTL_SECONDS = 2  # 2 seconds
        try:
            real_store.save("test-ttl-real", "expire-me")
            assert real_store.load("test-ttl-real") == "expire-me"
            time.sleep(3)  # Wait for TTL + 1s buffer
            assert real_store.load("test-ttl-real") is None
        finally:
            RedisSessionStore.TTL_SECONDS = original_ttl
            real_store.delete("test-ttl-real")
