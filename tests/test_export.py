"""Tests for MIDI export functionality."""

from __future__ import annotations

import tempfile
from pathlib import Path

import mido
import pytest

from midi_analyzer.export import (
    ExportOptions,
    export_song,
    export_track,
    export_tracks,
    extract_clip,
)
from midi_analyzer.models.core import NoteEvent, Song, TempoEvent, TimeSignature, Track


@pytest.fixture
def sample_track() -> Track:
    """Create a sample track for testing."""
    return Track(
        track_id=0,
        name="Test Bass",
        channel=0,
        notes=[
            NoteEvent(pitch=36, velocity=100, start_beat=0.0, duration_beats=1.0, track_id=0, channel=0),
            NoteEvent(pitch=38, velocity=90, start_beat=1.0, duration_beats=1.0, track_id=0, channel=0),
            NoteEvent(pitch=40, velocity=80, start_beat=2.0, duration_beats=2.0, track_id=0, channel=0),
            NoteEvent(pitch=41, velocity=85, start_beat=4.0, duration_beats=1.0, track_id=0, channel=0),
        ],
    )


@pytest.fixture
def sample_song(sample_track: Track) -> Song:
    """Create a sample song for testing."""
    return Song(
        song_id="test123",
        source_path="/test/song.mid",
        ticks_per_beat=480,
        tempo_map=[TempoEvent(tick=0, beat=0.0, tempo_bpm=120.0, microseconds_per_beat=500000)],
        time_sig_map=[TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4)],
        tracks=[sample_track],
        total_bars=2,
        total_beats=8.0,
    )


