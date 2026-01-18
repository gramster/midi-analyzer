"""Arpeggio inference from MIDI tracks.

Analyzes tracks with high arp probability to extract:
- Underlying chord per window
- Interval traversal sequence
- Octave jumps
- Rate and gate feel
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from midi_analyzer.harmony.chords import (
    CHORD_TEMPLATES,
    Chord,
    ChordQuality,
)
from midi_analyzer.models.patterns import ArpPattern

if TYPE_CHECKING:
    from midi_analyzer.models.core import NoteEvent, Song, Track


@dataclass
class ArpWindow:
    """A window of notes analyzed as an arpeggio.

    Attributes:
        start_beat: Start beat of the window.
        end_beat: End beat of the window.
        notes: Notes in this window.
        inferred_chord: The underlying chord inferred from notes.
        interval_sequence: Sequence of intervals from chord root.
        octave_jumps: Octave offset for each note relative to base.
        avg_note_duration: Average note duration in beats.
        rate: Detected rate as string (e.g., "1/16").
    """

    start_beat: float
    end_beat: float
    notes: list[NoteEvent] = field(default_factory=list)
    inferred_chord: Chord | None = None
    interval_sequence: list[int] = field(default_factory=list)
    octave_jumps: list[int] = field(default_factory=list)
    avg_note_duration: float = 0.0
    rate: str = "1/16"


@dataclass
class ArpAnalysis:
    """Result of arpeggio analysis on a track.

    Attributes:
        track_id: The analyzed track ID.
        windows: List of analyzed arp windows.
        dominant_rate: Most common note rate.
        dominant_pattern: Most common interval pattern.
        avg_gate: Average gate/sustain ratio.
        patterns: Extracted reusable arp patterns.
    """

    track_id: int
    windows: list[ArpWindow] = field(default_factory=list)
    dominant_rate: str = "1/16"
    dominant_pattern: list[int] = field(default_factory=list)
    avg_gate: float = 0.5
    patterns: list[ArpPattern] = field(default_factory=list)


class ArpAnalyzer:
    """Analyze tracks for arpeggio patterns.

    Groups notes into chord windows, infers the underlying chord,
    and extracts the traversal signature for arpeggiator replication.
    """

    # Window size in beats for chord inference
    DEFAULT_WINDOW_BEATS = 4.0  # One bar in 4/4

    # Common arp rates and their beat durations
    RATE_THRESHOLDS = [
        (0.125, "1/32"),   # 32nd notes
        (0.1875, "1/16T"), # 16th triplets
        (0.25, "1/16"),    # 16th notes
        (0.375, "1/8T"),   # 8th triplets
        (0.5, "1/8"),      # 8th notes
        (0.75, "1/4T"),    # Quarter triplets
        (1.0, "1/4"),      # Quarter notes
    ]

    def __init__(
        self,
        window_beats: float = DEFAULT_WINDOW_BEATS,
        min_notes_per_window: int = 4,
    ) -> None:
        """Initialize the analyzer.

        Args:
            window_beats: Size of analysis window in beats.
            min_notes_per_window: Minimum notes required for arp detection.
        """
        self.window_beats = window_beats
        self.min_notes_per_window = min_notes_per_window

    def analyze_track(self, track: Track, song: Song | None = None) -> ArpAnalysis:
        """Analyze a track for arpeggio patterns.

        Args:
            track: Track to analyze (should have high arp probability).
            song: Optional song for tempo/time sig context.

        Returns:
            ArpAnalysis with detected patterns.
        """
        if not track.notes:
            return ArpAnalysis(track_id=track.track_id)

        # Sort notes by start time
        notes = sorted(track.notes, key=lambda n: n.start_beat)

        # Determine window size from time signature if available
        window_beats = self.window_beats
        if song and song.time_sig_map:
            # Use first time signature's bar length
            first_ts = song.time_sig_map[0]
            window_beats = first_ts.beats_per_bar

        # Divide into windows
        windows = self._create_windows(notes, window_beats)

        # Analyze each window
        analyzed_windows: list[ArpWindow] = []
        for window in windows:
            if len(window.notes) >= self.min_notes_per_window:
                analyzed = self._analyze_window(window)
                analyzed_windows.append(analyzed)

        # Extract dominant patterns
        analysis = self._compile_analysis(track.track_id, analyzed_windows)

        return analysis

    def _create_windows(
        self,
        notes: list[NoteEvent],
        window_beats: float,
    ) -> list[ArpWindow]:
        """Divide notes into analysis windows.

        Args:
            notes: Sorted list of notes.
            window_beats: Window size in beats.

        Returns:
            List of ArpWindow objects.
        """
        if not notes:
            return []

        windows: list[ArpWindow] = []
        start_beat = notes[0].start_beat

        # Find end of track
        end_beat = max(n.start_beat + n.duration_beats for n in notes)

        while start_beat < end_beat:
            window_end = start_beat + window_beats

            # Collect notes in this window
            window_notes = [
                n for n in notes
                if start_beat <= n.start_beat < window_end
            ]

            if window_notes:
                windows.append(ArpWindow(
                    start_beat=start_beat,
                    end_beat=window_end,
                    notes=window_notes,
                ))

            start_beat = window_end

        return windows

    def _analyze_window(self, window: ArpWindow) -> ArpWindow:
        """Analyze a single window for arp characteristics.

        Args:
            window: Window with notes to analyze.

        Returns:
            Window with analysis filled in.
        """
        notes = sorted(window.notes, key=lambda n: n.start_beat)

        # Infer underlying chord from pitch classes
        pitch_classes = {n.pitch % 12 for n in notes}
        window.inferred_chord = self._infer_chord(pitch_classes)

        # Extract interval sequence relative to chord root
        if window.inferred_chord:
            root = window.inferred_chord.root
            base_octave = min(n.pitch for n in notes) // 12

            intervals: list[int] = []
            octave_jumps: list[int] = []

            for note in notes:
                # Interval from root (within octave)
                interval = (note.pitch - root) % 12
                intervals.append(interval)

                # Octave relative to base
                note_octave = note.pitch // 12
                octave_jumps.append(note_octave - base_octave)

            window.interval_sequence = intervals
            window.octave_jumps = octave_jumps

        # Calculate note rate
        if len(notes) >= 2:
            # Average time between consecutive notes
            deltas = [
                notes[i + 1].start_beat - notes[i].start_beat
                for i in range(len(notes) - 1)
            ]
            avg_delta = sum(deltas) / len(deltas) if deltas else 0.5
            window.rate = self._delta_to_rate(avg_delta)

            # Average duration for gate calculation
            window.avg_note_duration = sum(n.duration_beats for n in notes) / len(notes)

        return window

    def _infer_chord(self, pitch_classes: set[int]) -> Chord | None:
        """Infer the most likely chord from a set of pitch classes.

        Args:
            pitch_classes: Set of pitch classes (0-11).

        Returns:
            Best matching chord or None.
        """
        if len(pitch_classes) < 3:
            return None

        best_chord: Chord | None = None
        best_score = 0.0

        # Try each pitch class as potential root
        for root in range(12):
            # Transpose pitch classes relative to this root
            transposed = frozenset((pc - root) % 12 for pc in pitch_classes)

            # Check against chord templates
            for quality, template in CHORD_TEMPLATES.items():
                # Score = how many template notes are present / template size
                matches = len(transposed & template)
                coverage = matches / len(template)

                # Penalize extra notes not in template
                extras = len(transposed - template)
                penalty = extras * 0.1

                score = coverage - penalty

                if score > best_score:
                    best_score = score
                    best_chord = Chord(
                        root=root,
                        quality=quality,
                        confidence=min(1.0, score),
                    )

        return best_chord

    def _delta_to_rate(self, delta_beats: float) -> str:
        """Convert average note delta to rate string.

        Args:
            delta_beats: Average beats between notes.

        Returns:
            Rate string like "1/16".
        """
        for threshold, rate in self.RATE_THRESHOLDS:
            if delta_beats <= threshold * 1.25:  # Allow 25% tolerance
                return rate

        return "1/4"  # Default to quarter notes for slow arps

    def _compile_analysis(
        self,
        track_id: int,
        windows: list[ArpWindow],
    ) -> ArpAnalysis:
        """Compile window analyses into overall track analysis.

        Args:
            track_id: Track identifier.
            windows: Analyzed windows.

        Returns:
            ArpAnalysis with patterns extracted.
        """
        if not windows:
            return ArpAnalysis(track_id=track_id)

        # Find most common rate
        rate_counts: dict[str, int] = {}
        for w in windows:
            rate_counts[w.rate] = rate_counts.get(w.rate, 0) + 1
        dominant_rate = max(rate_counts, key=rate_counts.get)  # type: ignore[arg-type]

        # Find most common interval pattern (by first N intervals)
        pattern_counts: dict[tuple[int, ...], int] = {}
        for w in windows:
            if len(w.interval_sequence) >= 4:
                # Use first 4-8 intervals as pattern signature
                pattern_len = min(8, len(w.interval_sequence))
                pattern = tuple(w.interval_sequence[:pattern_len])
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

        dominant_pattern: list[int] = []
        if pattern_counts:
            dominant_pattern = list(max(pattern_counts, key=pattern_counts.get))  # type: ignore[arg-type]

        # Calculate average gate (note duration / note spacing)
        total_gate = 0.0
        gate_count = 0
        for w in windows:
            if w.avg_note_duration > 0 and len(w.notes) >= 2:
                notes = sorted(w.notes, key=lambda n: n.start_beat)
                deltas = [
                    notes[i + 1].start_beat - notes[i].start_beat
                    for i in range(len(notes) - 1)
                ]
                avg_delta = sum(deltas) / len(deltas) if deltas else 1.0
                if avg_delta > 0:
                    gate = min(1.0, w.avg_note_duration / avg_delta)
                    total_gate += gate
                    gate_count += 1

        avg_gate = total_gate / gate_count if gate_count > 0 else 0.5

        # Extract reusable patterns
        patterns = self._extract_patterns(windows, dominant_rate)

        return ArpAnalysis(
            track_id=track_id,
            windows=windows,
            dominant_rate=dominant_rate,
            dominant_pattern=dominant_pattern,
            avg_gate=avg_gate,
            patterns=patterns,
        )

    def _extract_patterns(
        self,
        windows: list[ArpWindow],
        dominant_rate: str,
    ) -> list[ArpPattern]:
        """Extract reusable ArpPattern objects from windows.

        Args:
            windows: Analyzed windows.
            dominant_rate: Most common rate.

        Returns:
            List of unique arp patterns.
        """
        seen_patterns: set[tuple[tuple[int, ...], tuple[int, ...]]] = set()
        patterns: list[ArpPattern] = []

        for window in windows:
            if len(window.interval_sequence) < 4:
                continue

            # Create pattern signature
            intervals = tuple(window.interval_sequence[:8])
            octaves = tuple(window.octave_jumps[:8]) if window.octave_jumps else (0,) * len(intervals)

            pattern_key = (intervals, octaves)
            if pattern_key in seen_patterns:
                continue
            seen_patterns.add(pattern_key)

            # Calculate gate for this pattern
            gate = 0.5
            if window.avg_note_duration > 0 and len(window.notes) >= 2:
                notes = sorted(window.notes, key=lambda n: n.start_beat)
                deltas = [
                    notes[i + 1].start_beat - notes[i].start_beat
                    for i in range(len(notes) - 1)
                ]
                avg_delta = sum(deltas) / len(deltas) if deltas else 1.0
                if avg_delta > 0:
                    gate = min(1.0, window.avg_note_duration / avg_delta)

            patterns.append(ArpPattern(
                rate=window.rate or dominant_rate,
                interval_sequence=list(intervals),
                octave_jumps=list(octaves),
                gate=gate,
            ))

        return patterns


def analyze_arp_track(track: Track, song: Song | None = None) -> ArpAnalysis:
    """Convenience function to analyze a track for arpeggio patterns.

    Args:
        track: Track to analyze.
        song: Optional song for context.

    Returns:
        ArpAnalysis with detected patterns.
    """
    analyzer = ArpAnalyzer()
    return analyzer.analyze_track(track, song)


def extract_arp_patterns(
    track: Track,
    song: Song | None = None,
    min_confidence: float = 0.5,
) -> list[ArpPattern]:
    """Extract arpeggio patterns from a track.

    Args:
        track: Track to analyze (should have high arp probability).
        song: Optional song for context.
        min_confidence: Minimum chord confidence to include pattern.

    Returns:
        List of ArpPattern objects.
    """
    analysis = analyze_arp_track(track, song)

    # Filter patterns based on chord confidence in their windows
    patterns: list[ArpPattern] = []
    for window in analysis.windows:
        if window.inferred_chord and window.inferred_chord.confidence >= min_confidence:
            if len(window.interval_sequence) >= 4:
                patterns.append(ArpPattern(
                    rate=window.rate,
                    interval_sequence=window.interval_sequence[:8],
                    octave_jumps=window.octave_jumps[:8] if window.octave_jumps else [],
                    gate=analysis.avg_gate,
                ))

    return patterns
