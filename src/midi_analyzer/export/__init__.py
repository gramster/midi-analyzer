"""MIDI export functionality for tracks and clips."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import mido

from midi_analyzer.models.core import NoteEvent, Song, TempoEvent, TimeSignature, Track

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class ExportOptions:
    """Options for MIDI export.

    Attributes:
        include_tempo: Include tempo events in export.
        include_time_sig: Include time signature events.
        normalize_start: Shift notes so first note starts at beat 0.
        velocity_scale: Scale velocities (1.0 = no change).
        transpose: Semitones to transpose (0 = no change).
        quantize: Quantize to grid (None = no quantization).
    """

    include_tempo: bool = True
    include_time_sig: bool = True
    normalize_start: bool = True
    velocity_scale: float = 1.0
    transpose: int = 0
    quantize: int | None = None


def export_track(
    track: Track,
    output_path: Path | str,
    *,
    ticks_per_beat: int = 480,
    tempo_bpm: float = 120.0,
    time_sig: tuple[int, int] = (4, 4),
    options: ExportOptions | None = None,
) -> Path:
    """Export a single track to a MIDI file.

    Args:
        track: Track to export.
        output_path: Path for the output MIDI file.
        ticks_per_beat: MIDI resolution (PPQ).
        tempo_bpm: Tempo in beats per minute.
        time_sig: Time signature as (numerator, denominator).
        options: Export options.

    Returns:
        Path to the created file.
    """
    options = options or ExportOptions()
    output_path = Path(output_path)

    # Create MIDI file
    midi = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    midi_track = mido.MidiTrack()
    midi.tracks.append(midi_track)

    # Add track name
    if track.name:
        midi_track.append(mido.MetaMessage("track_name", name=track.name, time=0))

    # Add tempo if requested
    if options.include_tempo:
        tempo_us = int(60_000_000 / tempo_bpm)
        midi_track.append(mido.MetaMessage("set_tempo", tempo=tempo_us, time=0))

    # Add time signature if requested
    if options.include_time_sig:
        midi_track.append(
            mido.MetaMessage(
                "time_signature",
                numerator=time_sig[0],
                denominator=time_sig[1],
                time=0,
            )
        )

    # Process notes
    notes = list(track.notes)
    if not notes:
        # Empty track - just save with metadata
        midi_track.append(mido.MetaMessage("end_of_track", time=0))
        midi.save(output_path)
        return output_path

    # Apply transformations
    notes = _apply_transformations(notes, ticks_per_beat, options)

    # Convert to MIDI events
    events = _notes_to_midi_events(notes, ticks_per_beat, track.channel)

    # Add events to track
    for event in events:
        midi_track.append(event)

    # End of track
    midi_track.append(mido.MetaMessage("end_of_track", time=0))

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(output_path)

    return output_path


def export_tracks(
    tracks: Sequence[Track],
    output_path: Path | str,
    *,
    ticks_per_beat: int = 480,
    tempo_bpm: float = 120.0,
    time_sig: tuple[int, int] = (4, 4),
    options: ExportOptions | None = None,
) -> Path:
    """Export multiple tracks to a single MIDI file.

    Args:
        tracks: Tracks to export.
        output_path: Path for the output MIDI file.
        ticks_per_beat: MIDI resolution (PPQ).
        tempo_bpm: Tempo in beats per minute.
        time_sig: Time signature as (numerator, denominator).
        options: Export options.

    Returns:
        Path to the created file.
    """
    options = options or ExportOptions()
    output_path = Path(output_path)

    # Create MIDI file (Type 1 - multi-track)
    midi = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)

    # Create tempo track
    tempo_track = mido.MidiTrack()
    midi.tracks.append(tempo_track)

    if options.include_tempo:
        tempo_us = int(60_000_000 / tempo_bpm)
        tempo_track.append(mido.MetaMessage("set_tempo", tempo=tempo_us, time=0))

    if options.include_time_sig:
        tempo_track.append(
            mido.MetaMessage(
                "time_signature",
                numerator=time_sig[0],
                denominator=time_sig[1],
                time=0,
            )
        )

    tempo_track.append(mido.MetaMessage("end_of_track", time=0))

    # Add each track
    for track in tracks:
        midi_track = mido.MidiTrack()
        midi.tracks.append(midi_track)

        if track.name:
            midi_track.append(mido.MetaMessage("track_name", name=track.name, time=0))

        notes = list(track.notes)
        if notes:
            notes = _apply_transformations(notes, ticks_per_beat, options)
            events = _notes_to_midi_events(notes, ticks_per_beat, track.channel)
            for event in events:
                midi_track.append(event)

        midi_track.append(mido.MetaMessage("end_of_track", time=0))

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(output_path)

    return output_path


def export_song(
    song: Song,
    output_path: Path | str,
    *,
    options: ExportOptions | None = None,
) -> Path:
    """Export a complete song to MIDI.

    Args:
        song: Song to export.
        output_path: Path for the output MIDI file.
        options: Export options.

    Returns:
        Path to the created file.
    """
    options = options or ExportOptions()
    tempo_bpm = song.primary_tempo
    time_sig = song.primary_time_sig

    # Don't normalize start for full song exports
    song_options = ExportOptions(
        include_tempo=options.include_tempo,
        include_time_sig=options.include_time_sig,
        normalize_start=False,  # Keep original timing
        velocity_scale=options.velocity_scale,
        transpose=options.transpose,
        quantize=options.quantize,
    )

    return export_tracks(
        song.tracks,
        output_path,
        ticks_per_beat=song.ticks_per_beat,
        tempo_bpm=tempo_bpm,
        time_sig=time_sig,
        options=song_options,
    )


def extract_clip(
    track: Track,
    start_bar: int,
    end_bar: int,
    *,
    beats_per_bar: float = 4.0,
) -> Track:
    """Extract a clip (portion) from a track.

    Args:
        track: Source track.
        start_bar: Starting bar (0-indexed).
        end_bar: Ending bar (exclusive).
        beats_per_bar: Beats per bar for calculation.

    Returns:
        New track containing only notes within the specified range.
    """
    start_beat = start_bar * beats_per_bar
    end_beat = end_bar * beats_per_bar

    # Filter notes within range
    clip_notes = []
    for note in track.notes:
        if start_beat <= note.start_beat < end_beat:
            # Shift note timing to start from 0
            shifted_note = NoteEvent(
                pitch=note.pitch,
                velocity=note.velocity,
                start_beat=note.start_beat - start_beat,
                duration_beats=note.duration_beats,
                track_id=note.track_id,
                channel=note.channel,
                start_tick=0,  # Will be recalculated on export
                bar=note.bar - start_bar,
                beat_in_bar=note.beat_in_bar,
            )
            clip_notes.append(shifted_note)

    return Track(
        track_id=track.track_id,
        name=f"{track.name} (bars {start_bar}-{end_bar})" if track.name else f"Clip bars {start_bar}-{end_bar}",
        channel=track.channel,
        notes=clip_notes,
        features=None,  # Would need recalculation
        role_probs=track.role_probs,
    )


def _apply_transformations(
    notes: list[NoteEvent],
    ticks_per_beat: int,
    options: ExportOptions,
) -> list[NoteEvent]:
    """Apply export transformations to notes."""
    if not notes:
        return notes

    result = []
    offset = notes[0].start_beat if options.normalize_start else 0.0

    for note in notes:
        pitch = note.pitch + options.transpose
        pitch = max(0, min(127, pitch))  # Clamp to valid range

        velocity = int(note.velocity * options.velocity_scale)
        velocity = max(1, min(127, velocity))  # Clamp to valid range

        start_beat = note.start_beat - offset
        duration_beats = note.duration_beats

        # Apply quantization if requested
        if options.quantize:
            grid = 4.0 / options.quantize  # Convert grid to beats
            start_beat = round(start_beat / grid) * grid
            duration_beats = max(grid, round(duration_beats / grid) * grid)

        result.append(
            NoteEvent(
                pitch=pitch,
                velocity=velocity,
                start_beat=start_beat,
                duration_beats=duration_beats,
                track_id=note.track_id,
                channel=note.channel,
            )
        )

    return result


def _notes_to_midi_events(
    notes: list[NoteEvent],
    ticks_per_beat: int,
    channel: int,
) -> list[mido.Message]:
    """Convert note events to MIDI messages with delta times."""
    if not notes:
        return []

    # Create note on/off events
    events: list[tuple[int, str, int, int]] = []  # (tick, type, pitch, velocity)

    for note in notes:
        start_tick = int(note.start_beat * ticks_per_beat)
        end_tick = int((note.start_beat + note.duration_beats) * ticks_per_beat)

        events.append((start_tick, "note_on", note.pitch, note.velocity))
        events.append((end_tick, "note_off", note.pitch, 0))

    # Sort by time
    events.sort(key=lambda e: (e[0], 0 if e[1] == "note_off" else 1))

    # Convert to MIDI messages with delta times
    messages = []
    last_tick = 0

    for tick, msg_type, pitch, velocity in events:
        delta = tick - last_tick
        messages.append(
            mido.Message(msg_type, note=pitch, velocity=velocity, channel=channel, time=delta)
        )
        last_tick = tick

    return messages


# Convenience aliases
__all__ = [
    "ExportOptions",
    "export_track",
    "export_tracks",
    "export_song",
    "extract_clip",
]