class TestExportTrack:
    """Tests for export_track function."""

    def test_basic_export(self, sample_track: Track):
        """Test basic track export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            result = export_track(sample_track, output)

            assert result == output
            assert output.exists()

            # Verify MIDI file structure
            midi = mido.MidiFile(output)
            assert len(midi.tracks) == 1

    def test_export_with_tempo(self, sample_track: Track):
        """Test export includes tempo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            export_track(sample_track, output, tempo_bpm=140.0)

            midi = mido.MidiFile(output)
            # Find tempo message
            tempo_msgs = [m for m in midi.tracks[0] if m.type == "set_tempo"]
            assert len(tempo_msgs) == 1
            assert tempo_msgs[0].tempo == int(60_000_000 / 140.0)

    def test_export_without_tempo(self, sample_track: Track):
        """Test export without tempo."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            options = ExportOptions(include_tempo=False)
            export_track(sample_track, output, options=options)

            midi = mido.MidiFile(output)
            tempo_msgs = [m for m in midi.tracks[0] if m.type == "set_tempo"]
            assert len(tempo_msgs) == 0

    def test_export_with_time_signature(self, sample_track: Track):
        """Test export includes time signature."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            export_track(sample_track, output, time_sig=(3, 4))

            midi = mido.MidiFile(output)
            ts_msgs = [m for m in midi.tracks[0] if m.type == "time_signature"]
            assert len(ts_msgs) == 1
            assert ts_msgs[0].numerator == 3
            assert ts_msgs[0].denominator == 4

    def test_export_transpose(self, sample_track: Track):
        """Test transposition on export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            options = ExportOptions(transpose=12)  # Up one octave
            export_track(sample_track, output, options=options)

            midi = mido.MidiFile(output)
            note_ons = [m for m in midi.tracks[0] if m.type == "note_on" and m.velocity > 0]
            # First note should be 36 + 12 = 48
            assert note_ons[0].note == 48

    def test_export_velocity_scale(self, sample_track: Track):
        """Test velocity scaling on export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            options = ExportOptions(velocity_scale=0.5)
            export_track(sample_track, output, options=options)

            midi = mido.MidiFile(output)
            note_ons = [m for m in midi.tracks[0] if m.type == "note_on" and m.velocity > 0]
            # First note velocity should be 100 * 0.5 = 50
            assert note_ons[0].velocity == 50

    def test_export_normalize_start(self, sample_track: Track):
        """Test start normalization."""
        # Create track starting at beat 4
        track = Track(
            track_id=0,
            name="Late Start",
            channel=0,
            notes=[
                NoteEvent(pitch=60, velocity=100, start_beat=4.0, duration_beats=1.0, track_id=0, channel=0),
                NoteEvent(pitch=62, velocity=100, start_beat=5.0, duration_beats=1.0, track_id=0, channel=0),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            options = ExportOptions(normalize_start=True)
            export_track(track, output, options=options)

            midi = mido.MidiFile(output)
            note_ons = [m for m in midi.tracks[0] if m.type == "note_on" and m.velocity > 0]
            # First note should start at time 0
            assert note_ons[0].time == 0

    def test_export_empty_track(self):
        """Test exporting empty track."""
        track = Track(track_id=0, name="Empty", channel=0, notes=[])

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            result = export_track(track, output)

            assert result.exists()
            midi = mido.MidiFile(output)
            assert len(midi.tracks) == 1

    def test_creates_parent_dirs(self, sample_track: Track):
        """Test that parent directories are created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "subdir" / "nested" / "test.mid"
            result = export_track(sample_track, output)

            assert result.exists()


class TestExportTracks:
    """Tests for export_tracks function."""

    def test_multi_track_export(self):
        """Test exporting multiple tracks."""
        tracks = [
            Track(
                track_id=0,
                name="Bass",
                channel=0,
                notes=[NoteEvent(pitch=36, velocity=100, start_beat=0.0, duration_beats=1.0, track_id=0, channel=0)],
            ),
            Track(
                track_id=1,
                name="Drums",
                channel=9,
                notes=[NoteEvent(pitch=42, velocity=100, start_beat=0.0, duration_beats=0.5, track_id=1, channel=9)],
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            result = export_tracks(tracks, output)

            assert result.exists()
            midi = mido.MidiFile(output)
            # Tempo track + 2 note tracks
            assert len(midi.tracks) == 3

    def test_empty_tracks_list(self):
        """Test exporting empty tracks list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            result = export_tracks([], output)

            assert result.exists()


class TestExportSong:
    """Tests for export_song function."""

    def test_song_export(self, sample_song: Song):
        """Test full song export."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            result = export_song(sample_song, output)

            assert result.exists()
            midi = mido.MidiFile(output)
            assert midi.ticks_per_beat == sample_song.ticks_per_beat


class TestExtractClip:
    """Tests for extract_clip function."""

    def test_basic_extraction(self, sample_track: Track):
        """Test basic clip extraction."""
        # Extract bars 0-1 (beats 0-4)
        clip = extract_clip(sample_track, start_bar=0, end_bar=1, beats_per_bar=4.0)

        # Should include notes at beats 0, 1, 2 (not 4)
        assert len(clip.notes) == 3
        assert clip.notes[0].pitch == 36
        assert clip.notes[0].start_beat == 0.0

    def test_extraction_with_offset(self, sample_track: Track):
        """Test clip extraction shifts timing."""
        # Extract bar 1 (beats 4-8)
        clip = extract_clip(sample_track, start_bar=1, end_bar=2, beats_per_bar=4.0)

        # Should include note at beat 4, shifted to beat 0
        assert len(clip.notes) == 1
        assert clip.notes[0].pitch == 41
        assert clip.notes[0].start_beat == 0.0

    def test_extraction_preserves_metadata(self, sample_track: Track):
        """Test clip preserves track metadata."""
        clip = extract_clip(sample_track, start_bar=0, end_bar=1)

        assert clip.track_id == sample_track.track_id
        assert clip.channel == sample_track.channel
        assert "bars 0-1" in clip.name

    def test_empty_range(self):
        """Test extracting from range with no notes."""
        track = Track(
            track_id=0,
            name="Test",
            channel=0,
            notes=[NoteEvent(pitch=60, velocity=100, start_beat=0.0, duration_beats=1.0, track_id=0, channel=0)],
        )

        clip = extract_clip(track, start_bar=10, end_bar=11)
        assert len(clip.notes) == 0


class TestExportOptions:
    """Tests for ExportOptions dataclass."""

    def test_defaults(self):
        """Test default values."""
        options = ExportOptions()

        assert options.include_tempo is True
        assert options.include_time_sig is True
        assert options.normalize_start is True
        assert options.velocity_scale == 1.0
        assert options.transpose == 0
        assert options.quantize is None

    def test_custom_values(self):
        """Test custom values."""
        options = ExportOptions(
            include_tempo=False,
            transpose=-5,
            quantize=16,
        )

        assert options.include_tempo is False
        assert options.transpose == -5
        assert options.quantize == 16


class TestQuantization:
    """Tests for quantization on export."""

    def test_quantize_to_16th(self):
        """Test quantization to 16th notes."""
        track = Track(
            track_id=0,
            name="Unquantized",
            channel=0,
            notes=[
                # Slightly off the grid
                NoteEvent(pitch=60, velocity=100, start_beat=0.13, duration_beats=0.23, track_id=0, channel=0),
                NoteEvent(pitch=62, velocity=100, start_beat=0.48, duration_beats=0.27, track_id=0, channel=0),
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            options = ExportOptions(quantize=16)
            export_track(track, output, options=options)

            # File should be created
            assert output.exists()


class TestEdgeCases:
    """Tests for edge cases."""

    def test_high_velocity_clamping(self):
        """Test velocity clamping at upper bound."""
        track = Track(
            track_id=0,
            name="Test",
            channel=0,
            notes=[NoteEvent(pitch=60, velocity=100, start_beat=0.0, duration_beats=1.0, track_id=0, channel=0)],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            options = ExportOptions(velocity_scale=2.0)  # Would be 200
            export_track(track, output, options=options)

            midi = mido.MidiFile(output)
            note_ons = [m for m in midi.tracks[0] if m.type == "note_on" and m.velocity > 0]
            assert note_ons[0].velocity == 127  # Clamped

    def test_pitch_clamping_high(self):
        """Test pitch clamping at upper bound."""
        track = Track(
            track_id=0,
            name="Test",
            channel=0,
            notes=[NoteEvent(pitch=120, velocity=100, start_beat=0.0, duration_beats=1.0, track_id=0, channel=0)],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            options = ExportOptions(transpose=20)  # Would be 140
            export_track(track, output, options=options)

            midi = mido.MidiFile(output)
            note_ons = [m for m in midi.tracks[0] if m.type == "note_on" and m.velocity > 0]
            assert note_ons[0].note == 127  # Clamped

    def test_pitch_clamping_low(self):
        """Test pitch clamping at lower bound."""
        track = Track(
            track_id=0,
            name="Test",
            channel=0,
            notes=[NoteEvent(pitch=10, velocity=100, start_beat=0.0, duration_beats=1.0, track_id=0, channel=0)],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "test.mid"
            options = ExportOptions(transpose=-20)  # Would be -10
            export_track(track, output, options=options)

            midi = mido.MidiFile(output)
            note_ons = [m for m in midi.tracks[0] if m.type == "note_on" and m.velocity > 0]
            assert note_ons[0].note == 0  # Clamped
