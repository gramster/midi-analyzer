"""SQLite database schema and migration system."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

# Schema version - increment when schema changes
SCHEMA_VERSION = 1

# SQL statements for creating tables
CREATE_TABLES = """
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Songs table: one row per analyzed MIDI file
CREATE TABLE IF NOT EXISTS songs (
    song_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    file_hash TEXT,
    ticks_per_beat INTEGER NOT NULL,
    total_bars INTEGER DEFAULT 0,
    total_beats REAL DEFAULT 0,
    detected_key TEXT,
    detected_mode TEXT,
    swing_style TEXT,
    swing_ratio REAL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Song metadata: artist, title, genre, tags
CREATE TABLE IF NOT EXISTS song_metadata (
    song_id TEXT PRIMARY KEY REFERENCES songs(song_id) ON DELETE CASCADE,
    artist TEXT,
    title TEXT,
    genre TEXT,
    album TEXT,
    year INTEGER,
    source TEXT,
    confidence REAL DEFAULT 0,
    musicbrainz_id TEXT,
    tags TEXT  -- JSON array
);

-- Tempo changes within songs
CREATE TABLE IF NOT EXISTS tempo_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id TEXT NOT NULL REFERENCES songs(song_id) ON DELETE CASCADE,
    tick INTEGER NOT NULL,
    beat REAL NOT NULL,
    tempo_bpm REAL NOT NULL,
    microseconds_per_beat INTEGER
);

-- Time signature changes
CREATE TABLE IF NOT EXISTS time_signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id TEXT NOT NULL REFERENCES songs(song_id) ON DELETE CASCADE,
    tick INTEGER NOT NULL,
    beat REAL NOT NULL,
    bar INTEGER NOT NULL,
    numerator INTEGER NOT NULL,
    denominator INTEGER NOT NULL
);

-- Tracks within songs
CREATE TABLE IF NOT EXISTS tracks (
    track_id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id TEXT NOT NULL REFERENCES songs(song_id) ON DELETE CASCADE,
    track_number INTEGER NOT NULL,
    name TEXT,
    channel INTEGER,
    instrument_name TEXT,
    instrument_program INTEGER,
    is_drum_track INTEGER DEFAULT 0,
    note_count INTEGER DEFAULT 0,
    UNIQUE(song_id, track_number)
);

-- Track features (analysis results)
CREATE TABLE IF NOT EXISTS track_features (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    note_density REAL,
    polyphony_ratio REAL,
    syncopation_score REAL,
    repetition_score REAL,
    pitch_class_entropy REAL,
    pitch_range INTEGER,
    median_pitch INTEGER,
    avg_velocity REAL,
    velocity_variance REAL,
    avg_duration_beats REAL
);

-- Track role probabilities
CREATE TABLE IF NOT EXISTS track_roles (
    track_id INTEGER PRIMARY KEY REFERENCES tracks(track_id) ON DELETE CASCADE,
    primary_role TEXT,
    drums_prob REAL DEFAULT 0,
    bass_prob REAL DEFAULT 0,
    chords_prob REAL DEFAULT 0,
    pad_prob REAL DEFAULT 0,
    lead_prob REAL DEFAULT 0,
    arp_prob REAL DEFAULT 0,
    other_prob REAL DEFAULT 0
);

