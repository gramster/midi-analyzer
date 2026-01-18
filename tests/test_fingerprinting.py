"""Tests for fingerprinting."""

import pytest

from midi_analyzer.models.core import NoteEvent
from midi_analyzer.patterns.chunking import BarChunk
from midi_analyzer.patterns.fingerprinting import (
    CombinedFingerprint,
    Fingerprinter,
    PitchFingerprint,
    RhythmFingerprint,
    pitch_fingerprint,
    rhythm_fingerprint,
)


class TestRhythmFingerprint:
    """Tests for RhythmFingerprint."""

    def test_basic_fingerprint(self) -> None:
        """Test basic fingerprint creation."""
        onset = (1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)
        accent = (1.0, 0, 0, 0, 0.8, 0, 0, 0, 0.6, 0, 0, 0, 0.4, 0, 0, 0)

        fp = RhythmFingerprint(
            onset_grid=onset,
            accent_grid=accent,
            grid_size=16,
            num_bars=1,
            note_count=4,
        )

        assert fp.note_count == 4
        assert fp.density == 4 / 16
        assert fp.hash_value  # Should have computed hash

    def test_hash_stability(self) -> None:
        """Test that same onset pattern produces same hash."""
        onset = (1, 0, 1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        fp1 = RhythmFingerprint(
            onset_grid=onset,
            accent_grid=tuple([0.5] * 16),
            grid_size=16,
            num_bars=1,
            note_count=4,
        )

        fp2 = RhythmFingerprint(
            onset_grid=onset,
            accent_grid=tuple([0.8] * 16),  # Different accents
            grid_size=16,
            num_bars=1,
            note_count=4,
        )

        # Same onset pattern should give same hash
        assert fp1.hash_value == fp2.hash_value

    def test_to_dict(self) -> None:
        """Test serialization."""
        fp = RhythmFingerprint(
            onset_grid=(1, 0, 0, 0),
            accent_grid=(1.0, 0.0, 0.0, 0.0),
            grid_size=4,
            num_bars=1,
            note_count=1,
        )

        d = fp.to_dict()
        assert d["onset_grid"] == [1, 0, 0, 0]
        assert "hash" in d
        assert "density" in d


class TestPitchFingerprint:
    """Tests for PitchFingerprint."""

    def test_basic_fingerprint(self) -> None:
        """Test basic pitch fingerprint."""
        fp = PitchFingerprint(
            intervals=(2, 2, 1),  # C-D-E-F
            pitch_classes=(1, 0, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0),  # C, D, E, F
            contour=(1, 1, 1),  # All ascending
            range_semitones=5,
            mean_pitch=62.0,
        )

        assert fp.range_semitones == 5
        assert len(fp.intervals) == 3

    def test_transposition_invariant_hash(self) -> None:
        """Test that transposition produces same interval hash."""
        # C-E-G intervals
        fp1 = PitchFingerprint(
            intervals=(4, 3),  # Major third + minor third
            pitch_classes=(1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0),
            contour=(1, 1),
            range_semitones=7,
            mean_pitch=64.0,
        )

        # D-F#-A intervals (same pattern, transposed)
        fp2 = PitchFingerprint(
            intervals=(4, 3),  # Same intervals!
            pitch_classes=(0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0, 0),
            contour=(1, 1),
            range_semitones=7,
            mean_pitch=66.0,
        )

        assert fp1.hash_value == fp2.hash_value

    def test_to_dict(self) -> None:
        """Test serialization."""
        fp = PitchFingerprint(
            intervals=(2,),
            pitch_classes=tuple([0] * 12),
            contour=(1,),
            range_semitones=2,
            mean_pitch=60.0,
        )

        d = fp.to_dict()
        assert d["intervals"] == [2]
        assert d["range_semitones"] == 2
        assert "hash" in d


class TestCombinedFingerprint:
    """Tests for CombinedFingerprint."""

    def test_combined_hash(self) -> None:
        """Test combined hash from rhythm and pitch."""
        rhythm = RhythmFingerprint(
            onset_grid=(1, 0, 1, 0),
            accent_grid=(1.0, 0, 0.5, 0),
            grid_size=4,
            num_bars=1,
            note_count=2,
        )

        pitch = PitchFingerprint(
            intervals=(2,),
            pitch_classes=tuple([0] * 12),
            contour=(1,),
            range_semitones=2,
            mean_pitch=60.0,
        )

        combined = CombinedFingerprint(rhythm=rhythm, pitch=pitch)

        assert combined.hash_value
        assert combined.hash_value != rhythm.hash_value
        assert combined.hash_value != pitch.hash_value

    def test_to_dict(self) -> None:
        """Test serialization."""
        rhythm = RhythmFingerprint(
            onset_grid=(1,),
            accent_grid=(1.0,),
            grid_size=1,
            num_bars=1,
            note_count=1,
        )

        pitch = PitchFingerprint(
            intervals=(),
            pitch_classes=tuple([0] * 12),
            contour=(),
            range_semitones=0,
            mean_pitch=60.0,
        )

        combined = CombinedFingerprint(rhythm=rhythm, pitch=pitch)
        d = combined.to_dict()

        assert "rhythm" in d
        assert "pitch" in d
        assert "hash" in d


class TestFingerprinter:
    """Tests for Fingerprinter class."""

    @pytest.fixture
    def simple_chunk(self) -> BarChunk:
        """Create a simple bar chunk with 4 quarter notes."""
        notes = [
            NoteEvent(
                pitch=60 + i * 2,  # C, D, E, F#
                velocity=100 - i * 10,  # Decreasing velocity
                start_beat=float(i),  # 0, 1, 2, 3
                duration_beats=0.5,
                track_id=0,
                channel=0,
            )
            for i in range(4)
        ]

        return BarChunk(
            start_bar=0,
            end_bar=1,
            num_bars=1,
            notes=notes,
            beats_per_bar=4.0,
        )

    def test_rhythm_fingerprint_onsets(self, simple_chunk: BarChunk) -> None:
        """Test rhythm fingerprint captures correct onsets."""
        fp = Fingerprinter(grid_size=16)
        rhythm = fp.rhythm_fingerprint(simple_chunk)

        # Notes at beats 0, 1, 2, 3 should be at steps 0, 4, 8, 12
        assert rhythm.onset_grid[0] == 1
        assert rhythm.onset_grid[4] == 1
        assert rhythm.onset_grid[8] == 1
        assert rhythm.onset_grid[12] == 1
        assert sum(rhythm.onset_grid) == 4

    def test_rhythm_fingerprint_accents(self, simple_chunk: BarChunk) -> None:
        """Test rhythm fingerprint captures velocity."""
        fp = Fingerprinter(grid_size=16)
        rhythm = fp.rhythm_fingerprint(simple_chunk)

        # First note has highest velocity (100)
        assert rhythm.accent_grid[0] > rhythm.accent_grid[4]

    def test_pitch_fingerprint_intervals(self, simple_chunk: BarChunk) -> None:
        """Test pitch fingerprint captures intervals."""
        fp = Fingerprinter()
        pitch = fp.pitch_fingerprint(simple_chunk)

        # Notes: C, D, E, F# (pitches 60, 62, 64, 66)
        # Intervals: +2, +2, +2
        assert pitch.intervals == (2, 2, 2)
        assert pitch.contour == (1, 1, 1)  # All ascending

    def test_pitch_fingerprint_range(self, simple_chunk: BarChunk) -> None:
        """Test pitch fingerprint range calculation."""
        fp = Fingerprinter()
        pitch = fp.pitch_fingerprint(simple_chunk)

        # Range from C (60) to F# (66) = 6 semitones
        assert pitch.range_semitones == 6

    def test_combined_fingerprint(self, simple_chunk: BarChunk) -> None:
        """Test combined fingerprint generation."""
        fp = Fingerprinter()
        combined = fp.fingerprint(simple_chunk)

        assert combined.rhythm.note_count == 4
        assert len(combined.pitch.intervals) == 3
        assert combined.hash_value

    def test_empty_chunk(self) -> None:
        """Test fingerprinting empty chunk."""
        empty = BarChunk(
            start_bar=0,
            end_bar=1,
            num_bars=1,
            notes=[],
            beats_per_bar=4.0,
        )

        fp = Fingerprinter()
        rhythm = fp.rhythm_fingerprint(empty)
        pitch = fp.pitch_fingerprint(empty)

        assert rhythm.note_count == 0
        assert sum(rhythm.onset_grid) == 0
        assert pitch.range_semitones == 0

    def test_fingerprint_multiple_chunks(self, simple_chunk: BarChunk) -> None:
        """Test fingerprinting a list of chunks."""
        fp = Fingerprinter()
        chunks = [simple_chunk, simple_chunk]
        fingerprints = fp.fingerprint_track_chunks(chunks)

        assert len(fingerprints) == 2
        # Same chunk should produce same fingerprint
        assert fingerprints[0].hash_value == fingerprints[1].hash_value


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_rhythm_fingerprint_function(self) -> None:
        """Test rhythm_fingerprint convenience function."""
        notes = [
            NoteEvent(
                pitch=60,
                velocity=100,
                start_beat=0.0,
                duration_beats=0.5,
                track_id=0,
                channel=0,
            ),
            NoteEvent(
                pitch=62,
                velocity=100,
                start_beat=0.5,
                duration_beats=0.5,
                track_id=0,
                channel=0,
            ),
        ]

        fp = rhythm_fingerprint(notes, beats_per_bar=4.0, num_bars=1, grid_size=8)

        assert fp.grid_size == 8
        assert fp.note_count == 2
        # Notes at beat 0 and 0.5 = steps 0 and 1 (with 8 steps per bar)
        assert fp.onset_grid[0] == 1
        assert fp.onset_grid[1] == 1

    def test_pitch_fingerprint_function(self) -> None:
        """Test pitch_fingerprint convenience function."""
        notes = [
            NoteEvent(
                pitch=60,
                velocity=100,
                start_beat=0.0,
                duration_beats=0.5,
                track_id=0,
                channel=0,
            ),
            NoteEvent(
                pitch=64,
                velocity=100,
                start_beat=1.0,
                duration_beats=0.5,
                track_id=0,
                channel=0,
            ),
        ]

        fp = pitch_fingerprint(notes)

        assert fp.intervals == (4,)  # Major third
        assert fp.range_semitones == 4
