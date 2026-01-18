"""MIDI file parser using mido library."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import mido

from midi_analyzer.models.core import (
    NoteEvent,
    Song,
    TempoEvent,
    TimeSignature,
    Track,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


# Default MIDI tempo (120 BPM = 500000 microseconds per beat)
DEFAULT_TEMPO = 500000
DEFAULT_TICKS_PER_BEAT = 480


class MidiParser:
    """Parser for MIDI files using mido library.

    Handles both Type 0 (single track) and Type 1 (multi-track) MIDI files.
    Extracts note events, tempo changes, and time signature changes.
    """

    def __init__(self, quantize_grid: int = 16) -> None:
        """Initialize the parser.

        Args:
            quantize_grid: Grid resolution for quantization (e.g., 16 for 16th notes).
        """
        self.quantize_grid = quantize_grid

    def parse_file(self, file_path: Path | str) -> Song:
        """Parse a MIDI file and return a Song object.

        Args:
            file_path: Path to the MIDI file.

        Returns:
            Song object with all extracted data.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the file is not a valid MIDI file.
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"MIDI file not found: {file_path}")

        try:
            midi_file = mido.MidiFile(file_path)
        except Exception as e:
            raise ValueError(f"Failed to parse MIDI file: {e}") from e

        # Generate song ID from file path
        song_id = self._generate_song_id(file_path)

        # Extract tempo and time signature maps
        tempo_map = self._extract_tempo_map(midi_file)
        time_sig_map = self._extract_time_sig_map(midi_file)

        # Extract tracks with notes
        tracks = self._extract_tracks(midi_file, tempo_map, time_sig_map)

        # Calculate total duration
        total_beats = self._calculate_total_beats(midi_file, tempo_map)
        total_bars = self._calculate_total_bars(total_beats, time_sig_map)

        return Song(
            song_id=song_id,
            source_path=str(file_path),
            ticks_per_beat=midi_file.ticks_per_beat or DEFAULT_TICKS_PER_BEAT,
            tempo_map=tempo_map,
            time_sig_map=time_sig_map,
            tracks=tracks,
            total_bars=total_bars,
            total_beats=total_beats,
        )

    def _generate_song_id(self, file_path: Path) -> str:
        """Generate a unique song ID from the file path."""
        path_str = str(file_path.resolve())
        return hashlib.md5(path_str.encode()).hexdigest()[:12]

    def _extract_tempo_map(self, midi_file: mido.MidiFile) -> list[TempoEvent]:
        """Extract all tempo changes from the MIDI file."""
        tempo_events: list[TempoEvent] = []
        ticks_per_beat = midi_file.ticks_per_beat or DEFAULT_TICKS_PER_BEAT

        # Track cumulative ticks and beats
        current_tick = 0
        current_beat = 0.0
        current_tempo = DEFAULT_TEMPO

        # For Type 0 files, all events are in track 0
        # For Type 1 files, tempo events are typically in track 0 (conductor track)
        for track in midi_file.tracks:
            tick = 0
            for msg in track:
                tick += msg.time
                if msg.type == "set_tempo":
                    # Calculate beat position based on tempo up to this point
                    if tempo_events:
                        # Ticks since last tempo change
                        delta_ticks = tick - current_tick
                        delta_beats = delta_ticks / ticks_per_beat
                        current_beat += delta_beats

                    tempo_bpm = mido.tempo2bpm(msg.tempo)
                    tempo_events.append(
                        TempoEvent(
                            tick=tick,
                            beat=current_beat,
                            tempo_bpm=tempo_bpm,
                            microseconds_per_beat=msg.tempo,
                        )
                    )
                    current_tick = tick
                    current_tempo = msg.tempo
            # Only process first track for tempo (Type 1 convention)
            if midi_file.type == 1:
                break

        # If no tempo events found, add default tempo
        if not tempo_events:
            tempo_events.append(
                TempoEvent(
                    tick=0,
                    beat=0.0,
                    tempo_bpm=120.0,
                    microseconds_per_beat=DEFAULT_TEMPO,
                )
            )

        return tempo_events

    def _extract_time_sig_map(self, midi_file: mido.MidiFile) -> list[TimeSignature]:
        """Extract all time signature changes from the MIDI file."""
        time_sigs: list[TimeSignature] = []
        ticks_per_beat = midi_file.ticks_per_beat or DEFAULT_TICKS_PER_BEAT

        current_tick = 0
        current_beat = 0.0
        current_bar = 0

        for track in midi_file.tracks:
            tick = 0
            for msg in track:
                tick += msg.time
                if msg.type == "time_signature":
                    # Calculate position
                    if time_sigs:
                        last_ts = time_sigs[-1]
                        delta_ticks = tick - current_tick
                        delta_beats = delta_ticks / ticks_per_beat
                        current_beat += delta_beats
                        # Calculate bars passed
                        bars_passed = int(delta_beats / last_ts.beats_per_bar)
                        current_bar += bars_passed

                    time_sigs.append(
                        TimeSignature(
                            tick=tick,
                            beat=current_beat,
                            bar=current_bar,
                            numerator=msg.numerator,
                            denominator=msg.denominator,
                        )
                    )
                    current_tick = tick

            # Only process first track for time sigs (Type 1 convention)
            if midi_file.type == 1:
                break

        # If no time signature found, add default 4/4
        if not time_sigs:
            time_sigs.append(
                TimeSignature(
                    tick=0,
                    beat=0.0,
                    bar=0,
                    numerator=4,
                    denominator=4,
                )
            )

        return time_sigs

    def _extract_tracks(
        self,
        midi_file: mido.MidiFile,
        tempo_map: list[TempoEvent],
        time_sig_map: list[TimeSignature],
    ) -> list[Track]:
        """Extract all tracks with their note events."""
        tracks: list[Track] = []
        ticks_per_beat = midi_file.ticks_per_beat or DEFAULT_TICKS_PER_BEAT

        for track_idx, midi_track in enumerate(midi_file.tracks):
            track_name = self._get_track_name(midi_track)
            notes = list(
                self._extract_notes(
                    midi_track,
                    track_idx,
                    ticks_per_beat,
                    tempo_map,
                    time_sig_map,
                )
            )

            # Skip empty tracks
            if not notes:
                continue

            # Determine primary channel
            channel = self._get_primary_channel(notes)

            tracks.append(
                Track(
                    track_id=track_idx,
                    name=track_name,
                    channel=channel,
                    notes=notes,
                )
            )

        return tracks

    def _get_track_name(self, track: mido.MidiTrack) -> str:
        """Extract track name from MIDI track."""
        for msg in track:
            if msg.type == "track_name":
                return msg.name
        return ""

    def _extract_notes(
        self,
        track: mido.MidiTrack,
        track_id: int,
        ticks_per_beat: int,
        tempo_map: list[TempoEvent],
        time_sig_map: list[TimeSignature],
    ) -> Iterator[NoteEvent]:
        """Extract note events from a MIDI track."""
        # Track active notes (pitch -> (start_tick, velocity, channel))
        active_notes: dict[tuple[int, int], tuple[int, int]] = {}

        current_tick = 0
        for msg in track:
            current_tick += msg.time

            if msg.type == "note_on" and msg.velocity > 0:
                # Note on
                key = (msg.note, msg.channel)
                active_notes[key] = (current_tick, msg.velocity)

            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                # Note off
                key = (msg.note, msg.channel)
                if key in active_notes:
                    start_tick, velocity = active_notes.pop(key)
                    duration_ticks = current_tick - start_tick

                    # Convert to beat-based timing
                    start_beat = start_tick / ticks_per_beat
                    duration_beats = duration_ticks / ticks_per_beat

                    # Calculate bar and beat position
                    bar, beat_in_bar = self._tick_to_bar_beat(
                        start_tick, ticks_per_beat, time_sig_map
                    )

                    yield NoteEvent(
                        pitch=msg.note,
                        velocity=velocity,
                        start_beat=start_beat,
                        duration_beats=duration_beats,
                        track_id=track_id,
                        channel=msg.channel,
                        start_tick=start_tick,
                        bar=bar,
                        beat_in_bar=beat_in_bar,
                    )

    def _tick_to_bar_beat(
        self,
        tick: int,
        ticks_per_beat: int,
        time_sig_map: list[TimeSignature],
    ) -> tuple[int, float]:
        """Convert tick position to bar and beat-within-bar."""
        beat = tick / ticks_per_beat

        # Find the active time signature
        active_ts = time_sig_map[0]
        for ts in time_sig_map:
            if ts.beat <= beat:
                active_ts = ts
            else:
                break

        # Calculate bar number and beat within bar
        beats_since_ts = beat - active_ts.beat
        bars_since_ts = int(beats_since_ts / active_ts.beats_per_bar)
        beat_in_bar = beats_since_ts - (bars_since_ts * active_ts.beats_per_bar)

        bar = active_ts.bar + bars_since_ts

        return bar, beat_in_bar

    def _get_primary_channel(self, notes: list[NoteEvent]) -> int:
        """Determine the most common MIDI channel in a list of notes."""
        if not notes:
            return 0

        channel_counts: dict[int, int] = {}
        for note in notes:
            channel_counts[note.channel] = channel_counts.get(note.channel, 0) + 1

        return max(channel_counts, key=channel_counts.get)  # type: ignore[arg-type]

    def _calculate_total_beats(
        self, midi_file: mido.MidiFile, tempo_map: list[TempoEvent]
    ) -> float:
        """Calculate the total duration in beats."""
        ticks_per_beat = midi_file.ticks_per_beat or DEFAULT_TICKS_PER_BEAT

        # Find the maximum tick across all tracks
        max_tick = 0
        for track in midi_file.tracks:
            tick = 0
            for msg in track:
                tick += msg.time
            max_tick = max(max_tick, tick)

        return max_tick / ticks_per_beat

    def _calculate_total_bars(
        self, total_beats: float, time_sig_map: list[TimeSignature]
    ) -> int:
        """Calculate the total number of bars."""
        if not time_sig_map:
            return int(total_beats / 4)  # Default 4/4

        # Use the last time signature to estimate remaining bars
        last_ts = time_sig_map[-1]
        beats_after_last_ts = total_beats - last_ts.beat
        bars_after_last_ts = int(beats_after_last_ts / last_ts.beats_per_bar) + 1

        return last_ts.bar + bars_after_last_ts


def parse_midi(file_path: Path | str, quantize_grid: int = 16) -> Song:
    """Convenience function to parse a MIDI file.

    Args:
        file_path: Path to the MIDI file.
        quantize_grid: Grid resolution for quantization.

    Returns:
        Song object with all extracted data.
    """
    parser = MidiParser(quantize_grid=quantize_grid)
    return parser.parse_file(file_path)
