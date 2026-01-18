"""Core data models for MIDI analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TrackRole(str, Enum):
    """Musical role classification for a track."""

    DRUMS = "drums"
    BASS = "bass"
    CHORDS = "chords"
    PAD = "pad"
    LEAD = "lead"
    ARP = "arp"
    OTHER = "other"


@dataclass
class RoleProbabilities:
    """Probability distribution over track roles."""

    drums: float = 0.0
    bass: float = 0.0
    chords: float = 0.0
    pad: float = 0.0
    lead: float = 0.0
    arp: float = 0.0
    other: float = 0.0

    def primary_role(self) -> TrackRole:
        """Return the role with highest probability."""
        role_probs = {
            TrackRole.DRUMS: self.drums,
            TrackRole.BASS: self.bass,
            TrackRole.CHORDS: self.chords,
            TrackRole.PAD: self.pad,
            TrackRole.LEAD: self.lead,
            TrackRole.ARP: self.arp,
            TrackRole.OTHER: self.other,
        }
        return max(role_probs, key=role_probs.get)  # type: ignore[arg-type]

    def to_dict(self) -> dict[str, float]:
        """Convert to dictionary."""
        return {
            "drums": self.drums,
            "bass": self.bass,
            "chords": self.chords,
            "pad": self.pad,
            "lead": self.lead,
            "arp": self.arp,
            "other": self.other,
        }


@dataclass
class NoteEvent:
    """A single note event with beat-based timing.

    Attributes:
        pitch: MIDI pitch (0-127)
        velocity: Note velocity (0-127)
        start_beat: Start time in beats from song start
        duration_beats: Duration in beats
        track_id: Source track identifier
        channel: MIDI channel (0-15)
        start_tick: Original start time in ticks (for reference)
        bar: Bar number (0-indexed)
        beat_in_bar: Beat position within the bar (0-indexed)
        quantized_start: Start time quantized to grid (optional)
        quantized_duration: Duration quantized to grid (optional)
    """

    pitch: int
    velocity: int
    start_beat: float
    duration_beats: float
    track_id: int
    channel: int
    start_tick: int = 0
    bar: int = 0
    beat_in_bar: float = 0.0
    quantized_start: float | None = None
    quantized_duration: float | None = None


@dataclass
class TempoEvent:
    """A tempo change event.

    Attributes:
        tick: Tick position of the tempo change
        beat: Beat position of the tempo change
        tempo_bpm: Tempo in beats per minute
        microseconds_per_beat: Tempo in microseconds per beat (MIDI native)
    """

    tick: int
    beat: float
    tempo_bpm: float
    microseconds_per_beat: int


@dataclass
class TimeSignature:
    """A time signature event.

    Attributes:
        tick: Tick position of the time signature change
        beat: Beat position of the change
        bar: Bar number where this time signature starts
        numerator: Beats per bar
        denominator: Beat unit (4 = quarter note, 8 = eighth note, etc.)
    """

    tick: int
    beat: float
    bar: int
    numerator: int
    denominator: int

    @property
    def beats_per_bar(self) -> float:
        """Calculate beats per bar (in quarter notes)."""
        return self.numerator * (4 / self.denominator)


@dataclass
class TrackFeatures:
    """Computed features for a track.

    Attributes:
        note_count: Total number of notes
        note_density: Average notes per bar
        polyphony_ratio: Ratio of overlapping notes
        pitch_min: Lowest pitch
        pitch_max: Highest pitch
        pitch_median: Median pitch
        pitch_range: Range of pitches
        avg_velocity: Average note velocity
        avg_duration: Average note duration in beats
        syncopation_score: Measure of rhythmic complexity
        repetition_score: Measure of pattern repetition
        is_channel_10: Whether track uses MIDI channel 10 (drums)
        pitch_class_entropy: Entropy of pitch class distribution
    """

    note_count: int = 0
    note_density: float = 0.0
    polyphony_ratio: float = 0.0
    pitch_min: int = 127
    pitch_max: int = 0
    pitch_median: float = 64.0
    pitch_range: int = 0
    avg_velocity: float = 64.0
    avg_duration: float = 1.0
    syncopation_score: float = 0.0
    repetition_score: float = 0.0
    is_channel_10: bool = False
    pitch_class_entropy: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "note_count": self.note_count,
            "note_density": self.note_density,
            "polyphony_ratio": self.polyphony_ratio,
            "pitch_min": self.pitch_min,
            "pitch_max": self.pitch_max,
            "pitch_median": self.pitch_median,
            "pitch_range": self.pitch_range,
            "avg_velocity": self.avg_velocity,
            "avg_duration": self.avg_duration,
            "syncopation_score": self.syncopation_score,
            "repetition_score": self.repetition_score,
            "is_channel_10": self.is_channel_10,
            "pitch_class_entropy": self.pitch_class_entropy,
        }


@dataclass
class Track:
    """A MIDI track with notes and metadata.

    Attributes:
        track_id: Unique identifier within the song
        name: Track name from MIDI metadata
        channel: Primary MIDI channel (most common)
        notes: List of note events
        features: Computed features (populated by analysis)
        role_probs: Role probability distribution (populated by analysis)
    """

    track_id: int
    name: str = ""
    channel: int = 0
    notes: list[NoteEvent] = field(default_factory=list)
    features: TrackFeatures | None = None
    role_probs: RoleProbabilities | None = None

    @property
    def primary_role(self) -> TrackRole:
        """Get the most likely role for this track."""
        if self.role_probs is None:
            return TrackRole.OTHER
        return self.role_probs.primary_role()


@dataclass
class SongMetadata:
    """Metadata extracted from filename, folder structure, or web APIs.

    Attributes:
        artist: Artist name
        title: Song title
        genre: Primary genre
        tags: Additional descriptive tags
        source: Where metadata was obtained (filename, musicbrainz, etc.)
        confidence: Confidence score for the metadata (0.0-1.0)
    """

    artist: str = ""
    title: str = ""
    genre: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = "unknown"
    confidence: float = 0.0


@dataclass
class Song:
    """A complete MIDI song with all extracted information.

    Attributes:
        song_id: Unique identifier (usually hash of file path)
        source_path: Original file path
        ticks_per_beat: MIDI resolution (PPQ)
        tempo_map: List of tempo changes
        time_sig_map: List of time signature changes
        tracks: List of tracks
        total_bars: Total number of bars
        total_beats: Total duration in beats
        detected_key: Detected musical key (e.g., "C major")
        detected_mode: Detected mode (major/minor/etc.)
        metadata: Song metadata (artist, title, genre, tags)
    """

    song_id: str
    source_path: str
    ticks_per_beat: int
    tempo_map: list[TempoEvent] = field(default_factory=list)
    time_sig_map: list[TimeSignature] = field(default_factory=list)
    tracks: list[Track] = field(default_factory=list)
    total_bars: int = 0
    total_beats: float = 0.0
    detected_key: str = ""
    detected_mode: str = ""
    metadata: SongMetadata = field(default_factory=SongMetadata)

    @property
    def primary_tempo(self) -> float:
        """Get the primary (first) tempo in BPM."""
        if self.tempo_map:
            return self.tempo_map[0].tempo_bpm
        return 120.0  # Default MIDI tempo

    @property
    def primary_time_sig(self) -> tuple[int, int]:
        """Get the primary (first) time signature as (numerator, denominator)."""
        if self.time_sig_map:
            ts = self.time_sig_map[0]
            return (ts.numerator, ts.denominator)
        return (4, 4)  # Default time signature
