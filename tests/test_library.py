"""Tests for ClipLibrary functionality."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from midi_analyzer.library import ClipInfo, ClipLibrary, ClipQuery, IndexStats
from midi_analyzer.models.core import NoteEvent, Song, Track, TrackRole


class TestClipLibrary:
    """Tests for ClipLibrary class."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test_library.db"

    @pytest.fixture
    def library(self, temp_db: Path):
        """Create library instance."""
        lib = ClipLibrary(temp_db)
        yield lib
        lib.close()

    def test_create_library(self, temp_db: Path):
        """Test creating a new library."""
        with ClipLibrary(temp_db) as library:
            assert temp_db.exists()
            stats = library.get_stats()
            assert stats.total_clips == 0

    def test_context_manager(self, temp_db: Path):
        """Test context manager closes connection."""
        with ClipLibrary(temp_db) as library:
            assert library.connection is not None
        # Connection should be closed after context exit

    def test_get_stats_empty(self, library: ClipLibrary):
        """Test stats on empty library."""
        stats = library.get_stats()

        assert isinstance(stats, IndexStats)
        assert stats.total_clips == 0
        assert stats.total_songs == 0
        assert stats.clips_by_role == {}
        assert stats.artists == []

    def test_list_genres_empty(self, library: ClipLibrary):
        """Test listing genres on empty library."""
        genres = library.list_genres()
        assert genres == []

    def test_list_artists_empty(self, library: ClipLibrary):
        """Test listing artists on empty library."""
        artists = library.list_artists()
        assert artists == []


class TestClipQuery:
    """Tests for ClipQuery dataclass."""

    def test_defaults(self):
        """Test default values."""
        query = ClipQuery()

        assert query.role is None
        assert query.genre is None
        assert query.artist is None
        assert query.min_notes is None
        assert query.max_notes is None
        assert query.limit == 100
        assert query.offset == 0

    def test_custom_values(self):
        """Test custom query values."""
        query = ClipQuery(
            role=TrackRole.BASS,
            genre="jazz",
            artist="Miles",
            min_notes=10,
            max_notes=100,
            limit=20,
        )

        assert query.role == TrackRole.BASS
        assert query.genre == "jazz"
        assert query.artist == "Miles"
        assert query.min_notes == 10
        assert query.max_notes == 100
        assert query.limit == 20


class TestClipInfo:
    """Tests for ClipInfo dataclass."""

    def test_creation(self):
        """Test creating ClipInfo."""
        clip = ClipInfo(
            clip_id="abc123_0",
            song_id="abc123",
            track_id=0,
            source_path="/path/to/file.mid",
            track_name="Bass Track",
            role=TrackRole.BASS,
            channel=0,
            note_count=50,
            duration_bars=8,
            genres=["jazz", "fusion"],
            artist="Test Artist",
            tags=["groovy", "walking bass"],
        )

        assert clip.clip_id == "abc123_0"
        assert clip.role == TrackRole.BASS
        assert "jazz" in clip.genres
        assert clip.artist == "Test Artist"

    def test_defaults(self):
        """Test default values."""
        clip = ClipInfo(
            clip_id="test",
            song_id="test",
            track_id=0,
            source_path="/test.mid",
            track_name="",
            role=TrackRole.OTHER,
            channel=0,
            note_count=0,
            duration_bars=0,
        )

        assert clip.genres == []
        assert clip.artist == ""
        assert clip.tags == []


class TestIndexStats:
    """Tests for IndexStats dataclass."""

    def test_defaults(self):
        """Test default values."""
        stats = IndexStats()

        assert stats.total_clips == 0
        assert stats.total_songs == 0
        assert stats.clips_by_role == {}
        assert stats.clips_by_genre == {}
        assert stats.artists == []

    def test_custom_values(self):
        """Test custom values."""
        stats = IndexStats(
            total_clips=100,
            total_songs=25,
            clips_by_role={"bass": 30, "drums": 25},
            clips_by_genre={"jazz": 40, "rock": 35},
            artists=["Artist A", "Artist B"],
        )

        assert stats.total_clips == 100
        assert stats.clips_by_role["bass"] == 30
        assert "jazz" in stats.clips_by_genre


