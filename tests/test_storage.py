"""Tests for database schema."""

import tempfile
from pathlib import Path

import pytest

from midi_analyzer.storage.schema import (
    SCHEMA_VERSION,
    Database,
    create_database,
    open_database,
)


class TestDatabase:
    """Tests for Database class."""

    def test_create_in_memory(self) -> None:
        """Test creating an in-memory database."""
        db = Database(":memory:")
        db.initialize_schema()

        # Should be able to query tables
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        assert "songs" in tables
        assert "tracks" in tables
        assert "patterns" in tables
        assert "pattern_instances" in tables

        db.close()

    def test_schema_version(self) -> None:
        """Test schema version tracking."""
        db = Database(":memory:")
        db.initialize_schema()

        version = db.get_schema_version()
        assert version == SCHEMA_VERSION

        db.close()

    def test_context_manager(self) -> None:
        """Test database as context manager."""
        with Database(":memory:") as db:
            db.initialize_schema()
            assert db.get_schema_version() == SCHEMA_VERSION

    def test_foreign_keys_enabled(self) -> None:
        """Test that foreign keys are enforced."""
        with Database(":memory:") as db:
            db.initialize_schema()

            # Try to insert a track with non-existent song_id
            with pytest.raises(Exception):  # IntegrityError
                db.execute(
                    "INSERT INTO tracks (song_id, track_number, name) VALUES (?, ?, ?)",
                    ("nonexistent", 0, "Test"),
                )
                db.commit()

    def test_execute_with_params(self) -> None:
        """Test execute with parameters."""
        with Database(":memory:") as db:
            db.initialize_schema()

            # Insert a song
            db.execute(
                """INSERT INTO songs (song_id, source_path, filename, ticks_per_beat)
                   VALUES (?, ?, ?, ?)""",
                ("test123", "/path/to/song.mid", "song.mid", 480),
            )
            db.commit()

            # Query it back
            cursor = db.execute(
                "SELECT * FROM songs WHERE song_id = ?", ("test123",)
            )
            row = cursor.fetchone()

            assert row["song_id"] == "test123"
            assert row["ticks_per_beat"] == 480

    def test_executemany(self) -> None:
        """Test executemany for batch inserts."""
        with Database(":memory:") as db:
            db.initialize_schema()

            # Insert a song first
            db.execute(
                """INSERT INTO songs (song_id, source_path, filename, ticks_per_beat)
                   VALUES (?, ?, ?, ?)""",
                ("song1", "/path/song.mid", "song.mid", 480),
            )

            # Batch insert tempo events
            events = [
                ("song1", 0, 0.0, 120.0),
                ("song1", 480, 1.0, 140.0),
                ("song1", 960, 2.0, 130.0),
            ]
            db.executemany(
                """INSERT INTO tempo_events (song_id, tick, beat, tempo_bpm)
                   VALUES (?, ?, ?, ?)""",
                events,
            )
            db.commit()

            cursor = db.execute(
                "SELECT COUNT(*) FROM tempo_events WHERE song_id = ?",
                ("song1",),
            )
            count = cursor.fetchone()[0]
            assert count == 3


