"""Tests for core data models."""


from midi_analyzer.models.core import (
    NoteEvent,
    RoleProbabilities,
    Song,
    TempoEvent,
    TimeSignature,
    Track,
    TrackFeatures,
    TrackRole,
)


class TestTrackRole:
    """Tests for TrackRole enum."""

    def test_role_values(self) -> None:
        """Test that all expected roles exist."""
        assert TrackRole.DRUMS.value == "drums"
        assert TrackRole.BASS.value == "bass"
        assert TrackRole.CHORDS.value == "chords"
        assert TrackRole.PAD.value == "pad"
        assert TrackRole.LEAD.value == "lead"
        assert TrackRole.ARP.value == "arp"
        assert TrackRole.OTHER.value == "other"


class TestRoleProbabilities:
    """Tests for RoleProbabilities."""

    def test_primary_role_drums(self) -> None:
        """Test primary role detection for drums."""
        probs = RoleProbabilities(drums=0.9, bass=0.05, other=0.05)
        assert probs.primary_role() == TrackRole.DRUMS

    def test_primary_role_bass(self) -> None:
        """Test primary role detection for bass."""
        probs = RoleProbabilities(bass=0.8, chords=0.1, other=0.1)
        assert probs.primary_role() == TrackRole.BASS

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        probs = RoleProbabilities(drums=0.5, bass=0.3)
        d = probs.to_dict()
        assert d["drums"] == 0.5
        assert d["bass"] == 0.3
        assert d["chords"] == 0.0


class TestNoteEvent:
    """Tests for NoteEvent."""

    def test_note_creation(self) -> None:
        """Test basic note creation."""
        note = NoteEvent(
            pitch=60,
            velocity=100,
            start_beat=0.0,
            duration_beats=1.0,
            track_id=0,
            channel=0,
        )
        assert note.pitch == 60
        assert note.velocity == 100
        assert note.start_beat == 0.0
        assert note.duration_beats == 1.0

    def test_note_with_quantization(self) -> None:
        """Test note with quantized timing."""
        note = NoteEvent(
            pitch=64,
            velocity=80,
            start_beat=0.123,
            duration_beats=0.456,
            track_id=0,
            channel=0,
            quantized_start=0.125,
            quantized_duration=0.5,
        )
        assert note.quantized_start == 0.125
        assert note.quantized_duration == 0.5


class TestTimeSignature:
    """Tests for TimeSignature."""

    def test_4_4_beats_per_bar(self) -> None:
        """Test 4/4 time signature."""
        ts = TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4)
        assert ts.beats_per_bar == 4.0

    def test_3_4_beats_per_bar(self) -> None:
        """Test 3/4 time signature."""
        ts = TimeSignature(tick=0, beat=0.0, bar=0, numerator=3, denominator=4)
        assert ts.beats_per_bar == 3.0

    def test_6_8_beats_per_bar(self) -> None:
        """Test 6/8 time signature (6 eighth notes = 3 quarter notes)."""
        ts = TimeSignature(tick=0, beat=0.0, bar=0, numerator=6, denominator=8)
        assert ts.beats_per_bar == 3.0


class TestTrack:
    """Tests for Track."""

    def test_primary_role_without_probs(self) -> None:
        """Test that track returns OTHER when no role probs set."""
        track = Track(track_id=0)
        assert track.primary_role == TrackRole.OTHER

    def test_primary_role_with_probs(self) -> None:
        """Test that track returns correct primary role."""
        track = Track(
            track_id=0,
            role_probs=RoleProbabilities(lead=0.7, arp=0.2, other=0.1),
        )
        assert track.primary_role == TrackRole.LEAD


class TestSong:
    """Tests for Song."""

    def test_default_tempo(self) -> None:
        """Test default tempo when no tempo events."""
        song = Song(song_id="test", source_path="test.mid", ticks_per_beat=480)
        assert song.primary_tempo == 120.0

    def test_custom_tempo(self) -> None:
        """Test tempo from tempo map."""
        song = Song(
            song_id="test",
            source_path="test.mid",
            ticks_per_beat=480,
            tempo_map=[TempoEvent(tick=0, beat=0.0, tempo_bpm=140.0, microseconds_per_beat=428571)],
        )
        assert song.primary_tempo == 140.0

    def test_default_time_sig(self) -> None:
        """Test default time signature when none specified."""
        song = Song(song_id="test", source_path="test.mid", ticks_per_beat=480)
        assert song.primary_time_sig == (4, 4)

    def test_custom_time_sig(self) -> None:
        """Test time signature from map."""
        song = Song(
            song_id="test",
            source_path="test.mid",
            ticks_per_beat=480,
            time_sig_map=[TimeSignature(tick=0, beat=0.0, bar=0, numerator=3, denominator=4)],
        )
        assert song.primary_time_sig == (3, 4)


class TestTrackFeatures:
    """Tests for TrackFeatures."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        features = TrackFeatures(
            note_count=100,
            note_density=4.5,
            polyphony_ratio=0.1,
            pitch_min=36,
            pitch_max=84,
        )
        d = features.to_dict()
        assert d["note_count"] == 100
        assert d["note_density"] == 4.5
        assert d["pitch_min"] == 36
        assert d["pitch_max"] == 84
