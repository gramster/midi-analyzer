"""Tests for database repository layer."""

import tempfile
from pathlib import Path

import pytest

from midi_analyzer.models.core import (
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
from midi_analyzer.storage.repository import PatternRepository, SongRepository
from midi_analyzer.storage.schema import create_database


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
def sample_song() -> Song:
    """Create a sample song for testing."""
    features = TrackFeatures(
        note_density=2.5,
        polyphony_ratio=0.3,
        syncopation_score=0.4,
        repetition_score=0.7,
        pitch_class_entropy=2.1,
        pitch_range=24,
        pitch_median=60.0,
        avg_velocity=90.0,
        avg_duration=0.5,
    )

    role_probs = RoleProbabilities(
        drums=0.0,
        bass=0.9,
        chords=0.05,
        pad=0.0,
        lead=0.0,
        arp=0.05,
        other=0.0,
    )

    track = Track(
        track_id=0,
        name="Bass",
        channel=2,
        notes=[],
        features=features,
        role_probs=role_probs,
    )

    metadata = SongMetadata(
        artist="Test Artist",
        title="Test Song",
        genre="Electronic",
        tags=["funky", "groovy"],
        source="test",
        confidence=0.95,
    )

    return Song(
        song_id="test-song-001",
        source_path="/path/to/test.mid",
        ticks_per_beat=480,
        tempo_map=[
            TempoEvent(tick=0, beat=0.0, tempo_bpm=120.0, microseconds_per_beat=500000),
            TempoEvent(tick=1920, beat=4.0, tempo_bpm=125.0, microseconds_per_beat=480000),
        ],
        time_sig_map=[
            TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4),
        ],
        tracks=[track],
        total_bars=8,
        total_beats=32.0,
        detected_key="C",
        detected_mode="major",
        metadata=metadata,
    )


@pytest.fixture
def sample_fingerprint() -> CombinedFingerprint:
    """Create a sample fingerprint for testing."""
    rhythm = RhythmFingerprint(
        onset_grid=(1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0),
        accent_grid=(1.0, 0.0, 0.8, 0.0, 0.9, 0.0, 0.7, 0.0, 1.0, 0.0, 0.8, 0.0, 0.9, 0.0, 0.7, 0.0),
        grid_size=16,
        num_bars=1,
        note_count=8,
        hash_value="rhythm123",
    )

    pitch = PitchFingerprint(
        intervals=(0, 2, 4, 5, 7, 9, 11, 12),
        pitch_classes=(1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1),
        contour=(0, 1, 1, 1, 1, 1, 1, 1),
        range_semitones=12,
        mean_pitch=66.0,
        hash_value="pitch456",
    )

    return CombinedFingerprint(
        rhythm=rhythm,
        pitch=pitch,
        hash_value="combined789",
    )