-- Patterns (deduplicated by fingerprint)
CREATE TABLE IF NOT EXISTS patterns (
    pattern_id TEXT PRIMARY KEY,  -- Hash of combined fingerprint
    pattern_type TEXT NOT NULL,  -- 'rhythm', 'pitch', 'combined'
    num_bars INTEGER NOT NULL,
    grid_size INTEGER,
    -- Rhythm fingerprint
    onset_grid TEXT,  -- JSON array
    accent_grid TEXT,  -- JSON array
    rhythm_hash TEXT,
    -- Pitch fingerprint
    intervals TEXT,  -- JSON array
    pitch_classes TEXT,  -- JSON array
    contour TEXT,  -- JSON array
    range_semitones INTEGER,
    mean_pitch REAL,
    pitch_hash TEXT,
    -- Metadata
    occurrence_count INTEGER DEFAULT 1,
    first_seen_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Pattern instances (occurrences of patterns in tracks)
CREATE TABLE IF NOT EXISTS pattern_instances (
    instance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_id TEXT NOT NULL REFERENCES patterns(pattern_id) ON DELETE CASCADE,
    track_id INTEGER NOT NULL REFERENCES tracks(track_id) ON DELETE CASCADE,
    start_bar INTEGER NOT NULL,
    end_bar INTEGER NOT NULL,
    transposition INTEGER DEFAULT 0,  -- Semitones from original
    confidence REAL DEFAULT 1.0
);

-- API response cache for MusicBrainz/other services
CREATE TABLE IF NOT EXISTS api_cache (
    cache_key TEXT PRIMARY KEY,
    service TEXT NOT NULL,  -- 'musicbrainz', 'discogs', etc.
    request_url TEXT,
    response_data TEXT,  -- JSON
    status_code INTEGER,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_songs_path ON songs(source_path);
CREATE INDEX IF NOT EXISTS idx_songs_key ON songs(detected_key);
CREATE INDEX IF NOT EXISTS idx_metadata_artist ON song_metadata(artist);
CREATE INDEX IF NOT EXISTS idx_metadata_genre ON song_metadata(genre);
CREATE INDEX IF NOT EXISTS idx_tracks_song ON tracks(song_id);
CREATE INDEX IF NOT EXISTS idx_tracks_role ON track_roles(primary_role);
CREATE INDEX IF NOT EXISTS idx_patterns_rhythm ON patterns(rhythm_hash);
CREATE INDEX IF NOT EXISTS idx_patterns_pitch ON patterns(pitch_hash);
CREATE INDEX IF NOT EXISTS idx_patterns_type ON patterns(pattern_type, num_bars);
CREATE INDEX IF NOT EXISTS idx_instances_pattern ON pattern_instances(pattern_id);
CREATE INDEX IF NOT EXISTS idx_instances_track ON pattern_instances(track_id);
CREATE INDEX IF NOT EXISTS idx_tempo_song ON tempo_events(song_id);
CREATE INDEX IF NOT EXISTS idx_timesig_song ON time_signatures(song_id);
CREATE INDEX IF NOT EXISTS idx_cache_service ON api_cache(service, expires_at);
"""


class Database:
    """SQLite database connection and schema management."""

    def __init__(self, db_path: str | Path) -> None:
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file. Use ':memory:' for in-memory.
        """
        self.db_path = Path(db_path) if db_path != ":memory:" else db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_path),
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            self._conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Database:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()

    def execute(self, sql: str, params: tuple | dict | None = None) -> sqlite3.Cursor:
        """Execute a SQL statement.

        Args:
            sql: SQL statement.
            params: Query parameters.

        Returns:
            Cursor with results.
        """
        if params is None:
            return self.connection.execute(sql)
        return self.connection.execute(sql, params)

    def executemany(
        self, sql: str, params_list: list[tuple | dict]
    ) -> sqlite3.Cursor:
        """Execute a SQL statement with multiple parameter sets.

        Args:
            sql: SQL statement.
            params_list: List of parameter sets.

        Returns:
            Cursor.
        """
        return self.connection.executemany(sql, params_list)

    def commit(self) -> None:
        """Commit current transaction."""
        self.connection.commit()

    def get_schema_version(self) -> int:
        """Get current schema version from database.

        Returns:
            Current version number, or 0 if not initialized.
        """
        try:
            cursor = self.execute(
                "SELECT MAX(version) FROM schema_version"
            )
            row = cursor.fetchone()
            return row[0] if row and row[0] else 0
        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return 0

    def initialize_schema(self) -> None:
        """Create all tables if they don't exist."""
        self.connection.executescript(CREATE_TABLES)
        self.commit()

        # Record schema version if not present
        current = self.get_schema_version()
        if current < SCHEMA_VERSION:
            self.execute(
                "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,),
            )
            self.commit()

    def needs_migration(self) -> bool:
        """Check if database needs schema migration.

        Returns:
            True if migration is needed.
        """
        return self.get_schema_version() < SCHEMA_VERSION


def create_database(db_path: str | Path) -> Database:
    """Create and initialize a new database.

    Args:
        db_path: Path to database file.

    Returns:
        Initialized Database instance.
    """
    db = Database(db_path)
    db.initialize_schema()
    return db


def open_database(db_path: str | Path) -> Database:
    """Open an existing database.

    Args:
        db_path: Path to database file.

    Returns:
        Database instance.

    Raises:
        FileNotFoundError: If database file doesn't exist.
    """
    path = Path(db_path)
    if db_path != ":memory:" and not path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    db = Database(db_path)

    if db.needs_migration():
        raise RuntimeError(
            f"Database schema version {db.get_schema_version()} "
            f"needs migration to version {SCHEMA_VERSION}"
        )

    return db
