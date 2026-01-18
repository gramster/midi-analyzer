"""Tests for pattern deduplication."""

import pytest

from midi_analyzer.models.core import NoteEvent
from midi_analyzer.patterns.chunking import BarChunk
from midi_analyzer.patterns.deduplication import (
    DeduplicationResult,
    PatternCluster,
    PatternDeduplicator,
    deduplicate_track,
    find_repeated_patterns,
)
from midi_analyzer.patterns.fingerprinting import (
    CombinedFingerprint,
    PitchFingerprint,
    RhythmFingerprint,
)


@pytest.fixture
def sample_chunks() -> list[BarChunk]:
    """Create sample chunks for testing."""
    # Create simple test notes
    notes = [
        NoteEvent(pitch=60, velocity=100, start_beat=0.0, duration_beats=0.5, track_id=0, channel=0),
        NoteEvent(pitch=62, velocity=90, start_beat=1.0, duration_beats=0.5, track_id=0, channel=0),
        NoteEvent(pitch=64, velocity=80, start_beat=2.0, duration_beats=0.5, track_id=0, channel=0),
        NoteEvent(pitch=65, velocity=70, start_beat=3.0, duration_beats=0.5, track_id=0, channel=0),
    ]

    # 4 chunks, some identical
    chunks = [
        BarChunk(start_bar=0, end_bar=1, num_bars=1, notes=notes),
        BarChunk(start_bar=1, end_bar=2, num_bars=1, notes=notes),  # Same as 0
        BarChunk(start_bar=2, end_bar=3, num_bars=1, notes=notes),  # Same as 0
        BarChunk(start_bar=3, end_bar=4, num_bars=1, notes=[]),  # Different
    ]

    return chunks


@pytest.fixture
def sample_fingerprints() -> list[CombinedFingerprint]:
    """Create fingerprints matching sample_chunks."""
    rhythm_a = RhythmFingerprint(
        onset_grid=(1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0),
        accent_grid=(1.0, 0, 0, 0, 0.9, 0, 0, 0, 0.8, 0, 0, 0, 0.7, 0, 0, 0),
        grid_size=16,
        num_bars=1,
        note_count=4,
        hash_value="rhythm-a",
    )

    pitch_a = PitchFingerprint(
        intervals=(0, 2, 2, 1),
        pitch_classes=(1, 0, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0),
        contour=(0, 1, 1, 1),
        range_semitones=5,
        mean_pitch=62.75,
        hash_value="pitch-a",
    )

    fp_a = CombinedFingerprint(rhythm=rhythm_a, pitch=pitch_a, hash_value="combined-a")

    # Empty chunk fingerprint
    rhythm_b = RhythmFingerprint(
        onset_grid=(0,) * 16,
        accent_grid=(0.0,) * 16,
        grid_size=16,
        num_bars=1,
        note_count=0,
        hash_value="rhythm-b",
    )

    pitch_b = PitchFingerprint(
        intervals=(),
        pitch_classes=(0,) * 12,
        contour=(),
        range_semitones=0,
        mean_pitch=0.0,
        hash_value="pitch-b",
    )

    fp_b = CombinedFingerprint(rhythm=rhythm_b, pitch=pitch_b, hash_value="combined-b")

    # Return: 3 identical, 1 different
    return [fp_a, fp_a, fp_a, fp_b]


