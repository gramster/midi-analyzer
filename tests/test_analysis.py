"""Tests for track analysis modules."""

import pytest

from midi_analyzer.models.core import NoteEvent, Track, TrackFeatures, TrackRole
from midi_analyzer.analysis.features import FeatureExtractor, extract_track_features
from midi_analyzer.analysis.roles import RoleClassifier, classify_track_role


class TestFeatureExtractor:
    """Tests for the feature extractor."""

    def test_empty_track(self) -> None:
        """Test feature extraction from empty track."""
        track = Track(track_id=0, notes=[])
        extractor = FeatureExtractor()
        features = extractor.extract_features(track, total_bars=16)

        assert features.note_count == 0
        assert features.note_density == 0.0

    def test_basic_features(self) -> None:
        """Test basic feature extraction."""
        notes = [
            NoteEvent(pitch=60, velocity=100, start_beat=0.0, duration_beats=1.0, track_id=0, channel=0, bar=0),
            NoteEvent(pitch=64, velocity=90, start_beat=1.0, duration_beats=1.0, track_id=0, channel=0, bar=0),
            NoteEvent(pitch=67, velocity=80, start_beat=2.0, duration_beats=1.0, track_id=0, channel=0, bar=0),
            NoteEvent(pitch=72, velocity=70, start_beat=3.0, duration_beats=1.0, track_id=0, channel=0, bar=0),
        ]
        track = Track(track_id=0, notes=notes)
        features = extract_track_features(track, total_bars=4)

        assert features.note_count == 4
        assert features.note_density == 1.0  # 4 notes / 4 bars
        assert features.pitch_min == 60
        assert features.pitch_max == 72
        assert features.pitch_range == 12
        assert features.avg_velocity == 85.0  # (100+90+80+70)/4
        assert features.avg_duration == 1.0

    def test_polyphony_detection(self) -> None:
        """Test polyphony ratio calculation."""
        # Overlapping notes (chord)
        notes = [
            NoteEvent(pitch=60, velocity=100, start_beat=0.0, duration_beats=2.0, track_id=0, channel=0, bar=0),
            NoteEvent(pitch=64, velocity=100, start_beat=0.0, duration_beats=2.0, track_id=0, channel=0, bar=0),
            NoteEvent(pitch=67, velocity=100, start_beat=0.0, duration_beats=2.0, track_id=0, channel=0, bar=0),
        ]
        track = Track(track_id=0, notes=notes)
        features = extract_track_features(track, total_bars=1)

        # All notes overlap, so polyphony should be high
        assert features.polyphony_ratio > 0.5

    def test_monophonic_track(self) -> None:
        """Test monophonic track detection."""
        # Sequential non-overlapping notes
        notes = [
            NoteEvent(pitch=60, velocity=100, start_beat=0.0, duration_beats=0.5, track_id=0, channel=0, bar=0),
            NoteEvent(pitch=64, velocity=100, start_beat=1.0, duration_beats=0.5, track_id=0, channel=0, bar=0),
            NoteEvent(pitch=67, velocity=100, start_beat=2.0, duration_beats=0.5, track_id=0, channel=0, bar=0),
        ]
        track = Track(track_id=0, notes=notes)
        features = extract_track_features(track, total_bars=1)

        assert features.polyphony_ratio == 0.0

    def test_drum_channel_detection(self) -> None:
        """Test channel 10 detection for drums."""
        notes = [
            NoteEvent(pitch=36, velocity=100, start_beat=0.0, duration_beats=0.1, track_id=0, channel=9, bar=0),
            NoteEvent(pitch=38, velocity=100, start_beat=1.0, duration_beats=0.1, track_id=0, channel=9, bar=0),
        ]
        track = Track(track_id=0, notes=notes, channel=9)
        features = extract_track_features(track, total_bars=1)

        assert features.is_channel_10 is True

    def test_syncopation_on_beat(self) -> None:
        """Test syncopation for on-beat notes."""
        # Notes on strong beats
        notes = [
            NoteEvent(pitch=60, velocity=100, start_beat=0.0, duration_beats=0.5, track_id=0, channel=0, bar=0),
            NoteEvent(pitch=60, velocity=100, start_beat=1.0, duration_beats=0.5, track_id=0, channel=0, bar=0),
            NoteEvent(pitch=60, velocity=100, start_beat=2.0, duration_beats=0.5, track_id=0, channel=0, bar=0),
            NoteEvent(pitch=60, velocity=100, start_beat=3.0, duration_beats=0.5, track_id=0, channel=0, bar=0),
        ]
        track = Track(track_id=0, notes=notes)
        features = extract_track_features(track, total_bars=1)

        assert features.syncopation_score == 0.0

    def test_pitch_class_entropy(self) -> None:
        """Test pitch class entropy calculation."""
        # Single pitch class - low entropy
        notes_single = [
            NoteEvent(pitch=60, velocity=100, start_beat=float(i), duration_beats=0.5, track_id=0, channel=0, bar=0)
            for i in range(8)
        ]
        track_single = Track(track_id=0, notes=notes_single)
        features_single = extract_track_features(track_single, total_bars=2)

        # Multiple pitch classes - higher entropy
        notes_varied = [
            NoteEvent(pitch=60+i, velocity=100, start_beat=float(i), duration_beats=0.5, track_id=0, channel=0, bar=0)
            for i in range(12)
        ]
        track_varied = Track(track_id=0, notes=notes_varied)
        features_varied = extract_track_features(track_varied, total_bars=3)

        assert features_single.pitch_class_entropy < features_varied.pitch_class_entropy


