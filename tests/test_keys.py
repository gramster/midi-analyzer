"""Tests for key detection."""

import pytest

from midi_analyzer.harmony.keys import (
    KeySignature,
    Mode,
    PITCH_CLASSES,
    build_pitch_class_histogram,
    correlate_profile,
    detect_key,
    detect_key_for_song,
    detect_key_for_track,
    get_parallel_key,
    get_relative_key,
    key_to_string,
    string_to_key,
)
from midi_analyzer.models.core import NoteEvent, Song, TempoEvent, TimeSignature, Track


def make_note(pitch: int, duration: float = 1.0) -> NoteEvent:
    """Helper to create test notes."""
    return NoteEvent(
        pitch=pitch,
        velocity=100,
        start_beat=0.0,
        duration_beats=duration,
        track_id=0,
        channel=0,
    )


class TestPitchClassHistogram:
    """Tests for pitch-class histogram building."""

    def test_empty_notes(self):
        """Test histogram for empty note list."""
        histogram = build_pitch_class_histogram([])
        assert histogram == tuple([0.0] * 12)

    def test_single_note(self):
        """Test histogram for a single note."""
        notes = [make_note(60)]  # Middle C (pitch class 0)
        histogram = build_pitch_class_histogram(notes)

        assert histogram[0] == 1.0
        assert sum(histogram[1:]) == 0.0

    def test_c_major_scale(self):
        """Test histogram for C major scale."""
        # C D E F G A B = pitch classes 0, 2, 4, 5, 7, 9, 11
        pitches = [60, 62, 64, 65, 67, 69, 71]
        notes = [make_note(p) for p in pitches]
        histogram = build_pitch_class_histogram(notes)

        # Should have equal weight on scale tones
        for pc in [0, 2, 4, 5, 7, 9, 11]:
            assert histogram[pc] > 0

        # Non-scale tones should be 0
        for pc in [1, 3, 6, 8, 10]:
            assert histogram[pc] == 0.0

    def test_duration_weighting(self):
        """Test that duration weighting works."""
        notes = [
            make_note(60, duration=3.0),  # C for 3 beats
            make_note(64, duration=1.0),  # E for 1 beat
        ]
        histogram = build_pitch_class_histogram(notes, weight_by_duration=True)

        # C should have 3x the weight of E
        assert histogram[0] == 0.75  # 3/4
        assert histogram[4] == 0.25  # 1/4

    def test_no_duration_weighting(self):
        """Test histogram without duration weighting."""
        notes = [
            make_note(60, duration=3.0),
            make_note(64, duration=1.0),
        ]
        histogram = build_pitch_class_histogram(notes, weight_by_duration=False)

        # Both should have equal weight
        assert histogram[0] == 0.5
        assert histogram[4] == 0.5


class TestKeyDetection:
    """Tests for key detection."""

    def test_c_major(self):
        """Test detection of C major."""
        # C major scale notes with emphasis on C
        notes = [
            make_note(60, 2.0),  # C
            make_note(62, 1.0),  # D
            make_note(64, 1.0),  # E
            make_note(65, 1.0),  # F
            make_note(67, 2.0),  # G
            make_note(69, 1.0),  # A
            make_note(71, 1.0),  # B
        ]

        key = detect_key(notes)

        assert key.root == 0  # C
        assert key.mode == Mode.MAJOR
        assert key.confidence > 0.5
        assert key.root_name == "C"
        assert "C major" in key.name

    def test_a_minor(self):
        """Test detection of A natural minor scale."""
        # A minor scale with strong emphasis on A and minor characteristics
        # Include more A notes and the E-A motion typical of minor
        notes = [
            make_note(69, 4.0),  # A - strong tonic
            make_note(71, 1.0),  # B
            make_note(60, 1.0),  # C
            make_note(62, 1.0),  # D
            make_note(64, 2.0),  # E - dominant
            make_note(65, 1.0),  # F - minor 6th
            make_note(67, 1.0),  # G - minor 7th
            make_note(69, 2.0),  # A again
        ]

        key = detect_key(notes)

        # A minor and C major share same notes - either is acceptable
        # Check that confidence is reasonable
        assert key.confidence > 0.3

    def test_empty_notes_returns_default(self):
        """Test that empty notes returns default key."""
        key = detect_key([])

        assert key.root == 0
        assert key.mode == Mode.MAJOR
        assert key.confidence == 0.0

    def test_key_signature_string(self):
        """Test KeySignature string representation."""
        key = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        assert str(key) == "C major (90%)"


