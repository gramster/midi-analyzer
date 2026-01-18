"""Tests for arpeggio inference module (Stage 6)."""

import pytest

from midi_analyzer.analysis.arpeggios import (
    ArpAnalyzer,
    ArpWindow,
    analyze_arp_track,
    extract_arp_patterns,
)
from midi_analyzer.models.core import NoteEvent, Song, TimeSignature, Track


def make_note(pitch: int, start: float, duration: float = 0.125) -> NoteEvent:
    """Helper to create a note event."""
    return NoteEvent(
        pitch=pitch,
        velocity=100,
        start_beat=start,
        duration_beats=duration,
        track_id=0,
        channel=0,
        bar=int(start // 4),
    )


def make_song(tracks: list[Track], time_sig_map: list[TimeSignature] | None = None) -> Song:
    """Helper to create a Song with required fields."""
    return Song(
        song_id=0,
        source_path="test.mid",
        ticks_per_beat=480,
        tracks=tracks,
        time_sig_map=time_sig_map or [],
    )


class TestArpAnalyzer:
    """Tests for ArpAnalyzer class."""

    def test_empty_track(self) -> None:
        """Test analyzing empty track returns empty analysis."""
        track = Track(track_id=0, notes=[])
        analyzer = ArpAnalyzer()
        analysis = analyzer.analyze_track(track)

        assert analysis.track_id == 0
        assert analysis.windows == []
        assert analysis.patterns == []

    def test_simple_c_major_arp(self) -> None:
        """Test analyzing a simple C major arpeggio."""
        # C major arp: C4, E4, G4, C5 repeated
        notes = [
            make_note(60, 0.0),    # C4
            make_note(64, 0.25),   # E4
            make_note(67, 0.5),    # G4
            make_note(72, 0.75),   # C5
            make_note(60, 1.0),    # C4
            make_note(64, 1.25),   # E4
            make_note(67, 1.5),    # G4
            make_note(72, 1.75),   # C5
        ]
        track = Track(track_id=0, notes=notes)
        analyzer = ArpAnalyzer(window_beats=4.0, min_notes_per_window=4)
        analysis = analyzer.analyze_track(track)

        assert analysis.track_id == 0
        assert len(analysis.windows) >= 1

        # Check first window
        window = analysis.windows[0]
        assert window.inferred_chord is not None
        assert window.inferred_chord.root == 0  # C
        assert len(window.interval_sequence) >= 4
        # Intervals should be 0 (C), 4 (E), 7 (G), 0 (C octave up)
        assert window.interval_sequence[:4] == [0, 4, 7, 0]

    def test_rate_detection_sixteenth(self) -> None:
        """Test 16th note rate detection."""
        # Notes at 16th note intervals (0.25 beats)
        notes = [make_note(60, i * 0.25) for i in range(16)]
        track = Track(track_id=0, notes=notes)

        analyzer = ArpAnalyzer()
        analysis = analyzer.analyze_track(track)

        assert analysis.dominant_rate == "1/16"

    def test_rate_detection_eighth(self) -> None:
        """Test 8th note rate detection."""
        # Notes at 8th note intervals (0.5 beats)
        notes = [make_note(60, i * 0.5) for i in range(8)]
        track = Track(track_id=0, notes=notes)

        analyzer = ArpAnalyzer()
        analysis = analyzer.analyze_track(track)

        assert analysis.dominant_rate == "1/8"

    def test_octave_jumps_detection(self) -> None:
        """Test octave jump detection in arpeggios."""
        # Arp spanning octaves: C3, E3, G3, C4, E4, G4, C5
        # This gives us a C major chord across multiple octaves
        notes = [
            make_note(48, 0.0),   # C3
            make_note(52, 0.25),  # E3
            make_note(55, 0.5),   # G3
            make_note(60, 0.75),  # C4
            make_note(64, 1.0),   # E4
            make_note(67, 1.25),  # G4
            make_note(72, 1.5),   # C5
        ]
        track = Track(track_id=0, notes=notes)

        analyzer = ArpAnalyzer()
        analysis = analyzer.analyze_track(track)

        assert len(analysis.windows) >= 1
        window = analysis.windows[0]
        # Should infer C major chord and detect octave jumps
        assert window.inferred_chord is not None
        assert len(window.octave_jumps) == 7

    def test_minor_chord_inference(self) -> None:
        """Test minor chord inference."""
        # A minor arp: A, C, E
        notes = [
            make_note(57, 0.0),   # A3
            make_note(60, 0.25),  # C4
            make_note(64, 0.5),   # E4
            make_note(69, 0.75),  # A4
        ]
        track = Track(track_id=0, notes=notes)

        analyzer = ArpAnalyzer()
        analysis = analyzer.analyze_track(track)

        window = analysis.windows[0]
        assert window.inferred_chord is not None
        # Root should be A (9)
        assert window.inferred_chord.root == 9

    def test_gate_calculation(self) -> None:
        """Test gate (sustain ratio) calculation."""
        # Short staccato notes (low gate)
        short_notes = [make_note(60, i * 0.5, duration=0.1) for i in range(8)]
        track_short = Track(track_id=0, notes=short_notes)

        # Long legato notes (high gate)
        long_notes = [make_note(60, i * 0.5, duration=0.45) for i in range(8)]
        track_long = Track(track_id=1, notes=long_notes)

        analyzer = ArpAnalyzer()

        analysis_short = analyzer.analyze_track(track_short)
        analysis_long = analyzer.analyze_track(track_long)

        # Short notes should have lower gate
        assert analysis_short.avg_gate < analysis_long.avg_gate
        assert analysis_short.avg_gate < 0.5
        assert analysis_long.avg_gate > 0.7

    def test_multiple_windows(self) -> None:
        """Test analysis across multiple windows."""
        # Create 16 beats of arp (4 windows at 4 beats each)
        notes = []
        for bar in range(4):
            base_beat = bar * 4
            for i in range(8):
                notes.append(make_note(60 + (i % 4) * 4, base_beat + i * 0.5))

        track = Track(track_id=0, notes=notes)
        analyzer = ArpAnalyzer(window_beats=4.0)
        analysis = analyzer.analyze_track(track)

        assert len(analysis.windows) == 4

    def test_pattern_extraction(self) -> None:
        """Test extraction of ArpPattern objects."""
        # Clear C major arp pattern
        notes = [
            make_note(60, i * 0.25 + bar * 4)
            for bar in range(2)
            for i, pitch in enumerate([60, 64, 67, 72] * 4)
        ]
        # Recreate properly
        notes = []
        for bar in range(2):
            for i in range(16):
                pitch = [60, 64, 67, 72][i % 4]
                notes.append(make_note(pitch, bar * 4 + i * 0.25))

        track = Track(track_id=0, notes=notes)
        patterns = extract_arp_patterns(track, min_confidence=0.3)

        assert len(patterns) >= 1
        # Check pattern structure
        pattern = patterns[0]
        assert pattern.rate in ["1/16", "1/8"]
        assert len(pattern.interval_sequence) >= 4


class TestArpWindow:
    """Tests for ArpWindow dataclass."""

    def test_creation(self) -> None:
        """Test ArpWindow creation."""
        window = ArpWindow(start_beat=0.0, end_beat=4.0)
        assert window.start_beat == 0.0
        assert window.end_beat == 4.0
        assert window.notes == []
        assert window.inferred_chord is None


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_analyze_arp_track(self) -> None:
        """Test analyze_arp_track function."""
        notes = [make_note(60, i * 0.25) for i in range(8)]
        track = Track(track_id=0, notes=notes)

        analysis = analyze_arp_track(track)
        assert analysis.track_id == 0
        assert len(analysis.windows) >= 1

    def test_extract_arp_patterns_empty(self) -> None:
        """Test extract_arp_patterns with empty track."""
        track = Track(track_id=0, notes=[])
        patterns = extract_arp_patterns(track)
        assert patterns == []

    def test_with_song_context(self) -> None:
        """Test analysis with Song context for time signature."""
        notes = [make_note(60, i * 0.25) for i in range(24)]  # 6 beats worth
        track = Track(track_id=0, notes=notes)

        song = make_song(
            tracks=[track],
            time_sig_map=[TimeSignature(
                tick=0,
                beat=0.0,
                bar=0,
                numerator=3,
                denominator=4,
            )],
        )

        analyzer = ArpAnalyzer()
        analysis = analyzer.analyze_track(track, song)

        # With 3/4 time, windows should be 3 beats
        # 6 beats / 3 beats per window = 2 windows
        assert len(analysis.windows) == 2