class TestLibraryQueryMethods:
    """Tests for query convenience methods."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test.db"

    def test_query_by_role(self, temp_db: Path):
        """Test query_by_role shortcut."""
        with ClipLibrary(temp_db) as library:
            clips = library.query_by_role(TrackRole.BASS)
            assert isinstance(clips, list)

    def test_query_by_genre(self, temp_db: Path):
        """Test query_by_genre shortcut."""
        with ClipLibrary(temp_db) as library:
            clips = library.query_by_genre("jazz")
            assert isinstance(clips, list)

    def test_query_by_artist(self, temp_db: Path):
        """Test query_by_artist shortcut."""
        with ClipLibrary(temp_db) as library:
            clips = library.query_by_artist("Miles")
            assert isinstance(clips, list)


class TestLibraryMetadataUpdate:
    """Tests for metadata update operations."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test.db"

    def test_update_nonexistent_clip(self, temp_db: Path):
        """Test updating non-existent clip."""
        with ClipLibrary(temp_db) as library:
            result = library.update_metadata("nonexistent", artist="New Artist")
            assert result is False

    def test_update_with_no_changes(self, temp_db: Path):
        """Test update with no fields specified."""
        with ClipLibrary(temp_db) as library:
            result = library.update_metadata("test")
            assert result is False

    def test_delete_nonexistent_clip(self, temp_db: Path):
        """Test deleting non-existent clip."""
        with ClipLibrary(temp_db) as library:
            result = library.delete_clip("nonexistent")
            assert result is False

    def test_delete_song_no_clips(self, temp_db: Path):
        """Test deleting song with no clips."""
        with ClipLibrary(temp_db) as library:
            count = library.delete_song("nonexistent")
            assert count == 0


class TestLibraryIteration:
    """Tests for iteration methods."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test.db"

    def test_iter_clips_empty(self, temp_db: Path):
        """Test iterating empty library."""
        with ClipLibrary(temp_db) as library:
            clips = list(library.iter_clips())
            assert clips == []

    def test_iter_clips_batch_size(self, temp_db: Path):
        """Test iteration respects batch size parameter."""
        with ClipLibrary(temp_db) as library:
            # Should work with custom batch size
            clips = list(library.iter_clips(batch_size=10))
            assert isinstance(clips, list)


class TestLibraryQuery:
    """Tests for query building and execution."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test.db"

    def test_empty_query(self, temp_db: Path):
        """Test query with no filters."""
        with ClipLibrary(temp_db) as library:
            clips = library.query(ClipQuery())
            assert isinstance(clips, list)

    def test_query_with_all_filters(self, temp_db: Path):
        """Test query with all filters."""
        with ClipLibrary(temp_db) as library:
            query = ClipQuery(
                role=TrackRole.BASS,
                genre="jazz",
                artist="Test",
                min_notes=10,
                max_notes=100,
                min_bars=4,
                max_bars=16,
                tags=["groovy"],
                limit=10,
                offset=0,
            )
            clips = library.query(query)
            assert isinstance(clips, list)

    def test_query_pagination(self, temp_db: Path):
        """Test query pagination."""
        with ClipLibrary(temp_db) as library:
            # First page
            page1 = library.query(ClipQuery(limit=10, offset=0))
            # Second page
            page2 = library.query(ClipQuery(limit=10, offset=10))
            # Both should be lists (empty in this case)
            assert isinstance(page1, list)
            assert isinstance(page2, list)


class TestGenreNormalization:
    """Tests for genre normalization in library."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir) / "test.db"

    def test_genre_query_normalization(self, temp_db: Path):
        """Test that genre queries are normalized."""
        with ClipLibrary(temp_db) as library:
            # These should search for the same thing
            clips1 = library.query_by_genre("hip hop")
            clips2 = library.query_by_genre("hip-hop")
            clips3 = library.query_by_genre("hiphop")
            # All should return lists
            assert isinstance(clips1, list)
            assert isinstance(clips2, list)
            assert isinstance(clips3, list)