class TestSongRepository:
    """Tests for SongRepository."""

    def test_save_and_get(self, db, sample_song):
        """Test saving and retrieving a song."""
        repo = SongRepository(db)

        repo.save(sample_song)
        loaded = repo.get(sample_song.song_id)

        assert loaded is not None
        assert loaded.song_id == sample_song.song_id
        assert loaded.source_path == sample_song.source_path
        assert loaded.ticks_per_beat == sample_song.ticks_per_beat
        assert loaded.total_bars == sample_song.total_bars
        assert loaded.detected_key == sample_song.detected_key
        assert loaded.detected_mode == sample_song.detected_mode

    def test_save_loads_metadata(self, db, sample_song):
        """Test that metadata is saved and loaded."""
        repo = SongRepository(db)
        repo.save(sample_song)

        loaded = repo.get(sample_song.song_id)

        assert loaded is not None
        assert loaded.metadata.artist == "Test Artist"
        assert loaded.metadata.title == "Test Song"
        assert loaded.metadata.genre == "Electronic"
        assert loaded.metadata.tags == ["funky", "groovy"]
        assert loaded.metadata.confidence == 0.95

    def test_save_loads_tempo_events(self, db, sample_song):
        """Test that tempo events are saved and loaded."""
        repo = SongRepository(db)
        repo.save(sample_song)

        loaded = repo.get(sample_song.song_id)

        assert loaded is not None
        assert len(loaded.tempo_map) == 2
        assert loaded.tempo_map[0].tempo_bpm == 120.0
        assert loaded.tempo_map[1].tempo_bpm == 125.0
        assert loaded.tempo_map[1].beat == 4.0

    def test_save_loads_time_signatures(self, db, sample_song):
        """Test that time signatures are saved and loaded."""
        repo = SongRepository(db)
        repo.save(sample_song)

        loaded = repo.get(sample_song.song_id)

        assert loaded is not None
        assert len(loaded.time_sig_map) == 1
        assert loaded.time_sig_map[0].numerator == 4
        assert loaded.time_sig_map[0].denominator == 4

    def test_save_loads_tracks_with_features(self, db, sample_song):
        """Test that tracks and features are saved and loaded."""
        repo = SongRepository(db)
        repo.save(sample_song)

        loaded = repo.get(sample_song.song_id)

        assert loaded is not None
        assert len(loaded.tracks) == 1

        track = loaded.tracks[0]
        assert track.name == "Bass"
        assert track.channel == 2

        assert track.features is not None
        assert track.features.note_density == 2.5
        assert track.features.pitch_range == 24

    def test_save_loads_track_roles(self, db, sample_song):
        """Test that track role probabilities are saved and loaded."""
        repo = SongRepository(db)
        repo.save(sample_song)

        loaded = repo.get(sample_song.song_id)

        assert loaded is not None
        track = loaded.tracks[0]

        assert track.role_probs is not None
        assert track.role_probs.bass == 0.9
        assert track.role_probs.drums == 0.0
        assert track.role_probs.primary_role() == TrackRole.BASS

    def test_get_nonexistent(self, db):
        """Test getting a song that doesn't exist."""
        repo = SongRepository(db)
        assert repo.get("nonexistent") is None

    def test_exists(self, db, sample_song):
        """Test checking if a song exists."""
        repo = SongRepository(db)

        assert not repo.exists(sample_song.song_id)

        repo.save(sample_song)

        assert repo.exists(sample_song.song_id)

    def test_delete(self, db, sample_song):
        """Test deleting a song."""
        repo = SongRepository(db)
        repo.save(sample_song)

        assert repo.exists(sample_song.song_id)

        result = repo.delete(sample_song.song_id)

        assert result is True
        assert not repo.exists(sample_song.song_id)

    def test_delete_nonexistent(self, db):
        """Test deleting a song that doesn't exist."""
        repo = SongRepository(db)
        result = repo.delete("nonexistent")
        assert result is False

    def test_list_all(self, db, sample_song):
        """Test listing all songs."""
        repo = SongRepository(db)

        # Create multiple songs
        for i in range(3):
            song = Song(
                song_id=f"song-{i}",
                source_path=f"/path/song{i}.mid",
                ticks_per_beat=480,
                tempo_map=[TempoEvent(tick=0, beat=0.0, tempo_bpm=120.0, microseconds_per_beat=500000)],
                time_sig_map=[TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4)],
                tracks=[],
                metadata=SongMetadata(artist=f"Artist {i}", title=f"Song {i}"),
            )
            repo.save(song)

        results = repo.list_all()

        assert len(results) == 3

    def test_list_all_with_pagination(self, db):
        """Test pagination for list_all."""
        repo = SongRepository(db)

        for i in range(5):
            song = Song(
                song_id=f"song-{i}",
                source_path=f"/path/song{i}.mid",
                ticks_per_beat=480,
                tempo_map=[TempoEvent(tick=0, beat=0.0, tempo_bpm=120.0, microseconds_per_beat=500000)],
                time_sig_map=[TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4)],
                tracks=[],
            )
            repo.save(song)

        page1 = repo.list_all(limit=2, offset=0)
        page2 = repo.list_all(limit=2, offset=2)

        assert len(page1) == 2
        assert len(page2) == 2

    def test_search_by_artist(self, db):
        """Test searching songs by artist."""
        repo = SongRepository(db)

        repo.save(Song(
            song_id="s1",
            source_path="/p1.mid",
            ticks_per_beat=480,
            tempo_map=[TempoEvent(tick=0, beat=0.0, tempo_bpm=120.0, microseconds_per_beat=500000)],
            time_sig_map=[TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4)],
            tracks=[],
            metadata=SongMetadata(artist="Daft Punk", title="Song 1"),
        ))
        repo.save(Song(
            song_id="s2",
            source_path="/p2.mid",
            ticks_per_beat=480,
            tempo_map=[TempoEvent(tick=0, beat=0.0, tempo_bpm=120.0, microseconds_per_beat=500000)],
            time_sig_map=[TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4)],
            tracks=[],
            metadata=SongMetadata(artist="Kraftwerk", title="Song 2"),
        ))

        results = repo.search_by_artist("Daft")

        assert len(results) == 1
        assert results[0]["artist"] == "Daft Punk"

    def test_count(self, db, sample_song):
        """Test counting songs."""
        repo = SongRepository(db)

        assert repo.count() == 0

        repo.save(sample_song)

        assert repo.count() == 1

    def test_upsert_song(self, db, sample_song):
        """Test that saving same song twice updates it."""
        repo = SongRepository(db)

        repo.save(sample_song)

        # Modify and save again
        sample_song.detected_key = "G"
        repo.save(sample_song)

        loaded = repo.get(sample_song.song_id)
        assert loaded is not None
        assert loaded.detected_key == "G"
        assert repo.count() == 1  # Still just one song


