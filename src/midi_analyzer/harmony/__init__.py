"""Harmony, key detection, and chord analysis."""

from midi_analyzer.harmony.chords import (
    Chord,
    ChordEvent,
    ChordProgression,
    ChordQuality,
    detect_chord_progression,
    detect_chord_progression_for_song,
    detect_chord_progression_for_track,
    detect_chords,
    get_common_progressions,
    identify_progression_pattern,
    match_chord,
    smooth_chord_progression,
)
from midi_analyzer.harmony.keys import (
    KeySignature,
    Mode,
    PITCH_CLASSES,
    build_pitch_class_histogram,
    detect_key,
    detect_key_for_song,
    detect_key_for_track,
    get_parallel_key,
    get_relative_key,
    key_to_string,
    string_to_key,
)

__all__ = [
    # Chords
    "Chord",
    "ChordEvent",
    "ChordProgression",
    "ChordQuality",
    "detect_chord_progression",
    "detect_chord_progression_for_song",
    "detect_chord_progression_for_track",
    "detect_chords",
    "get_common_progressions",
    "identify_progression_pattern",
    "match_chord",
    "smooth_chord_progression",
    # Keys
    "KeySignature",
    "Mode",
    "PITCH_CLASSES",
    "build_pitch_class_histogram",
    "detect_key",
    "detect_key_for_song",
    "detect_key_for_track",
    "get_parallel_key",
    "get_relative_key",
    "key_to_string",
    "string_to_key",
]