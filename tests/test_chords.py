"""Tests for chord detection and progression inference."""

import pytest

from midi_analyzer.harmony.chords import (
    Chord,
    ChordEvent,
    ChordProgression,
    ChordQuality,
    detect_chord_progression,
    detect_chord_progression_for_song,
    detect_chord_progression_for_track,
    detect_chords,
    get_common_progressions,
    get_pitch_classes_in_window,
    identify_progression_pattern,
    match_chord,
    smooth_chord_progression,
)
from midi_analyzer.harmony.keys import KeySignature, Mode
from midi_analyzer.models.core import NoteEvent, Song, TempoEvent, TimeSignature, Track


def make_note(pitch: int, duration: float, start: float = 0.0) -> NoteEvent:
    """Helper to create note events."""
    return NoteEvent(
        pitch=pitch,
        velocity=100,
        start_tick=int(start * 480),
        start_beat=start,
        duration_beats=duration,
        track_id=0,
        channel=0,
    )


class TestChordDataclass:
    """Tests for Chord dataclass."""

    def test_chord_creation(self):
        """Test basic chord creation."""
        chord = Chord(root=0, quality=ChordQuality.MAJOR)
        assert chord.root == 0
        assert chord.quality == ChordQuality.MAJOR
        assert chord.bass is None
        assert chord.confidence == 1.0

    def test_chord_root_name(self):
        """Test root note name property."""
        chord = Chord(root=0, quality=ChordQuality.MAJOR)
        assert chord.root_name == "C"

        chord = Chord(root=9, quality=ChordQuality.MINOR)
        assert chord.root_name == "A"

    def test_chord_name_major(self):
        """Test major chord name."""
        chord = Chord(root=0, quality=ChordQuality.MAJOR)
        assert chord.name == "C"

    def test_chord_name_minor(self):
        """Test minor chord name."""
        chord = Chord(root=0, quality=ChordQuality.MINOR)
        assert chord.name == "Cm"

    def test_chord_name_seventh(self):
        """Test seventh chord name."""
        chord = Chord(root=0, quality=ChordQuality.DOMINANT_7)
        assert chord.name == "C7"

    def test_chord_name_with_bass(self):
        """Test chord name with bass note (inversion)."""
        chord = Chord(root=0, quality=ChordQuality.MAJOR, bass=4)
        assert chord.name == "C/E"

    def test_chord_str(self):
        """Test string representation."""
        chord = Chord(root=0, quality=ChordQuality.MAJOR)
        assert str(chord) == "C"


class TestChordRomanNumerals:
    """Tests for Roman numeral conversion."""

    def test_tonic_major(self):
        """Test I chord in major key."""
        chord = Chord(root=0, quality=ChordQuality.MAJOR)
        key = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        assert chord.to_roman_numeral(key) == "I"

    def test_dominant_major(self):
        """Test V chord in major key."""
        chord = Chord(root=7, quality=ChordQuality.MAJOR)
        key = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        assert chord.to_roman_numeral(key) == "V"

    def test_subdominant_major(self):
        """Test IV chord in major key."""
        chord = Chord(root=5, quality=ChordQuality.MAJOR)
        key = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        assert chord.to_roman_numeral(key) == "IV"

    def test_relative_minor_vi(self):
        """Test vi chord in major key."""
        chord = Chord(root=9, quality=ChordQuality.MINOR)
        key = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        assert chord.to_roman_numeral(key) == "vi"

    def test_diminished_vii(self):
        """Test vii° chord."""
        chord = Chord(root=11, quality=ChordQuality.DIMINISHED)
        key = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        assert "°" in chord.to_roman_numeral(key)

    def test_minor_key_tonic(self):
        """Test i chord in minor key."""
        chord = Chord(root=9, quality=ChordQuality.MINOR)
        key = KeySignature(root=9, mode=Mode.MINOR, confidence=0.9, correlation=0.8)
        assert chord.to_roman_numeral(key) == "i"


class TestChordMatching:
    """Tests for chord matching."""

    def test_match_c_major_triad(self):
        """Test matching C major triad."""
        pitch_classes = {0, 4, 7}  # C, E, G
        chord = match_chord(pitch_classes)

        assert chord.root == 0
        assert chord.quality == ChordQuality.MAJOR

    def test_match_a_minor_triad(self):
        """Test matching A minor triad."""
        pitch_classes = {9, 0, 4}  # A, C, E
        chord = match_chord(pitch_classes)

        assert chord.root == 9
        assert chord.quality == ChordQuality.MINOR

    def test_match_g_dominant_7(self):
        """Test matching G7 chord."""
        pitch_classes = {7, 11, 2, 5}  # G, B, D, F
        chord = match_chord(pitch_classes)

        assert chord.root == 7
        assert chord.quality == ChordQuality.DOMINANT_7

    def test_match_empty_returns_unknown(self):
        """Test matching empty pitch classes."""
        chord = match_chord(set())
        assert chord.quality == ChordQuality.UNKNOWN
        assert chord.confidence == 0.0

    def test_match_power_chord(self):
        """Test matching power chord."""
        pitch_classes = {0, 7}  # C, G
        chord = match_chord(pitch_classes)

        # Could be power chord or incomplete major/minor
        assert chord.root == 0
        assert chord.quality in (ChordQuality.POWER, ChordQuality.MAJOR, ChordQuality.MINOR)