class TestRoleClassifier:
    """Tests for the role classifier."""

    def test_drum_classification(self) -> None:
        """Test drum track classification."""
        features = TrackFeatures(
            note_count=64,
            note_density=16.0,
            polyphony_ratio=0.1,
            pitch_min=36,
            pitch_max=51,
            pitch_median=42.0,
            pitch_range=15,
            avg_velocity=100.0,
            avg_duration=0.1,
            syncopation_score=0.3,
            repetition_score=0.5,
            is_channel_10=True,
            pitch_class_entropy=0.3,
        )
        track = Track(track_id=0, features=features)
        probs = classify_track_role(track)

        assert probs.primary_role() == TrackRole.DRUMS
        assert probs.drums > 0.5

    def test_bass_classification(self) -> None:
        """Test bass track classification."""
        features = TrackFeatures(
            note_count=32,
            note_density=4.0,
            polyphony_ratio=0.05,
            pitch_min=28,
            pitch_max=48,
            pitch_median=38.0,
            pitch_range=20,
            avg_velocity=90.0,
            avg_duration=0.5,
            syncopation_score=0.1,
            repetition_score=0.4,
            is_channel_10=False,
            pitch_class_entropy=0.5,
        )
        track = Track(track_id=0, features=features)
        probs = classify_track_role(track)

        assert probs.primary_role() == TrackRole.BASS
        assert probs.bass > 0.3

    def test_chords_classification(self) -> None:
        """Test chord track classification."""
        features = TrackFeatures(
            note_count=48,
            note_density=6.0,
            polyphony_ratio=0.6,
            pitch_min=48,
            pitch_max=72,
            pitch_median=60.0,
            pitch_range=24,
            avg_velocity=80.0,
            avg_duration=1.0,
            syncopation_score=0.2,
            repetition_score=0.3,
            is_channel_10=False,
            pitch_class_entropy=0.7,
        )
        track = Track(track_id=0, features=features)
        probs = classify_track_role(track)

        assert probs.primary_role() == TrackRole.CHORDS
        assert probs.chords > 0.3

    def test_lead_classification(self) -> None:
        """Test lead track classification."""
        features = TrackFeatures(
            note_count=64,
            note_density=4.0,
            polyphony_ratio=0.05,
            pitch_min=60,
            pitch_max=96,
            pitch_median=78.0,
            pitch_range=36,
            avg_velocity=90.0,
            avg_duration=0.5,
            syncopation_score=0.4,
            repetition_score=0.2,
            is_channel_10=False,
            pitch_class_entropy=0.8,
        )
        track = Track(track_id=0, features=features)
        probs = classify_track_role(track)

        assert probs.primary_role() == TrackRole.LEAD
        assert probs.lead > 0.3

    def test_arp_classification(self) -> None:
        """Test arpeggio track classification."""
        features = TrackFeatures(
            note_count=128,
            note_density=16.0,
            polyphony_ratio=0.1,
            pitch_min=60,
            pitch_max=84,
            pitch_median=72.0,
            pitch_range=24,
            avg_velocity=70.0,
            avg_duration=0.125,
            syncopation_score=0.1,
            repetition_score=0.6,
            is_channel_10=False,
            pitch_class_entropy=0.4,
        )
        track = Track(track_id=0, features=features)
        probs = classify_track_role(track)

        assert probs.primary_role() == TrackRole.ARP
        assert probs.arp > 0.3

    def test_pad_classification(self) -> None:
        """Test pad track classification."""
        features = TrackFeatures(
            note_count=8,
            note_density=1.0,
            polyphony_ratio=0.5,
            pitch_min=48,
            pitch_max=72,
            pitch_median=60.0,
            pitch_range=24,
            avg_velocity=60.0,
            avg_duration=4.0,
            syncopation_score=0.0,
            repetition_score=0.2,
            is_channel_10=False,
            pitch_class_entropy=0.5,
        )
        track = Track(track_id=0, features=features)
        probs = classify_track_role(track)

        assert probs.primary_role() == TrackRole.PAD
        assert probs.pad > 0.3

    def test_no_features_returns_other(self) -> None:
        """Test that track without features returns OTHER role."""
        track = Track(track_id=0, features=None)
        probs = classify_track_role(track)

        assert probs.primary_role() == TrackRole.OTHER
        assert probs.other == 1.0
