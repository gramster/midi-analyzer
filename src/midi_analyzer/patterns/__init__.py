"""Pattern extraction and mining."""

from midi_analyzer.patterns.chunking import (
    BarChunk,
    BarChunker,
    chunk_song,
    chunk_track,
)
from midi_analyzer.patterns.deduplication import (
    DeduplicationResult,
    PatternCluster,
    PatternDeduplicator,
    PatternMatch,
    deduplicate_track,
    find_repeated_patterns,
)
from midi_analyzer.patterns.fingerprinting import (
    CombinedFingerprint,
    Fingerprinter,
    PitchFingerprint,
    RhythmFingerprint,
    pitch_fingerprint,
    rhythm_fingerprint,
)

__all__ = [
    "BarChunk",
    "BarChunker",
    "chunk_song",
    "chunk_track",
    "CombinedFingerprint",
    "DeduplicationResult",
    "Fingerprinter",
    "PatternCluster",
    "PatternDeduplicator",
    "PatternMatch",
    "PitchFingerprint",
    "RhythmFingerprint",
    "deduplicate_track",
    "find_repeated_patterns",
    "pitch_fingerprint",
    "rhythm_fingerprint",
]
