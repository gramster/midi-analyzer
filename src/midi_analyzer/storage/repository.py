"""Repository classes for database CRUD operations."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

from midi_analyzer.models.core import (
    NoteEvent,
    RoleProbabilities,
    Song,
    SongMetadata,
    TempoEvent,
    TimeSignature,
    Track,
    TrackFeatures,
    TrackRole,
)
from midi_analyzer.patterns.fingerprinting import (
    CombinedFingerprint,
    PitchFingerprint,
    RhythmFingerprint,
)

if TYPE_CHECKING:
    from midi_analyzer.storage.schema import Database


class SongRepository:
    """Repository for Song entities and related data."""

    def __init__(self, db: Database) -> None:
        """Initialize repository.

        Args:
            db: Database connection.
        """
        self.db = db

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Context manager for a database transaction.

        Commits on success, rolls back on exception.
        """
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.connection.rollback()
            raise

    def save(self, song: Song) -> None:
        """Save a song and all its related data.

        Args:
            song: Song to save.
        """
        with self.transaction():
            self._save_song(song)
            self._save_metadata(song)
            self._save_tempo_events(song)
            self._save_time_signatures(song)
            self._save_tracks(song)

    def _save_song(self, song: Song) -> None:
        """Save the main song record."""
        self.db.execute(
            """INSERT OR REPLACE INTO songs
               (song_id, source_path, filename, ticks_per_beat,
                total_bars, total_beats, detected_key, detected_mode)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                song.song_id,
                song.source_path,
                song.source_path.split("/")[-1] if "/" in song.source_path else song.source_path,
                song.ticks_per_beat,
                song.total_bars,
                song.total_beats,
                song.detected_key,
                song.detected_mode,
            ),
        )

    def _save_metadata(self, song: Song) -> None:
        """Save song metadata."""
        meta = song.metadata
        tags_json = json.dumps(meta.tags) if meta.tags else "[]"

        self.db.execute(
            """INSERT OR REPLACE INTO song_metadata
               (song_id, artist, title, genre, source, confidence, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                song.song_id,
                meta.artist,
                meta.title,
                meta.genre,
                meta.source,
                meta.confidence,
                tags_json,
            ),
        )

    def _save_tempo_events(self, song: Song) -> None:
        """Save tempo events."""
        # Delete existing and insert fresh
        self.db.execute(
            "DELETE FROM tempo_events WHERE song_id = ?", (song.song_id,)
        )

        if song.tempo_map:
            self.db.executemany(
                """INSERT INTO tempo_events
                   (song_id, tick, beat, tempo_bpm, microseconds_per_beat)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (
                        song.song_id,
                        te.tick,
                        te.beat,
                        te.tempo_bpm,
                        te.microseconds_per_beat,
                    )
                    for te in song.tempo_map
                ],
            )

    def _save_time_signatures(self, song: Song) -> None:
        """Save time signature events."""
        self.db.execute(
            "DELETE FROM time_signatures WHERE song_id = ?", (song.song_id,)
        )

        if song.time_sig_map:
            self.db.executemany(
                """INSERT INTO time_signatures
                   (song_id, tick, beat, bar, numerator, denominator)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        song.song_id,
                        ts.tick,
                        ts.beat,
                        ts.bar,
                        ts.numerator,
                        ts.denominator,
                    )
                    for ts in song.time_sig_map
                ],
            )

    def _save_tracks(self, song: Song) -> None:
        """Save tracks with features and roles."""
        for track in song.tracks:
            # Determine if drum track based on role probs or channel 10
            is_drum = 0
            if track.role_probs and track.role_probs.primary_role() == TrackRole.DRUMS:
                is_drum = 1
            elif track.channel == 9:  # MIDI channel 10 (0-indexed)
                is_drum = 1

            # Insert track
            self.db.execute(
                """INSERT OR REPLACE INTO tracks
                   (song_id, track_number, name, channel, instrument_name,
                    instrument_program, is_drum_track, note_count)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    song.song_id,
                    track.track_id,
                    track.name,
                    track.channel,
                    "",  # instrument_name not in Track model
                    0,  # instrument_program not in Track model
                    is_drum,
                    len(track.notes),
                ),
            )

            # Get the auto-generated track_id
            cursor = self.db.execute(
                "SELECT track_id FROM tracks WHERE song_id = ? AND track_number = ?",
                (song.song_id, track.track_id),
            )
            db_track_id = cursor.fetchone()[0]

            # Save features if present
            if track.features:
                self._save_track_features(db_track_id, track.features)

            # Save role probabilities if present
            if track.role_probs:
                self._save_track_roles(db_track_id, track.role_probs)

    def _save_track_features(self, track_id: int, features: TrackFeatures) -> None:
        """Save track features."""
        self.db.execute(
            """INSERT OR REPLACE INTO track_features
               (track_id, note_density, polyphony_ratio, syncopation_score,
                repetition_score, pitch_class_entropy, pitch_range, median_pitch,
                avg_velocity, velocity_variance, avg_duration_beats)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                track_id,
                features.note_density,
                features.polyphony_ratio,
                features.syncopation_score,
                features.repetition_score,
                features.pitch_class_entropy,
                features.pitch_range,
                features.pitch_median,
                features.avg_velocity,
                0.0,  # velocity_variance not in model, use 0
                features.avg_duration,
            ),
        )

    def _save_track_roles(self, track_id: int, roles: RoleProbabilities) -> None:
        """Save track role probabilities."""
        self.db.execute(
            """INSERT OR REPLACE INTO track_roles
               (track_id, primary_role, drums_prob, bass_prob, chords_prob,
                pad_prob, lead_prob, arp_prob, other_prob)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                track_id,
                roles.primary_role().value,
                roles.drums,
                roles.bass,
                roles.chords,
                roles.pad,
                roles.lead,
                roles.arp,
                roles.other,
            ),
        )

    def get(self, song_id: str) -> Song | None:
        """Get a song by ID.

        Args:
            song_id: Song identifier.

        Returns:
            Song if found, None otherwise.
        """
        cursor = self.db.execute(
            "SELECT * FROM songs WHERE song_id = ?", (song_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        # Load metadata
        metadata = self._load_metadata(song_id)

        # Load tempo events
        tempo_map = self._load_tempo_events(song_id)

        # Load time signatures
        time_sig_map = self._load_time_signatures(song_id)

        # Load tracks
        tracks = self._load_tracks(song_id)

        return Song(
            song_id=row["song_id"],
            source_path=row["source_path"],
            ticks_per_beat=row["ticks_per_beat"],
            tempo_map=tempo_map,
            time_sig_map=time_sig_map,
            tracks=tracks,
            total_bars=row["total_bars"] or 0,
            total_beats=row["total_beats"] or 0.0,
            detected_key=row["detected_key"] or "",
            detected_mode=row["detected_mode"] or "",
            metadata=metadata,
        )

    def _load_metadata(self, song_id: str) -> SongMetadata:
        """Load song metadata."""
        cursor = self.db.execute(
            "SELECT * FROM song_metadata WHERE song_id = ?", (song_id,)
        )
        row = cursor.fetchone()

        if not row:
            return SongMetadata()

        tags = json.loads(row["tags"]) if row["tags"] else []

        return SongMetadata(
            artist=row["artist"] or "",
            title=row["title"] or "",
            genre=row["genre"] or "",
            tags=tags,
            source=row["source"] or "unknown",
            confidence=row["confidence"] or 0.0,
        )

    def _load_tempo_events(self, song_id: str) -> list[TempoEvent]:
        """Load tempo events for a song."""
        cursor = self.db.execute(
            "SELECT * FROM tempo_events WHERE song_id = ? ORDER BY tick",
            (song_id,),
        )

        return [
            TempoEvent(
                tick=row["tick"],
                beat=row["beat"],
                tempo_bpm=row["tempo_bpm"],
                microseconds_per_beat=row["microseconds_per_beat"] or 500000,
            )
            for row in cursor.fetchall()
        ]

    def _load_time_signatures(self, song_id: str) -> list[TimeSignature]:
        """Load time signatures for a song."""
        cursor = self.db.execute(
            "SELECT * FROM time_signatures WHERE song_id = ? ORDER BY tick",
            (song_id,),
        )

        return [
            TimeSignature(
                tick=row["tick"],
                beat=row["beat"],
                bar=row["bar"],
                numerator=row["numerator"],
                denominator=row["denominator"],
            )
            for row in cursor.fetchall()
        ]

    def _load_tracks(self, song_id: str) -> list[Track]:
        """Load tracks for a song."""
        cursor = self.db.execute(
            "SELECT * FROM tracks WHERE song_id = ? ORDER BY track_number",
            (song_id,),
        )

        tracks = []
        for row in cursor.fetchall():
            db_track_id = row["track_id"]

            # Load features
            features = self._load_track_features(db_track_id)

            # Load roles
            role_probs = self._load_track_roles(db_track_id)

            track = Track(
                track_id=row["track_number"],
                name=row["name"] or "",
                channel=row["channel"],
                notes=[],  # Notes not stored in DB
                features=features,
                role_probs=role_probs,
            )
            tracks.append(track)

        return tracks

    def _load_track_features(self, track_id: int) -> TrackFeatures | None:
        """Load features for a track."""
        cursor = self.db.execute(
            "SELECT * FROM track_features WHERE track_id = ?", (track_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return TrackFeatures(
            note_density=row["note_density"] or 0.0,
            polyphony_ratio=row["polyphony_ratio"] or 0.0,
            syncopation_score=row["syncopation_score"] or 0.0,
            repetition_score=row["repetition_score"] or 0.0,
            pitch_class_entropy=row["pitch_class_entropy"] or 0.0,
            pitch_range=row["pitch_range"] or 0,
            pitch_median=row["median_pitch"] or 64.0,
            avg_velocity=row["avg_velocity"] or 64.0,
            avg_duration=row["avg_duration_beats"] or 1.0,
        )

    def _load_track_roles(self, track_id: int) -> RoleProbabilities | None:
        """Load role probabilities for a track."""
        cursor = self.db.execute(
            "SELECT * FROM track_roles WHERE track_id = ?", (track_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return RoleProbabilities(
            drums=row["drums_prob"] or 0.0,
            bass=row["bass_prob"] or 0.0,
            chords=row["chords_prob"] or 0.0,
            pad=row["pad_prob"] or 0.0,
            lead=row["lead_prob"] or 0.0,
            arp=row["arp_prob"] or 0.0,
            other=row["other_prob"] or 0.0,
        )

    def exists(self, song_id: str) -> bool:
        """Check if a song exists.

        Args:
            song_id: Song identifier.

        Returns:
            True if song exists.
        """
        cursor = self.db.execute(
            "SELECT 1 FROM songs WHERE song_id = ?", (song_id,)
        )
        return cursor.fetchone() is not None

    def delete(self, song_id: str) -> bool:
        """Delete a song and all related data.

        Args:
            song_id: Song identifier.

        Returns:
            True if deleted, False if not found.
        """
        with self.transaction():
            cursor = self.db.execute(
                "DELETE FROM songs WHERE song_id = ?", (song_id,)
            )
            return cursor.rowcount > 0

    def list_all(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """List all songs with basic info.

        Args:
            limit: Maximum results.
            offset: Pagination offset.

        Returns:
            List of song summaries.
        """
        cursor = self.db.execute(
            """SELECT s.song_id, s.source_path, s.detected_key,
                      m.artist, m.title, m.genre
               FROM songs s
               LEFT JOIN song_metadata m ON s.song_id = m.song_id
               ORDER BY s.created_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        )

        return [dict(row) for row in cursor.fetchall()]

    def search_by_artist(self, artist: str) -> list[dict]:
        """Search songs by artist name.

        Args:
            artist: Artist name (partial match).

        Returns:
            List of matching songs.
        """
        cursor = self.db.execute(
            """SELECT s.song_id, s.source_path, m.artist, m.title
               FROM songs s
               JOIN song_metadata m ON s.song_id = m.song_id
               WHERE m.artist LIKE ?
               ORDER BY m.artist, m.title""",
            (f"%{artist}%",),
        )

        return [dict(row) for row in cursor.fetchall()]

    def count(self) -> int:
        """Get total number of songs.

        Returns:
            Song count.
        """
        cursor = self.db.execute("SELECT COUNT(*) FROM songs")
        return cursor.fetchone()[0]