class TestSchemaStructure:
    """Tests for schema table structures."""

    @pytest.fixture
    def db(self) -> Database:
        """Create a test database."""
        db = Database(":memory:")
        db.initialize_schema()
        yield db
        db.close()

    def test_songs_table(self, db: Database) -> None:
        """Test songs table structure."""
        db.execute(
            """INSERT INTO songs
               (song_id, source_path, filename, ticks_per_beat, 
                total_bars, detected_key, swing_style)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("s1", "/path.mid", "path.mid", 480, 32, "C major", "straight"),
        )
        db.commit()

        cursor = db.execute("SELECT * FROM songs WHERE song_id = 's1'")
        row = cursor.fetchone()

        assert row["detected_key"] == "C major"
        assert row["swing_style"] == "straight"
        assert row["total_bars"] == 32

    def test_track_features_table(self, db: Database) -> None:
        """Test track features table."""
        # Create song and track first
        db.execute(
            """INSERT INTO songs (song_id, source_path, filename, ticks_per_beat)
               VALUES (?, ?, ?, ?)""",
            ("s1", "/p.mid", "p.mid", 480),
        )
        db.execute(
            """INSERT INTO tracks (song_id, track_number, name)
               VALUES (?, ?, ?)""",
            ("s1", 0, "Lead"),
        )
        track_id = db.execute(
            "SELECT track_id FROM tracks WHERE song_id = ?", ("s1",)
        ).fetchone()[0]

        # Insert features
        db.execute(
            """INSERT INTO track_features 
               (track_id, note_density, polyphony_ratio, syncopation_score)
               VALUES (?, ?, ?, ?)""",
            (track_id, 4.5, 0.3, 0.6),
        )
        db.commit()

        cursor = db.execute(
            "SELECT * FROM track_features WHERE track_id = ?", (track_id,)
        )
        row = cursor.fetchone()

        assert row["note_density"] == 4.5
        assert row["polyphony_ratio"] == 0.3

    def test_patterns_table(self, db: Database) -> None:
        """Test patterns table."""
        db.execute(
            """INSERT INTO patterns 
               (pattern_id, pattern_type, num_bars, rhythm_hash, pitch_hash)
               VALUES (?, ?, ?, ?, ?)""",
            ("p1", "combined", 1, "abc123", "def456"),
        )
        db.commit()

        cursor = db.execute("SELECT * FROM patterns WHERE pattern_id = 'p1'")
        row = cursor.fetchone()

        assert row["pattern_type"] == "combined"
        assert row["rhythm_hash"] == "abc123"

    def test_cascade_delete(self, db: Database) -> None:
        """Test cascading deletes work correctly."""
        # Create song with track
        db.execute(
            """INSERT INTO songs (song_id, source_path, filename, ticks_per_beat)
               VALUES (?, ?, ?, ?)""",
            ("s1", "/p.mid", "p.mid", 480),
        )
        db.execute(
            """INSERT INTO tracks (song_id, track_number, name)
               VALUES (?, ?, ?)""",
            ("s1", 0, "Track"),
        )
        db.commit()

        # Verify track exists
        cursor = db.execute("SELECT COUNT(*) FROM tracks WHERE song_id = 's1'")
        assert cursor.fetchone()[0] == 1

        # Delete song
        db.execute("DELETE FROM songs WHERE song_id = 's1'")
        db.commit()

        # Track should be deleted
        cursor = db.execute("SELECT COUNT(*) FROM tracks WHERE song_id = 's1'")
        assert cursor.fetchone()[0] == 0


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_database(self) -> None:
        """Test create_database function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = create_database(db_path)

            assert db_path.exists()
            assert db.get_schema_version() == SCHEMA_VERSION

            db.close()

    def test_open_database(self) -> None:
        """Test open_database function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create it first
            db = create_database(db_path)
            db.close()

            # Now open it
            db = open_database(db_path)
            assert db.get_schema_version() == SCHEMA_VERSION
            db.close()

    def test_open_nonexistent_database(self) -> None:
        """Test opening non-existent database raises error."""
        with pytest.raises(FileNotFoundError):
            open_database("/nonexistent/path/db.sqlite")

    def test_open_in_memory(self) -> None:
        """Test opening in-memory database."""
        # In-memory doesn't check for file existence
        db = Database(":memory:")
        db.initialize_schema()
        assert db.get_schema_version() == SCHEMA_VERSION
        db.close()


class TestIndexes:
    """Tests for index existence."""

    def test_indexes_created(self) -> None:
        """Test that all expected indexes are created."""
        with Database(":memory:") as db:
            db.initialize_schema()

            cursor = db.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
            indexes = [row[0] for row in cursor.fetchall()]

            assert "idx_songs_path" in indexes
            assert "idx_patterns_rhythm" in indexes
            assert "idx_patterns_pitch" in indexes
            assert "idx_instances_pattern" in indexes
