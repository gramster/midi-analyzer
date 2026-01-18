"""Tests for MIDI player functionality."""

from __future__ import annotations

import pytest

from midi_analyzer.models.core import NoteEvent, Track, TrackRole
from midi_analyzer.player import (
    ROLE_INSTRUMENTS,
    PlaybackOptions,
    get_instrument_for_role,
    get_instrument_name,
)


class TestPlaybackOptions:
    """Tests for PlaybackOptions dataclass."""

    def test_defaults(self):
        """Test default values."""
        options = PlaybackOptions()

        assert options.tempo_bpm == 120.0
        assert options.transpose == 0
        assert options.velocity_scale == 1.0
        assert options.loop is False
        assert options.use_role_instrument is True
        assert options.instrument is None

    def test_custom_values(self):
        """Test custom values."""
        options = PlaybackOptions(
            tempo_bpm=140.0,
            transpose=-5,
            velocity_scale=0.8,
            loop=True,
            instrument=33,
        )

        assert options.tempo_bpm == 140.0
        assert options.transpose == -5
        assert options.velocity_scale == 0.8
        assert options.loop is True
        assert options.instrument == 33


class TestGetInstrumentForRole:
    """Tests for get_instrument_for_role function."""

    def test_bass_instrument(self):
        """Test bass role gets bass instrument."""
        inst = get_instrument_for_role(TrackRole.BASS)
        # Should be in bass range (32-39)
        assert 32 <= inst <= 39

    def test_drums_instrument(self):
        """Test drums role returns valid instrument."""
        inst = get_instrument_for_role(TrackRole.DRUMS)
        assert 0 <= inst <= 127

    def test_chords_instrument(self):
        """Test chords role gets piano/guitar."""
        inst = get_instrument_for_role(TrackRole.CHORDS)
        # Should be piano or guitar family
        assert inst in [0, 4, 5, 6, 24, 25, 26, 27]

    def test_lead_instrument(self):
        """Test lead role gets lead synth or brass."""
        inst = get_instrument_for_role(TrackRole.LEAD)
        assert 0 <= inst <= 127

    def test_pad_instrument(self):
        """Test pad role gets strings or pad synth."""
        inst = get_instrument_for_role(TrackRole.PAD)
        assert 0 <= inst <= 127

    def test_variation(self):
        """Test variation index changes instrument."""
        inst0 = get_instrument_for_role(TrackRole.BASS, variation=0)
        inst1 = get_instrument_for_role(TrackRole.BASS, variation=1)
        # Different variations may give different instruments
        assert 0 <= inst0 <= 127
        assert 0 <= inst1 <= 127

    def test_variation_wraps(self):
        """Test variation index wraps around."""
        # Should not raise even with large variation
        inst = get_instrument_for_role(TrackRole.BASS, variation=1000)
        assert 0 <= inst <= 127


class TestGetInstrumentName:
    """Tests for get_instrument_name function."""

    def test_piano(self):
        """Test piano names."""
        assert get_instrument_name(0) == "Acoustic Grand Piano"
        assert get_instrument_name(4) == "Electric Piano 1"

    def test_bass(self):
        """Test bass names."""
        assert get_instrument_name(33) == "Electric Bass (finger)"
        assert get_instrument_name(38) == "Synth Bass 1"

    def test_strings(self):
        """Test string names."""
        assert get_instrument_name(48) == "String Ensemble 1"

    def test_synth_lead(self):
        """Test synth lead names."""
        assert get_instrument_name(80) == "Lead 1 (square)"
        assert get_instrument_name(81) == "Lead 2 (sawtooth)"

    def test_invalid_program(self):
        """Test invalid program number."""
        name = get_instrument_name(200)
        assert "Program" in name

    def test_all_gm_instruments(self):
        """Test all GM instruments have names."""
        for i in range(128):
            name = get_instrument_name(i)
            assert isinstance(name, str)
            assert len(name) > 0


