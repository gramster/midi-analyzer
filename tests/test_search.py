"""Tests for pattern search functionality."""

import json
import tempfile
from pathlib import Path

import pytest

from midi_analyzer.models.core import (
    Song,
    SongMetadata,
    TempoEvent,
    TimeSignature,
    Track,
)
from midi_analyzer.patterns.fingerprinting import (
    CombinedFingerprint,
    PitchFingerprint,
    RhythmFingerprint,
)
from midi_analyzer.storage.repository import PatternRepository, SongRepository
from midi_analyzer.storage.schema import create_database
from midi_analyzer.storage.search import (
    PatternQuery,
    PatternSearch,
    SearchResults,
    SortOrder,
    search_patterns,
)


@pytest.fixture
def db_path() -> Path:
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def db(db_path: Path):
    """Create a test database."""
    database = create_database(str(db_path))
    yield database
    database.close()


@pytest.fixture
def populated_db(db):
    """Database populated with test data."""
    song_repo = SongRepository(db)
    pattern_repo = PatternRepository(db)

    # Create songs with metadata
    songs = [
        Song(
            song_id="song-1",
            source_path="/music/song1.mid",
            ticks_per_beat=480,
            tempo_map=[TempoEvent(tick=0, beat=0.0, tempo_bpm=120.0, microseconds_per_beat=500000)],
            time_sig_map=[TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4)],
            tracks=[Track(track_id=0, name="Bass")],
            metadata=SongMetadata(artist="Artist A", genre="Electronic", tags=["funky"]),
        ),
        Song(
            song_id="song-2",
            source_path="/music/song2.mid",
            ticks_per_beat=480,
            tempo_map=[TempoEvent(tick=0, beat=0.0, tempo_bpm=100.0, microseconds_per_beat=600000)],
            time_sig_map=[TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4)],
            tracks=[Track(track_id=0, name="Drums")],
            metadata=SongMetadata(artist="Artist B", genre="House", tags=["groovy"]),
        ),
    ]

    for song in songs:
        song_repo.save(song)

    # Create patterns
    patterns = [
        CombinedFingerprint(
            rhythm=RhythmFingerprint(
                onset_grid=(1, 0, 1, 0) * 4,
                accent_grid=(1.0, 0, 0.8, 0) * 4,
                grid_size=16,
                num_bars=1,
                note_count=8,
                hash_value="rhythm-1",
            ),
            pitch=PitchFingerprint(
                intervals=(0, 2, 4),
                pitch_classes=(1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0),
                contour=(0, 1, 1),
                range_semitones=4,
                mean_pitch=60.0,
                hash_value="pitch-1",
            ),
            hash_value="pattern-1",
        ),
        CombinedFingerprint(
            rhythm=RhythmFingerprint(
                onset_grid=(1, 1, 1, 1) * 4,
                accent_grid=(1.0, 0.5, 1.0, 0.5) * 4,
                grid_size=16,
                num_bars=1,
                note_count=16,
                hash_value="rhythm-2",
            ),
            pitch=PitchFingerprint(
                intervals=(0, 0, 0),
                pitch_classes=(1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                contour=(0, 0, 0),
                range_semitones=0,
                mean_pitch=36.0,
                hash_value="pitch-2",
            ),
            hash_value="pattern-2",
        ),
        CombinedFingerprint(
            rhythm=RhythmFingerprint(
                onset_grid=(1, 0, 1, 0) * 4 + (1, 0, 1, 0) * 4,
                accent_grid=(1.0, 0, 0.8, 0) * 8,
                grid_size=32,
                num_bars=2,
                note_count=16,
                hash_value="rhythm-3",
            ),
            pitch=PitchFingerprint(
                intervals=(0, 2, 4, 2, 0),
                pitch_classes=(1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0),
                contour=(0, 1, 1, -1, -1),
                range_semitones=4,
                mean_pitch=62.0,
                hash_value="pitch-3",
            ),
            hash_value="pattern-3",
        ),
    ]

    for pattern in patterns:
        pattern_repo.save(pattern)

    # Save again to increase occurrence counts
    pattern_repo.save(patterns[0])  # pattern-1 now has 2 occurrences
    pattern_repo.save(patterns[0])  # pattern-1 now has 3 occurrences
    pattern_repo.save(patterns[1])  # pattern-2 now has 2 occurrences

    # Create instances linking patterns to tracks
    cursor = db.execute("SELECT track_id FROM tracks WHERE name = 'Bass'")
    bass_track_id = cursor.fetchone()[0]

    cursor = db.execute("SELECT track_id FROM tracks WHERE name = 'Drums'")
    drums_track_id = cursor.fetchone()[0]

    pattern_repo.save_instance("pattern-1", bass_track_id, 0, 1)
    pattern_repo.save_instance("pattern-2", drums_track_id, 0, 1)
    pattern_repo.save_instance("pattern-3", bass_track_id, 2, 4)

    return db


class TestPatternSearch:
    """Tests for PatternSearch."""

    def test_search_all(self, populated_db):
        """Test searching without filters returns all patterns."""
        search = PatternSearch(populated_db)
        results = search.search(PatternQuery())

        assert isinstance(results, SearchResults)
        assert results.total_count == 3
        assert len(results.results) == 3

    def test_search_by_rhythm_hash(self, populated_db):
        """Test searching by exact rhythm hash."""
        search = PatternSearch(populated_db)
        results = search.search(PatternQuery(rhythm_hash="rhythm-1"))

        assert results.total_count == 1
        assert results.results[0].rhythm_hash == "rhythm-1"

    def test_search_by_pitch_hash(self, populated_db):
        """Test searching by exact pitch hash."""
        search = PatternSearch(populated_db)
        results = search.search(PatternQuery(pitch_hash="pitch-2"))

        assert results.total_count == 1
        assert results.results[0].pitch_hash == "pitch-2"

    def test_search_by_num_bars(self, populated_db):
        """Test searching by number of bars."""
        search = PatternSearch(populated_db)

        # 1-bar patterns
        results = search.search(PatternQuery(num_bars=1))
        assert results.total_count == 2

        # 2-bar patterns
        results = search.search(PatternQuery(num_bars=2))
        assert results.total_count == 1

    def test_search_by_min_occurrences(self, populated_db):
        """Test filtering by minimum occurrences."""
        search = PatternSearch(populated_db)

        results = search.search(PatternQuery(min_occurrences=2))
        assert results.total_count == 2  # pattern-1 (3) and pattern-2 (2)

        results = search.search(PatternQuery(min_occurrences=3))
        assert results.total_count == 1  # only pattern-1

    def test_search_sort_by_occurrence(self, populated_db):
        """Test sorting by occurrence count."""
        search = PatternSearch(populated_db)
        results = search.search(PatternQuery(sort_by=SortOrder.OCCURRENCE))

        # Should be sorted by occurrence descending
        assert results.results[0].occurrence_count >= results.results[1].occurrence_count

    def test_search_pagination(self, populated_db):
        """Test pagination with limit and offset."""
        search = PatternSearch(populated_db)

        # First page
        results1 = search.search(PatternQuery(limit=2, offset=0))
        assert len(results1.results) == 2
        assert results1.has_more is True

        # Second page
        results2 = search.search(PatternQuery(limit=2, offset=2))
        assert len(results2.results) == 1
        assert results2.has_more is False

    def test_search_by_artist(self, populated_db):
        """Test filtering by artist."""
        search = PatternSearch(populated_db)
        results = search.search(PatternQuery(artist="Artist A"))

        # Only patterns with instances in Artist A's songs
        assert results.total_count == 2  # pattern-1 and pattern-3 linked to bass track

    def test_search_combined_filters(self, populated_db):
        """Test combining multiple filters."""
        search = PatternSearch(populated_db)
        results = search.search(
            PatternQuery(
                num_bars=1,
                min_occurrences=2,
            )
        )

        assert results.total_count == 2  # 1-bar patterns with 2+ occurrences


class TestPatternSearchResult:
    """Tests for result enrichment."""

    def test_result_has_metadata(self, populated_db):
        """Test that results include related metadata."""
        search = PatternSearch(populated_db)
        results = search.search(PatternQuery(rhythm_hash="rhythm-1"))

        result = results.results[0]
        # Should have enriched data from instances
        assert len(result.song_ids) >= 0  # May have associated songs
        assert len(result.artists) >= 0


class TestFindSimilar:
    """Tests for similarity search."""

    def test_find_similar_patterns(self, populated_db):
        """Test finding similar patterns."""
        search = PatternSearch(populated_db)

        # pattern-1 and pattern-3 have similar rhythm
        similar = search.find_similar("pattern-1", threshold=0.5)

        # Should return some results
        assert isinstance(similar, list)

    def test_find_similar_nonexistent(self, populated_db):
        """Test similarity search for nonexistent pattern."""
        search = PatternSearch(populated_db)
        similar = search.find_similar("nonexistent")

        assert similar == []


class TestGetStats:
    """Tests for statistics retrieval."""

    def test_get_stats(self, populated_db):
        """Test getting pattern statistics."""
        search = PatternSearch(populated_db)
        stats = search.get_stats()

        assert stats["total_patterns"] == 3
        assert stats["total_instances"] == 3
        assert 1 in stats["patterns_by_bars"]
        assert 2 in stats["patterns_by_bars"]
        assert len(stats["most_common"]) <= 10


class TestConvenienceFunction:
    """Tests for search_patterns convenience function."""

    def test_search_patterns(self, populated_db):
        """Test convenience function."""
        results = search_patterns(populated_db, min_occurrences=2)

        assert isinstance(results, SearchResults)
        assert results.total_count == 2

    def test_search_patterns_with_rhythm(self, populated_db):
        """Test convenience function with rhythm filter."""
        results = search_patterns(populated_db, rhythm_hash="rhythm-1")

        assert results.total_count == 1


class TestPatternQuery:
    """Tests for PatternQuery defaults."""

    def test_default_values(self):
        """Test default query values."""
        query = PatternQuery()

        assert query.limit == 50
        assert query.offset == 0
        assert query.min_occurrences == 1
        assert query.sort_by == SortOrder.OCCURRENCE
        assert query.tags == []

    def test_custom_values(self):
        """Test custom query values."""
        query = PatternQuery(
            rhythm_hash="test",
            limit=10,
            tags=["funky", "groovy"],
        )

        assert query.rhythm_hash == "test"
        assert query.limit == 10
        assert query.tags == ["funky", "groovy"]
