"""Tests for pattern models."""


from midi_analyzer.models.core import TrackRole
from midi_analyzer.models.patterns import (
    ArpPattern,
    DrumPattern,
    MelodicEvent,
    MelodicPattern,
    Pattern,
    PatternHit,
    PatternInstance,
    PitchFingerprint,
    RhythmFingerprint,
)


class TestDrumPattern:
    """Tests for DrumPattern."""

    def test_basic_pattern(self) -> None:
        """Test creating a basic drum pattern."""
        pattern = DrumPattern(
            steps_per_bar=16,
            hits=[
                PatternHit(step=0, pitch=36, velocity=110),
                PatternHit(step=4, pitch=38, velocity=90),
                PatternHit(step=8, pitch=36, velocity=100),
                PatternHit(step=12, pitch=38, velocity=85),
            ],
        )
        assert len(pattern.hits) == 4
        assert pattern.steps_per_bar == 16

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        pattern = DrumPattern(
            steps_per_bar=16,
            length_bars=1,
            hits=[PatternHit(step=0, pitch=36, velocity=110)],
        )
        d = pattern.to_dict()
        assert d["stepsPerBar"] == 16
        assert d["lengthBars"] == 1
        assert len(d["hits"]) == 1
        assert d["hits"][0]["step"] == 0


class TestMelodicPattern:
    """Tests for MelodicPattern."""

    def test_basic_pattern(self) -> None:
        """Test creating a basic melodic pattern."""
        pattern = MelodicPattern(
            steps_per_bar=16,
            events=[
                MelodicEvent(step=0, interval=0, duration=4),
                MelodicEvent(step=4, interval=3, duration=4),
                MelodicEvent(step=8, interval=7, duration=8),
            ],
        )
        assert len(pattern.events) == 3

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        pattern = MelodicPattern(
            steps_per_bar=16,
            events=[MelodicEvent(step=0, interval=0, duration=4)],
        )
        d = pattern.to_dict()
        assert d["stepsPerBar"] == 16
        assert d["events"][0]["interval"] == 0


class TestArpPattern:
    """Tests for ArpPattern."""

    def test_basic_arp(self) -> None:
        """Test creating a basic arp pattern."""
        arp = ArpPattern(
            rate="1/16",
            interval_sequence=[0, 4, 7, 12],
            octave_jumps=[0, 0, 0, 1],
            gate=0.75,
        )
        assert arp.rate == "1/16"
        assert len(arp.interval_sequence) == 4

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        arp = ArpPattern(
            rate="1/8",
            interval_sequence=[0, 7],
            octave_jumps=[0, 0],
        )
        d = arp.to_dict()
        assert d["rate"] == "1/8"
        assert d["interval_sequence"] == [0, 7]


class TestFingerprints:
    """Tests for fingerprint classes."""

    def test_rhythm_fingerprint_hash(self) -> None:
        """Test rhythm fingerprint hashing."""
        fp = RhythmFingerprint(
            onset_grid=[1.0, 0.0, 0.5, 0.0, 1.0, 0.0, 0.0, 0.0],
            accent_profile=[1.0, 0.0, 0.5, 0.0, 0.8, 0.0, 0.0, 0.0],
            density=0.375,
        )
        hash_str = fp.to_hash()
        # 1.0 > 0.1 = 1, 0.0 = 0, 0.5 > 0.1 = 1, 0.0 = 0, 1.0 = 1, rest = 0
        assert hash_str == "10101000"

    def test_pitch_fingerprint_hash(self) -> None:
        """Test pitch fingerprint hashing."""
        fp = PitchFingerprint(
            interval_sequence=[0, 3, -2, 5],
            contour=[1, -1, 1],  # up, down, up
            pitch_classes={0, 3, 5, 7},
        )
        hash_str = fp.to_hash()
        assert hash_str == "UDU"


class TestPattern:
    """Tests for Pattern."""

    def test_combo_fingerprint(self) -> None:
        """Test combined fingerprint generation."""
        pattern = Pattern(
            pattern_id="test-001",
            role=TrackRole.BASS,
            length_bars=1,
            meter="4/4",
            grid_resolution=16,
            rhythm_fp=RhythmFingerprint(
                onset_grid=[1.0, 0.0, 0.0, 0.0],
                accent_profile=[1.0, 0.0, 0.0, 0.0],
                density=0.25,
            ),
            pitch_fp=PitchFingerprint(
                interval_sequence=[0, 5],
                contour=[1],
                pitch_classes={0, 5},
            ),
        )
        combo = pattern.combo_fingerprint
        assert ":" in combo  # Format is "rhythm:pitch"


class TestPatternInstance:
    """Tests for PatternInstance."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        instance = PatternInstance(
            pattern_id="test-001",
            song_id="song-abc",
            track_id=2,
            start_bar=16,
            confidence=0.95,
            transform={"transposition": 5},
        )
        d = instance.to_dict()
        assert d["pattern_id"] == "test-001"
        assert d["song_id"] == "song-abc"
        assert d["confidence"] == 0.95
        assert d["transform"]["transposition"] == 5
