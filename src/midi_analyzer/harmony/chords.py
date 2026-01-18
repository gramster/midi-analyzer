"""Chord detection and progression inference."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from midi_analyzer.harmony.keys import KeySignature, Mode, detect_key
from midi_analyzer.models.core import TrackRole

if TYPE_CHECKING:
    from midi_analyzer.models.core import NoteEvent, Song, Track


class ChordQuality(Enum):
    """Chord quality/type."""

    MAJOR = "major"
    MINOR = "minor"
    DIMINISHED = "dim"
    AUGMENTED = "aug"
    DOMINANT_7 = "7"
    MAJOR_7 = "maj7"
    MINOR_7 = "m7"
    DIMINISHED_7 = "dim7"
    HALF_DIMINISHED_7 = "m7b5"
    SUSPENDED_2 = "sus2"
    SUSPENDED_4 = "sus4"
    POWER = "5"
    UNKNOWN = "?"


# Chord templates: pitch class intervals from root
CHORD_TEMPLATES: dict[ChordQuality, frozenset[int]] = {
    ChordQuality.MAJOR: frozenset({0, 4, 7}),
    ChordQuality.MINOR: frozenset({0, 3, 7}),
    ChordQuality.DIMINISHED: frozenset({0, 3, 6}),
    ChordQuality.AUGMENTED: frozenset({0, 4, 8}),
    ChordQuality.DOMINANT_7: frozenset({0, 4, 7, 10}),
    ChordQuality.MAJOR_7: frozenset({0, 4, 7, 11}),
    ChordQuality.MINOR_7: frozenset({0, 3, 7, 10}),
    ChordQuality.DIMINISHED_7: frozenset({0, 3, 6, 9}),
    ChordQuality.HALF_DIMINISHED_7: frozenset({0, 3, 6, 10}),
    ChordQuality.SUSPENDED_2: frozenset({0, 2, 7}),
    ChordQuality.SUSPENDED_4: frozenset({0, 5, 7}),
    ChordQuality.POWER: frozenset({0, 7}),
}

# Pitch class names
PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")

# Roman numeral mapping for scale degrees
ROMAN_NUMERALS_MAJOR = ["I", "bII", "II", "bIII", "III", "IV", "#IV", "V", "bVI", "VI", "bVII", "VII"]
ROMAN_NUMERALS_MINOR = ["i", "bII", "ii", "bIII", "III", "iv", "#iv", "v", "bVI", "VI", "bVII", "VII"]


@dataclass
class Chord:
    """A detected chord.

    Attributes:
        root: Root pitch class (0-11).
        quality: Chord quality/type.
        bass: Bass note pitch class if different from root (for inversions).
        confidence: Detection confidence (0-1).
    """

    root: int
    quality: ChordQuality
    bass: int | None = None
    confidence: float = 1.0

    @property
    def root_name(self) -> str:
        """Get root note name."""
        return PITCH_CLASSES[self.root]

    @property
    def name(self) -> str:
        """Get full chord name (e.g., 'Cmaj7')."""
        quality_str = ""
        if self.quality == ChordQuality.MAJOR:
            quality_str = ""
        elif self.quality == ChordQuality.MINOR:
            quality_str = "m"
        else:
            quality_str = self.quality.value

        name = f"{self.root_name}{quality_str}"

        if self.bass is not None and self.bass != self.root:
            name = f"{name}/{PITCH_CLASSES[self.bass]}"

        return name

    def to_roman_numeral(self, key: KeySignature) -> str:
        """Convert chord to Roman numeral relative to key.

        Args:
            key: The key to analyze the chord against.

        Returns:
            Roman numeral representation (e.g., 'IV', 'vi').
        """
        # Calculate scale degree (0-11) relative to key
        degree = (self.root - key.root) % 12

        # Choose appropriate numeral based on key mode
        if key.mode == Mode.MAJOR:
            numeral = ROMAN_NUMERALS_MAJOR[degree]
        else:
            numeral = ROMAN_NUMERALS_MINOR[degree]

        # Adjust case based on chord quality
        if self.quality in (ChordQuality.MINOR, ChordQuality.MINOR_7, ChordQuality.DIMINISHED,
                           ChordQuality.DIMINISHED_7, ChordQuality.HALF_DIMINISHED_7):
            numeral = numeral.lower()
        else:
            numeral = numeral.upper()

        # Add quality suffix
        if self.quality == ChordQuality.DIMINISHED:
            numeral += "°"
        elif self.quality == ChordQuality.AUGMENTED:
            numeral += "+"
        elif self.quality in (ChordQuality.DOMINANT_7, ChordQuality.MAJOR_7,
                             ChordQuality.MINOR_7, ChordQuality.DIMINISHED_7,
                             ChordQuality.HALF_DIMINISHED_7):
            numeral += self.quality.value

        return numeral

    def __str__(self) -> str:
        """String representation."""
        return self.name


@dataclass
class ChordEvent:
    """A chord at a specific time.

    Attributes:
        chord: The detected chord.
        start_beat: Start time in beats.
        end_beat: End time in beats.
        notes: Notes that form this chord.
    """

    chord: Chord
    start_beat: float
    end_beat: float
    notes: list[NoteEvent] = field(default_factory=list)

    @property
    def duration_beats(self) -> float:
        """Duration in beats."""
        return self.end_beat - self.start_beat


@dataclass
class ChordProgression:
    """A sequence of chords.

    Attributes:
        chords: List of chord events.
        key: Detected key for the progression.
    """

    chords: list[ChordEvent]
    key: KeySignature | None = None

    def to_roman_numerals(self) -> list[str]:
        """Convert progression to Roman numeral representation.

        Returns:
            List of Roman numeral strings.
        """
        if not self.key:
            return [chord.chord.name for chord in self.chords]

        return [chord.chord.to_roman_numeral(self.key) for chord in self.chords]

    def simplify(self) -> list[str]:
        """Get simplified chord names (no duplicates in sequence).

        Returns:
            List of chord names with consecutive duplicates removed.
        """
        if not self.chords:
            return []

        result = [self.chords[0].chord.name]
        for event in self.chords[1:]:
            if event.chord.name != result[-1]:
                result.append(event.chord.name)

        return result


def get_pitch_classes_in_window(
    notes: list[NoteEvent],
    start_beat: float,
    end_beat: float,
    weight_by_duration: bool = True,
) -> dict[int, float]:
    """Get pitch classes and their weights in a time window.

    Args:
        notes: List of note events.
        start_beat: Window start time in beats.
        end_beat: Window end time in beats.
        weight_by_duration: Whether to weight by duration.

    Returns:
        Dictionary mapping pitch class to weight.
    """
    pitch_weights: dict[int, float] = {}

    for note in notes:
        # Check if note overlaps with window
        note_end = note.start_beat + note.duration_beats
        if note.start_beat >= end_beat or note_end <= start_beat:
            continue

        # Calculate overlap
        overlap_start = max(note.start_beat, start_beat)
        overlap_end = min(note_end, end_beat)
        overlap = overlap_end - overlap_start

        pitch_class = note.pitch % 12
        weight = overlap if weight_by_duration else 1.0
        pitch_weights[pitch_class] = pitch_weights.get(pitch_class, 0.0) + weight

    return pitch_weights


def match_chord(
    pitch_classes: set[int],
    weights: dict[int, float] | None = None,
) -> Chord:
    """Match pitch classes to the best chord.

    Args:
        pitch_classes: Set of pitch classes present.
        weights: Optional weights for each pitch class.

    Returns:
        Best matching chord.
    """
    if not pitch_classes:
        return Chord(root=0, quality=ChordQuality.UNKNOWN, confidence=0.0)

    best_root = 0
    best_quality = ChordQuality.UNKNOWN
    best_score = 0.0

    # Try each pitch class as potential root
    for root in pitch_classes:
        # Transpose pitch classes relative to root
        intervals = frozenset((pc - root) % 12 for pc in pitch_classes)

        # Match against templates
        for quality, template in CHORD_TEMPLATES.items():
            # Calculate match score
            common = len(intervals & template)
            # Penalize extra notes not in template
            extra = len(intervals - template)
            # Penalize missing notes from template
            missing = len(template - intervals)

            # Score based on coverage of template
            score = (common - extra * 0.5 - missing * 0.3) / len(template)

            # Prefer triads over power chords
            if quality == ChordQuality.POWER and best_quality != ChordQuality.UNKNOWN:
                score *= 0.8

            # Use root weight as tiebreaker
            if weights and root in weights:
                score *= (1.0 + weights[root] * 0.1)

            if score > best_score:
                best_score = score
                best_root = root
                best_quality = quality

    confidence = max(0.0, min(1.0, best_score))
    return Chord(root=best_root, quality=best_quality, confidence=confidence)


def detect_bass_note(
    notes: list[NoteEvent],
    start_beat: float,
    end_beat: float,
) -> int | None:
    """Detect the bass note in a time window.

    Args:
        notes: List of note events.
        start_beat: Window start time.
        end_beat: Window end time.

    Returns:
        Bass note pitch class or None.
    """
    bass_notes: list[tuple[int, float]] = []  # (pitch, duration_in_window)

    for note in notes:
        note_end = note.start_beat + note.duration_beats
        if note.start_beat >= end_beat or note_end <= start_beat:
            continue

        overlap_start = max(note.start_beat, start_beat)
        overlap_end = min(note_end, end_beat)
        overlap = overlap_end - overlap_start

        bass_notes.append((note.pitch, overlap))

    if not bass_notes:
        return None

    # Find lowest pitch, weighted by duration
    bass_notes.sort(key=lambda x: (x[0], -x[1]))
    return bass_notes[0][0] % 12


def detect_chords(
    notes: list[NoteEvent],
    window_beats: float = 2.0,
    hop_beats: float = 1.0,
    min_notes: int = 2,
    detect_inversions: bool = True,
) -> list[ChordEvent]:
    """Detect chords from a sequence of notes using sliding window.

    Args:
        notes: List of note events.
        window_beats: Size of analysis window in beats.
        hop_beats: Hop size between windows in beats.
        min_notes: Minimum notes required for chord detection.
        detect_inversions: Whether to detect inversions (slash chords).

    Returns:
        List of detected chord events.
    """
    if not notes:
        return []

    # Find time range
    min_beat = min(n.start_beat for n in notes)
    max_beat = max(n.start_beat + n.duration_beats for n in notes)

    chord_events: list[ChordEvent] = []
    current_beat = min_beat

    while current_beat < max_beat:
        window_end = current_beat + window_beats

        # Get pitch classes in window
        pitch_weights = get_pitch_classes_in_window(notes, current_beat, window_end)

        if len(pitch_weights) >= min_notes:
            # Match chord
            chord = match_chord(set(pitch_weights.keys()), pitch_weights)

            # Detect bass note for inversions
            if detect_inversions:
                bass = detect_bass_note(notes, current_beat, window_end)
                if bass is not None and bass != chord.root:
                    chord = Chord(
                        root=chord.root,
                        quality=chord.quality,
                        bass=bass,
                        confidence=chord.confidence,
                    )

            # Get notes in this window
            window_notes = [
                n for n in notes
                if n.start_beat < window_end and n.start_beat + n.duration_beats > current_beat
            ]

            chord_events.append(ChordEvent(
                chord=chord,
                start_beat=current_beat,
                end_beat=window_end,
                notes=window_notes,
            ))

        current_beat += hop_beats

    return chord_events


def smooth_chord_progression(
    chord_events: list[ChordEvent],
    min_duration_beats: float = 1.0,
) -> list[ChordEvent]:
    """Smooth a chord progression by merging short/repeated chords.

    Args:
        chord_events: List of chord events.
        min_duration_beats: Minimum duration for a chord.

    Returns:
        Smoothed list of chord events.
    """
    if not chord_events:
        return []

    smoothed: list[ChordEvent] = []

    for event in chord_events:
        if not smoothed:
            smoothed.append(event)
            continue

        prev = smoothed[-1]

        # Merge if same chord
        if event.chord.root == prev.chord.root and event.chord.quality == prev.chord.quality:
            # Extend previous chord
            smoothed[-1] = ChordEvent(
                chord=prev.chord,
                start_beat=prev.start_beat,
                end_beat=event.end_beat,
                notes=prev.notes + event.notes,
            )
        else:
            # Check if previous chord is too short
            if prev.duration_beats < min_duration_beats and len(smoothed) > 1:
                # Remove short chord and extend the one before
                short = smoothed.pop()
                if smoothed:
                    smoothed[-1] = ChordEvent(
                        chord=smoothed[-1].chord,
                        start_beat=smoothed[-1].start_beat,
                        end_beat=short.end_beat,
                        notes=smoothed[-1].notes + short.notes,
                    )
            smoothed.append(event)

    return smoothed


def detect_chord_progression(
    notes: list[NoteEvent],
    window_beats: float = 2.0,
    hop_beats: float = 1.0,
    smooth: bool = True,
    detect_key_signature: bool = True,
) -> ChordProgression:
    """Detect chord progression from notes.

    Args:
        notes: List of note events.
        window_beats: Analysis window size in beats.
        hop_beats: Hop size between windows.
        smooth: Whether to apply temporal smoothing.
        detect_key_signature: Whether to detect the key.

    Returns:
        Detected chord progression.
    """
    # Detect chords
    chord_events = detect_chords(notes, window_beats, hop_beats)

    # Apply smoothing
    if smooth:
        chord_events = smooth_chord_progression(chord_events)

    # Detect key if requested
    key = None
    if detect_key_signature and notes:
        key = detect_key(notes)

    return ChordProgression(chords=chord_events, key=key)


def detect_chord_progression_for_track(track: Track, **kwargs) -> ChordProgression:
    """Detect chord progression for a track.

    Args:
        track: Track to analyze.
        **kwargs: Additional arguments for detect_chord_progression.

    Returns:
        Detected chord progression.
    """
    return detect_chord_progression(track.notes, **kwargs)


def detect_chord_progression_for_song(
    song: Song,
    combine_tracks: bool = True,
    exclude_drums: bool = True,
    **kwargs,
) -> ChordProgression:
    """Detect chord progression for a song.

    Args:
        song: Song to analyze.
        combine_tracks: Whether to combine all tracks.
        exclude_drums: Whether to exclude drum tracks.
        **kwargs: Additional arguments for detect_chord_progression.

    Returns:
        Detected chord progression.
    """
    def is_drum_track(track: Track) -> bool:
        """Check if track is a drum track."""
        return track.primary_role == TrackRole.DRUMS

    if combine_tracks:
        all_notes = []
        for track in song.tracks:
            if exclude_drums and is_drum_track(track):
                continue
            all_notes.extend(track.notes)

        # Sort by start time
        all_notes.sort(key=lambda n: n.start_beat)
        return detect_chord_progression(all_notes, **kwargs)

    # Return progression from first non-drum track
    for track in song.tracks:
        if exclude_drums and is_drum_track(track):
            continue
        return detect_chord_progression(track.notes, **kwargs)

    return ChordProgression(chords=[])


def get_common_progressions() -> dict[str, list[str]]:
    """Get common chord progressions for reference.

    Returns:
        Dictionary of progression names to Roman numeral lists.
    """
    return {
        "I-IV-V-I": ["I", "IV", "V", "I"],
        "I-V-vi-IV": ["I", "V", "vi", "IV"],
        "ii-V-I": ["ii", "V", "I"],
        "I-vi-IV-V": ["I", "vi", "IV", "V"],
        "I-IV-vi-V": ["I", "IV", "vi", "V"],
        "vi-IV-I-V": ["vi", "IV", "I", "V"],
        "I-V-IV": ["I", "V", "IV"],
        "12-bar blues": ["I", "I", "I", "I", "IV", "IV", "I", "I", "V", "IV", "I", "V"],
        "Andalusian cadence": ["i", "VII", "VI", "V"],
        "Circle of fifths": ["I", "IV", "vii°", "iii", "vi", "ii", "V", "I"],
    }


def identify_progression_pattern(
    progression: ChordProgression,
    tolerance: int = 0,
) -> str | None:
    """Identify if a progression matches a common pattern.

    Args:
        progression: Chord progression to analyze.
        tolerance: Number of mismatches allowed.

    Returns:
        Name of matching pattern or None.
    """
    if not progression.key or not progression.chords:
        return None

    roman_numerals = progression.to_roman_numerals()
    common = get_common_progressions()

    for name, pattern in common.items():
        if len(roman_numerals) < len(pattern):
            continue

        # Check for pattern match at any position
        for i in range(len(roman_numerals) - len(pattern) + 1):
            segment = roman_numerals[i : i + len(pattern)]
            mismatches = sum(1 for a, b in zip(segment, pattern) if a != b)
            if mismatches <= tolerance:
                return name

    return None
