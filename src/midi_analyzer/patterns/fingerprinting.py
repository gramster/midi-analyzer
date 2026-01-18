"""Fingerprinting for pattern matching."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from midi_analyzer.models.core import NoteEvent
    from midi_analyzer.patterns.chunking import BarChunk


@dataclass
class RhythmFingerprint:
    """A rhythm fingerprint for a bar chunk.

    Captures the onset pattern (when notes start) as a binary grid,
    plus accent information (velocity weighting).

    Attributes:
        onset_grid: Binary grid of note onsets (1=note, 0=rest)
        accent_grid: Weighted grid of velocities (0.0-1.0)
        grid_size: Number of steps per bar (16 or 32)
        num_bars: Number of bars this fingerprint spans
        note_count: Total number of notes
    """

    onset_grid: tuple[int, ...]
    accent_grid: tuple[float, ...]
    grid_size: int
    num_bars: int
    note_count: int
    hash_value: str = ""

    def __post_init__(self) -> None:
        """Compute hash after initialization."""
        if not self.hash_value:
            self.hash_value = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute a stable hash for this fingerprint."""
        # Use only onset grid for the primary hash (velocity-independent)
        onset_str = "".join(str(x) for x in self.onset_grid)
        return hashlib.md5(onset_str.encode()).hexdigest()[:16]

    @property
    def density(self) -> float:
        """Get the note density (notes per step)."""
        total_steps = len(self.onset_grid)
        if total_steps == 0:
            return 0.0
        return sum(self.onset_grid) / total_steps

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "onset_grid": list(self.onset_grid),
            "accent_grid": [round(v, 3) for v in self.accent_grid],
            "grid_size": self.grid_size,
            "num_bars": self.num_bars,
            "note_count": self.note_count,
            "hash": self.hash_value,
            "density": round(self.density, 3),
        }


