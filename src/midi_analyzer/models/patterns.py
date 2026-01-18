"""Pattern data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from midi_analyzer.models.core import TrackRole


@dataclass
class PatternHit:
    """A single hit in a drum pattern."""

    step: int  # Step within the pattern (0-indexed)
    pitch: int  # MIDI pitch (drum sound)
    velocity: int  # Hit velocity


@dataclass
class DrumPattern:
    """A drum pattern representation.

    Attributes:
        steps_per_bar: Grid resolution (e.g., 16 for 16th notes)
        hits: List of drum hits
        length_bars: Pattern length in bars
    """

    steps_per_bar: int
    hits: list[PatternHit] = field(default_factory=list)
    length_bars: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "stepsPerBar": self.steps_per_bar,
            "lengthBars": self.length_bars,
            "hits": [{"step": h.step, "pitch": h.pitch, "vel": h.velocity} for h in self.hits],
        }


@dataclass
class MelodicEvent:
    """A single event in a melodic pattern."""

    step: int  # Step position
    interval: int  # Interval from pattern root (semitones)
    duration: int  # Duration in steps


@dataclass
class MelodicPattern:
    """A melodic pattern representation (transposition-independent).

    Attributes:
        steps_per_bar: Grid resolution
        events: List of melodic events with relative intervals
        length_bars: Pattern length in bars
    """

    steps_per_bar: int
    events: list[MelodicEvent] = field(default_factory=list)
    length_bars: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "stepsPerBar": self.steps_per_bar,
            "lengthBars": self.length_bars,
            "events": [
                {"step": e.step, "interval": e.interval, "dur": e.duration} for e in self.events
            ],
        }


@dataclass
class ArpPattern:
    """An arpeggio pattern representation.

    Attributes:
        rate: Note rate (e.g., "1/16", "1/8")
        interval_sequence: Sequence of intervals from chord root
        octave_jumps: Octave offset for each step
        gate: Note length as fraction of step (0.0-1.0)
    """

    rate: str
    interval_sequence: list[int] = field(default_factory=list)
    octave_jumps: list[int] = field(default_factory=list)
    gate: float = 0.5

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "rate": self.rate,
            "interval_sequence": self.interval_sequence,
            "octave_jumps": self.octave_jumps,
            "gate": self.gate,
        }


@dataclass
class RhythmFingerprint:
    """Fingerprint of a pattern's rhythm.

    Attributes:
        onset_grid: Binary or weighted grid of note onsets
        accent_profile: Velocity profile normalized to grid
        density: Notes per step
    """

    onset_grid: list[float]  # Weighted onset at each step
    accent_profile: list[float]  # Normalized velocity at each step
    density: float

    def to_hash(self) -> str:
        """Generate a hash string for fast comparison."""
        # Quantize to binary for hashing
        binary = "".join("1" if v > 0.1 else "0" for v in self.onset_grid)
        return binary


@dataclass
class PitchFingerprint:
    """Fingerprint of a pattern's pitch content.

    Attributes:
        interval_sequence: Relative intervals between consecutive notes
        contour: Simplified up/down/same contour
        pitch_classes: Set of pitch classes used
    """

    interval_sequence: list[int]
    contour: list[int]  # -1 = down, 0 = same, 1 = up
    pitch_classes: set[int]

    def to_hash(self) -> str:
        """Generate a hash string for fast comparison."""
        # Use contour for transposition-invariant hash
        contour_str = "".join(
            "D" if c < 0 else ("U" if c > 0 else "S") for c in self.contour
        )
        return contour_str


@dataclass
class Pattern:
    """A reusable musical pattern.

    Attributes:
        pattern_id: Unique identifier
        role: Track role this pattern is associated with
        length_bars: Pattern length in bars
        meter: Time signature as "num/denom"
        grid_resolution: Steps per bar
        rhythm_fp: Rhythm fingerprint
        pitch_fp: Pitch fingerprint (None for drums)
        representation: Role-specific pattern representation
        stats: Additional statistics
        tags: Descriptive tags
    """

    pattern_id: str
    role: TrackRole
    length_bars: int
    meter: str
    grid_resolution: int
    rhythm_fp: RhythmFingerprint | None = None
    pitch_fp: PitchFingerprint | None = None
    representation: DrumPattern | MelodicPattern | ArpPattern | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    @property
    def combo_fingerprint(self) -> str:
        """Combined rhythm and pitch fingerprint for deduplication."""
        rhythm_hash = self.rhythm_fp.to_hash() if self.rhythm_fp else ""
        pitch_hash = self.pitch_fp.to_hash() if self.pitch_fp else ""
        return f"{rhythm_hash}:{pitch_hash}"


@dataclass
class PatternInstance:
    """An instance of a pattern found in a song.

    Attributes:
        pattern_id: Reference to the canonical pattern
        song_id: Song where this instance was found
        track_id: Track within the song
        start_bar: Starting bar of the instance
        confidence: Confidence score for the match
        transform: Any transformation applied (transposition, etc.)
    """

    pattern_id: str
    song_id: str
    track_id: int
    start_bar: int
    confidence: float = 1.0
    transform: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "pattern_id": self.pattern_id,
            "song_id": self.song_id,
            "track_id": self.track_id,
            "start_bar": self.start_bar,
            "confidence": self.confidence,
            "transform": self.transform,
        }
