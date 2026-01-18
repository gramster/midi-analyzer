"""MIDI playback functionality."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from midi_analyzer.analysis.roles import classify_track_role
from midi_analyzer.models.core import Track, TrackRole

if TYPE_CHECKING:
    from midi_analyzer.models.core import Song

# General MIDI instrument mappings by track role
# These are GM program numbers (0-127)
ROLE_INSTRUMENTS: dict[TrackRole, int] = {
    TrackRole.DRUMS: 0,  # Drums use channel 9, program doesn't matter
    TrackRole.BASS: 33,  # Electric Bass (finger)
    TrackRole.CHORDS: 4,  # Electric Piano 1
    TrackRole.PAD: 89,  # Pad 2 (warm)
    TrackRole.LEAD: 80,  # Lead 1 (square)
    TrackRole.ARP: 81,  # Lead 2 (sawtooth)
    TrackRole.OTHER: 0,  # Acoustic Grand Piano
}

# Alternative instrument choices per role for variety
ROLE_INSTRUMENT_ALTERNATIVES: dict[TrackRole, list[int]] = {
    TrackRole.DRUMS: [0],
    TrackRole.BASS: [33, 34, 35, 36, 38, 39],  # Various bass sounds
    TrackRole.CHORDS: [0, 4, 5, 6, 24, 25, 26, 27],  # Piano, guitar
    TrackRole.PAD: [48, 49, 50, 51, 89, 90, 91, 92],  # Strings, pads
    TrackRole.LEAD: [56, 57, 73, 80, 81],  # Trumpet, brass, leads
    TrackRole.ARP: [11, 12, 13, 46, 81],  # Vibes, marimba, harp
    TrackRole.OTHER: [0, 4, 24, 40, 48],  # Various
}


@dataclass
class PlaybackOptions:
    """Options for MIDI playback.

    Attributes:
        tempo_bpm: Playback tempo in BPM.
        transpose: Semitones to transpose.
        velocity_scale: Scale velocities (1.0 = no change).
        loop: Whether to loop playback.
        use_role_instrument: Use instrument based on track role.
        instrument: Override instrument (GM program number 0-127).
    """

    tempo_bpm: float = 120.0
    transpose: int = 0
    velocity_scale: float = 1.0
    loop: bool = False
    use_role_instrument: bool = True
    instrument: int | None = None


def get_instrument_for_role(role: TrackRole, variation: int = 0) -> int:
    """Get a GM instrument number for a track role.

    Args:
        role: Track role.
        variation: Variation index for alternative instruments.

    Returns:
        GM program number (0-127).
    """
    alternatives = ROLE_INSTRUMENT_ALTERNATIVES.get(role, [0])
    return alternatives[variation % len(alternatives)]


def get_instrument_name(program: int) -> str:
    """Get the name of a GM instrument.

    Args:
        program: GM program number (0-127).

    Returns:
        Instrument name.
    """
    # General MIDI instrument names
    names = [
        # Piano (0-7)
        "Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano",
        "Honky-tonk Piano", "Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet",
        # Chromatic Percussion (8-15)
        "Celesta", "Glockenspiel", "Music Box", "Vibraphone",
        "Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
        # Organ (16-23)
        "Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ",
        "Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
        # Guitar (24-31)
        "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)", "Electric Guitar (jazz)",
        "Electric Guitar (clean)", "Electric Guitar (muted)", "Overdriven Guitar",
        "Distortion Guitar", "Guitar Harmonics",
        # Bass (32-39)
        "Acoustic Bass", "Electric Bass (finger)", "Electric Bass (pick)",
        "Fretless Bass", "Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2",
        # Strings (40-47)
        "Violin", "Viola", "Cello", "Contrabass",
        "Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
        # Ensemble (48-55)
        "String Ensemble 1", "String Ensemble 2", "Synth Strings 1", "Synth Strings 2",
        "Choir Aahs", "Voice Oohs", "Synth Voice", "Orchestra Hit",
        # Brass (56-63)
        "Trumpet", "Trombone", "Tuba", "Muted Trumpet",
        "French Horn", "Brass Section", "Synth Brass 1", "Synth Brass 2",
        # Reed (64-71)
        "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
        "Oboe", "English Horn", "Bassoon", "Clarinet",
        # Pipe (72-79)
        "Piccolo", "Flute", "Recorder", "Pan Flute",
        "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina",
        # Synth Lead (80-87)
        "Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)", "Lead 4 (chiff)",
        "Lead 5 (charang)", "Lead 6 (voice)", "Lead 7 (fifths)", "Lead 8 (bass + lead)",
        # Synth Pad (88-95)
        "Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)", "Pad 4 (choir)",
        "Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)",
        # Synth Effects (96-103)
        "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)",
        "FX 5 (brightness)", "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)",
        # Ethnic (104-111)
        "Sitar", "Banjo", "Shamisen", "Koto",
        "Kalimba", "Bagpipe", "Fiddle", "Shanai",
        # Percussive (112-119)
        "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
        "Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal",
        # Sound Effects (120-127)
        "Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
        "Telephone Ring", "Helicopter", "Applause", "Gunshot",
    ]
    if 0 <= program < len(names):
        return names[program]
    return f"Program {program}"


class MidiPlayer:
    """MIDI player using pygame.

    Example:
        player = MidiPlayer()
        player.play_track(track, tempo_bpm=120)
        player.stop()
        player.close()
    """

    def __init__(self) -> None:
        """Initialize the MIDI player."""
        self._initialized = False
        self._midi_out = None
        self._playing = False

    def _ensure_init(self) -> None:
        """Ensure pygame.midi is initialized."""
        if self._initialized:
            return

        try:
            import pygame
            import pygame.midi
        except ImportError as e:
            raise RuntimeError(
                "pygame is required for MIDI playback. Install with: pip install pygame"
            ) from e

        pygame.init()
        pygame.midi.init()

        # Find default output device
        device_id = pygame.midi.get_default_output_id()
        if device_id == -1:
            # Try to find any output device
            for i in range(pygame.midi.get_count()):
                info = pygame.midi.get_device_info(i)
                if info[3] == 1:  # Is output
                    device_id = i
                    break

        if device_id == -1:
            raise RuntimeError("No MIDI output device found")

        self._midi_out = pygame.midi.Output(device_id)
        self._initialized = True

    def close(self) -> None:
        """Close the MIDI player and release resources."""
        if self._midi_out:
            self._midi_out.close()
            self._midi_out = None

        if self._initialized:
            import pygame.midi
            pygame.midi.quit()
            self._initialized = False

    def __enter__(self) -> MidiPlayer:
        """Context manager entry."""
        return self

    def __exit__(self, *args: object) -> None:
        """Context manager exit."""
        self.close()

    def stop(self) -> None:
        """Stop current playback."""
        self._playing = False
        if self._midi_out:
            # All notes off on all channels
            for channel in range(16):
                self._midi_out.write_short(0xB0 | channel, 123, 0)

    def set_instrument(self, channel: int, program: int) -> None:
        """Set the instrument for a channel.

        Args:
            channel: MIDI channel (0-15).
            program: GM program number (0-127).
        """
        self._ensure_init()
        if self._midi_out:
            self._midi_out.set_instrument(program, channel)

    def play_track(
        self,
        track: Track,
        options: PlaybackOptions | None = None,
    ) -> None:
        """Play a single track.

        Args:
            track: Track to play.
            options: Playback options.
        """
        self._ensure_init()
        if not self._midi_out:
            return

        options = options or PlaybackOptions()
        self._playing = True

        # Determine channel and instrument
        role = classify_track_role(track)
        is_drums = role == TrackRole.DRUMS or track.channel == 9

        if is_drums:
            channel = 9  # Drums always on channel 10 (0-indexed: 9)
        else:
            channel = 0

        # Set instrument
        if not is_drums:
            if options.instrument is not None:
                program = options.instrument
            elif options.use_role_instrument:
                program = get_instrument_for_role(role)
            else:
                program = 0
            self._midi_out.set_instrument(program, channel)

        # Calculate timing
        seconds_per_beat = 60.0 / options.tempo_bpm

        # Sort notes by start time
        notes = sorted(track.notes, key=lambda n: n.start_beat)
        if not notes:
            return

        # Normalize start if needed
        start_offset = notes[0].start_beat

        while self._playing:
            current_time = 0.0
            active_notes: list[tuple[float, int]] = []  # (end_time, pitch)

            for note in notes:
                if not self._playing:
                    break

                # Calculate note timing
                note_start = (note.start_beat - start_offset) * seconds_per_beat
                note_end = note_start + (note.duration_beats * seconds_per_beat)

                # Wait until note start
                wait_time = note_start - current_time
                if wait_time > 0:
                    # Check for notes that should end during wait
                    self._process_note_offs(active_notes, current_time, wait_time)
                    time.sleep(wait_time)
                    current_time = note_start

                # Apply transformations
                pitch = note.pitch + options.transpose
                pitch = max(0, min(127, pitch))

                velocity = int(note.velocity * options.velocity_scale)
                velocity = max(1, min(127, velocity))

                # Note on
                self._midi_out.note_on(pitch, velocity, channel)
                active_notes.append((note_end, pitch))

            # Wait for remaining notes to finish
            if active_notes and self._playing:
                max_end = max(end for end, _ in active_notes)
                remaining = max_end - current_time
                if remaining > 0:
                    self._process_note_offs(active_notes, current_time, remaining)
                    time.sleep(remaining)

            # Turn off any remaining notes
            for _, pitch in active_notes:
                self._midi_out.note_off(pitch, 0, channel)

            if not options.loop:
                break

        self._playing = False

    def _process_note_offs(
        self,
        active_notes: list[tuple[float, int]],
        current_time: float,
        wait_duration: float,
    ) -> None:
        """Process note-off events during a wait period."""
        if not self._midi_out:
            return

        end_time = current_time + wait_duration
        elapsed = 0.0

        # Sort by end time
        active_notes.sort(key=lambda x: x[0])

        while active_notes and self._playing:
            next_end, pitch = active_notes[0]
            if next_end > end_time:
                break

            # Wait until this note should end
            wait = next_end - current_time - elapsed
            if wait > 0:
                time.sleep(wait)
                elapsed += wait

            # Note off
            self._midi_out.note_off(pitch, 0, 0)  # Channel 0 for now
            active_notes.pop(0)

    def play_song(
        self,
        song: Song,
        options: PlaybackOptions | None = None,
    ) -> None:
        """Play a complete song.

        Args:
            song: Song to play.
            options: Playback options.
        """
        self._ensure_init()
        if not self._midi_out:
            return

        options = options or PlaybackOptions()
        tempo = options.tempo_bpm or song.primary_tempo

        # Use song's tempo if not overridden
        if options.tempo_bpm == 120.0 and song.primary_tempo != 120.0:
            options = PlaybackOptions(
                tempo_bpm=song.primary_tempo,
                transpose=options.transpose,
                velocity_scale=options.velocity_scale,
                loop=options.loop,
                use_role_instrument=options.use_role_instrument,
                instrument=options.instrument,
            )

        # For now, play tracks sequentially
        # TODO: Implement multi-track playback
        for track in song.tracks:
            if not self._playing:
                break
            if track.notes:
                self.play_track(track, options)


def play_track(
    track: Track,
    tempo_bpm: float = 120.0,
    transpose: int = 0,
    loop: bool = False,
) -> None:
    """Convenience function to play a track.

    Args:
        track: Track to play.
        tempo_bpm: Playback tempo.
        transpose: Semitones to transpose.
        loop: Whether to loop.
    """
    options = PlaybackOptions(
        tempo_bpm=tempo_bpm,
        transpose=transpose,
        loop=loop,
    )

    with MidiPlayer() as player:
        player.play_track(track, options)


def list_midi_devices() -> list[tuple[int, str, bool]]:
    """List available MIDI devices.

    Returns:
        List of (device_id, name, is_output) tuples.
    """
    try:
        import pygame
        import pygame.midi
    except ImportError:
        return []

    pygame.init()
    pygame.midi.init()

    devices = []
    for i in range(pygame.midi.get_count()):
        info = pygame.midi.get_device_info(i)
        name = info[1].decode() if isinstance(info[1], bytes) else str(info[1])
        is_output = bool(info[3])
        devices.append((i, name, is_output))

    pygame.midi.quit()
    return devices


__all__ = [
    "MidiPlayer",
    "PlaybackOptions",
    "ROLE_INSTRUMENT_ALTERNATIVES",
    "ROLE_INSTRUMENTS",
    "get_instrument_for_role",
    "get_instrument_name",
    "list_midi_devices",
    "play_track",
]
