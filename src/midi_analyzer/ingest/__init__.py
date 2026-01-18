"""MIDI file ingestion and normalization."""

from pathlib import Path

from midi_analyzer.ingest.metadata import MetadataExtractor
from midi_analyzer.ingest.parser import MidiParser
from midi_analyzer.ingest.timing import (
    SwingAnalysis,
    SwingStyle,
    TimingResolver,
    detect_song_swing,
    detect_swing,
)
from midi_analyzer.models.core import Song


def parse_midi_file(file_path: Path | str) -> Song:
    """Convenience function to parse a MIDI file.

    Args:
        file_path: Path to the MIDI file.

    Returns:
        Parsed Song object.
    """
    parser = MidiParser()
    return parser.parse_file(file_path)


__all__ = [
    "MidiParser",
    "TimingResolver",
    "MetadataExtractor",
    "SwingStyle",
    "SwingAnalysis",
    "detect_swing",
    "detect_song_swing",
    "parse_midi_file",
]