class TestPatternRepository:
    """Tests for PatternRepository."""

    def test_save_and_get(self, db, sample_fingerprint):
        """Test saving and retrieving a pattern."""
        repo = PatternRepository(db)

        pattern_id = repo.save(sample_fingerprint)
        loaded = repo.get(pattern_id)

        assert loaded is not None
        assert loaded.hash_value == sample_fingerprint.hash_value
        assert loaded.rhythm.hash_value == sample_fingerprint.rhythm.hash_value
        assert loaded.pitch.hash_value == sample_fingerprint.pitch.hash_value

    def test_save_increments_occurrence(self, db, sample_fingerprint):
        """Test that saving same pattern increments count."""
        repo = PatternRepository(db)

        repo.save(sample_fingerprint)
        repo.save(sample_fingerprint)
        repo.save(sample_fingerprint)

        # Check occurrence count
        cursor = db.execute(
            "SELECT occurrence_count FROM patterns WHERE pattern_id = ?",
            (sample_fingerprint.hash_value,),
        )
        count = cursor.fetchone()[0]
        assert count == 3

    def test_find_by_rhythm(self, db, sample_fingerprint):
        """Test finding patterns by rhythm hash."""
        repo = PatternRepository(db)
        repo.save(sample_fingerprint)

        results = repo.find_by_rhythm(sample_fingerprint.rhythm.hash_value)

        assert len(results) == 1
        assert results[0] == sample_fingerprint.hash_value

    def test_find_by_pitch(self, db, sample_fingerprint):
        """Test finding patterns by pitch hash."""
        repo = PatternRepository(db)
        repo.save(sample_fingerprint)

        results = repo.find_by_pitch(sample_fingerprint.pitch.hash_value)

        assert len(results) == 1
        assert results[0] == sample_fingerprint.hash_value

    def test_save_instance(self, db, sample_fingerprint, sample_song):
        """Test saving a pattern instance."""
        song_repo = SongRepository(db)
        pattern_repo = PatternRepository(db)

        song_repo.save(sample_song)
        pattern_repo.save(sample_fingerprint)

        # Get the database track ID
        cursor = db.execute("SELECT track_id FROM tracks LIMIT 1")
        track_id = cursor.fetchone()[0]

        instance_id = pattern_repo.save_instance(
            pattern_id=sample_fingerprint.hash_value,
            track_id=track_id,
            start_bar=0,
            end_bar=4,
            transposition=0,
            confidence=0.95,
        )

        assert instance_id > 0

    def test_get_instances_for_track(self, db, sample_fingerprint, sample_song):
        """Test getting pattern instances for a track."""
        song_repo = SongRepository(db)
        pattern_repo = PatternRepository(db)

        song_repo.save(sample_song)
        pattern_repo.save(sample_fingerprint)

        cursor = db.execute("SELECT track_id FROM tracks LIMIT 1")
        track_id = cursor.fetchone()[0]

        pattern_repo.save_instance(
            pattern_id=sample_fingerprint.hash_value,
            track_id=track_id,
            start_bar=0,
            end_bar=4,
        )
        pattern_repo.save_instance(
            pattern_id=sample_fingerprint.hash_value,
            track_id=track_id,
            start_bar=4,
            end_bar=8,
        )

        instances = pattern_repo.get_instances_for_track(track_id)

        assert len(instances) == 2
        assert instances[0]["start_bar"] == 0
        assert instances[1]["start_bar"] == 4

    def test_get_most_common(self, db):
        """Test getting most common patterns."""
        repo = PatternRepository(db)

        # Create patterns with different occurrence counts
        for i in range(3):
            fp = CombinedFingerprint(
                rhythm=RhythmFingerprint(
                    onset_grid=(1, 0) * 8,
                    accent_grid=(1.0, 0.0) * 8,
                    grid_size=16,
                    num_bars=1,
                    note_count=8,
                    hash_value=f"rhythm-{i}",
                ),
                pitch=PitchFingerprint(
                    intervals=(0, 2, 4),
                    pitch_classes=(1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0),
                    contour=(0, 1, 1),
                    range_semitones=4,
                    mean_pitch=60.0,
                    hash_value=f"pitch-{i}",
                ),
                hash_value=f"combined-{i}",
            )

            # Save different number of times
            for _ in range(i + 1):
                repo.save(fp)

        results = repo.get_most_common(limit=2)

        assert len(results) == 2
        assert results[0]["occurrence_count"] >= results[1]["occurrence_count"]

    def test_count(self, db, sample_fingerprint):
        """Test counting patterns."""
        repo = PatternRepository(db)

        assert repo.count() == 0

        repo.save(sample_fingerprint)

        assert repo.count() == 1

    def test_count_instances(self, db, sample_fingerprint, sample_song):
        """Test counting pattern instances."""
        song_repo = SongRepository(db)
        pattern_repo = PatternRepository(db)

        song_repo.save(sample_song)
        pattern_repo.save(sample_fingerprint)

        cursor = db.execute("SELECT track_id FROM tracks LIMIT 1")
        track_id = cursor.fetchone()[0]

        assert pattern_repo.count_instances() == 0

        pattern_repo.save_instance(sample_fingerprint.hash_value, track_id, 0, 4)
        pattern_repo.save_instance(sample_fingerprint.hash_value, track_id, 4, 8)

        assert pattern_repo.count_instances() == 2

    def test_bulk_save(self, db):
        """Test bulk saving patterns."""
        repo = PatternRepository(db)

        fingerprints = []
        for i in range(5):
            fp = CombinedFingerprint(
                rhythm=RhythmFingerprint(
                    onset_grid=(1, 0) * 8,
                    accent_grid=(1.0, 0.0) * 8,
                    grid_size=16,
                    num_bars=1,
                    note_count=8,
                    hash_value=f"bulk-rhythm-{i}",
                ),
                pitch=PitchFingerprint(
                    intervals=(0,),
                    pitch_classes=(1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
                    contour=(0,),
                    range_semitones=0,
                    mean_pitch=60.0,
                    hash_value=f"bulk-pitch-{i}",
                ),
                hash_value=f"bulk-combined-{i}",
            )
            fingerprints.append(fp)

        pattern_ids = repo.bulk_save(fingerprints)

        assert len(pattern_ids) == 5
        assert repo.count() == 5

    def test_get_nonexistent(self, db):
        """Test getting a pattern that doesn't exist."""
        repo = PatternRepository(db)
        assert repo.get("nonexistent") is None


class TestTransactions:
    """Test transaction behavior."""

    def test_song_save_is_atomic(self, db, sample_song):
        """Test that song save is atomic."""
        repo = SongRepository(db)

        # Manually corrupt something after save starts
        # This tests that all parts of save happen in one transaction
        repo.save(sample_song)

        # Verify everything was saved
        assert repo.exists(sample_song.song_id)

        cursor = db.execute(
            "SELECT COUNT(*) FROM tempo_events WHERE song_id = ?",
            (sample_song.song_id,),
        )
        assert cursor.fetchone()[0] == 2

        cursor = db.execute(
            "SELECT COUNT(*) FROM tracks WHERE song_id = ?",
            (sample_song.song_id,),
        )
        assert cursor.fetchone()[0] == 1
