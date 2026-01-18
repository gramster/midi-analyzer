"""Track feature extraction for role classification and analysis."""

from __future__ import annotations

import math
from collections import Counter
from typing import TYPE_CHECKING

from midi_analyzer.models.core import NoteEvent, Track, TrackFeatures

if TYPE_CHECKING:
    pass


class FeatureExtractor:
    """Extract musical features from tracks for analysis and classification."""

    def extract_features(self, track: Track, total_bars: int) -> TrackFeatures:
        """Extract all features from a track.

        Args:
            track: Track to analyze.
            total_bars: Total bars in the song (for density calculation).

        Returns:
            TrackFeatures with computed values.
        """
        notes = track.notes

        if not notes:
            return TrackFeatures()

        # Basic statistics
        note_count = len(notes)
        note_density = note_count / max(total_bars, 1)

        # Pitch statistics
        pitches = [n.pitch for n in notes]
        pitch_min = min(pitches)
        pitch_max = max(pitches)
        pitch_range = pitch_max - pitch_min
        pitch_median = self._median(pitches)

        # Velocity statistics
        velocities = [n.velocity for n in notes]
        avg_velocity = sum(velocities) / len(velocities)

        # Duration statistics
        durations = [n.duration_beats for n in notes]
        avg_duration = sum(durations) / len(durations)

        # Polyphony analysis
        polyphony_ratio = self._calculate_polyphony_ratio(notes)

        # Rhythmic complexity
        syncopation_score = self._calculate_syncopation(notes)

        # Repetition analysis
        repetition_score = self._calculate_repetition_score(notes)

        # Drum track indicators
        channels = [n.channel for n in notes]
        is_channel_10 = 9 in channels  # MIDI channel 10 (0-indexed as 9)

        # Pitch class entropy (for drum detection)
        pitch_class_entropy = self._calculate_pitch_class_entropy(pitches)

        return TrackFeatures(
            note_count=note_count,
            note_density=note_density,
            polyphony_ratio=polyphony_ratio,
            pitch_min=pitch_min,
            pitch_max=pitch_max,
            pitch_median=pitch_median,
            pitch_range=pitch_range,
            avg_velocity=avg_velocity,
            avg_duration=avg_duration,
            syncopation_score=syncopation_score,
            repetition_score=repetition_score,
            is_channel_10=is_channel_10,
            pitch_class_entropy=pitch_class_entropy,
        )

    def _median(self, values: list[int | float]) -> float:
        """Calculate median of a list of values."""
        sorted_values = sorted(values)
        n = len(sorted_values)
        if n == 0:
            return 0.0
        if n % 2 == 1:
            return float(sorted_values[n // 2])
        return (sorted_values[n // 2 - 1] + sorted_values[n // 2]) / 2

    def _calculate_polyphony_ratio(self, notes: list[NoteEvent]) -> float:
        """Calculate the ratio of overlapping notes (polyphony).

        Returns a value between 0 (monophonic) and 1 (highly polyphonic).
        """
        if len(notes) < 2:
            return 0.0

        # Sort by start time
        sorted_notes = sorted(notes, key=lambda n: n.start_beat)

        overlap_count = 0
        total_comparisons = 0

        for i, note in enumerate(sorted_notes[:-1]):
            note_end = note.start_beat + note.duration_beats

            # Check for overlap with subsequent notes
            for next_note in sorted_notes[i + 1 :]:
                if next_note.start_beat >= note_end:
                    break  # No more overlaps possible

                overlap_count += 1
                total_comparisons += 1

                # Limit comparisons for performance
                if total_comparisons >= 1000:
                    break

            if total_comparisons >= 1000:
                break

        if total_comparisons == 0:
            return 0.0

        return min(1.0, overlap_count / total_comparisons)

    def _calculate_syncopation(self, notes: list[NoteEvent]) -> float:
        """Calculate syncopation score based on off-beat note placement.

        Higher values indicate more syncopated rhythms.
        """
        if not notes:
            return 0.0

        off_beat_count = 0
        for note in notes:
            # Get position within the beat (0.0 = on beat, 0.5 = off beat)
            beat_position = note.start_beat % 1.0

            # Consider positions away from strong beats as syncopated
            # Strong beats: 0.0 (downbeat), potentially 0.5 (backbeat)
            if 0.1 < beat_position < 0.4 or 0.6 < beat_position < 0.9:
                off_beat_count += 1

        return off_beat_count / len(notes)

    def _calculate_repetition_score(self, notes: list[NoteEvent], window_beats: float = 4.0) -> float:
        """Calculate repetition score based on recurring pitch patterns.

        Higher values indicate more repetitive patterns.
        """
        if len(notes) < 8:
            return 0.0

        # Create pitch sequences for each bar
        bar_patterns: list[tuple[int, ...]] = []

        # Group notes by bar
        notes_by_bar: dict[int, list[int]] = {}
        for note in notes:
            bar = note.bar
            if bar not in notes_by_bar:
                notes_by_bar[bar] = []
            notes_by_bar[bar].append(note.pitch)

        # Create pattern tuples for each bar
        for bar in sorted(notes_by_bar.keys()):
            pitches = tuple(notes_by_bar[bar])
            bar_patterns.append(pitches)

        if len(bar_patterns) < 2:
            return 0.0

        # Count pattern repetitions
        pattern_counts = Counter(bar_patterns)
        repeated_patterns = sum(1 for count in pattern_counts.values() if count > 1)

        return repeated_patterns / len(bar_patterns)

    def _calculate_pitch_class_entropy(self, pitches: list[int]) -> float:
        """Calculate entropy of pitch class distribution.

        Low entropy suggests drum track (few distinct pitch classes used repeatedly).
        High entropy suggests melodic content.
        """
        if not pitches:
            return 0.0

        # Convert to pitch classes (0-11)
        pitch_classes = [p % 12 for p in pitches]

        # Count occurrences
        counts = Counter(pitch_classes)
        total = len(pitch_classes)

        # Calculate entropy
        entropy = 0.0
        for count in counts.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        # Normalize by max possible entropy (log2(12) for 12 pitch classes)
        max_entropy = math.log2(12)
        return entropy / max_entropy if max_entropy > 0 else 0.0


def extract_track_features(track: Track, total_bars: int) -> TrackFeatures:
    """Convenience function to extract features from a track.

    Args:
        track: Track to analyze.
        total_bars: Total bars in the song.

    Returns:
        TrackFeatures with computed values.
    """
    extractor = FeatureExtractor()
    return extractor.extract_features(track, total_bars)