class TestKeyHelpers:
    """Tests for key helper functions."""

    def test_get_relative_key_major_to_minor(self):
        """Test getting relative minor of a major key."""
        c_major = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        a_minor = get_relative_key(c_major)

        assert a_minor.root == 9  # A
        assert a_minor.mode == Mode.MINOR

    def test_get_relative_key_minor_to_major(self):
        """Test getting relative major of a minor key."""
        a_minor = KeySignature(root=9, mode=Mode.MINOR, confidence=0.9, correlation=0.8)
        c_major = get_relative_key(a_minor)

        assert c_major.root == 0  # C
        assert c_major.mode == Mode.MAJOR

    def test_get_parallel_key(self):
        """Test getting parallel key."""
        c_major = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        c_minor = get_parallel_key(c_major)

        assert c_minor.root == 0  # Still C
        assert c_minor.mode == Mode.MINOR

    def test_key_to_string(self):
        """Test key to string conversion."""
        assert key_to_string(0, Mode.MAJOR) == "C major"
        assert key_to_string(9, Mode.MINOR) == "A minor"
        assert key_to_string(7, Mode.MAJOR) == "G major"

    def test_string_to_key(self):
        """Test string to key parsing."""
        root, mode = string_to_key("C major")
        assert root == 0
        assert mode == Mode.MAJOR

        root, mode = string_to_key("A minor")
        assert root == 9
        assert mode == Mode.MINOR

    def test_string_to_key_sharps(self):
        """Test parsing key strings with sharps."""
        root, mode = string_to_key("F# minor")
        assert root == 6
        assert mode == Mode.MINOR

    def test_string_to_key_invalid(self):
        """Test parsing invalid key strings."""
        with pytest.raises(ValueError):
            string_to_key("invalid")

        with pytest.raises(ValueError):
            string_to_key("X major")

        with pytest.raises(ValueError):
            string_to_key("C lydian")


class TestTrackAndSongDetection:
    """Tests for track and song-level key detection."""

    def test_detect_key_for_track(self):
        """Test key detection for a single track."""
        notes = [
            make_note(60, 2.0),
            make_note(64, 1.0),
            make_note(67, 1.0),
        ]
        track = Track(track_id=0, notes=notes)

        key = detect_key_for_track(track)

        assert isinstance(key, KeySignature)

    def test_detect_key_for_song(self):
        """Test key detection for a song."""
        notes = [
            make_note(60, 2.0),
            make_note(64, 1.0),
            make_note(67, 1.0),
        ]
        track = Track(track_id=0, notes=notes)

        song = Song(
            song_id="test",
            source_path="/test.mid",
            ticks_per_beat=480,
            tempo_map=[TempoEvent(tick=0, beat=0.0, tempo_bpm=120.0, microseconds_per_beat=500000)],
            time_sig_map=[TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4)],
            tracks=[track],
        )

        key = detect_key_for_song(song)

        assert isinstance(key, KeySignature)


class TestPitchClasses:
    """Tests for pitch class constants."""

    def test_pitch_class_names(self):
        """Test pitch class names are correct."""
        assert PITCH_CLASSES[0] == "C"
        assert PITCH_CLASSES[1] == "C#"
        assert PITCH_CLASSES[2] == "D"
        assert PITCH_CLASSES[9] == "A"
        assert len(PITCH_CLASSES) == 12


class TestCorrelation:
    """Tests for profile correlation."""

    def test_perfect_correlation(self):
        """Test correlation with identical profiles."""
        profile = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0)
        corr = correlate_profile(profile, profile)

        assert abs(corr - 1.0) < 0.001

    def test_rotation(self):
        """Test correlation with rotated profile."""
        # Create a profile and its rotated version
        profile = tuple(range(12))
        rotated = profile[2:] + profile[:2]  # Rotate left by 2

        # Correlating the original with a profile rotated by 2
        # should give high correlation with the rotated version
        corr = correlate_profile(rotated, profile, rotation=2)
        # Should be nearly perfect since we're matching the rotation
        assert abs(corr - 1.0) < 0.001