class TestPatternDeduplicator:
    """Tests for PatternDeduplicator."""

    def test_init_default_thresholds(self):
        """Test default threshold values."""
        dedup = PatternDeduplicator()
        assert dedup.rhythm_threshold == 0.9
        assert dedup.pitch_threshold == 0.85
        assert dedup.allow_transposition is True

    def test_init_custom_thresholds(self):
        """Test custom threshold values."""
        dedup = PatternDeduplicator(
            rhythm_threshold=0.8,
            pitch_threshold=0.7,
            allow_transposition=False,
        )
        assert dedup.rhythm_threshold == 0.8
        assert dedup.pitch_threshold == 0.7
        assert dedup.allow_transposition is False

    def test_deduplicate_empty(self):
        """Test deduplication of empty list."""
        dedup = PatternDeduplicator()
        result = dedup.deduplicate([], [])

        assert isinstance(result, DeduplicationResult)
        assert result.clusters == []
        assert result.total_chunks == 0
        assert result.unique_patterns == 0

    def test_deduplicate_mismatched_lengths(self):
        """Test that mismatched lengths raise error."""
        dedup = PatternDeduplicator()

        chunks = [
            BarChunk(start_bar=0, end_bar=1, num_bars=1, notes=[]),
        ]
        fingerprints: list[CombinedFingerprint] = []

        with pytest.raises(ValueError, match="same length"):
            dedup.deduplicate(chunks, fingerprints)

    def test_deduplicate_finds_exact_matches(self, sample_chunks, sample_fingerprints):
        """Test finding exact fingerprint matches."""
        dedup = PatternDeduplicator()
        result = dedup.deduplicate(sample_chunks, sample_fingerprints)

        assert result.total_chunks == 4
        assert result.unique_patterns == 2  # 2 unique fingerprints

        # Find the cluster with 3 members
        big_cluster = [c for c in result.clusters if c.count == 3][0]
        assert len(big_cluster.members) == 3
        assert big_cluster.confidence == 1.0  # Exact match

    def test_deduplicate_calculates_repetition_ratio(self, sample_chunks, sample_fingerprints):
        """Test repetition ratio calculation."""
        dedup = PatternDeduplicator()
        result = dedup.deduplicate(sample_chunks, sample_fingerprints)

        # 4 total chunks, 2 unique = 2 repeated
        # repetition_ratio = (3-1 + 1-1) / 4 = 2/4 = 0.5
        assert result.repetition_ratio == 0.5

    def test_rhythm_similarity_identical(self, sample_fingerprints):
        """Test rhythm similarity for identical patterns."""
        dedup = PatternDeduplicator()

        sim = dedup._rhythm_similarity(sample_fingerprints[0], sample_fingerprints[0])
        assert sim == 1.0

    def test_rhythm_similarity_different(self, sample_fingerprints):
        """Test rhythm similarity for different patterns."""
        dedup = PatternDeduplicator()

        sim = dedup._rhythm_similarity(sample_fingerprints[0], sample_fingerprints[3])
        assert sim == 0.0  # One is empty

    def test_pitch_similarity_identical(self, sample_fingerprints):
        """Test pitch similarity for identical patterns."""
        dedup = PatternDeduplicator()

        sim = dedup._pitch_similarity(sample_fingerprints[0], sample_fingerprints[0])
        assert sim == 1.0


class TestPatternCluster:
    """Tests for PatternCluster."""

    def test_count_property(self, sample_chunks):
        """Test count property."""
        cluster = PatternCluster(
            canonical=sample_chunks[0],
            fingerprint=CombinedFingerprint(
                rhythm=RhythmFingerprint(
                    onset_grid=(1,) * 16,
                    accent_grid=(1.0,) * 16,
                    grid_size=16,
                    num_bars=1,
                    note_count=16,
                    hash_value="test",
                ),
                pitch=PitchFingerprint(
                    intervals=(),
                    pitch_classes=(0,) * 12,
                    contour=(),
                    range_semitones=0,
                    mean_pitch=60.0,
                    hash_value="test",
                ),
                hash_value="test",
            ),
            members=sample_chunks[:3],
        )

        assert cluster.count == 3

    def test_bar_positions_property(self, sample_chunks):
        """Test bar_positions property."""
        cluster = PatternCluster(
            canonical=sample_chunks[0],
            fingerprint=CombinedFingerprint(
                rhythm=RhythmFingerprint(
                    onset_grid=(1,) * 16,
                    accent_grid=(1.0,) * 16,
                    grid_size=16,
                    num_bars=1,
                    note_count=16,
                    hash_value="test",
                ),
                pitch=PitchFingerprint(
                    intervals=(),
                    pitch_classes=(0,) * 12,
                    contour=(),
                    range_semitones=0,
                    mean_pitch=60.0,
                    hash_value="test",
                ),
                hash_value="test",
            ),
            members=sample_chunks[:3],
        )

        assert cluster.bar_positions == [0, 1, 2]