class PatternRepository:
    """Repository for Pattern entities."""

    def __init__(self, db: Database) -> None:
        """Initialize repository.

        Args:
            db: Database connection.
        """
        self.db = db

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Context manager for a database transaction."""
        try:
            yield
            self.db.commit()
        except Exception:
            self.db.connection.rollback()
            raise

    def save(self, fingerprint: CombinedFingerprint, pattern_type: str = "combined") -> str:
        """Save a pattern fingerprint.

        If pattern already exists (same hash), increments occurrence count.

        Args:
            fingerprint: Combined fingerprint.
            pattern_type: Type of pattern.

        Returns:
            Pattern ID (hash).
        """
        pattern_id = fingerprint.hash_value

        with self.transaction():
            # Try to increment existing
            cursor = self.db.execute(
                """UPDATE patterns
                   SET occurrence_count = occurrence_count + 1
                   WHERE pattern_id = ?""",
                (pattern_id,),
            )

            if cursor.rowcount == 0:
                # Insert new pattern
                self.db.execute(
                    """INSERT INTO patterns
                       (pattern_id, pattern_type, num_bars, grid_size,
                        onset_grid, accent_grid, rhythm_hash,
                        intervals, pitch_classes, contour,
                        range_semitones, mean_pitch, pitch_hash)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        pattern_id,
                        pattern_type,
                        fingerprint.rhythm.num_bars,
                        fingerprint.rhythm.grid_size,
                        json.dumps(list(fingerprint.rhythm.onset_grid)),
                        json.dumps([round(x, 3) for x in fingerprint.rhythm.accent_grid]),
                        fingerprint.rhythm.hash_value,
                        json.dumps(list(fingerprint.pitch.intervals)),
                        json.dumps(list(fingerprint.pitch.pitch_classes)),
                        json.dumps(list(fingerprint.pitch.contour)),
                        fingerprint.pitch.range_semitones,
                        fingerprint.pitch.mean_pitch,
                        fingerprint.pitch.hash_value,
                    ),
                )

        return pattern_id

    def save_instance(
        self,
        pattern_id: str,
        track_id: int,
        start_bar: int,
        end_bar: int,
        transposition: int = 0,
        confidence: float = 1.0,
    ) -> int:
        """Save a pattern instance (occurrence).

        Args:
            pattern_id: Pattern identifier.
            track_id: Database track ID.
            start_bar: Starting bar number.
            end_bar: Ending bar number.
            transposition: Semitones from original pitch.
            confidence: Match confidence.

        Returns:
            Instance ID.
        """
        with self.transaction():
            cursor = self.db.execute(
                """INSERT INTO pattern_instances
                   (pattern_id, track_id, start_bar, end_bar, transposition, confidence)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (pattern_id, track_id, start_bar, end_bar, transposition, confidence),
            )
            return cursor.lastrowid or 0

    def get(self, pattern_id: str) -> CombinedFingerprint | None:
        """Get a pattern by ID.

        Args:
            pattern_id: Pattern identifier.

        Returns:
            CombinedFingerprint if found.
        """
        cursor = self.db.execute(
            "SELECT * FROM patterns WHERE pattern_id = ?", (pattern_id,)
        )
        row = cursor.fetchone()

        if not row:
            return None

        rhythm = RhythmFingerprint(
            onset_grid=tuple(json.loads(row["onset_grid"] or "[]")),
            accent_grid=tuple(json.loads(row["accent_grid"] or "[]")),
            grid_size=row["grid_size"] or 16,
            num_bars=row["num_bars"],
            note_count=sum(json.loads(row["onset_grid"] or "[]")),
            hash_value=row["rhythm_hash"] or "",
        )

        pitch = PitchFingerprint(
            intervals=tuple(json.loads(row["intervals"] or "[]")),
            pitch_classes=tuple(json.loads(row["pitch_classes"] or "[0]*12")),
            contour=tuple(json.loads(row["contour"] or "[]")),
            range_semitones=row["range_semitones"] or 0,
            mean_pitch=row["mean_pitch"] or 0.0,
            hash_value=row["pitch_hash"] or "",
        )

        return CombinedFingerprint(
            rhythm=rhythm,
            pitch=pitch,
            hash_value=pattern_id,
        )

    def find_by_rhythm(self, rhythm_hash: str) -> list[str]:
        """Find patterns with matching rhythm fingerprint.

        Args:
            rhythm_hash: Rhythm fingerprint hash.

        Returns:
            List of pattern IDs.
        """
        cursor = self.db.execute(
            "SELECT pattern_id FROM patterns WHERE rhythm_hash = ?",
            (rhythm_hash,),
        )
        return [row[0] for row in cursor.fetchall()]

    def find_by_pitch(self, pitch_hash: str) -> list[str]:
        """Find patterns with matching pitch fingerprint.

        Args:
            pitch_hash: Pitch fingerprint hash.

        Returns:
            List of pattern IDs.
        """
        cursor = self.db.execute(
            "SELECT pattern_id FROM patterns WHERE pitch_hash = ?",
            (pitch_hash,),
        )
        return [row[0] for row in cursor.fetchall()]

    def get_most_common(self, limit: int = 20) -> list[dict]:
        """Get most frequently occurring patterns.

        Args:
            limit: Maximum results.

        Returns:
            List of patterns with occurrence counts.
        """
        cursor = self.db.execute(
            """SELECT pattern_id, pattern_type, num_bars, occurrence_count, rhythm_hash
               FROM patterns
               ORDER BY occurrence_count DESC
               LIMIT ?""",
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_instances_for_track(self, track_id: int) -> list[dict]:
        """Get all pattern instances in a track.

        Args:
            track_id: Database track ID.

        Returns:
            List of pattern instances.
        """
        cursor = self.db.execute(
            """SELECT pi.*, p.rhythm_hash, p.pitch_hash
               FROM pattern_instances pi
               JOIN patterns p ON pi.pattern_id = p.pattern_id
               WHERE pi.track_id = ?
               ORDER BY pi.start_bar""",
            (track_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def count(self) -> int:
        """Get total number of unique patterns.

        Returns:
            Pattern count.
        """
        cursor = self.db.execute("SELECT COUNT(*) FROM patterns")
        return cursor.fetchone()[0]

    def count_instances(self) -> int:
        """Get total number of pattern instances.

        Returns:
            Instance count.
        """
        cursor = self.db.execute("SELECT COUNT(*) FROM pattern_instances")
        return cursor.fetchone()[0]

    def bulk_save(self, fingerprints: list[CombinedFingerprint]) -> list[str]:
        """Save multiple patterns efficiently.

        Args:
            fingerprints: List of fingerprints.

        Returns:
            List of pattern IDs.
        """
        pattern_ids = []

        with self.transaction():
            for fp in fingerprints:
                pattern_id = fp.hash_value

                # Try update first
                cursor = self.db.execute(
                    """UPDATE patterns
                       SET occurrence_count = occurrence_count + 1
                       WHERE pattern_id = ?""",
                    (pattern_id,),
                )

                if cursor.rowcount == 0:
                    self.db.execute(
                        """INSERT INTO patterns
                           (pattern_id, pattern_type, num_bars, grid_size,
                            onset_grid, accent_grid, rhythm_hash,
                            intervals, pitch_classes, contour,
                            range_semitones, mean_pitch, pitch_hash)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            pattern_id,
                            "combined",
                            fp.rhythm.num_bars,
                            fp.rhythm.grid_size,
                            json.dumps(list(fp.rhythm.onset_grid)),
                            json.dumps([round(x, 3) for x in fp.rhythm.accent_grid]),
                            fp.rhythm.hash_value,
                            json.dumps(list(fp.pitch.intervals)),
                            json.dumps(list(fp.pitch.pitch_classes)),
                            json.dumps(list(fp.pitch.contour)),
                            fp.pitch.range_semitones,
                            fp.pitch.mean_pitch,
                            fp.pitch.hash_value,
                        ),
                    )

                pattern_ids.append(pattern_id)

        return pattern_ids
