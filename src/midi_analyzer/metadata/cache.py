"""API response caching with SQLite backend."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CacheEntry:
    """A cached API response.

    Attributes:
        key: Cache key (hashed query).
        value: Cached response data.
        source: API source (e.g., 'musicbrainz', 'discogs').
        created_at: Unix timestamp when cached.
        expires_at: Unix timestamp when cache expires.
        hit_count: Number of cache hits.
    """

    key: str
    value: Any
    source: str
    created_at: float
    expires_at: float
    hit_count: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() > self.expires_at


@dataclass
class CacheStats:
    """Cache statistics.

    Attributes:
        total_entries: Total number of cached entries.
        hit_count: Total cache hits.
        miss_count: Total cache misses.
        expired_count: Number of expired entries.
        size_bytes: Total size in bytes.
    """

    total_entries: int = 0
    hit_count: int = 0
    miss_count: int = 0
    expired_count: int = 0
    size_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hit_count + self.miss_count
        return self.hit_count / total if total > 0 else 0.0


@dataclass
class RateLimitState:
    """Rate limiter state for an API.

    Attributes:
        source: API source name.
        last_request: Unix timestamp of last request.
        request_count: Requests in current window.
        window_start: Start of current rate limit window.
        backoff_until: Unix timestamp until which to back off.
        consecutive_failures: Number of consecutive failures.
    """

    source: str
    last_request: float = 0.0
    request_count: int = 0
    window_start: float = 0.0
    backoff_until: float = 0.0
    consecutive_failures: int = 0


# Default TTL values (in seconds)
DEFAULT_TTL = 86400 * 7  # 7 days
TTL_BY_SOURCE: dict[str, int] = {
    "musicbrainz": 86400 * 7,  # 7 days
    "discogs": 86400 * 7,  # 7 days
    "search": 86400,  # 1 day for searches
}

# Rate limits (requests per second)
RATE_LIMITS: dict[str, float] = {
    "musicbrainz": 1.0,  # 1 request/second
    "discogs": 1.0,  # 1 request/second
}


class APICache:
    """SQLite-backed API response cache with rate limiting.

    This class provides caching for API responses with TTL-based expiry
    and exponential backoff for rate limit handling.

    Example:
        cache = APICache("./cache.db")
        cache.initialize()

        # Cache a response
        cache.set("musicbrainz", query_params, response_data)

        # Retrieve cached response
        data = cache.get("musicbrainz", query_params)

        # Rate limiting
        if cache.can_request("musicbrainz"):
            # Make API call
            cache.record_request("musicbrainz")
    """

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        default_ttl: int = DEFAULT_TTL,
    ) -> None:
        """Initialize the cache.

        Args:
            db_path: Path to SQLite database file.
            default_ttl: Default TTL for cached entries in seconds.
        """
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        self.default_ttl = default_ttl
        self._conn: sqlite3.Connection | None = None
        self._stats = CacheStats()
        self._rate_limits: dict[str, RateLimitState] = {}

    def initialize(self) -> None:
        """Initialize the database schema."""
        self._conn = sqlite3.connect(
            str(self.db_path) if isinstance(self.db_path, Path) else self.db_path,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self) -> None:
        """Create cache tables if they don't exist."""
        if not self._conn:
            return

        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS api_cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL,
                hit_count INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_cache_source ON api_cache(source);
            CREATE INDEX IF NOT EXISTS idx_cache_expires ON api_cache(expires_at);

            CREATE TABLE IF NOT EXISTS rate_limits (
                source TEXT PRIMARY KEY,
                last_request REAL DEFAULT 0,
                request_count INTEGER DEFAULT 0,
                window_start REAL DEFAULT 0,
                backoff_until REAL DEFAULT 0,
                consecutive_failures INTEGER DEFAULT 0
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _make_key(self, source: str, params: dict[str, Any]) -> str:
        """Create a cache key from source and parameters.

        Args:
            source: API source name.
            params: Query parameters.

        Returns:
            Hashed cache key.
        """
        data = json.dumps({"source": source, **params}, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

    def get(
        self,
        source: str,
        params: dict[str, Any],
        ignore_expired: bool = False,
    ) -> Any | None:
        """Get a cached response.

        Args:
            source: API source name.
            params: Query parameters.
            ignore_expired: Whether to return expired entries.

        Returns:
            Cached value or None if not found/expired.
        """
        if not self._conn:
            self._stats.miss_count += 1
            return None

        key = self._make_key(source, params)
        cursor = self._conn.execute(
            "SELECT value, expires_at FROM api_cache WHERE key = ?",
            (key,),
        )
        row = cursor.fetchone()

        if not row:
            self._stats.miss_count += 1
            return None

        value, expires_at = row["value"], row["expires_at"]

        # Check expiry
        if not ignore_expired and time.time() > expires_at:
            self._stats.miss_count += 1
            self._stats.expired_count += 1
            return None

        # Update hit count
        self._conn.execute(
            "UPDATE api_cache SET hit_count = hit_count + 1 WHERE key = ?",
            (key,),
        )
        self._conn.commit()

        self._stats.hit_count += 1
        return json.loads(value)

    def set(
        self,
        source: str,
        params: dict[str, Any],
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """Cache a response.

        Args:
            source: API source name.
            params: Query parameters.
            value: Response data to cache.
            ttl: TTL in seconds (uses source default if None).
        """
        if not self._conn:
            return

        key = self._make_key(source, params)
        now = time.time()

        # Get TTL
        if ttl is None:
            ttl = TTL_BY_SOURCE.get(source, self.default_ttl)

        expires_at = now + ttl
        value_json = json.dumps(value)

        self._conn.execute(
            """
            INSERT OR REPLACE INTO api_cache 
            (key, value, source, created_at, expires_at, hit_count)
            VALUES (?, ?, ?, ?, ?, 0)
            """,
            (key, value_json, source, now, expires_at),
        )
        self._conn.commit()
        self._stats.total_entries += 1

    def delete(self, source: str, params: dict[str, Any]) -> bool:
        """Delete a cached entry.

        Args:
            source: API source name.
            params: Query parameters.

        Returns:
            True if entry was deleted.
        """
        if not self._conn:
            return False

        key = self._make_key(source, params)
        cursor = self._conn.execute(
            "DELETE FROM api_cache WHERE key = ?",
            (key,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def clear(self, source: str | None = None) -> int:
        """Clear cached entries.

        Args:
            source: If provided, only clear entries for this source.

        Returns:
            Number of entries cleared.
        """
        if not self._conn:
            return 0

        if source:
            cursor = self._conn.execute(
                "DELETE FROM api_cache WHERE source = ?",
                (source,),
            )
        else:
            cursor = self._conn.execute("DELETE FROM api_cache")

        self._conn.commit()
        return cursor.rowcount

    def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed.
        """
        if not self._conn:
            return 0

        now = time.time()
        cursor = self._conn.execute(
            "DELETE FROM api_cache WHERE expires_at < ?",
            (now,),
        )
        self._conn.commit()
        return cursor.rowcount

    # Rate limiting methods

    def can_request(self, source: str) -> bool:
        """Check if a request can be made within rate limits.

        Args:
            source: API source name.

        Returns:
            True if request is allowed.
        """
        state = self._get_rate_limit_state(source)
        now = time.time()

        # Check backoff
        if now < state.backoff_until:
            return False

        # Check rate limit
        rate_limit = RATE_LIMITS.get(source, 1.0)
        min_interval = 1.0 / rate_limit

        return now - state.last_request >= min_interval

    def record_request(self, source: str, success: bool = True) -> None:
        """Record an API request.

        Args:
            source: API source name.
            success: Whether the request succeeded.
        """
        state = self._get_rate_limit_state(source)
        now = time.time()

        state.last_request = now
        state.request_count += 1

        if success:
            state.consecutive_failures = 0
            state.backoff_until = 0.0
        else:
            state.consecutive_failures += 1
            # Exponential backoff: 2^n seconds, max 5 minutes
            backoff = min(2 ** state.consecutive_failures, 300)
            state.backoff_until = now + backoff

        self._save_rate_limit_state(state)

    def wait_for_rate_limit(self, source: str) -> float:
        """Wait until a request can be made.

        Args:
            source: API source name.

        Returns:
            Time waited in seconds.
        """
        start = time.time()

        while not self.can_request(source):
            time.sleep(0.1)

        return time.time() - start

    def _get_rate_limit_state(self, source: str) -> RateLimitState:
        """Get rate limit state for a source.

        Args:
            source: API source name.

        Returns:
            Rate limit state.
        """
        if source in self._rate_limits:
            return self._rate_limits[source]

        # Try to load from database
        if self._conn:
            cursor = self._conn.execute(
                "SELECT * FROM rate_limits WHERE source = ?",
                (source,),
            )
            row = cursor.fetchone()

            if row:
                state = RateLimitState(
                    source=source,
                    last_request=row["last_request"],
                    request_count=row["request_count"],
                    window_start=row["window_start"],
                    backoff_until=row["backoff_until"],
                    consecutive_failures=row["consecutive_failures"],
                )
                self._rate_limits[source] = state
                return state

        # Create new state
        state = RateLimitState(source=source)
        self._rate_limits[source] = state
        return state

    def _save_rate_limit_state(self, state: RateLimitState) -> None:
        """Save rate limit state to database.

        Args:
            state: Rate limit state to save.
        """
        if not self._conn:
            return

        self._conn.execute(
            """
            INSERT OR REPLACE INTO rate_limits
            (source, last_request, request_count, window_start, 
             backoff_until, consecutive_failures)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                state.source,
                state.last_request,
                state.request_count,
                state.window_start,
                state.backoff_until,
                state.consecutive_failures,
            ),
        )
        self._conn.commit()

    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            Cache statistics.
        """
        if not self._conn:
            return self._stats

        # Count total entries
        cursor = self._conn.execute("SELECT COUNT(*) FROM api_cache")
        self._stats.total_entries = cursor.fetchone()[0]

        # Count expired entries
        now = time.time()
        cursor = self._conn.execute(
            "SELECT COUNT(*) FROM api_cache WHERE expires_at < ?",
            (now,),
        )
        self._stats.expired_count = cursor.fetchone()[0]

        # Calculate size
        cursor = self._conn.execute(
            "SELECT SUM(LENGTH(value)) FROM api_cache"
        )
        result = cursor.fetchone()[0]
        self._stats.size_bytes = result or 0

        return self._stats

    def __enter__(self) -> APICache:
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()


# Global cache instance
_global_cache: APICache | None = None


def get_cache(db_path: str | Path | None = None) -> APICache:
    """Get or create the global cache instance.

    Args:
        db_path: Optional path to database file.

    Returns:
        Global cache instance.
    """
    global _global_cache

    if _global_cache is None:
        path = db_path or ":memory:"
        _global_cache = APICache(path)
        _global_cache.initialize()

    return _global_cache


def close_cache() -> None:
    """Close the global cache instance."""
    global _global_cache

    if _global_cache is not None:
        _global_cache.close()
        _global_cache = None