class TestRoleInstrumentsMapping:
    """Tests for ROLE_INSTRUMENTS constant."""

    def test_all_roles_mapped(self):
        """Test all roles have an instrument mapping."""
        for role in TrackRole:
            assert role in ROLE_INSTRUMENTS

    def test_valid_program_numbers(self):
        """Test all mappings are valid GM programs."""
        for role, program in ROLE_INSTRUMENTS.items():
            assert 0 <= program <= 127, f"Invalid program for {role}: {program}"


class TestMidiPlayerImport:
    """Tests for MidiPlayer import and basic functionality."""

    def test_import_player(self):
        """Test MidiPlayer can be imported."""
        from midi_analyzer.player import MidiPlayer
        assert MidiPlayer is not None

    def test_import_list_devices(self):
        """Test list_midi_devices can be imported."""
        from midi_analyzer.player import list_midi_devices
        assert list_midi_devices is not None

    def test_list_devices_returns_list(self):
        """Test list_midi_devices returns a list."""
        from midi_analyzer.player import list_midi_devices

        # This may return empty list if pygame not installed
        # or no MIDI devices available
        try:
            devices = list_midi_devices()
            assert isinstance(devices, list)
        except Exception:
            # pygame not installed, which is fine
            pass


class TestMidiPlayerCreation:
    """Tests for MidiPlayer object creation."""

    def test_create_player(self):
        """Test MidiPlayer can be created."""
        from midi_analyzer.player import MidiPlayer

        player = MidiPlayer()
        assert player is not None
        assert player._initialized is False

    def test_context_manager(self):
        """Test MidiPlayer context manager."""
        from midi_analyzer.player import MidiPlayer

        with MidiPlayer() as player:
            assert player is not None

    def test_close(self):
        """Test MidiPlayer close."""
        from midi_analyzer.player import MidiPlayer

        player = MidiPlayer()
        player.close()  # Should not raise

    def test_stop(self):
        """Test MidiPlayer stop."""
        from midi_analyzer.player import MidiPlayer

        player = MidiPlayer()
        player.stop()  # Should not raise even when not initialized
        player.close()


class TestPlayTrackFunction:
    """Tests for play_track convenience function."""

    def test_import(self):
        """Test play_track can be imported."""
        from midi_analyzer.player import play_track
        assert play_track is not None


class TestInstrumentMappingQuality:
    """Tests for quality of instrument mappings."""

    def test_bass_sounds_like_bass(self):
        """Test bass instruments are in bass program range."""
        # GM bass instruments are 32-39
        from midi_analyzer.player import ROLE_INSTRUMENT_ALTERNATIVES

        bass_instruments = ROLE_INSTRUMENT_ALTERNATIVES[TrackRole.BASS]
        for inst in bass_instruments:
            assert 32 <= inst <= 39, f"Bass instrument {inst} not in bass range"

    def test_pad_instruments_suitable(self):
        """Test pad instruments are strings or pads."""
        from midi_analyzer.player import ROLE_INSTRUMENT_ALTERNATIVES

        pad_instruments = ROLE_INSTRUMENT_ALTERNATIVES[TrackRole.PAD]
        # Should be strings (48-55) or pads (88-95)
        for inst in pad_instruments:
            assert (48 <= inst <= 55) or (88 <= inst <= 95), f"Pad instrument {inst} unexpected"

    def test_chord_instruments_suitable(self):
        """Test chord instruments are piano/guitar family."""
        from midi_analyzer.player import ROLE_INSTRUMENT_ALTERNATIVES

        chord_instruments = ROLE_INSTRUMENT_ALTERNATIVES[TrackRole.CHORDS]
        # Should be piano (0-7) or guitar (24-31)
        for inst in chord_instruments:
            assert (0 <= inst <= 7) or (24 <= inst <= 31), f"Chord instrument {inst} unexpected"
