"""Bar chunking for pattern extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from midi_analyzer.models.core import NoteEvent, Song, TimeSignature, Track


@dataclass
class BarChunk:
    """A chunk of notes spanning one or more bars.

    Attributes:
        start_bar: Starting bar number (0-indexed)
        end_bar: Ending bar number (exclusive)
        num_bars: Number of bars in this chunk
        notes: Notes within this chunk (with local timing)
        time_sig: Time signature active at start of chunk
        beats_per_bar: Beats per bar for this chunk
    """

    start_bar: int
    end_bar: int
    num_bars: int
    notes: list[NoteEvent] = field(default_factory=list)
    time_sig: TimeSignature | None = None
    beats_per_bar: float = 4.0

    @property
    def start_beat(self) -> float:
        """Get the start beat of this chunk."""
        return self.start_bar * self.beats_per_bar

    @property
    def end_beat(self) -> float:
        """Get the end beat of this chunk."""
        return self.end_bar * self.beats_per_bar

    @property
    def duration_beats(self) -> float:
        """Get the duration of this chunk in beats."""
        return self.num_bars * self.beats_per_bar

    @property
    def is_empty(self) -> bool:
        """Check if this chunk has no notes."""
        return len(self.notes) == 0

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "start_bar": self.start_bar,
            "end_bar": self.end_bar,
            "num_bars": self.num_bars,
            "note_count": len(self.notes),
            "beats_per_bar": self.beats_per_bar,
        }


class BarChunker:
    """Segments tracks into bar-aligned chunks."""

    def __init__(self, default_beats_per_bar: float = 4.0) -> None:
        """Initialize the bar chunker.

        Args:
            default_beats_per_bar: Default beats per bar if no time sig.
        """
        self.default_beats_per_bar = default_beats_per_bar

    def get_beats_per_bar_at(
        self, bar: int, time_sig_map: list[TimeSignature]
    ) -> float:
        """Get beats per bar at a specific bar number.

        Args:
            bar: Bar number.
            time_sig_map: Time signature map.

        Returns:
            Beats per bar.
        """
        if not time_sig_map:
            return self.default_beats_per_bar

        active_ts = time_sig_map[0]
        for ts in time_sig_map:
            if ts.bar <= bar:
                active_ts = ts
            else:
                break

        return active_ts.beats_per_bar

    def get_time_sig_at(
        self, bar: int, time_sig_map: list[TimeSignature]
    ) -> TimeSignature | None:
        """Get the time signature at a specific bar.

        Args:
            bar: Bar number.
            time_sig_map: Time signature map.

        Returns:
            Active time signature or None.
        """
        if not time_sig_map:
            return None

        active_ts = time_sig_map[0]
        for ts in time_sig_map:
            if ts.bar <= bar:
                active_ts = ts
            else:
                break

        return active_ts

    def _bar_to_beat(
        self, bar: int, time_sig_map: list[TimeSignature]
    ) -> float:
        """Convert bar number to beat position.

        This handles time signature changes by accumulating beats.

        Args:
            bar: Target bar number.
            time_sig_map: Time signature map.

        Returns:
            Beat position at start of the bar.
        """
        if not time_sig_map:
            return bar * self.default_beats_per_bar

        beat = 0.0
        current_bar = 0

        # Iterate through time signatures
        for i, ts in enumerate(time_sig_map):
            if ts.bar > bar:
                break

            # Add beats from previous section
            if i > 0:
                prev_ts = time_sig_map[i - 1]
                bars_in_section = ts.bar - prev_ts.bar
                beat += bars_in_section * prev_ts.beats_per_bar
            current_bar = ts.bar

        # Add remaining bars with current time signature
        if time_sig_map:
            current_ts = self.get_time_sig_at(bar, time_sig_map)
            if current_ts:
                beat += (bar - current_bar) * current_ts.beats_per_bar

        return beat

    def get_song_length_bars(
        self, song: Song
    ) -> int:
        """Calculate the total length of a song in bars.

        Args:
            song: Song to analyze.

        Returns:
            Total number of bars (rounded up).
        """
        if not song.tracks:
            return 0

        max_beat = 0.0
        for track in song.tracks:
            for note in track.notes:
                end_beat = note.start_beat + note.duration_beats
                if end_beat > max_beat:
                    max_beat = end_beat

        if not song.time_sig_map:
            return int(max_beat / self.default_beats_per_bar) + 1

        # Convert max beat to bars
        beats_per_bar = self.get_beats_per_bar_at(0, song.time_sig_map)
        return int(max_beat / beats_per_bar) + 1

    def chunk_track(
        self,
        track: Track,
        time_sig_map: list[TimeSignature],
        chunk_size: int = 1,
        song_length_bars: int | None = None,
    ) -> Iterator[BarChunk]:
        """Segment a track into bar-aligned chunks.

        Args:
            track: Track to segment.
            time_sig_map: Time signature map for the song.
            chunk_size: Number of bars per chunk (1, 2, 4, 8, or 16).
            song_length_bars: Total bars in song (for partial final chunk).

        Yields:
            BarChunk objects.
        """
        if song_length_bars is None:
            # Estimate from track
            max_beat = 0.0
            for note in track.notes:
                end_beat = note.start_beat + note.duration_beats
                if end_beat > max_beat:
                    max_beat = end_beat

            beats_per_bar = self.get_beats_per_bar_at(0, time_sig_map)
            song_length_bars = int(max_beat / beats_per_bar) + 1

        # Sort notes by start time
        sorted_notes = sorted(track.notes, key=lambda n: n.start_beat)

        bar = 0
        while bar < song_length_bars:
            # Determine chunk bounds
            start_bar = bar
            end_bar = min(bar + chunk_size, song_length_bars)
            num_bars = end_bar - start_bar

            # Get timing info
            beats_per_bar = self.get_beats_per_bar_at(start_bar, time_sig_map)
            time_sig = self.get_time_sig_at(start_bar, time_sig_map)

            start_beat = start_bar * beats_per_bar
            end_beat = end_bar * beats_per_bar

            # Collect notes in this chunk
            chunk_notes = []
            for note in sorted_notes:
                # Note starts in chunk
                if start_beat <= note.start_beat < end_beat:
                    # Create note with local timing (relative to chunk start)
                    local_note = NoteEvent(
                        pitch=note.pitch,
                        velocity=note.velocity,
                        start_beat=note.start_beat - start_beat,
                        duration_beats=note.duration_beats,
                        track_id=note.track_id,
                        channel=note.channel,
                        start_tick=note.start_tick,
                        bar=note.bar - start_bar,
                        beat_in_bar=note.beat_in_bar,
                        quantized_start=(
                            note.quantized_start - start_beat
                            if note.quantized_start is not None
                            else None
                        ),
                        quantized_duration=note.quantized_duration,
                    )
                    chunk_notes.append(local_note)

            yield BarChunk(
                start_bar=start_bar,
                end_bar=end_bar,
                num_bars=num_bars,
                notes=chunk_notes,
                time_sig=time_sig,
                beats_per_bar=beats_per_bar,
            )

            bar += chunk_size

    def chunk_song(
        self,
        song: Song,
        chunk_sizes: list[int] | None = None,
    ) -> dict[int, dict[int, list[BarChunk]]]:
        """Segment all tracks in a song into chunks of multiple sizes.

        Args:
            song: Song to segment.
            chunk_sizes: List of chunk sizes to generate (default: [1, 2, 4, 8, 16]).

        Returns:
            Nested dict: {chunk_size: {track_id: [chunks]}}
        """
        if chunk_sizes is None:
            chunk_sizes = [1, 2, 4, 8, 16]

        song_length = self.get_song_length_bars(song)
        result: dict[int, dict[int, list[BarChunk]]] = {}

        for size in chunk_sizes:
            result[size] = {}
            for track in song.tracks:
                chunks = list(
                    self.chunk_track(
                        track,
                        song.time_sig_map,
                        chunk_size=size,
                        song_length_bars=song_length,
                    )
                )
                result[size][track.track_id] = chunks

        return result


def chunk_track(
    track: Track,
    time_sig_map: list[TimeSignature],
    chunk_size: int = 1,
) -> list[BarChunk]:
    """Convenience function to chunk a single track.

    Args:
        track: Track to segment.
        time_sig_map: Time signature map.
        chunk_size: Bars per chunk.

    Returns:
        List of BarChunk objects.
    """
    chunker = BarChunker()
    return list(chunker.chunk_track(track, time_sig_map, chunk_size))


def chunk_song(
    song: Song,
    chunk_sizes: list[int] | None = None,
) -> dict[int, dict[int, list[BarChunk]]]:
    """Convenience function to chunk all tracks in a song.

    Args:
        song: Song to segment.
        chunk_sizes: List of chunk sizes (default: [1, 2, 4, 8, 16]).

    Returns:
        Nested dict: {chunk_size: {track_id: [chunks]}}
    """
    chunker = BarChunker()
    return chunker.chunk_song(song, chunk_sizes)
