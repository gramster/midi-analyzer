"""Key detection using pitch-class histogram analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from midi_analyzer.models.core import NoteEvent, Song, Track


class Mode(Enum):
    """Musical mode (major or minor)."""

    MAJOR = "major"
    MINOR = "minor"


# Krumhansl-Schmuckler key profiles
# Based on empirical studies of Western tonal music
MAJOR_PROFILE = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
MINOR_PROFILE = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)

# Pitch class names
PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


@dataclass
class KeySignature:
    """Detected key signature.

    Attributes:
        root: Root note (0-11, where 0=C, 1=C#, etc.)
        mode: Major or minor mode.
        confidence: Confidence score (0-1).
        correlation: Correlation with key profile.
        root_name: Human-readable root name.
    """

    root: int
    mode: Mode
    confidence: float
    correlation: float

    @property
    def root_name(self) -> str:
        """Get the root note name."""
        return PITCH_CLASSES[self.root]

    @property
    def name(self) -> str:
        """Get the full key name (e.g., 'C major')."""
        return f"{self.root_name} {self.mode.value}"

    def __str__(self) -> str:
        """String representation."""
        return f"{self.name} ({self.confidence:.0%})"


def build_pitch_class_histogram(
    notes: list[NoteEvent],
    weight_by_duration: bool = True,
) -> tuple[float, ...]:
    """Build a pitch-class histogram from notes.

    Args:
        notes: List of note events.
        weight_by_duration: Whether to weight by note duration.

    Returns:
        Tuple of 12 values representing pitch class frequencies.
    """
    histogram = [0.0] * 12

    total_weight = 0.0
    for note in notes:
        pitch_class = note.pitch % 12
        weight = note.duration_beats if weight_by_duration else 1.0
        histogram[pitch_class] += weight
        total_weight += weight

    # Normalize
    if total_weight > 0:
        histogram = [v / total_weight for v in histogram]

    return tuple(histogram)


def correlate_profile(
    histogram: tuple[float, ...],
    profile: tuple[float, ...],
    rotation: int = 0,
) -> float:
    """Calculate Pearson correlation between histogram and profile.

    Args:
        histogram: Pitch-class histogram.
        profile: Key profile to match against.
        rotation: Number of semitones to rotate the profile.

    Returns:
        Correlation coefficient (-1 to 1).
    """
    # Rotate profile to match the key
    rotated = profile[rotation:] + profile[:rotation]

    # Calculate means
    hist_mean = sum(histogram) / 12
    prof_mean = sum(rotated) / 12

    # Calculate correlation
    numerator = sum((h - hist_mean) * (p - prof_mean) for h, p in zip(histogram, rotated))
    hist_var = sum((h - hist_mean) ** 2 for h in histogram)
    prof_var = sum((p - prof_mean) ** 2 for p in rotated)

    denominator = (hist_var * prof_var) ** 0.5

    if denominator == 0:
        return 0.0

    return numerator / denominator


def detect_key(
    notes: list[NoteEvent],
    weight_by_duration: bool = True,
) -> KeySignature:
    """Detect the key of a sequence of notes.

    Uses the Krumhansl-Schmuckler algorithm.

    Args:
        notes: List of note events.
        weight_by_duration: Whether to weight by note duration.

    Returns:
        Detected key signature.
    """
    if not notes:
        return KeySignature(root=0, mode=Mode.MAJOR, confidence=0.0, correlation=0.0)

    histogram = build_pitch_class_histogram(notes, weight_by_duration)

    best_root = 0
    best_mode = Mode.MAJOR
    best_correlation = -2.0  # Correlation range is -1 to 1

    # Test all 24 possible keys (12 major + 12 minor)
    correlations = []

    for root in range(12):
        major_corr = correlate_profile(histogram, MAJOR_PROFILE, root)
        minor_corr = correlate_profile(histogram, MINOR_PROFILE, root)

        correlations.extend([(major_corr, root, Mode.MAJOR), (minor_corr, root, Mode.MINOR)])

        if major_corr > best_correlation:
            best_correlation = major_corr
            best_root = root
            best_mode = Mode.MAJOR

        if minor_corr > best_correlation:
            best_correlation = minor_corr
            best_root = root
            best_mode = Mode.MINOR

    # Calculate confidence based on how much better the best match is
    correlations.sort(reverse=True, key=lambda x: x[0])
    second_best = correlations[1][0] if len(correlations) > 1 else 0.0

    # Confidence is based on the margin between best and second-best
    # and the absolute correlation value
    margin = best_correlation - second_best
    confidence = (best_correlation + 1) / 2 * 0.5 + margin * 0.5

    # Clamp to 0-1
    confidence = max(0.0, min(1.0, confidence))

    return KeySignature(
        root=best_root,
        mode=best_mode,
        confidence=confidence,
        correlation=best_correlation,
    )


def detect_key_for_track(track: Track) -> KeySignature:
    """Detect the key for a single track.

    Args:
        track: Track to analyze.

    Returns:
        Detected key signature.
    """
    return detect_key(track.notes)


def detect_key_for_song(song: Song) -> KeySignature:
    """Detect the overall key for a song.

    Combines notes from all non-drum tracks.

    Args:
        song: Song to analyze.

    Returns:
        Detected key signature.
    """
    all_notes = []

    for track in song.tracks:
        # Skip drum tracks
        if track.role_probs and track.role_probs.drums > 0.5:
            continue
        if track.channel == 9:  # MIDI channel 10 (0-indexed)
            continue

        all_notes.extend(track.notes)

    return detect_key(all_notes)


def get_relative_key(key: KeySignature) -> KeySignature:
    """Get the relative major/minor key.

    Args:
        key: Input key.

    Returns:
        Relative key (major -> relative minor, minor -> relative major).
    """
    if key.mode == Mode.MAJOR:
        # Relative minor is 3 semitones down (9 semitones up)
        relative_root = (key.root + 9) % 12
        relative_mode = Mode.MINOR
    else:
        # Relative major is 3 semitones up
        relative_root = (key.root + 3) % 12
        relative_mode = Mode.MAJOR

    return KeySignature(
        root=relative_root,
        mode=relative_mode,
        confidence=key.confidence,
        correlation=key.correlation,
    )


def get_parallel_key(key: KeySignature) -> KeySignature:
    """Get the parallel major/minor key.

    Args:
        key: Input key.

    Returns:
        Parallel key (same root, opposite mode).
    """
    parallel_mode = Mode.MINOR if key.mode == Mode.MAJOR else Mode.MAJOR

    return KeySignature(
        root=key.root,
        mode=parallel_mode,
        confidence=key.confidence,
        correlation=key.correlation,
    )


def key_to_string(root: int, mode: Mode) -> str:
    """Convert key root and mode to string.

    Args:
        root: Root pitch class (0-11).
        mode: Major or minor.

    Returns:
        Key name string.
    """
    return f"{PITCH_CLASSES[root]} {mode.value}"


def string_to_key(key_string: str) -> tuple[int, Mode]:
    """Parse key string to root and mode.

    Args:
        key_string: Key name (e.g., "C major", "A minor").

    Returns:
        Tuple of (root, mode).

    Raises:
        ValueError: If key string is invalid.
    """
    parts = key_string.strip().split()
    if len(parts) != 2:
        raise ValueError(f"Invalid key string: {key_string}")

    root_name = parts[0].upper()
    mode_name = parts[1].lower()

    # Handle flat names
    if root_name.endswith("B") and len(root_name) == 2:
        # Convert flat to sharp equivalent
        flat_to_sharp = {
            "DB": "C#",
            "EB": "D#",
            "GB": "F#",
            "AB": "G#",
            "BB": "A#",
        }
        root_name = flat_to_sharp.get(root_name, root_name)

    try:
        root = PITCH_CLASSES.index(root_name)
    except ValueError:
        raise ValueError(f"Invalid root: {parts[0]}")

    try:
        mode = Mode(mode_name)
    except ValueError:
        raise ValueError(f"Invalid mode: {parts[1]}")

    return root, mode