class TestPitchClassesInWindow:
    """Tests for pitch class extraction."""

    def test_single_note_in_window(self):
        """Test extracting single note."""
        notes = [make_note(60, 2.0, 0.0)]  # Middle C
        result = get_pitch_classes_in_window(notes, 0.0, 2.0)

        assert 0 in result  # C
        assert result[0] == 2.0  # Full duration

    def test_partial_overlap(self):
        """Test partial note overlap with window."""
        notes = [make_note(60, 4.0, 0.0)]
        result = get_pitch_classes_in_window(notes, 1.0, 2.0)

        assert 0 in result
        assert result[0] == 1.0  # Only 1 beat in window

    def test_note_outside_window(self):
        """Test note outside window."""
        notes = [make_note(60, 1.0, 5.0)]
        result = get_pitch_classes_in_window(notes, 0.0, 2.0)

        assert len(result) == 0


class TestChordDetection:
    """Tests for chord detection."""

    def test_detect_single_chord(self):
        """Test detecting a single chord."""
        # C major chord
        notes = [
            make_note(60, 4.0, 0.0),  # C
            make_note(64, 4.0, 0.0),  # E
            make_note(67, 4.0, 0.0),  # G
        ]

        chords = detect_chords(notes, window_beats=4.0, hop_beats=4.0)

        assert len(chords) >= 1
        assert chords[0].chord.root == 0
        assert chords[0].chord.quality == ChordQuality.MAJOR

    def test_detect_chord_sequence(self):
        """Test detecting multiple chords."""
        # C major then G major
        notes = [
            make_note(60, 2.0, 0.0),  # C
            make_note(64, 2.0, 0.0),  # E
            make_note(67, 2.0, 0.0),  # G
            make_note(67, 2.0, 2.0),  # G
            make_note(71, 2.0, 2.0),  # B
            make_note(74, 2.0, 2.0),  # D
        ]

        chords = detect_chords(notes, window_beats=2.0, hop_beats=2.0)

        assert len(chords) >= 2

    def test_detect_empty_notes(self):
        """Test with empty notes."""
        chords = detect_chords([])
        assert len(chords) == 0


class TestChordSmoothing:
    """Tests for chord progression smoothing."""

    def test_merge_repeated_chords(self):
        """Test merging consecutive identical chords."""
        events = [
            ChordEvent(
                chord=Chord(root=0, quality=ChordQuality.MAJOR),
                start_beat=0.0,
                end_beat=1.0,
            ),
            ChordEvent(
                chord=Chord(root=0, quality=ChordQuality.MAJOR),
                start_beat=1.0,
                end_beat=2.0,
            ),
        ]

        smoothed = smooth_chord_progression(events)

        assert len(smoothed) == 1
        assert smoothed[0].start_beat == 0.0
        assert smoothed[0].end_beat == 2.0

    def test_keep_different_chords(self):
        """Test that different chords are kept."""
        events = [
            ChordEvent(
                chord=Chord(root=0, quality=ChordQuality.MAJOR),
                start_beat=0.0,
                end_beat=2.0,
            ),
            ChordEvent(
                chord=Chord(root=7, quality=ChordQuality.MAJOR),
                start_beat=2.0,
                end_beat=4.0,
            ),
        ]

        smoothed = smooth_chord_progression(events)

        assert len(smoothed) == 2

    def test_empty_input(self):
        """Test with empty input."""
        smoothed = smooth_chord_progression([])
        assert len(smoothed) == 0


class TestChordProgression:
    """Tests for ChordProgression class."""

    def test_to_roman_numerals_with_key(self):
        """Test Roman numeral conversion with key."""
        chords = [
            ChordEvent(
                chord=Chord(root=0, quality=ChordQuality.MAJOR),
                start_beat=0.0,
                end_beat=2.0,
            ),
            ChordEvent(
                chord=Chord(root=7, quality=ChordQuality.MAJOR),
                start_beat=2.0,
                end_beat=4.0,
            ),
        ]
        key = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        prog = ChordProgression(chords=chords, key=key)

        numerals = prog.to_roman_numerals()

        assert numerals == ["I", "V"]

    def test_to_roman_numerals_without_key(self):
        """Test that without key, chord names are returned."""
        chords = [
            ChordEvent(
                chord=Chord(root=0, quality=ChordQuality.MAJOR),
                start_beat=0.0,
                end_beat=2.0,
            ),
        ]
        prog = ChordProgression(chords=chords, key=None)

        numerals = prog.to_roman_numerals()

        assert numerals == ["C"]

    def test_simplify_removes_duplicates(self):
        """Test simplify removes consecutive duplicates."""
        chords = [
            ChordEvent(
                chord=Chord(root=0, quality=ChordQuality.MAJOR),
                start_beat=0.0,
                end_beat=1.0,
            ),
            ChordEvent(
                chord=Chord(root=0, quality=ChordQuality.MAJOR),
                start_beat=1.0,
                end_beat=2.0,
            ),
            ChordEvent(
                chord=Chord(root=7, quality=ChordQuality.MAJOR),
                start_beat=2.0,
                end_beat=4.0,
            ),
        ]
        prog = ChordProgression(chords=chords)

        simplified = prog.simplify()

        assert simplified == ["C", "G"]

    def test_simplify_empty(self):
        """Test simplify with empty progression."""
        prog = ChordProgression(chords=[])
        assert prog.simplify() == []


