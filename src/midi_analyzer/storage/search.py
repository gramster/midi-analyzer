"""Pattern search and query interface."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from midi_analyzer.storage.schema import Database


class SortOrder(Enum):
    """Sort order for search results."""

    RELEVANCE = "relevance"
    OCCURRENCE = "occurrence"
    NEWEST = "newest"
    OLDEST = "oldest"


@dataclass
class PatternQuery:
    """Query parameters for pattern search.

    Attributes:
        rhythm_hash: Exact rhythm fingerprint hash to match.
        pitch_hash: Exact pitch fingerprint hash to match.
        pattern_type: Type of pattern (e.g., "combined").
        num_bars: Number of bars in pattern.
        min_occurrences: Minimum occurrence count.
        artist: Filter by artist (partial match).
        genre: Filter by genre (partial match).
        role: Filter by track role.
        tags: Filter by tags (any match).
        limit: Maximum results to return.
        offset: Pagination offset.
        sort_by: How to sort results.
    """

    rhythm_hash: str | None = None
    pitch_hash: str | None = None
    pattern_type: str | None = None
    num_bars: int | None = None
    min_occurrences: int = 1
    artist: str | None = None
    genre: str | None = None
    role: str | None = None
    tags: list[str] = field(default_factory=list)
    limit: int = 50
    offset: int = 0
    sort_by: SortOrder = SortOrder.OCCURRENCE


@dataclass
class PatternSearchResult:
    """A single search result.

    Attributes:
        pattern_id: Unique pattern identifier.
        rhythm_hash: Rhythm fingerprint hash.
        pitch_hash: Pitch fingerprint hash.
        num_bars: Number of bars.
        occurrence_count: How many times this pattern appears.
        song_ids: Songs containing this pattern.
        artists: Artists with this pattern.
        genres: Genres containing this pattern.
    """

    pattern_id: str
    rhythm_hash: str
    pitch_hash: str
    num_bars: int
    occurrence_count: int
    song_ids: list[str] = field(default_factory=list)
    artists: list[str] = field(default_factory=list)
    genres: list[str] = field(default_factory=list)


@dataclass
class SearchResults:
    """Search results with pagination info.

    Attributes:
        results: List of matching patterns.
        total_count: Total number of matches (before pagination).
        query: The query that produced these results.
        has_more: Whether there are more results.
    """

    results: list[PatternSearchResult]
    total_count: int
    query: PatternQuery
    has_more: bool = False


class PatternSearch:
    """Search interface for finding patterns in the database."""

    def __init__(self, db: Database) -> None:
        """Initialize search interface.

        Args:
            db: Database connection.
        """
        self.db = db

    def search(self, query: PatternQuery) -> SearchResults:
        """Search for patterns matching query.

        Args:
            query: Search parameters.

        Returns:
            SearchResults with matching patterns.
        """
        # Build SQL query
        base_sql, params = self._build_query(query)

        # Get total count first
        count_sql = f"SELECT COUNT(*) FROM ({base_sql}) AS subq"
        cursor = self.db.execute(count_sql, params)
        total_count = cursor.fetchone()[0]

        # Add sorting and pagination
        order_clause = self._get_order_clause(query.sort_by)
        paginated_sql = f"{base_sql} {order_clause} LIMIT ? OFFSET ?"
        paginated_params = params + (query.limit, query.offset)

        cursor = self.db.execute(paginated_sql, paginated_params)
        rows = cursor.fetchall()

        # Convert to results
        results = []
        for row in rows:
            result = PatternSearchResult(
                pattern_id=row["pattern_id"],
                rhythm_hash=row["rhythm_hash"] or "",
                pitch_hash=row["pitch_hash"] or "",
                num_bars=row["num_bars"] or 1,
                occurrence_count=row["occurrence_count"] or 0,
            )

            # Load related metadata
            self._enrich_result(result)
            results.append(result)

        has_more = (query.offset + len(results)) < total_count

        return SearchResults(
            results=results,
            total_count=total_count,
            query=query,
            has_more=has_more,
        )

    def _build_query(self, query: PatternQuery) -> tuple[str, tuple]:
        """Build SQL query from search parameters.

        Args:
            query: Search parameters.

        Returns:
            SQL query string and parameters tuple.
        """
        sql = """
            SELECT DISTINCT p.*
            FROM patterns p
        """

        joins = []
        conditions = []
        params: list = []

        # Join with instances for metadata filtering
        if query.artist or query.genre or query.role or query.tags:
            joins.append("""
                JOIN pattern_instances pi ON p.pattern_id = pi.pattern_id
                JOIN tracks t ON pi.track_id = t.track_id
                JOIN songs s ON t.song_id = s.song_id
                LEFT JOIN song_metadata m ON s.song_id = m.song_id
            """)

            if query.role:
                joins.append("LEFT JOIN track_roles tr ON t.track_id = tr.track_id")

        # Exact hash matches
        if query.rhythm_hash:
            conditions.append("p.rhythm_hash = ?")
            params.append(query.rhythm_hash)

        if query.pitch_hash:
            conditions.append("p.pitch_hash = ?")
            params.append(query.pitch_hash)

        # Pattern type
        if query.pattern_type:
            conditions.append("p.pattern_type = ?")
            params.append(query.pattern_type)

        # Number of bars
        if query.num_bars is not None:
            conditions.append("p.num_bars = ?")
            params.append(query.num_bars)

        # Minimum occurrences
        if query.min_occurrences > 1:
            conditions.append("p.occurrence_count >= ?")
            params.append(query.min_occurrences)

        # Artist filter
        if query.artist:
            conditions.append("m.artist LIKE ?")
            params.append(f"%{query.artist}%")

        # Genre filter
        if query.genre:
            conditions.append("m.genre LIKE ?")
            params.append(f"%{query.genre}%")

        # Role filter
        if query.role:
            conditions.append("tr.primary_role = ?")
            params.append(query.role)

        # Tags filter (any match)
        if query.tags:
            tag_conditions = []
            for tag in query.tags:
                tag_conditions.append("m.tags LIKE ?")
                params.append(f'%"{tag}"%')
            conditions.append(f"({' OR '.join(tag_conditions)})")

        # Build final query
        if joins:
            sql += " " + " ".join(joins)

        if conditions:
            sql += " WHERE " + " AND ".join(conditions)

        return sql, tuple(params)

    def _get_order_clause(self, sort_by: SortOrder) -> str:
        """Get ORDER BY clause for sort order."""
        if sort_by == SortOrder.OCCURRENCE:
            return "ORDER BY p.occurrence_count DESC"
        elif sort_by == SortOrder.NEWEST:
            return "ORDER BY p.created_at DESC"
        elif sort_by == SortOrder.OLDEST:
            return "ORDER BY p.created_at ASC"
        else:  # RELEVANCE - default to occurrence
            return "ORDER BY p.occurrence_count DESC"

    def _enrich_result(self, result: PatternSearchResult) -> None:
        """Add related metadata to search result.

        Args:
            result: Result to enrich.
        """
        # Get songs and artists
        cursor = self.db.execute(
            """
            SELECT DISTINCT s.song_id, m.artist, m.genre
            FROM pattern_instances pi
            JOIN tracks t ON pi.track_id = t.track_id
            JOIN songs s ON t.song_id = s.song_id
            LEFT JOIN song_metadata m ON s.song_id = m.song_id
            WHERE pi.pattern_id = ?
            LIMIT 10
            """,
            (result.pattern_id,),
        )

        for row in cursor.fetchall():
            if row["song_id"] and row["song_id"] not in result.song_ids:
                result.song_ids.append(row["song_id"])
            if row["artist"] and row["artist"] not in result.artists:
                result.artists.append(row["artist"])
            if row["genre"] and row["genre"] not in result.genres:
                result.genres.append(row["genre"])

    def find_similar(
        self,
        pattern_id: str,
        threshold: float = 0.8,
        limit: int = 20,
    ) -> list[tuple[str, float]]:
        """Find patterns similar to a given pattern.

        Args:
            pattern_id: Pattern to find similar patterns for.
            threshold: Minimum similarity score (0-1).
            limit: Maximum results.

        Returns:
            List of (pattern_id, similarity_score) tuples.
        """
        # Get the target pattern
        cursor = self.db.execute(
            "SELECT onset_grid, pitch_classes FROM patterns WHERE pattern_id = ?",
            (pattern_id,),
        )
        row = cursor.fetchone()

        if not row:
            return []

        import json

        target_onset = set(
            i for i, v in enumerate(json.loads(row["onset_grid"] or "[]")) if v
        )
        target_pitch = json.loads(row["pitch_classes"] or "[0]*12")

        # Get all other patterns and calculate similarity
        cursor = self.db.execute(
            "SELECT pattern_id, onset_grid, pitch_classes FROM patterns WHERE pattern_id != ?",
            (pattern_id,),
        )

        similar = []
        for row in cursor.fetchall():
            other_onset = set(
                i for i, v in enumerate(json.loads(row["onset_grid"] or "[]")) if v
            )
            other_pitch = json.loads(row["pitch_classes"] or "[0]*12")

            # Calculate Jaccard similarity for rhythm
            if target_onset or other_onset:
                rhythm_sim = len(target_onset & other_onset) / len(target_onset | other_onset)
            else:
                rhythm_sim = 1.0

            # Calculate cosine similarity for pitch classes
            pitch_sim = self._cosine_similarity(target_pitch, other_pitch)

            # Combined similarity
            combined = (rhythm_sim + pitch_sim) / 2

            if combined >= threshold:
                similar.append((row["pattern_id"], combined))

        # Sort by similarity descending
        similar.sort(key=lambda x: x[1], reverse=True)

        return similar[:limit]

    def _cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(v1) != len(v2):
            return 0.0

        dot_product = sum(a * b for a, b in zip(v1, v2))
        mag1 = sum(a * a for a in v1) ** 0.5
        mag2 = sum(a * a for a in v2) ** 0.5

        if mag1 == 0 or mag2 == 0:
            return 1.0 if mag1 == mag2 else 0.0

        return dot_product / (mag1 * mag2)

    def get_stats(self) -> dict:
        """Get overall pattern statistics.

        Returns:
            Dictionary with pattern counts and distributions.
        """
        stats = {}

        # Total patterns
        cursor = self.db.execute("SELECT COUNT(*) FROM patterns")
        stats["total_patterns"] = cursor.fetchone()[0]

        # Total instances
        cursor = self.db.execute("SELECT COUNT(*) FROM pattern_instances")
        stats["total_instances"] = cursor.fetchone()[0]

        # Patterns by bar count
        cursor = self.db.execute(
            """
            SELECT num_bars, COUNT(*) as count
            FROM patterns
            GROUP BY num_bars
            ORDER BY num_bars
            """
        )
        stats["patterns_by_bars"] = {row["num_bars"]: row["count"] for row in cursor.fetchall()}

        # Most common patterns
        cursor = self.db.execute(
            """
            SELECT pattern_id, occurrence_count
            FROM patterns
            ORDER BY occurrence_count DESC
            LIMIT 10
            """
        )
        stats["most_common"] = [
            {"pattern_id": row["pattern_id"], "count": row["occurrence_count"]}
            for row in cursor.fetchall()
        ]

        return stats


def search_patterns(
    db: Database,
    rhythm_hash: str | None = None,
    pitch_hash: str | None = None,
    artist: str | None = None,
    genre: str | None = None,
    min_occurrences: int = 1,
    limit: int = 50,
) -> SearchResults:
    """Convenience function for pattern search.

    Args:
        db: Database connection.
        rhythm_hash: Exact rhythm hash to match.
        pitch_hash: Exact pitch hash to match.
        artist: Filter by artist name.
        genre: Filter by genre.
        min_occurrences: Minimum occurrence count.
        limit: Maximum results.

    Returns:
        SearchResults with matching patterns.
    """
    query = PatternQuery(
        rhythm_hash=rhythm_hash,
        pitch_hash=pitch_hash,
        artist=artist,
        genre=genre,
        min_occurrences=min_occurrences,
        limit=limit,
    )

    search = PatternSearch(db)
    return search.search(query)
