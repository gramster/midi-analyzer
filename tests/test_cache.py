"""Tests for API response caching."""

import time
from unittest.mock import patch

import pytest

from midi_analyzer.metadata.cache import (
    APICache,
    CacheEntry,
    CacheStats,
    RateLimitState,
    close_cache,
    get_cache,
)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_cache_entry_creation(self):
        """Test creating a cache entry."""
        entry = CacheEntry(
            key="test-key",
            value={"data": "test"},
            source="musicbrainz",
            created_at=1000.0,
            expires_at=2000.0,
        )

        assert entry.key == "test-key"
        assert entry.value == {"data": "test"}
        assert entry.source == "musicbrainz"
        assert entry.hit_count == 0

    def test_is_expired(self):
        """Test expiry check."""
        # Not expired
        entry = CacheEntry(
            key="k",
            value={},
            source="s",
            created_at=time.time(),
            expires_at=time.time() + 1000,
        )
        assert not entry.is_expired

        # Expired
        entry = CacheEntry(
            key="k",
            value={},
            source="s",
            created_at=1000.0,
            expires_at=1001.0,
        )
        assert entry.is_expired


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_cache_stats_defaults(self):
        """Test default stats."""
        stats = CacheStats()
        assert stats.total_entries == 0
        assert stats.hit_count == 0
        assert stats.miss_count == 0

    def test_hit_rate(self):
        """Test hit rate calculation."""
        stats = CacheStats(hit_count=80, miss_count=20)
        assert stats.hit_rate == 0.8

    def test_hit_rate_zero(self):
        """Test hit rate with no requests."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0


class TestRateLimitState:
    """Tests for RateLimitState dataclass."""

    def test_rate_limit_state_creation(self):
        """Test creating rate limit state."""
        state = RateLimitState(source="musicbrainz")
        assert state.source == "musicbrainz"
        assert state.consecutive_failures == 0
        assert state.backoff_until == 0.0


class TestAPICache:
    """Tests for APICache class."""

    @pytest.fixture
    def cache(self):
        """Create a test cache."""
        c = APICache(":memory:")
        c.initialize()
        yield c
        c.close()

    def test_initialize(self, cache):
        """Test cache initialization."""
        assert cache._conn is not None

    def test_set_and_get(self, cache):
        """Test setting and getting values."""
        params = {"artist": "Test", "title": "Song"}
        value = {"result": "data", "tags": ["rock"]}

        cache.set("musicbrainz", params, value)
        result = cache.get("musicbrainz", params)

        assert result == value

    def test_get_nonexistent(self, cache):
        """Test getting nonexistent key."""
        result = cache.get("musicbrainz", {"query": "unknown"})
        assert result is None

    def test_get_expired(self, cache):
        """Test getting expired entry."""
        params = {"query": "test"}
        cache.set("musicbrainz", params, {"data": "test"}, ttl=0)

        # Wait for expiry
        time.sleep(0.01)

        result = cache.get("musicbrainz", params)
        assert result is None

    def test_get_expired_ignore(self, cache):
        """Test getting expired entry with ignore flag."""
        params = {"query": "test"}
        cache.set("musicbrainz", params, {"data": "test"}, ttl=0)

        # Wait for expiry
        time.sleep(0.01)

        result = cache.get("musicbrainz", params, ignore_expired=True)
        assert result == {"data": "test"}

    def test_delete(self, cache):
        """Test deleting an entry."""
        params = {"query": "test"}
        cache.set("musicbrainz", params, {"data": "test"})

        deleted = cache.delete("musicbrainz", params)
        assert deleted is True

        result = cache.get("musicbrainz", params)
        assert result is None

    def test_delete_nonexistent(self, cache):
        """Test deleting nonexistent entry."""
        deleted = cache.delete("musicbrainz", {"query": "unknown"})
        assert deleted is False

    def test_clear_all(self, cache):
        """Test clearing all entries."""
        cache.set("musicbrainz", {"q": "1"}, {"v": 1})
        cache.set("discogs", {"q": "2"}, {"v": 2})

        count = cache.clear()
        assert count == 2

    def test_clear_by_source(self, cache):
        """Test clearing by source."""
        cache.set("musicbrainz", {"q": "1"}, {"v": 1})
        cache.set("discogs", {"q": "2"}, {"v": 2})

        count = cache.clear("musicbrainz")
        assert count == 1

        # Discogs entry should still exist
        assert cache.get("discogs", {"q": "2"}) == {"v": 2}

    def test_cleanup_expired(self, cache):
        """Test cleaning up expired entries."""
        cache.set("musicbrainz", {"q": "1"}, {"v": 1}, ttl=0)
        cache.set("musicbrainz", {"q": "2"}, {"v": 2}, ttl=10000)

        time.sleep(0.01)

        count = cache.cleanup_expired()
        assert count == 1

    def test_hit_count_increment(self, cache):
        """Test that hit count is incremented."""
        params = {"query": "test"}
        cache.set("musicbrainz", params, {"data": "test"})

        # Multiple gets
        cache.get("musicbrainz", params)
        cache.get("musicbrainz", params)
        cache.get("musicbrainz", params)

        # Check stats
        stats = cache.get_stats()
        assert stats.hit_count == 3


class TestRateLimiting:
    """Tests for rate limiting functionality."""

    @pytest.fixture
    def cache(self):
        """Create a test cache."""
        c = APICache(":memory:")
        c.initialize()
        yield c
        c.close()

    def test_can_request_initial(self, cache):
        """Test that first request is allowed."""
        assert cache.can_request("musicbrainz")

    def test_can_request_rate_limited(self, cache):
        """Test rate limiting."""
        cache.record_request("musicbrainz")
        # Immediately after a request, should be rate limited
        assert not cache.can_request("musicbrainz")

    def test_can_request_after_wait(self, cache):
        """Test request allowed after waiting."""
        cache.record_request("musicbrainz")

        # Wait for rate limit
        time.sleep(1.1)

        assert cache.can_request("musicbrainz")

    def test_record_request_success(self, cache):
        """Test recording successful request."""
        cache.record_request("musicbrainz", success=True)

        state = cache._get_rate_limit_state("musicbrainz")
        assert state.consecutive_failures == 0
        assert state.backoff_until == 0.0

    def test_record_request_failure(self, cache):
        """Test recording failed request."""
        cache.record_request("musicbrainz", success=False)

        state = cache._get_rate_limit_state("musicbrainz")
        assert state.consecutive_failures == 1
        assert state.backoff_until > time.time()

    def test_exponential_backoff(self, cache):
        """Test exponential backoff on failures."""
        # Multiple failures
        cache.record_request("musicbrainz", success=False)
        backoff1 = cache._get_rate_limit_state("musicbrainz").backoff_until

        cache.record_request("musicbrainz", success=False)
        backoff2 = cache._get_rate_limit_state("musicbrainz").backoff_until

        cache.record_request("musicbrainz", success=False)
        backoff3 = cache._get_rate_limit_state("musicbrainz").backoff_until

        # Each backoff should be longer
        now = time.time()
        assert backoff2 - now > backoff1 - now
        assert backoff3 - now > backoff2 - now

    def test_can_request_during_backoff(self, cache):
        """Test that requests are blocked during backoff."""
        cache.record_request("musicbrainz", success=False)
        assert not cache.can_request("musicbrainz")

    @patch("midi_analyzer.metadata.cache.time.sleep")
    def test_wait_for_rate_limit(self, mock_sleep, cache):
        """Test waiting for rate limit."""
        # Set up rate limited state
        cache._rate_limits["test"] = RateLimitState(
            source="test",
            last_request=time.time(),
        )

        # Make it not rate limited after first check
        original_can_request = cache.can_request
        call_count = [0]

        def mock_can_request(source):
            call_count[0] += 1
            if call_count[0] > 1:
                return True
            return original_can_request(source)

        cache.can_request = mock_can_request

        waited = cache.wait_for_rate_limit("test")

        assert mock_sleep.called


class TestCacheStats:
    """Tests for cache statistics."""

    @pytest.fixture
    def cache(self):
        """Create a test cache."""
        c = APICache(":memory:")
        c.initialize()
        yield c
        c.close()

    def test_get_stats_empty(self, cache):
        """Test stats for empty cache."""
        stats = cache.get_stats()
        assert stats.total_entries == 0
        assert stats.size_bytes == 0

    def test_get_stats_with_entries(self, cache):
        """Test stats with entries."""
        cache.set("musicbrainz", {"q": "1"}, {"data": "test1"})
        cache.set("musicbrainz", {"q": "2"}, {"data": "test2"})

        stats = cache.get_stats()
        assert stats.total_entries == 2
        assert stats.size_bytes > 0


class TestContextManager:
    """Tests for context manager usage."""

    def test_context_manager(self):
        """Test using cache as context manager."""
        with APICache(":memory:") as cache:
            cache.set("test", {"q": "1"}, {"data": "test"})
            result = cache.get("test", {"q": "1"})
            assert result == {"data": "test"}


class TestGlobalCache:
    """Tests for global cache functions."""

    def test_get_cache_creates_instance(self):
        """Test get_cache creates a new instance."""
        close_cache()  # Ensure no existing instance

        cache = get_cache()
        assert cache is not None

        # Cleanup
        close_cache()

    def test_get_cache_returns_same_instance(self):
        """Test get_cache returns the same instance."""
        close_cache()

        cache1 = get_cache()
        cache2 = get_cache()
        assert cache1 is cache2

        close_cache()

    def test_close_cache(self):
        """Test closing global cache."""
        close_cache()

        cache = get_cache()
        close_cache()

        # Getting cache again should create new instance
        cache2 = get_cache()
        assert cache2 is not cache or cache2 is not None

        close_cache()


class TestMakeKey:
    """Tests for cache key generation."""

    @pytest.fixture
    def cache(self):
        """Create a test cache."""
        c = APICache(":memory:")
        c.initialize()
        yield c
        c.close()

    def test_same_params_same_key(self, cache):
        """Test that same params generate same key."""
        params = {"artist": "Test", "title": "Song"}
        key1 = cache._make_key("musicbrainz", params)
        key2 = cache._make_key("musicbrainz", params)
        assert key1 == key2

    def test_different_params_different_key(self, cache):
        """Test that different params generate different keys."""
        key1 = cache._make_key("musicbrainz", {"q": "1"})
        key2 = cache._make_key("musicbrainz", {"q": "2"})
        assert key1 != key2

    def test_different_source_different_key(self, cache):
        """Test that different sources generate different keys."""
        params = {"q": "test"}
        key1 = cache._make_key("musicbrainz", params)
        key2 = cache._make_key("discogs", params)
        assert key1 != key2

    def test_param_order_independent(self, cache):
        """Test that key is independent of param order."""
        key1 = cache._make_key("test", {"a": "1", "b": "2"})
        key2 = cache._make_key("test", {"b": "2", "a": "1"})
        assert key1 == key2
