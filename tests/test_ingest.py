"""Tests for MIDI ingest modules."""

from pathlib import Path
import tempfile

import mido
import pytest

from midi_analyzer.ingest.parser import MidiParser, parse_midi
from midi_analyzer.ingest.timing import TimingResolver, quantize_song
from midi_analyzer.ingest.metadata import MetadataExtractor, extract_metadata
from midi_analyzer.models.core import TempoEvent, TimeSignature


class TestMidiParser:
    """Tests for the MIDI parser."""

    @pytest.fixture
    def simple_midi_file(self) -> Path:
        """Create a simple MIDI file for testing."""
        mid = mido.MidiFile(ticks_per_beat=480)

        # Track 0: tempo and time signature
        track0 = mido.MidiTrack()
        mid.tracks.append(track0)
        track0.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))  # 120 BPM
        track0.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
        track0.append(mido.MetaMessage("track_name", name="Test Song", time=0))

        # Track 1: some notes
        track1 = mido.MidiTrack()
        mid.tracks.append(track1)
        track1.append(mido.MetaMessage("track_name", name="Piano", time=0))
        track1.append(mido.Message("note_on", note=60, velocity=100, time=0, channel=0))
        track1.append(mido.Message("note_off", note=60, velocity=0, time=480, channel=0))
        track1.append(mido.Message("note_on", note=64, velocity=90, time=0, channel=0))
        track1.append(mido.Message("note_off", note=64, velocity=0, time=480, channel=0))
        track1.append(mido.Message("note_on", note=67, velocity=80, time=0, channel=0))
        track1.append(mido.Message("note_off", note=67, velocity=0, time=480, channel=0))

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            mid.save(f.name)
            return Path(f.name)

    def test_parse_simple_file(self, simple_midi_file: Path) -> None:
        """Test parsing a simple MIDI file."""
        parser = MidiParser()
        song = parser.parse_file(simple_midi_file)

        assert song.ticks_per_beat == 480
        assert len(song.tempo_map) >= 1
        assert song.tempo_map[0].tempo_bpm == 120.0
        assert len(song.time_sig_map) >= 1
        assert song.time_sig_map[0].numerator == 4
        assert song.time_sig_map[0].denominator == 4

    def test_parse_extracts_notes(self, simple_midi_file: Path) -> None:
        """Test that notes are correctly extracted."""
        parser = MidiParser()
        song = parser.parse_file(simple_midi_file)

        # Should have at least one track with notes
        tracks_with_notes = [t for t in song.tracks if t.notes]
        assert len(tracks_with_notes) >= 1

        # Check first track's notes
        track = tracks_with_notes[0]
        assert len(track.notes) == 3
        assert track.notes[0].pitch == 60
        assert track.notes[0].velocity == 100
        assert track.notes[0].duration_beats == 1.0

    def test_parse_nonexistent_file(self) -> None:
        """Test that parsing nonexistent file raises error."""
        parser = MidiParser()
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/nonexistent/file.mid")

    def test_parse_midi_convenience_function(self, simple_midi_file: Path) -> None:
        """Test the convenience function."""
        song = parse_midi(simple_midi_file)
        assert song.ticks_per_beat == 480


class TestTimingResolver:
    """Tests for the timing resolver."""

    def test_tick_to_beat(self) -> None:
        """Test tick to beat conversion."""
        resolver = TimingResolver(ticks_per_beat=480)
        assert resolver.tick_to_beat(0) == 0.0
        assert resolver.tick_to_beat(480) == 1.0
        assert resolver.tick_to_beat(240) == 0.5

    def test_beat_to_tick(self) -> None:
        """Test beat to tick conversion."""
        resolver = TimingResolver(ticks_per_beat=480)
        assert resolver.beat_to_tick(0.0) == 0
        assert resolver.beat_to_tick(1.0) == 480
        assert resolver.beat_to_tick(0.5) == 240

    def test_quantize_beat_16th_notes(self) -> None:
        """Test quantization to 16th notes."""
        resolver = TimingResolver()
        # 16th note in 4/4 = 0.25 beats
        assert resolver.quantize_beat(0.0, grid=16) == 0.0
        assert resolver.quantize_beat(0.1, grid=16) == 0.0
        assert resolver.quantize_beat(0.2, grid=16) == 0.25
        assert resolver.quantize_beat(0.5, grid=16) == 0.5

    def test_quantize_beat_8th_notes(self) -> None:
        """Test quantization to 8th notes."""
        resolver = TimingResolver()
        # 8th note in 4/4 = 0.5 beats
        assert resolver.quantize_beat(0.0, grid=8) == 0.0
        assert resolver.quantize_beat(0.3, grid=8) == 0.5
        assert resolver.quantize_beat(0.6, grid=8) == 0.5
        assert resolver.quantize_beat(0.8, grid=8) == 1.0

    def test_get_tempo_at_beat(self) -> None:
        """Test tempo lookup."""
        resolver = TimingResolver()
        tempo_map = [
            TempoEvent(tick=0, beat=0.0, tempo_bpm=120.0, microseconds_per_beat=500000),
            TempoEvent(tick=1920, beat=4.0, tempo_bpm=140.0, microseconds_per_beat=428571),
        ]

        assert resolver.get_tempo_at_beat(0.0, tempo_map) == 120.0
        assert resolver.get_tempo_at_beat(2.0, tempo_map) == 120.0
        assert resolver.get_tempo_at_beat(4.0, tempo_map) == 140.0
        assert resolver.get_tempo_at_beat(8.0, tempo_map) == 140.0

    def test_get_tempo_empty_map(self) -> None:
        """Test tempo lookup with empty map returns default."""
        resolver = TimingResolver()
        assert resolver.get_tempo_at_beat(0.0, []) == 120.0

    def test_beat_to_bar_beat_4_4(self) -> None:
        """Test bar/beat calculation in 4/4."""
        resolver = TimingResolver()
        time_sig_map = [
            TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4),
        ]

        assert resolver.beat_to_bar_beat(0.0, time_sig_map) == (0, 0.0)
        assert resolver.beat_to_bar_beat(1.0, time_sig_map) == (0, 1.0)
        assert resolver.beat_to_bar_beat(4.0, time_sig_map) == (1, 0.0)
        assert resolver.beat_to_bar_beat(5.5, time_sig_map) == (1, 1.5)

    def test_beat_to_bar_beat_3_4(self) -> None:
        """Test bar/beat calculation in 3/4."""
        resolver = TimingResolver()
        time_sig_map = [
            TimeSignature(tick=0, beat=0.0, bar=0, numerator=3, denominator=4),
        ]

        assert resolver.beat_to_bar_beat(0.0, time_sig_map) == (0, 0.0)
        assert resolver.beat_to_bar_beat(3.0, time_sig_map) == (1, 0.0)
        assert resolver.beat_to_bar_beat(6.0, time_sig_map) == (2, 0.0)