class TestProgressionDetection:
    """Tests for full progression detection."""

    def test_detect_chord_progression(self):
        """Test full chord progression detection."""
        # C - G - Am - F progression
        notes = [
            # C major
            make_note(60, 2.0, 0.0),
            make_note(64, 2.0, 0.0),
            make_note(67, 2.0, 0.0),
            # G major
            make_note(67, 2.0, 2.0),
            make_note(71, 2.0, 2.0),
            make_note(74, 2.0, 2.0),
            # A minor
            make_note(69, 2.0, 4.0),
            make_note(72, 2.0, 4.0),
            make_note(76, 2.0, 4.0),
            # F major
            make_note(65, 2.0, 6.0),
            make_note(69, 2.0, 6.0),
            make_note(72, 2.0, 6.0),
        ]

        prog = detect_chord_progression(notes, window_beats=2.0, hop_beats=2.0)

        assert len(prog.chords) >= 4
        assert prog.key is not None


class TestTrackAndSongDetection:
    """Tests for track and song chord detection."""

    def test_detect_for_track(self):
        """Test chord detection for a track."""
        notes = [
            make_note(60, 2.0, 0.0),
            make_note(64, 2.0, 0.0),
            make_note(67, 2.0, 0.0),
        ]
        track = Track(track_id=0, notes=notes)

        prog = detect_chord_progression_for_track(track)

        assert isinstance(prog, ChordProgression)

    def test_detect_for_song(self):
        """Test chord detection for a song."""
        notes = [
            make_note(60, 2.0, 0.0),
            make_note(64, 2.0, 0.0),
            make_note(67, 2.0, 0.0),
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

        prog = detect_chord_progression_for_song(song)

        assert isinstance(prog, ChordProgression)


class TestCommonProgressions:
    """Tests for common progression utilities."""

    def test_get_common_progressions(self):
        """Test getting common progressions."""
        common = get_common_progressions()

        assert "I-V-vi-IV" in common
        assert "ii-V-I" in common
        assert len(common) > 0

    def test_identify_I_V_vi_IV(self):
        """Test identifying the famous pop progression."""
        chords = [
            ChordEvent(
                chord=Chord(root=0, quality=ChordQuality.MAJOR),
                start_beat=0.0,
                end_beat=2.0,
            ),
            ChordEvent(
                chord=Chord(root=7, quality=ChordQuality.MAJOR),
                start_beat=2.0,
                end_beat=4.0,
            ),
            ChordEvent(
                chord=Chord(root=9, quality=ChordQuality.MINOR),
                start_beat=4.0,
                end_beat=6.0,
            ),
            ChordEvent(
                chord=Chord(root=5, quality=ChordQuality.MAJOR),
                start_beat=6.0,
                end_beat=8.0,
            ),
        ]
        key = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        prog = ChordProgression(chords=chords, key=key)

        pattern = identify_progression_pattern(prog)

        assert pattern == "I-V-vi-IV"

    def test_identify_no_match(self):
        """Test when no pattern matches."""
        chords = [
            ChordEvent(
                chord=Chord(root=0, quality=ChordQuality.MAJOR),
                start_beat=0.0,
                end_beat=2.0,
            ),
        ]
        key = KeySignature(root=0, mode=Mode.MAJOR, confidence=0.9, correlation=0.8)
        prog = ChordProgression(chords=chords, key=key)

        pattern = identify_progression_pattern(prog)

        assert pattern is None  # Too short to match any

    def test_identify_no_key(self):
        """Test identification without key."""
        prog = ChordProgression(chords=[], key=None)
        pattern = identify_progression_pattern(prog)
        assert pattern is None


class TestChordQuality:
    """Tests for chord quality enum."""

    def test_all_qualities(self):
        """Test all chord qualities have values."""
        assert ChordQuality.MAJOR.value == "major"
        assert ChordQuality.MINOR.value == "minor"
        assert ChordQuality.DIMINISHED.value == "dim"
        assert ChordQuality.AUGMENTED.value == "aug"


class TestChordEvent:
    """Tests for ChordEvent class."""

    def test_duration_beats(self):
        """Test duration calculation."""
        event = ChordEvent(
            chord=Chord(root=0, quality=ChordQuality.MAJOR),
            start_beat=2.0,
            end_beat=6.0,
        )
        assert event.duration_beats == 4.0
