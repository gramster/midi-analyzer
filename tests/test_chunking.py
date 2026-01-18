"""Tests for bar chunking."""

import pytest

from midi_analyzer.models.core import NoteEvent, Song, TimeSignature, Track
from midi_analyzer.patterns.chunking import BarChunk, BarChunker, chunk_song, chunk_track


class TestBarChunk:
    """Tests for BarChunk dataclass."""

    def test_basic_chunk(self) -> None:
        """Test basic chunk creation."""
        chunk = BarChunk(
            start_bar=0,
            end_bar=1,
            num_bars=1,
            notes=[],
            beats_per_bar=4.0,
        )

        assert chunk.start_beat == 0.0
        assert chunk.end_beat == 4.0
        assert chunk.duration_beats == 4.0
        assert chunk.is_empty

    def test_chunk_with_notes(self) -> None:
        """Test chunk with notes."""
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
                start_beat=1.0,
                duration_beats=0.5,
                track_id=0,
                channel=0,
            ),
        ]
        chunk = BarChunk(
            start_bar=0,
            end_bar=1,
            num_bars=1,
            notes=notes,
            beats_per_bar=4.0,
        )

        assert not chunk.is_empty
        assert len(chunk.notes) == 2

    def test_to_dict(self) -> None:
        """Test serialization."""
        chunk = BarChunk(
            start_bar=2,
            end_bar=4,
            num_bars=2,
            notes=[],
            beats_per_bar=4.0,
        )

        d = chunk.to_dict()
        assert d["start_bar"] == 2
        assert d["end_bar"] == 4
        assert d["num_bars"] == 2
        assert d["note_count"] == 0


class TestBarChunker:
    """Tests for BarChunker class."""

    @pytest.fixture
    def simple_track(self) -> Track:
        """Create a simple track with notes spanning 4 bars."""
        notes = []
        for bar in range(4):
            for beat in range(4):  # 4 beats per bar
                notes.append(
                    NoteEvent(
                        pitch=60 + beat,
                        velocity=100,
                        start_beat=bar * 4 + beat,
                        duration_beats=0.5,
                        track_id=0,
                        channel=0,
                        bar=bar,
                        beat_in_bar=float(beat),
                    )
                )
        return Track(track_id=0, name="Test", channel=0, notes=notes)

    def test_chunk_single_bar(self, simple_track: Track) -> None:
        """Test chunking into 1-bar chunks."""
        chunker = BarChunker()
        chunks = list(
            chunker.chunk_track(simple_track, [], chunk_size=1, song_length_bars=4)
        )

        assert len(chunks) == 4
        assert all(c.num_bars == 1 for c in chunks)
        assert chunks[0].start_bar == 0
        assert chunks[1].start_bar == 1
        assert chunks[2].start_bar == 2
        assert chunks[3].start_bar == 3

    def test_chunk_two_bars(self, simple_track: Track) -> None:
        """Test chunking into 2-bar chunks."""
        chunker = BarChunker()
        chunks = list(
            chunker.chunk_track(simple_track, [], chunk_size=2, song_length_bars=4)
        )

        assert len(chunks) == 2
        assert all(c.num_bars == 2 for c in chunks)
        assert chunks[0].start_bar == 0
        assert chunks[0].end_bar == 2
        assert chunks[1].start_bar == 2
        assert chunks[1].end_bar == 4

    def test_chunk_four_bars(self, simple_track: Track) -> None:
        """Test chunking into 4-bar chunks."""
        chunker = BarChunker()
        chunks = list(
            chunker.chunk_track(simple_track, [], chunk_size=4, song_length_bars=4)
        )

        assert len(chunks) == 1
        assert chunks[0].num_bars == 4
        assert chunks[0].start_bar == 0
        assert chunks[0].end_bar == 4

    def test_notes_have_local_timing(self, simple_track: Track) -> None:
        """Test that notes in chunks have local (relative) timing."""
        chunker = BarChunker()
        chunks = list(
            chunker.chunk_track(simple_track, [], chunk_size=1, song_length_bars=4)
        )

        # Check bar 2's chunk
        bar2_chunk = chunks[2]
        assert bar2_chunk.start_bar == 2

        # Notes should have local timing relative to chunk start
        for note in bar2_chunk.notes:
            assert 0.0 <= note.start_beat < 4.0  # Within one bar

    def test_partial_final_chunk(self) -> None:
        """Test handling of partial bars at song end."""
        # Track with 3 notes in 3 bars
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
                pitch=60,
                velocity=100,
                start_beat=4.0,
                duration_beats=0.5,
                track_id=0,
                channel=0,
            ),
            NoteEvent(
                pitch=60,
                velocity=100,
                start_beat=8.0,
                duration_beats=0.5,
                track_id=0,
                channel=0,
            ),
        ]
        track = Track(track_id=0, name="Test", channel=0, notes=notes)

        chunker = BarChunker()
        chunks = list(
            chunker.chunk_track(track, [], chunk_size=2, song_length_bars=3)
        )

        # Should have 2 chunks: bars 0-1 (full) and bars 2-3 (partial, only 1 bar of data)
        assert len(chunks) == 2
        assert chunks[0].num_bars == 2
        assert chunks[1].num_bars == 1  # Partial final chunk

    def test_chunk_with_time_signature(self) -> None:
        """Test chunking with time signature info."""
        notes = [
            NoteEvent(
                pitch=60,
                velocity=100,
                start_beat=0.0,
                duration_beats=0.5,
                track_id=0,
                channel=0,
            ),
        ]
        track = Track(track_id=0, name="Test", channel=0, notes=notes)
        time_sigs = [TimeSignature(tick=0, beat=0.0, bar=0, numerator=4, denominator=4)]

        chunker = BarChunker()
        chunks = list(
            chunker.chunk_track(track, time_sigs, chunk_size=1, song_length_bars=2)
        )

        assert len(chunks) == 2
        assert chunks[0].time_sig is not None
        assert chunks[0].beats_per_bar == 4.0


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.fixture
    def simple_song(self) -> Song:
        """Create a simple song."""
        notes = []
        for bar in range(4):
            notes.append(
                NoteEvent(
                    pitch=60,
                    velocity=100,
                    start_beat=bar * 4.0,
                    duration_beats=0.5,
                    track_id=0,
                    channel=0,
                )
            )

        track = Track(track_id=0, name="Test", channel=0, notes=notes)
        return Song(
            song_id="test",
            source_path="/test/song.mid",
            tracks=[track],
            ticks_per_beat=480,
        )

    def test_chunk_track_function(self, simple_song: Song) -> None:
        """Test chunk_track convenience function."""
        track = simple_song.tracks[0]
        chunks = chunk_track(track, simple_song.time_sig_map, chunk_size=2)

        # Notes at beats 0, 4, 8, 12 = bars 0, 1, 2, 3
        # With 2-bar chunks: bars 0-1, 2-3 = 2 chunks
        assert len(chunks) == 2

    def test_chunk_song_function(self, simple_song: Song) -> None:
        """Test chunk_song convenience function."""
        result = chunk_song(simple_song)

        # Should have chunks for sizes 1, 2, and 4
        assert 1 in result
        assert 2 in result
        assert 4 in result

        # Track 0 should have chunks
        assert 0 in result[1]
        assert 0 in result[2]
        assert 0 in result[4]

    def test_chunk_song_custom_sizes(self, simple_song: Song) -> None:
        """Test chunk_song with custom chunk sizes."""
        result = chunk_song(simple_song, chunk_sizes=[1, 8])

        assert 1 in result
        assert 8 in result
        assert 2 not in result
        assert 4 not in result
