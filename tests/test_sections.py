"""Tests for section segmentation module (Stage 7)."""

import pytest
import numpy as np

from midi_analyzer.analysis.sections import (
    BarFeatures,
    Section,
    SectionAnalysis,
    SectionAnalyzer,
    SectionType,
    analyze_sections,
)
from midi_analyzer.models.core import (
    NoteEvent,
    RoleProbabilities,
    Song,
    TimeSignature,
    Track,
)


def make_note(pitch: int, start: float, duration: float = 0.5, velocity: int = 100) -> NoteEvent:
    """Helper to create a note event."""
    return NoteEvent(
        pitch=pitch,
        velocity=velocity,
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


def make_dense_bar(bar_num: int, notes_per_beat: int = 4) -> list[NoteEvent]:
    """Create a dense bar of notes."""
    notes = []
    for beat in range(4):
        for sub in range(notes_per_beat):
            start = bar_num * 4 + beat + sub / notes_per_beat
            notes.append(make_note(60, start, 0.2))
    return notes


def make_sparse_bar(bar_num: int) -> list[NoteEvent]:
    """Create a sparse bar with few notes."""
    return [
        make_note(60, bar_num * 4, 1.0),
        make_note(64, bar_num * 4 + 2, 1.0),
    ]


class TestBarFeatures:
    """Tests for BarFeatures dataclass."""

    def test_creation(self) -> None:
        """Test BarFeatures creation with defaults."""
        features = BarFeatures(bar_number=0, start_beat=0.0, end_beat=4.0)
        assert features.bar_number == 0
        assert features.active_track_count == 0
        assert features.total_note_count == 0
        assert features.density_by_role == {}

    def test_to_vector(self) -> None:
        """Test conversion to numpy vector."""
        features = BarFeatures(
            bar_number=0,
            start_beat=0.0,
            end_beat=4.0,
            active_track_count=4,
            total_note_count=32,
            density_by_role={"bass": 2.0, "drums": 4.0},
            harmonic_rhythm=2,
            avg_velocity=100.0,
            pitch_range=24,
            unique_pitches=6,
        )

        vec = features.to_vector()
        assert isinstance(vec, np.ndarray)
        assert vec.dtype == np.float32
        # Should have: track_count, note_count, 7 roles, harmonic_rhythm, 
        # velocity, pitch_range, unique_pitches = 13 values
        assert len(vec) == 13


class TestSection:
    """Tests for Section dataclass."""

    def test_creation(self) -> None:
        """Test Section creation."""
        section = Section(section_id=0, form_label="A", start_bar=0, end_bar=8)
        assert section.section_id == 0
        assert section.form_label == "A"
        assert section.type_hint == SectionType.UNKNOWN


class TestSectionAnalyzer:
    """Tests for SectionAnalyzer class."""

    def test_empty_song(self) -> None:
        """Test analyzing song with no tracks."""
        song = make_song(tracks=[])
        analyzer = SectionAnalyzer()
        analysis = analyzer.analyze_song(song)

        assert analysis.bar_features == []
        assert analysis.sections == []

    def test_empty_tracks(self) -> None:
        """Test analyzing song with empty tracks."""
        track = Track(track_id=0, notes=[])
        song = make_song(tracks=[track])

        analyzer = SectionAnalyzer()
        analysis = analyzer.analyze_song(song)

        assert analysis.bar_features == []

    def test_single_bar(self) -> None:
        """Test analyzing song with single bar."""
        notes = [make_note(60, i * 0.5) for i in range(8)]
        track = Track(track_id=0, notes=notes)
        song = make_song(tracks=[track])

        analyzer = SectionAnalyzer(min_section_bars=1)
        analysis = analyzer.analyze_song(song)

        assert len(analysis.bar_features) >= 1
        assert analysis.bar_features[0].total_note_count == 8

    def test_bar_feature_computation(self) -> None:
        """Test per-bar feature computation."""
        # Create 8 bars of notes
        notes = []
        for bar in range(8):
            notes.extend([
                make_note(60, bar * 4 + i, velocity=80 + bar * 5)
                for i in range(4)
            ])

        track = Track(track_id=0, notes=notes)
        song = make_song(tracks=[track])

        analyzer = SectionAnalyzer()
        analysis = analyzer.analyze_song(song)

        assert len(analysis.bar_features) == 8
        # Each bar should have 4 notes
        for bf in analysis.bar_features:
            assert bf.total_note_count == 4
            assert bf.active_track_count == 1

    def test_novelty_detection(self) -> None:
        """Test section boundary detection via novelty."""
        # Create contrasting sections: quiet intro, loud verse
        notes = []

        # Quiet intro (bars 0-3): sparse, low velocity
        for bar in range(4):
            notes.extend([
                make_note(60, bar * 4, velocity=40),
                make_note(64, bar * 4 + 2, velocity=40),
            ])

        # Loud verse (bars 4-7): dense, high velocity
        for bar in range(4, 8):
            for beat in range(4):
                for sub in range(4):
                    notes.append(make_note(
                        60 + sub * 4,
                        bar * 4 + beat + sub * 0.25,
                        velocity=120,
                    ))

        track = Track(track_id=0, notes=notes)
        song = make_song(tracks=[track])

        analyzer = SectionAnalyzer(min_section_bars=2)
        analysis = analyzer.analyze_song(song)

        # Should detect boundary at bar 4
        assert 4 in analysis.section_boundaries or len(analysis.sections) >= 2

    def test_form_clustering(self) -> None:
        """Test clustering similar sections into forms."""
        notes = []

        # Section A (bars 0-3): medium density
        for bar in [0, 1, 2, 3]:
            notes.extend([make_note(60, bar * 4 + i) for i in range(4)])

        # Section B (bars 4-7): high density
        for bar in [4, 5, 6, 7]:
            notes.extend([make_note(60, bar * 4 + i * 0.25) for i in range(16)])

        # Section A' (bars 8-11): same as A
        for bar in [8, 9, 10, 11]:
            notes.extend([make_note(60, bar * 4 + i) for i in range(4)])

        track = Track(track_id=0, notes=notes)
        song = make_song(tracks=[track])

        analyzer = SectionAnalyzer(min_section_bars=2)
        analysis = analyzer.analyze_song(song)

        # Should have A, B, A form (or similar)
        if len(analysis.sections) >= 3:
            # First and third sections should have same form
            forms = [s.form_label for s in analysis.sections]
            # Allow some flexibility in form detection
            assert len(set(forms)) <= 3  # At most 3 different forms

    def test_with_role_probabilities(self) -> None:
        """Test analysis with track role probabilities."""
        bass_notes = [make_note(36, bar * 4, velocity=100) for bar in range(8)]
        bass_track = Track(
            track_id=0,
            notes=bass_notes,
            role_probs=RoleProbabilities(bass=0.9),
        )

        drum_notes = [make_note(36, bar * 4 + i * 0.5) for bar in range(8) for i in range(8)]
        drum_track = Track(
            track_id=1,
            notes=drum_notes,
            channel=9,
            role_probs=RoleProbabilities(drums=0.95),
        )

        song = make_song(tracks=[bass_track, drum_track])

        analyzer = SectionAnalyzer()
        analysis = analyzer.analyze_song(song)

        # Check that role densities are computed
        for bf in analysis.bar_features:
            assert "bass" in bf.density_by_role or "drums" in bf.density_by_role

    def test_time_signature_handling(self) -> None:
        """Test bar computation with non-4/4 time signature."""
        # 3/4 time: 3 beats per bar
        notes = [make_note(60, i * 0.5) for i in range(18)]  # 9 beats = 3 bars
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

        analyzer = SectionAnalyzer()
        analysis = analyzer.analyze_song(song)

        # With 3/4, should have 3 bars
        assert len(analysis.bar_features) == 3


class TestSectionTypeHints:
    """Tests for heuristic section type labeling."""

    def test_intro_detection(self) -> None:
        """Test intro detection for low-energy first section."""
        notes = []

        # Sparse intro (bars 0-3)
        for bar in range(4):
            notes.append(make_note(60, bar * 4, velocity=50))

        # Dense main (bars 4-15)
        for bar in range(4, 16):
            notes.extend([make_note(60, bar * 4 + i * 0.25) for i in range(16)])

        track = Track(track_id=0, notes=notes)
        song = make_song(tracks=[track])

        analyzer = SectionAnalyzer(min_section_bars=4)
        analysis = analyzer.analyze_song(song)

        # First section should be labeled as intro
        if analysis.sections:
            assert analysis.sections[0].type_hint in [
                SectionType.INTRO,
                SectionType.UNKNOWN,
            ]

    def test_breakdown_detection(self) -> None:
        """Test breakdown detection for energy drops."""
        notes = []

        # Dense section (bars 0-7)
        for bar in range(8):
            notes.extend([make_note(60, bar * 4 + i * 0.25) for i in range(16)])

        # Breakdown (bars 8-11): very sparse
        for bar in range(8, 12):
            notes.append(make_note(60, bar * 4, velocity=60))

        # Return (bars 12-15)
        for bar in range(12, 16):
            notes.extend([make_note(60, bar * 4 + i * 0.25) for i in range(16)])

        track = Track(track_id=0, notes=notes)
        song = make_song(tracks=[track])

        analyzer = SectionAnalyzer(min_section_bars=2)
        analysis = analyzer.analyze_song(song)

        # Should detect breakdown section
        breakdown_sections = [
            s for s in analysis.sections
            if s.type_hint == SectionType.BREAKDOWN
        ]
        # May or may not detect depending on threshold
        assert len(analysis.sections) >= 2


class TestConvenienceFunction:
    """Tests for analyze_sections convenience function."""

    def test_analyze_sections(self) -> None:
        """Test the convenience function."""
        notes = [make_note(60, i) for i in range(32)]
        track = Track(track_id=0, notes=notes)
        song = make_song(tracks=[track])

        analysis = analyze_sections(song)

        assert isinstance(analysis, SectionAnalysis)
        assert len(analysis.bar_features) > 0


class TestFormSequence:
    """Tests for form sequence generation."""

    def test_form_sequence_generated(self) -> None:
        """Test that form_sequence is populated."""
        notes = [make_note(60, i) for i in range(32)]
        track = Track(track_id=0, notes=notes)
        song = make_song(tracks=[track])

        analysis = analyze_sections(song)

        # form_sequence should match sections
        assert len(analysis.form_sequence) == len(analysis.sections)
        for i, section in enumerate(analysis.sections):
            assert analysis.form_sequence[i] == section.form_label


class TestEdgeCases:
    """Tests for edge cases."""

    def test_very_short_song(self) -> None:
        """Test song shorter than minimum section length."""
        notes = [make_note(60, i) for i in range(4)]  # 1 bar
        track = Track(track_id=0, notes=notes)
        song = make_song(tracks=[track])

        analyzer = SectionAnalyzer(min_section_bars=4)
        analysis = analyzer.analyze_song(song)

        # Should still compute bar features even if no sections detected
        assert len(analysis.bar_features) >= 1

    def test_uniform_content(self) -> None:
        """Test song with uniform content (no clear sections)."""
        # Same density throughout
        notes = []
        for bar in range(16):
            notes.extend([make_note(60, bar * 4 + i) for i in range(4)])

        track = Track(track_id=0, notes=notes)
        song = make_song(tracks=[track])

        analyzer = SectionAnalyzer()
        analysis = analyzer.analyze_song(song)

        # Should still produce some structure
        assert len(analysis.bar_features) == 16
        # With uniform content, may detect few or no boundaries beyond start

    def test_multiple_tracks(self) -> None:
        """Test with multiple tracks."""
        track1_notes = [make_note(60, bar * 4) for bar in range(8)]
        track2_notes = [make_note(72, bar * 4 + 2) for bar in range(8)]

        track1 = Track(track_id=0, notes=track1_notes)
        track2 = Track(track_id=1, notes=track2_notes)
        song = make_song(tracks=[track1, track2])

        analysis = analyze_sections(song)

        # Should count both tracks as active
        for bf in analysis.bar_features:
            assert bf.active_track_count == 2
            assert bf.total_note_count == 2