class TestDeduplicateTrack:
    """Tests for deduplicate_track convenience function."""

    def test_basic_deduplication(self, sample_chunks, sample_fingerprints):
        """Test basic deduplication."""
        result = deduplicate_track(sample_chunks, sample_fingerprints)

        assert isinstance(result, DeduplicationResult)
        assert result.unique_patterns == 2

    def test_custom_thresholds(self, sample_chunks, sample_fingerprints):
        """Test with custom thresholds."""
        result = deduplicate_track(
            sample_chunks,
            sample_fingerprints,
            rhythm_threshold=1.0,
            pitch_threshold=1.0,
        )

        # With exact thresholds, should still find 2 unique
        assert result.unique_patterns == 2


class TestFindRepeatedPatterns:
    """Tests for find_repeated_patterns function."""

    def test_filters_single_occurrence(self, sample_chunks, sample_fingerprints):
        """Test filtering out single-occurrence patterns."""
        dedup = PatternDeduplicator()
        result = dedup.deduplicate(sample_chunks, sample_fingerprints)

        repeated = find_repeated_patterns(result.clusters)

        # Only the cluster with 3 members should remain
        assert len(repeated) == 1
        assert repeated[0].count == 3

    def test_custom_min_occurrences(self, sample_chunks, sample_fingerprints):
        """Test with higher minimum occurrences."""
        dedup = PatternDeduplicator()
        result = dedup.deduplicate(sample_chunks, sample_fingerprints)

        repeated = find_repeated_patterns(result.clusters, min_occurrences=3)

        assert len(repeated) == 1

        repeated = find_repeated_patterns(result.clusters, min_occurrences=4)

        assert len(repeated) == 0


class TestFuzzyMatching:
    """Tests for fuzzy matching behavior."""

    def test_similar_rhythm_patterns(self):
        """Test clustering of similar (not identical) rhythm patterns."""
        # Create two similar rhythm patterns
        rhythm1 = RhythmFingerprint(
            onset_grid=(1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0),
            accent_grid=(1.0,) * 16,
            grid_size=16,
            num_bars=1,
            note_count=8,
            hash_value="rhythm-1",
        )

        # Very similar - differs by one onset
        rhythm2 = RhythmFingerprint(
            onset_grid=(1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 0, 0),
            accent_grid=(1.0,) * 16,
            grid_size=16,
            num_bars=1,
            note_count=7,
            hash_value="rhythm-2",
        )

        pitch = PitchFingerprint(
            intervals=(0,),
            pitch_classes=(1,) + (0,) * 11,
            contour=(0,),
            range_semitones=0,
            mean_pitch=60.0,
            hash_value="pitch-same",
        )

        fp1 = CombinedFingerprint(rhythm=rhythm1, pitch=pitch, hash_value="fp1")
        fp2 = CombinedFingerprint(rhythm=rhythm2, pitch=pitch, hash_value="fp2")

        # Check similarity
        dedup = PatternDeduplicator(rhythm_threshold=0.8)
        sim = dedup._rhythm_similarity(fp1, fp2)

        # 7/8 = 0.875 similarity (Jaccard)
        assert sim > 0.8

    def test_transposition_detection(self):
        """Test finding transposition between patterns."""
        pitch1 = PitchFingerprint(
            intervals=(0, 2, 4),
            pitch_classes=(1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0),
            contour=(0, 1, 1),
            range_semitones=4,
            mean_pitch=64.0,
            hash_value="pitch-1",
        )

        pitch2 = PitchFingerprint(
            intervals=(0, 2, 4),
            pitch_classes=(1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0),
            contour=(0, 1, 1),
            range_semitones=4,
            mean_pitch=67.0,  # 3 semitones higher
            hash_value="pitch-2",
        )

        rhythm = RhythmFingerprint(
            onset_grid=(1, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            accent_grid=(1.0, 0, 1.0, 0, 1.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            grid_size=16,
            num_bars=1,
            note_count=3,
            hash_value="rhythm-same",
        )

        fp1 = CombinedFingerprint(rhythm=rhythm, pitch=pitch1, hash_value="fp1")
        fp2 = CombinedFingerprint(rhythm=rhythm, pitch=pitch2, hash_value="fp2")

        dedup = PatternDeduplicator(allow_transposition=True)
        transposition = dedup.find_transposition(fp1, fp2)

        assert transposition == -3  # fp2 is 3 semitones higher
