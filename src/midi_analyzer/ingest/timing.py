"""Timing resolution and quantization utilities."""

from __future__ import annotations

from dataclasses import dataclass

from midi_analyzer.models.core import NoteEvent, Song, TempoEvent, TimeSignature


@dataclass
class TimingContext:
    """Context for timing calculations at a specific point in the song."""

    tick: int
    beat: float
    bar: int
    beat_in_bar: float
    tempo_bpm: float
    time_sig_numerator: int
    time_sig_denominator: int


class TimingResolver:
    """Resolves tick-based timing to beat-based timing with quantization support."""

    def __init__(self, ticks_per_beat: int = 480) -> None:
        """Initialize the timing resolver.

        Args:
            ticks_per_beat: MIDI resolution (PPQ).
        """
        self.ticks_per_beat = ticks_per_beat

    def tick_to_beat(self, tick: int) -> float:
        """Convert tick position to beat position.

        Args:
            tick: Tick position.

        Returns:
            Beat position.
        """
        return tick / self.ticks_per_beat

    def beat_to_tick(self, beat: float) -> int:
        """Convert beat position to tick position.

        Args:
            beat: Beat position.

        Returns:
            Tick position (rounded to nearest tick).
        """
        return round(beat * self.ticks_per_beat)

    def quantize_beat(self, beat: float, grid: int = 16, beats_per_bar: float = 4.0) -> float:
        """Quantize a beat position to a grid.

        Args:
            beat: Beat position to quantize.
            grid: Grid resolution (e.g., 16 for 16th notes per bar).
            beats_per_bar: Number of beats per bar.

        Returns:
            Quantized beat position.
        """
        # Calculate step size in beats
        step_size = beats_per_bar / grid

        # Quantize to nearest step
        steps = round(beat / step_size)
        return steps * step_size

    def quantize_duration(
        self, duration: float, grid: int = 16, beats_per_bar: float = 4.0, min_duration: float = 0.0
    ) -> float:
        """Quantize a duration to a grid.

        Args:
            duration: Duration in beats.
            grid: Grid resolution.
            beats_per_bar: Number of beats per bar.
            min_duration: Minimum duration (defaults to one grid step if 0).

        Returns:
            Quantized duration.
        """
        step_size = beats_per_bar / grid

        if min_duration == 0.0:
            min_duration = step_size

        # Quantize to nearest step, ensuring minimum duration
        steps = max(1, round(duration / step_size))
        return max(min_duration, steps * step_size)

    def get_tempo_at_beat(self, beat: float, tempo_map: list[TempoEvent]) -> float:
        """Get the tempo (BPM) at a specific beat position.

        Args:
            beat: Beat position.
            tempo_map: List of tempo events.

        Returns:
            Tempo in BPM.
        """
        if not tempo_map:
            return 120.0  # Default tempo

        active_tempo = tempo_map[0]
        for event in tempo_map:
            if event.beat <= beat:
                active_tempo = event
            else:
                break

        return active_tempo.tempo_bpm

    def get_time_sig_at_beat(
        self, beat: float, time_sig_map: list[TimeSignature]
    ) -> tuple[int, int]:
        """Get the time signature at a specific beat position.

        Args:
            beat: Beat position.
            time_sig_map: List of time signature events.

        Returns:
            Tuple of (numerator, denominator).
        """
        if not time_sig_map:
            return (4, 4)  # Default time signature

        active_ts = time_sig_map[0]
        for ts in time_sig_map:
            if ts.beat <= beat:
                active_ts = ts
            else:
                break

        return (active_ts.numerator, active_ts.denominator)

    def beat_to_bar_beat(
        self, beat: float, time_sig_map: list[TimeSignature]
    ) -> tuple[int, float]:
        """Convert beat position to bar number and beat-within-bar.

        Args:
            beat: Beat position.
            time_sig_map: List of time signature events.

        Returns:
            Tuple of (bar_number, beat_in_bar).
        """
        if not time_sig_map:
            # Default 4/4
            bar = int(beat / 4)
            beat_in_bar = beat - (bar * 4)
            return (bar, beat_in_bar)

        # Find active time signature
        active_ts = time_sig_map[0]
        for ts in time_sig_map:
            if ts.beat <= beat:
                active_ts = ts
            else:
                break

        # Calculate bar and beat within bar
        beats_since_ts = beat - active_ts.beat
        bars_since_ts = int(beats_since_ts / active_ts.beats_per_bar)
        beat_in_bar = beats_since_ts - (bars_since_ts * active_ts.beats_per_bar)

        return (active_ts.bar + bars_since_ts, beat_in_bar)

    def get_context_at_beat(
        self,
        beat: float,
        tempo_map: list[TempoEvent],
        time_sig_map: list[TimeSignature],
    ) -> TimingContext:
        """Get full timing context at a specific beat position.

        Args:
            beat: Beat position.
            tempo_map: List of tempo events.
            time_sig_map: List of time signature events.

        Returns:
            TimingContext with all timing information.
        """
        bar, beat_in_bar = self.beat_to_bar_beat(beat, time_sig_map)
        tempo = self.get_tempo_at_beat(beat, tempo_map)
        num, denom = self.get_time_sig_at_beat(beat, time_sig_map)

        return TimingContext(
            tick=self.beat_to_tick(beat),
            beat=beat,
            bar=bar,
            beat_in_bar=beat_in_bar,
            tempo_bpm=tempo,
            time_sig_numerator=num,
            time_sig_denominator=denom,
        )


def quantize_song(song: Song, grid: int = 16) -> Song:
    """Quantize all notes in a song to a grid.

    This modifies the quantized_start and quantized_duration fields
    of each note, preserving the original timing.

    Args:
        song: Song to quantize.
        grid: Grid resolution (steps per bar).

    Returns:
        The same Song object with quantized fields populated.
    """
    resolver = TimingResolver(ticks_per_beat=song.ticks_per_beat)

    for track in song.tracks:
        for note in track.notes:
            # Get beats per bar at this note's position
            num, denom = resolver.get_time_sig_at_beat(note.start_beat, song.time_sig_map)
            beats_per_bar = num * (4 / denom)

            # Quantize start and duration
            note.quantized_start = resolver.quantize_beat(
                note.start_beat, grid=grid, beats_per_bar=beats_per_bar
            )
            note.quantized_duration = resolver.quantize_duration(
                note.duration_beats, grid=grid, beats_per_bar=beats_per_bar
            )

    return song