class TestSwingDetection:
    """Tests for swing detection."""

    def test_straight_timing(self) -> None:
        """Test detection of straight (non-swung) timing."""
        from midi_analyzer.ingest.timing import SwingStyle, detect_swing
        from midi_analyzer.models.core import NoteEvent

        # Create notes with straight 8th note timing
        notes = []
        for i in range(16):
            notes.append(
                NoteEvent(
                    pitch=60,
                    velocity=100,
                    start_tick=i * 240,  # 240 ticks = 8th note at 480 ppq
                    channel=0,
                    track_id=0,
                    start_beat=i * 0.5,
                    duration_beats=0.4,
                )
            )

        result = detect_swing(notes)
        assert result.style == SwingStyle.STRAIGHT
        assert result.sample_count > 0

    def test_heavy_swing(self) -> None:
        """Test detection of triplet swing."""
        from midi_analyzer.ingest.timing import SwingStyle, detect_swing
        from midi_analyzer.models.core import NoteEvent

        # Create notes with triplet swing (~67% ratio)
        # In swing, the downbeat 8th is longer, upbeat 8th is shorter
        # Downbeat at 0.0, upbeat at 0.67 (instead of straight 0.5)
        # Then next downbeat at 1.0, upbeat at 1.67, etc.
        notes = []
        for i in range(8):
            beat = float(i)
            # Downbeat note (on the beat)
            notes.append(
                NoteEvent(
                    pitch=60,
                    velocity=100,
                    start_tick=0,
                    channel=0,
                    track_id=0,
                    start_beat=beat,
                    duration_beats=0.6,
                )
            )
            # Swung upbeat (at beat + 0.67 instead of beat + 0.5)
            notes.append(
                NoteEvent(
                    pitch=60,
                    velocity=100,
                    start_tick=0,
                    channel=0,
                    track_id=0,
                    start_beat=beat + 0.67,
                    duration_beats=0.25,
                )
            )

        result = detect_swing(notes)
        # Should detect swing (ratio around 0.67)
        assert result.ratio > 0.55  # Clearly not straight
        assert result.style in (SwingStyle.MEDIUM, SwingStyle.HEAVY)

    def test_insufficient_notes(self) -> None:
        """Test handling of too few notes."""
        from midi_analyzer.ingest.timing import SwingStyle, detect_swing
        from midi_analyzer.models.core import NoteEvent

        notes = [
            NoteEvent(
                pitch=60,
                velocity=100,
                start_tick=0,
                channel=0,
                track_id=0,
                start_beat=0.0,
                duration_beats=0.4,
            )
        ]

        result = detect_swing(notes)
        assert result.style == SwingStyle.STRAIGHT
        assert result.confidence == 0.0
        assert result.sample_count == 0


class TestMetadataExtractor:
    """Tests for metadata extraction."""

    def test_extract_from_folder_structure(self) -> None:
        """Test extraction from Letter/Artist/Title structure."""
        extractor = MetadataExtractor()
        path = Path("/music/R/Ramones/I Wanna Be Sedated.mid")
        metadata = extractor._extract_from_folder_structure(path)

        assert metadata.artist == "Ramones"
        assert metadata.title == "I Wanna Be Sedated"
        assert metadata.source == "folder_structure"

    def test_extract_from_separator_format(self) -> None:
        """Test extraction from 'Artist - Title' format."""
        extractor = MetadataExtractor()
        path = Path("/music/Queen - Bohemian Rhapsody.mid")
        metadata = extractor._extract_from_filename(path)

        assert metadata.artist == "Queen"
        assert metadata.title == "Bohemian Rhapsody"

    def test_extract_cleans_nonstop2k_format(self) -> None:
        """Test cleaning of nonstop2k filename format."""
        extractor = MetadataExtractor()
        filename = "le-youth-jerro-lizzy-land-lost-20230130024203-nonstop2k.com"
        cleaned = extractor._clean_filename(filename)

        assert "nonstop2k.com" not in cleaned
        assert "20230130024203" not in cleaned

    def test_extract_convenience_function(self) -> None:
        """Test the convenience function."""
        path = Path("/music/Artist - Song.mid")
        metadata = extract_metadata(path)

        assert metadata.artist == "Artist"
        assert metadata.title == "Song"

    def test_extract_fallback_to_filename(self) -> None:
        """Test fallback when no structure is detected."""
        extractor = MetadataExtractor()
        path = Path("/music/some_random_song.mid")
        metadata = extractor.extract(path)

        assert metadata.title  # Should have some title
        assert metadata.source == "filename_fallback" or metadata.source == "filename_hyphenated"
