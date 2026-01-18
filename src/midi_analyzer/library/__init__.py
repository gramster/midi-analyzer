"""Clip library for indexing and querying tracks by genre, artist, and role."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from midi_analyzer.analysis.features import FeatureExtractor
from midi_analyzer.analysis.roles import classify_track_role
from midi_analyzer.ingest import parse_midi_file
from midi_analyzer.ingest.metadata import MetadataExtractor
from midi_analyzer.metadata.genres import GenreNormalizer, GenreResult, normalize_tag
from midi_analyzer.models.core import Song, Track, TrackRole

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


@dataclass
class ClipInfo:
    """Information about an indexed clip/track.

    Attributes:
        clip_id: Unique identifier for the clip.
        song_id: Parent song identifier.
        track_id: Track index within the song.
        source_path: Path to the source MIDI file.
        track_name: Name of the track.
        role: Detected track role (drums, bass, etc.).
        channel: MIDI channel.
        note_count: Number of notes in the track.
        duration_bars: Duration in bars.
        genres: Normalized genre tags.
        artist: Artist name.
        tags: Additional tags.
    """

    clip_id: str
    song_id: str
    track_id: int
    source_path: str
    track_name: str
    role: TrackRole
    channel: int
    note_count: int
    duration_bars: int
    genres: list[str] = field(default_factory=list)
    artist: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class ClipQuery:
    """Query parameters for clip search.

    Attributes:
        role: Filter by track role.
        genre: Filter by genre (normalized).
        artist: Filter by artist name (case-insensitive partial match).
        min_notes: Minimum note count.
        max_notes: Maximum note count.
        min_bars: Minimum duration in bars.
        max_bars: Maximum duration in bars.
        tags: Filter by tags (any match).
        limit: Maximum results to return.
        offset: Offset for pagination.
    """

    role: TrackRole | None = None
    genre: str | None = None
    artist: str | None = None
    min_notes: int | None = None
    max_notes: int | None = None
    min_bars: int | None = None
    max_bars: int | None = None
    tags: list[str] | None = None
    limit: int = 100
    offset: int = 0


@dataclass
class IndexStats:
    """Statistics about the clip library index.

    Attributes:
        total_clips: Total number of indexed clips.
        total_songs: Total number of indexed songs.
        clips_by_role: Count of clips per role.
        clips_by_genre: Count of clips per genre.
        artists: List of unique artists.
    """

    total_clips: int = 0
    total_songs: int = 0
    clips_by_role: dict[str, int] = field(default_factory=dict)
    clips_by_genre: dict[str, int] = field(default_factory=dict)
    artists: list[str] = field(default_factory=list)


class ClipLibrary:
    """Library for indexing and querying MIDI clips by various criteria.

    Example:
        library = ClipLibrary("clips.db")

        # Index a directory of MIDI files
        library.index_directory("/path/to/midis", genre="jazz", artist="Various")

        # Query for bass tracks from jazz songs
        clips = library.query(ClipQuery(role=TrackRole.BASS, genre="jazz"))

        # Load and export a clip
        track = library.load_track(clips[0])
        export_track(track, "bass_clip.mid")
    """

    def __init__(self, db_path: Path | str) -> None:
        """Initialize the clip library.

        Args:
            db_path: Path to the SQLite database.
        """
        self.db_path = Path(db_path)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        # Use WAL mode for better concurrent access
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._genre_normalizer = GenreNormalizer()
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        cursor = self.connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clips (
                clip_id TEXT PRIMARY KEY,
                song_id TEXT NOT NULL,
                track_id INTEGER NOT NULL,
                source_path TEXT NOT NULL,
                track_name TEXT,
                role TEXT NOT NULL,
                channel INTEGER NOT NULL,
                note_count INTEGER NOT NULL,
                duration_bars INTEGER NOT NULL,
                genres TEXT,
                artist TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_clips_role ON clips(role)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_clips_artist ON clips(artist)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_clips_song ON clips(song_id)
        """)

        self.connection.commit()

    def close(self) -> None:
        """Close the database connection."""
        self.connection.close()

    def __enter__(self) -> ClipLibrary:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.close()

    def index_file(
        self,
        file_path: Path | str,
        *,
        genres: list[str] | None = None,
        artist: str = "",
        tags: list[str] | None = None,
    ) -> list[ClipInfo]:
        """Index a single MIDI file.

        Args:
            file_path: Path to the MIDI file.
            genres: Genre tags for all tracks.
            artist: Artist name.
            tags: Additional tags.

        Returns:
            List of indexed clips.
        """
        file_path = Path(file_path)
        song = parse_midi_file(file_path)

        # Extract metadata from filename/path if not provided
        if not artist:
            extractor = MetadataExtractor()
            metadata = extractor.extract(file_path)
            artist = metadata.artist or ""

        # Normalize genres
        normalized_genres = []
        if genres:
            for g in genres:
                canonical = normalize_tag(g)
                if canonical and canonical not in normalized_genres:
                    normalized_genres.append(canonical)

        clips = []
        cursor = self.connection.cursor()
        feature_extractor = FeatureExtractor()

        for track in song.tracks:
            if not track.notes:
                continue

            # Extract features and classify role
            track.features = feature_extractor.extract_features(track, song.total_bars or 1)
            role_probs = classify_track_role(track)
            role = role_probs.primary_role()

            # Generate clip ID
            clip_id = f"{song.song_id}_{track.track_id}"

            clip = ClipInfo(
                clip_id=clip_id,
                song_id=song.song_id,
                track_id=track.track_id,
                source_path=str(file_path.resolve()),
                track_name=track.name,
                role=role,
                channel=track.channel,
                note_count=len(track.notes),
                duration_bars=song.total_bars,
                genres=normalized_genres,
                artist=artist,
                tags=tags or [],
            )

            # Insert into database
            cursor.execute(
                """INSERT OR REPLACE INTO clips
                   (clip_id, song_id, track_id, source_path, track_name,
                    role, channel, note_count, duration_bars, genres, artist, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    clip.clip_id,
                    clip.song_id,
                    clip.track_id,
                    clip.source_path,
                    clip.track_name,
                    clip.role.value,
                    clip.channel,
                    clip.note_count,
                    clip.duration_bars,
                    json.dumps(clip.genres),
                    clip.artist,
                    json.dumps(clip.tags),
                ),
            )

            clips.append(clip)

        self.connection.commit()

        return clips

    def index_directory(
        self,
        directory: Path | str,
        *,
        recursive: bool = True,
        genres: list[str] | None = None,
        artist: str = "",
        tags: list[str] | None = None,
        progress_callback: Callable[[int, int, str], None] | None = None,
        error_callback: Callable[[Path, Exception], None] | None = None,
    ) -> int:
        """Index all MIDI files in a directory.

        Args:
            directory: Directory to index.
            recursive: Whether to recurse into subdirectories.
            genres: Default genres for all files.
            artist: Default artist for all files.
            tags: Default tags for all files.
            progress_callback: Optional callback(current, total, filename).
            error_callback: Optional callback(file_path, exception) for errors.

        Returns:
            Number of clips indexed.
        """
        directory = Path(directory)
        pattern = "**/*.mid" if recursive else "*.mid"

        files = list(directory.glob(pattern))
        files.extend(directory.glob(pattern.replace(".mid", ".midi")))

        total_clips = 0
        for i, file_path in enumerate(files):
            try:
                clips = self.index_file(
                    file_path,
                    genres=genres,
                    artist=artist,
                    tags=tags,
                )
                total_clips += len(clips)

                if progress_callback:
                    progress_callback(i + 1, len(files), file_path.name)
            except Exception as e:
                # Report error if callback provided, otherwise skip silently
                if error_callback:
                    error_callback(file_path, e)
                continue

        return total_clips

    def query(self, query: ClipQuery) -> list[ClipInfo]:
        """Query clips matching the given criteria.

        Args:
            query: Query parameters.

        Returns:
            List of matching clips.
        """
        cursor = self.connection.cursor()

        sql = "SELECT * FROM clips WHERE 1=1"
        params: list = []

        if query.role:
            sql += " AND role = ?"
            params.append(query.role.value)

        if query.genre:
            # Normalize and search in genres JSON
            canonical = normalize_tag(query.genre) or query.genre
            sql += " AND genres LIKE ?"
            params.append(f'%"{canonical}"%')

        if query.artist:
            sql += " AND artist LIKE ?"
            params.append(f"%{query.artist}%")

        if query.min_notes is not None:
            sql += " AND note_count >= ?"
            params.append(query.min_notes)

        if query.max_notes is not None:
            sql += " AND note_count <= ?"
            params.append(query.max_notes)

        if query.min_bars is not None:
            sql += " AND duration_bars >= ?"
            params.append(query.min_bars)

        if query.max_bars is not None:
            sql += " AND duration_bars <= ?"
            params.append(query.max_bars)

        if query.tags:
            # Match any tag
            tag_conditions = []
            for tag in query.tags:
                tag_conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')
            sql += f" AND ({' OR '.join(tag_conditions)})"

        sql += f" ORDER BY note_count DESC LIMIT ? OFFSET ?"
        params.extend([query.limit, query.offset])

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        return [self._row_to_clip(row) for row in rows]

    def query_by_role(self, role: TrackRole, limit: int = 100) -> list[ClipInfo]:
        """Shortcut to query clips by role.

        Args:
            role: Track role to filter by.
            limit: Maximum results.

        Returns:
            List of matching clips.
        """
        return self.query(ClipQuery(role=role, limit=limit))

    def query_by_genre(self, genre: str, limit: int = 100) -> list[ClipInfo]:
        """Shortcut to query clips by genre.

        Args:
            genre: Genre to filter by.
            limit: Maximum results.

        Returns:
            List of matching clips.
        """
        return self.query(ClipQuery(genre=genre, limit=limit))

    def query_by_artist(self, artist: str, limit: int = 100) -> list[ClipInfo]:
        """Shortcut to query clips by artist.

        Args:
            artist: Artist name (partial match).
            limit: Maximum results.

        Returns:
            List of matching clips.
        """
        return self.query(ClipQuery(artist=artist, limit=limit))

    def load_track(self, clip: ClipInfo) -> Track:
        """Load the actual track data for a clip.

        Args:
            clip: Clip info to load.

        Returns:
            Track object with note data.
        """
        song = parse_midi_file(clip.source_path)

        for track in song.tracks:
            if track.track_id == clip.track_id:
                return track

        raise ValueError(f"Track {clip.track_id} not found in {clip.source_path}")

    def load_song(self, clip: ClipInfo) -> Song:
        """Load the complete song for a clip.

        Args:
            clip: Clip info to load.

        Returns:
            Song object.
        """
        return parse_midi_file(clip.source_path)

    def get_stats(self) -> IndexStats:
        """Get statistics about the library.

        Returns:
            Index statistics.
        """
        cursor = self.connection.cursor()

        # Total counts
        cursor.execute("SELECT COUNT(*) FROM clips")
        total_clips = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT song_id) FROM clips")
        total_songs = cursor.fetchone()[0]

        # Clips by role
        cursor.execute("SELECT role, COUNT(*) FROM clips GROUP BY role")
        clips_by_role = dict(cursor.fetchall())

        # Clips by genre (need to parse JSON)
        cursor.execute("SELECT genres FROM clips WHERE genres IS NOT NULL")
        genre_counts: dict[str, int] = {}
        for (genres_json,) in cursor.fetchall():
            genres = json.loads(genres_json) if genres_json else []
            for genre in genres:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1

        # Unique artists
        cursor.execute("SELECT DISTINCT artist FROM clips WHERE artist != ''")
        artists = [row[0] for row in cursor.fetchall()]

        return IndexStats(
            total_clips=total_clips,
            total_songs=total_songs,
            clips_by_role=clips_by_role,
            clips_by_genre=genre_counts,
            artists=sorted(artists),
        )

    def list_genres(self) -> list[str]:
        """List all genres in the library.

        Returns:
            Sorted list of genres.
        """
        stats = self.get_stats()
        return sorted(stats.clips_by_genre.keys())

    def list_artists(self) -> list[str]:
        """List all artists in the library.

        Returns:
            Sorted list of artists.
        """
        cursor = self.connection.cursor()
        cursor.execute("SELECT DISTINCT artist FROM clips WHERE artist != '' ORDER BY artist")
        return [row[0] for row in cursor.fetchall()]

    def delete_clip(self, clip_id: str) -> bool:
        """Delete a clip from the library.

        Args:
            clip_id: ID of clip to delete.

        Returns:
            True if deleted, False if not found.
        """
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM clips WHERE clip_id = ?", (clip_id,))
        self.connection.commit()
        return cursor.rowcount > 0

    def delete_song(self, song_id: str) -> int:
        """Delete all clips from a song.

        Args:
            song_id: ID of song to delete.

        Returns:
            Number of clips deleted.
        """
        cursor = self.connection.cursor()
        cursor.execute("DELETE FROM clips WHERE song_id = ?", (song_id,))
        self.connection.commit()
        return cursor.rowcount

    def update_metadata(
        self,
        clip_id: str,
        *,
        genres: list[str] | None = None,
        artist: str | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Update metadata for a clip.

        Args:
            clip_id: ID of clip to update.
            genres: New genres (or None to keep existing).
            artist: New artist (or None to keep existing).
            tags: New tags (or None to keep existing).

        Returns:
            True if updated, False if not found.
        """
        cursor = self.connection.cursor()

        updates = []
        params = []

        if genres is not None:
            normalized = [normalize_tag(g) or g for g in genres]
            updates.append("genres = ?")
            params.append(json.dumps(normalized))

        if artist is not None:
            updates.append("artist = ?")
            params.append(artist)

        if tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(tags))

        if not updates:
            return False

        params.append(clip_id)
        cursor.execute(
            f"UPDATE clips SET {', '.join(updates)} WHERE clip_id = ?",
            params,
        )
        self.connection.commit()

        return cursor.rowcount > 0

    def _row_to_clip(self, row: sqlite3.Row) -> ClipInfo:
        """Convert a database row to ClipInfo."""
        return ClipInfo(
            clip_id=row["clip_id"],
            song_id=row["song_id"],
            track_id=row["track_id"],
            source_path=row["source_path"],
            track_name=row["track_name"] or "",
            role=TrackRole(row["role"]),
            channel=row["channel"],
            note_count=row["note_count"],
            duration_bars=row["duration_bars"],
            genres=json.loads(row["genres"]) if row["genres"] else [],
            artist=row["artist"] or "",
            tags=json.loads(row["tags"]) if row["tags"] else [],
        )

    def iter_clips(self, batch_size: int = 100) -> Iterator[ClipInfo]:
        """Iterate over all clips in the library.

        Args:
            batch_size: Number of clips per batch.

        Yields:
            ClipInfo objects.
        """
        offset = 0
        while True:
            clips = self.query(ClipQuery(limit=batch_size, offset=offset))
            if not clips:
                break
            yield from clips
            offset += batch_size


__all__ = [
    "ClipInfo",
    "ClipLibrary",
    "ClipQuery",
    "IndexStats",
]