@dataclass
class PitchFingerprint:
    """A pitch fingerprint for a bar chunk.

    Captures melodic intervals and pitch class distribution.

    Attributes:
        intervals: Sequence of intervals between consecutive notes (in semitones)
        pitch_classes: Histogram of pitch classes (12 values, 0-11)
        contour: Simplified melodic contour (-1=down, 0=same, 1=up)
        range_semitones: Total pitch range
        mean_pitch: Average MIDI pitch
    """

    intervals: tuple[int, ...]
    pitch_classes: tuple[int, ...]
    contour: tuple[int, ...]
    range_semitones: int
    mean_pitch: float
    hash_value: str = ""

    def __post_init__(self) -> None:
        """Compute hash after initialization."""
        if not self.hash_value:
            self.hash_value = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute a stable hash for this fingerprint."""
        # Use intervals for primary hash (transposition-independent)
        interval_str = ",".join(str(x) for x in self.intervals)
        return hashlib.md5(interval_str.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "intervals": list(self.intervals),
            "pitch_classes": list(self.pitch_classes),
            "contour": list(self.contour),
            "range_semitones": self.range_semitones,
            "mean_pitch": round(self.mean_pitch, 1),
            "hash": self.hash_value,
        }


@dataclass
class CombinedFingerprint:
    """Combined rhythm and pitch fingerprint."""

    rhythm: RhythmFingerprint
    pitch: PitchFingerprint
    hash_value: str = ""

    def __post_init__(self) -> None:
        """Compute combined hash."""
        if not self.hash_value:
            combined = f"{self.rhythm.hash_value}:{self.pitch.hash_value}"
            self.hash_value = hashlib.md5(combined.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "rhythm": self.rhythm.to_dict(),
            "pitch": self.pitch.to_dict(),
            "hash": self.hash_value,
        }


class Fingerprinter:
    """Generates fingerprints from bar chunks."""

    def __init__(self, grid_size: int = 16) -> None:
        """Initialize the fingerprinter.

        Args:
            grid_size: Steps per bar for rhythm grid (16 or 32).
        """
        self.grid_size = grid_size

    def rhythm_fingerprint(
        self,
        chunk: BarChunk,
    ) -> RhythmFingerprint:
        """Generate a rhythm fingerprint for a bar chunk.

        Args:
            chunk: Bar chunk with notes (local timing).

        Returns:
            RhythmFingerprint capturing onset pattern.
        """
        total_steps = self.grid_size * chunk.num_bars
        step_duration = chunk.beats_per_bar / self.grid_size

        # Initialize grids
        onset_grid = [0] * total_steps
        accent_grid = [0.0] * total_steps

        for note in chunk.notes:
            # Calculate which step this note falls on
            step = int(note.start_beat / step_duration)
            if 0 <= step < total_steps:
                onset_grid[step] = 1
                # Normalize velocity to 0-1 range, take max if multiple notes
                velocity_norm = note.velocity / 127.0
                accent_grid[step] = max(accent_grid[step], velocity_norm)

        return RhythmFingerprint(
            onset_grid=tuple(onset_grid),
            accent_grid=tuple(accent_grid),
            grid_size=self.grid_size,
            num_bars=chunk.num_bars,
            note_count=len(chunk.notes),
        )

    def pitch_fingerprint(
        self,
        chunk: BarChunk,
    ) -> PitchFingerprint:
        """Generate a pitch fingerprint for a bar chunk.

        Args:
            chunk: Bar chunk with notes.

        Returns:
            PitchFingerprint capturing melodic content.
        """
        if not chunk.notes:
            return PitchFingerprint(
                intervals=(),
                pitch_classes=tuple([0] * 12),
                contour=(),
                range_semitones=0,
                mean_pitch=0.0,
            )

        # Sort notes by start time
        sorted_notes = sorted(chunk.notes, key=lambda n: n.start_beat)

        # Extract pitches
        pitches = [n.pitch for n in sorted_notes]

        # Calculate intervals between consecutive notes
        intervals = []
        for i in range(1, len(pitches)):
            intervals.append(pitches[i] - pitches[i - 1])

        # Calculate simplified contour
        contour = []
        for interval in intervals:
            if interval > 0:
                contour.append(1)  # Up
            elif interval < 0:
                contour.append(-1)  # Down
            else:
                contour.append(0)  # Same

        # Pitch class histogram
        pitch_classes = [0] * 12
        for pitch in pitches:
            pc = pitch % 12
            pitch_classes[pc] += 1

        # Range and mean
        range_semitones = max(pitches) - min(pitches) if pitches else 0
        mean_pitch = sum(pitches) / len(pitches) if pitches else 0.0

        return PitchFingerprint(
            intervals=tuple(intervals),
            pitch_classes=tuple(pitch_classes),
            contour=tuple(contour),
            range_semitones=range_semitones,
            mean_pitch=mean_pitch,
        )

    def fingerprint(
        self,
        chunk: BarChunk,
    ) -> CombinedFingerprint:
        """Generate a combined fingerprint for a bar chunk.

        Args:
            chunk: Bar chunk with notes.

        Returns:
            CombinedFingerprint with rhythm and pitch info.
        """
        rhythm = self.rhythm_fingerprint(chunk)
        pitch = self.pitch_fingerprint(chunk)
        return CombinedFingerprint(rhythm=rhythm, pitch=pitch)

    def fingerprint_track_chunks(
        self,
        chunks: list[BarChunk],
    ) -> list[CombinedFingerprint]:
        """Generate fingerprints for a list of chunks.

        Args:
            chunks: List of bar chunks.

        Returns:
            List of combined fingerprints.
        """
        return [self.fingerprint(chunk) for chunk in chunks]


def rhythm_fingerprint(
    notes: list[NoteEvent],
    beats_per_bar: float = 4.0,
    num_bars: int = 1,
    grid_size: int = 16,
) -> RhythmFingerprint:
    """Convenience function to generate rhythm fingerprint from notes.

    Args:
        notes: List of notes with local timing (relative to bar start).
        beats_per_bar: Beats per bar.
        num_bars: Number of bars.
        grid_size: Steps per bar.

    Returns:
        RhythmFingerprint.
    """
    # Create a temporary chunk
    from midi_analyzer.patterns.chunking import BarChunk

    chunk = BarChunk(
        start_bar=0,
        end_bar=num_bars,
        num_bars=num_bars,
        notes=notes,
        beats_per_bar=beats_per_bar,
    )

    fingerprinter = Fingerprinter(grid_size=grid_size)
    return fingerprinter.rhythm_fingerprint(chunk)


def pitch_fingerprint(
    notes: list[NoteEvent],
    beats_per_bar: float = 4.0,
    num_bars: int = 1,
) -> PitchFingerprint:
    """Convenience function to generate pitch fingerprint from notes.

    Args:
        notes: List of notes.
        beats_per_bar: Beats per bar.
        num_bars: Number of bars.

    Returns:
        PitchFingerprint.
    """
    from midi_analyzer.patterns.chunking import BarChunk

    chunk = BarChunk(
        start_bar=0,
        end_bar=num_bars,
        num_bars=num_bars,
        notes=notes,
        beats_per_bar=beats_per_bar,
    )

    fingerprinter = Fingerprinter()
    return fingerprinter.pitch_fingerprint(chunk)
