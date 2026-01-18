"""Timing resolution and quantization utilities."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from midi_analyzer.models.core import NoteEvent, Song, TempoEvent, TimeSignature


class SwingStyle(Enum):
    """Detected swing style."""

    STRAIGHT = "straight"
    LIGHT = "light"  # ~55% ratio
    MEDIUM = "medium"  # ~60% ratio
    HEAVY = "heavy"  # ~67% triplet swing


@dataclass
class SwingAnalysis:
    """Results of swing detection analysis."""

    style: SwingStyle
    ratio: float  # Ratio of long-to-short 8th notes (0.5 = straight, 0.67 = triplet)
    confidence: float  # 0-1 confidence in the detection
    sample_count: int  # Number of pairs analyzed


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


def detect_swing(notes: list[NoteEvent], beats_per_bar: float = 4.0) -> SwingAnalysis:
    """Detect swing feel from a list of notes.

    Analyzes the timing of consecutive 8th note pairs to detect swing.
    Swing is measured by the ratio of the first 8th note's duration to
    the total duration of the pair.

    Args:
        notes: List of note events (should be sorted by start time).
        beats_per_bar: Beats per bar for grid calculation.

    Returns:
        SwingAnalysis with detected swing style, ratio, and confidence.
    """
    if len(notes) < 4:
        return SwingAnalysis(
            style=SwingStyle.STRAIGHT,
            ratio=0.5,
            confidence=0.0,
            sample_count=0,
        )

    # 8th note duration in beats (in 4/4, an 8th = 0.5 beats)
    eighth_note = beats_per_bar / 8.0
    tolerance = eighth_note * 0.3  # 30% tolerance

    ratios: list[float] = []

    # Look at consecutive note pairs that fall on 8th note boundaries
    sorted_notes = sorted(notes, key=lambda n: n.start_beat)

    for i in range(len(sorted_notes) - 1):
        note1 = sorted_notes[i]
        note2 = sorted_notes[i + 1]

        # Check if note1 is on a downbeat (beat position 0.0, 1.0, 2.0, etc)
        # or on an even 8th note position (0.0, 0.5, 1.0, 1.5, etc in straight time)
        beat_pos = note1.start_beat % 1.0

        # Is it on a downbeat?
        is_on_downbeat = beat_pos < tolerance or beat_pos > (1.0 - tolerance)

        if not is_on_downbeat:
            continue

        # Check the gap between notes - should be around half a beat (8th note)
        gap = note2.start_beat - note1.start_beat

        # In straight time, gap would be 0.5 beats
        # In swing time, the first 8th is longer, so gap might be 0.55-0.67
        # We're looking for gaps that could be swing 8ths
        if gap < 0.3 or gap > 0.8:
            # Not an 8th note pair
            continue

        # The ratio is: how far into the half-beat does the 2nd note land?
        # Straight time: gap/0.5 = 1.0 (second note exactly at upbeat)
        # Light swing: ratio > 1.0 (second note later than upbeat)
        # We normalize to express as "percentage of first 8th in the pair"
        # For straight: first = 0.5, second = 0.5, ratio = 0.5
        # For triplet swing: first = 0.67 * (total), second = 0.33 * (total)
        # So ratio = first / (first + second) = gap / half_beat

        # But it's easier to think of it as where in the beat the upbeat falls
        # If downbeat is at 0.0, upbeat at 0.5 = straight
        # If downbeat is at 0.0, upbeat at 0.67 = triplet swing
        ratio = gap  # Direct gap measurement works for 4/4

        ratios.append(ratio)

    if len(ratios) < 3:
        return SwingAnalysis(
            style=SwingStyle.STRAIGHT,
            ratio=0.5,
            confidence=0.0,
            sample_count=len(ratios),
        )

    # Calculate average ratio and variance
    avg_ratio = sum(ratios) / len(ratios)
    variance = sum((r - avg_ratio) ** 2 for r in ratios) / len(ratios)
    std_dev = variance**0.5

    # Confidence based on consistency (low std dev = high confidence)
    confidence = max(0.0, min(1.0, 1.0 - (std_dev * 5)))

    # Classify swing style
    if avg_ratio < 0.52:
        style = SwingStyle.STRAIGHT
    elif avg_ratio < 0.58:
        style = SwingStyle.LIGHT
    elif avg_ratio < 0.64:
        style = SwingStyle.MEDIUM
    else:
        style = SwingStyle.HEAVY

    return SwingAnalysis(
        style=style,
        ratio=avg_ratio,
        confidence=confidence,
        sample_count=len(ratios),
    )


def detect_song_swing(song: Song) -> SwingAnalysis:
    """Detect swing for an entire song by analyzing all tracks.

    Args:
        song: Song to analyze.

    Returns:
        SwingAnalysis representing the overall swing feel.
    """
    all_notes: list[NoteEvent] = []

    for track in song.tracks:
        all_notes.extend(track.notes)

    if not all_notes:
        return SwingAnalysis(
            style=SwingStyle.STRAIGHT,
            ratio=0.5,
            confidence=0.0,
            sample_count=0,
        )

    # Get beats per bar from first time signature
    beats_per_bar = 4.0
    if song.time_sig_map:
        ts = song.time_sig_map[0]
        beats_per_bar = ts.beats_per_bar

    return detect_swing(all_notes, beats_per_bar)

    return song
