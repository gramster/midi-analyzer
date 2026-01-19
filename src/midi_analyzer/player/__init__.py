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


# Default soundfont locations to search
SOUNDFONT_PATHS = [
    "/opt/homebrew/Cellar/fluid-synth/2.5.2/share/fluid-synth/sf2/VintageDreamsWaves-v2.sf2",
    "/opt/homebrew/share/soundfonts/default.sf2",
    "/usr/share/soundfonts/default.sf2",
    "/usr/share/sounds/sf2/FluidR3_GM.sf2",
    "/usr/share/sounds/sf2/TimGM6mb.sf2",
]


def find_soundfont() -> str | None:
    """Find an available soundfont file.
    
    Returns:
        Path to soundfont file, or None if not found.
    """
    import os
    for path in SOUNDFONT_PATHS:
        if os.path.exists(path):
            return path
    return None


class MidiPlayer:
    """MIDI player using FluidSynth for General MIDI playback.

    Example:
        player = MidiPlayer()
        player.play_track(track, tempo_bpm=120)
        player.stop()
        player.close()
    """

    def __init__(self, soundfont: str | None = None) -> None:
        """Initialize the MIDI player.
        
        Args:
            soundfont: Path to soundfont file. If None, searches common locations.
        """
        self._initialized = False
        self._synth = None
        self._sfid = None
        self._playing = False
        self._soundfont = soundfont
        # Position tracking
        self._playback_start_time: float = 0.0
        self._playback_duration: float = 0.0
        self._current_position: float = 0.0

    def _ensure_init(self) -> None:
        """Ensure FluidSynth is initialized."""
        if self._initialized:
            return

        try:
            import fluidsynth
        except ImportError as e:
            raise RuntimeError(
                "pyfluidsynth is required for MIDI playback. "
                "Install with: pip install pyfluidsynth\n"
                "Also ensure FluidSynth is installed: brew install fluid-synth"
            ) from e

        # Find soundfont
        sf_path = self._soundfont or find_soundfont()
        if sf_path is None:
            raise RuntimeError(
                "No soundfont found. Install one or specify path.\n"
                "On macOS: brew install fluid-synth (includes a soundfont)"
            )

        # Initialize synthesizer
        self._synth = fluidsynth.Synth()
        self._synth.start(driver="coreaudio")
        
        # Load soundfont
        self._sfid = self._synth.sfload(sf_path)
        if self._sfid == -1:
            raise RuntimeError(f"Failed to load soundfont: {sf_path}")
        
        # Set up all channels with default instruments
        for channel in range(16):
            if channel == 9:
                # Drums on channel 10 (0-indexed: 9)
                self._synth.program_select(channel, self._sfid, 128, 0)
            else:
                self._synth.program_select(channel, self._sfid, 0, 0)
        
        self._initialized = True

    def close(self) -> None:
        """Close the MIDI player and release resources."""
        if self._synth:
            self._synth.delete()
            self._synth = None
        self._sfid = None
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
        self._current_position = 0.0
        if self._synth:
            # All notes off on all channels
            for channel in range(16):
                self._synth.cc(channel, 123, 0)  # All notes off

    @property
    def is_playing(self) -> bool:
        """Return whether playback is in progress."""
        return self._playing

    @property
    def position(self) -> float:
        """Return current playback position in seconds."""
        if self._playing:
            return time.time() - self._playback_start_time
        return self._current_position

    @property
    def duration(self) -> float:
        """Return total playback duration in seconds."""
        return self._playback_duration

    def set_instrument(self, channel: int, program: int) -> None:
        """Set the instrument for a channel.

        Args:
            channel: MIDI channel (0-15).
            program: GM program number (0-127).
        """
        self._ensure_init()
        if self._synth and self._sfid is not None:
            # For drums (channel 9), use bank 128
            if channel == 9:
                self._synth.program_select(channel, self._sfid, 128, program)
            else:
                self._synth.program_select(channel, self._sfid, 0, program)

    def _note_on(self, pitch: int, velocity: int, channel: int) -> None:
        """Send a note-on message."""
        if self._synth:
            self._synth.noteon(channel, pitch, velocity)

    def _note_off(self, pitch: int, channel: int) -> None:
        """Send a note-off message."""
        if self._synth:
            self._synth.noteoff(channel, pitch)

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
        if not self._synth:
            return

        options = options or PlaybackOptions()
        self._playing = True

        # Determine channel and instrument
        role_probs = classify_track_role(track)
        role = role_probs.primary_role()
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
            self.set_instrument(channel, program)

        # Calculate timing
        seconds_per_beat = 60.0 / options.tempo_bpm

        # Sort notes by start time
        notes = sorted(track.notes, key=lambda n: n.start_beat)
        if not notes:
            return

        # Normalize start if needed
        start_offset = notes[0].start_beat
        
        # Calculate and store duration
        max_end_beat = max(n.start_beat + n.duration_beats for n in notes) - start_offset
        self._playback_duration = max_end_beat * seconds_per_beat
        self._playback_start_time = time.time()

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
                self._note_on(pitch, velocity, channel)
                active_notes.append((note_end, pitch))

            # Wait for remaining notes to finish
            if active_notes and self._playing:
                max_end = max(end for end, _ in active_notes)
                remaining = max_end - current_time
                if remaining > 0:
                    self._process_note_offs(active_notes, current_time, remaining, channel)
                    time.sleep(remaining)

            # Turn off any remaining notes
            for _, pitch in active_notes:
                self._note_off(pitch, channel)

            if not options.loop:
                break

        self._playing = False

    def _process_note_offs(
        self,
        active_notes: list[tuple[float, int]],
        current_time: float,
        wait_duration: float,
        channel: int = 0,
    ) -> None:
        """Process note-off events during a wait period."""
        if not self._synth:
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
            self._note_off(pitch, channel)
            active_notes.pop(0)

    def play_song(
        self,
        song: Song,
        options: PlaybackOptions | None = None,
    ) -> None:
        """Play a complete song with all tracks simultaneously.

        Args:
            song: Song to play.
            options: Playback options.
        """
        self._ensure_init()
        if not self._synth:
            return

        options = options or PlaybackOptions()

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

        self._playing = True
        seconds_per_beat = 60.0 / options.tempo_bpm

        # Assign channels and set instruments for each track
        track_channels: dict[int, int] = {}
        next_channel = 0
        
        for track in song.tracks:
            if not track.notes:
                continue
                
            role_probs = classify_track_role(track)
            role = role_probs.primary_role()
            is_drums = role == TrackRole.DRUMS or track.channel == 9
            
            if is_drums:
                channel = 9
            else:
                channel = next_channel
                if next_channel == 9:
                    next_channel = 10  # Skip drum channel
                else:
                    next_channel += 1
                if next_channel > 15:
                    next_channel = 0  # Wrap around (reuse channels if needed)
            
            track_channels[track.track_id] = channel
            
            # Set instrument
            if not is_drums:
                if options.instrument is not None:
                    program = options.instrument
                elif options.use_role_instrument:
                    program = get_instrument_for_role(role)
                else:
                    program = 0
                self.set_instrument(channel, program)

        # Collect all notes from all tracks with their timing and channel
        all_events: list[tuple[float, str, int, int, int, int]] = []  # (time, type, pitch, velocity, channel, track_id)
        
        min_start = float('inf')
        for track in song.tracks:
            if not track.notes or track.track_id not in track_channels:
                continue
            channel = track_channels[track.track_id]
            for note in track.notes:
                start_time = note.start_beat * seconds_per_beat
                end_time = (note.start_beat + note.duration_beats) * seconds_per_beat
                
                pitch = note.pitch + options.transpose
                pitch = max(0, min(127, pitch))
                
                velocity = int(note.velocity * options.velocity_scale)
                velocity = max(1, min(127, velocity))
                
                all_events.append((start_time, 'on', pitch, velocity, channel, track.track_id))
                all_events.append((end_time, 'off', pitch, 0, channel, track.track_id))
                
                if start_time < min_start:
                    min_start = start_time

        if not all_events:
            return

        # Normalize times (start from 0)
        if min_start > 0:
            all_events = [(t - min_start, typ, p, v, c, tid) for t, typ, p, v, c, tid in all_events]

        # Sort by time, with note-offs before note-ons at same time
        all_events.sort(key=lambda e: (e[0], 0 if e[1] == 'off' else 1))

        # Calculate and store duration
        self._playback_duration = max(e[0] for e in all_events) if all_events else 0.0
        self._playback_start_time = time.time()

        # Play all events
        current_time = 0.0
        
        while self._playing:
            for event_time, event_type, pitch, velocity, channel, _ in all_events:
                if not self._playing:
                    break
                
                # Wait until this event
                wait_time = event_time - current_time
                if wait_time > 0:
                    time.sleep(wait_time)
                    current_time = event_time
                
                if event_type == 'on':
                    self._note_on(pitch, velocity, channel)
                else:
                    self._note_off(pitch, channel)
            
            if not options.loop:
                break
            
            # Reset for loop
            current_time = 0.0
            # Turn off all notes before looping
            for channel in range(16):
                if self._synth:
                    self._synth.cc(channel, 123, 0)

        self._playing = False


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
    # With FluidSynth, we use built-in synthesis, so no external MIDI devices needed
    # But we can still list available audio drivers
    devices = []
    try:
        import fluidsynth
        # FluidSynth uses audio drivers, not MIDI devices
        devices.append((0, "FluidSynth (coreaudio)", True))
    except ImportError:
        pass
    return devices


__all__ = [
    "MidiPlayer",
    "PlaybackOptions",
    "ROLE_INSTRUMENT_ALTERNATIVES",
    "ROLE_INSTRUMENTS",
    "SOUNDFONT_PATHS",
    "find_soundfont",
    "get_instrument_for_role",
    "get_instrument_name",
    "list_midi_devices",
    "play_track",
]
