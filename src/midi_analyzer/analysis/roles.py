"""Track role classification based on musical features."""

from __future__ import annotations

from midi_analyzer.models.core import RoleProbabilities, Track, TrackFeatures, TrackRole


class RoleClassifier:
    """Classify track roles based on extracted features.

    Uses heuristic scoring to determine probabilities for each role:
    - Drums: Channel 10, high density, short notes, low pitch entropy
    - Bass: Low register, monophonic, downbeat emphasis
    - Chords/Pad: Polyphonic, longer notes, mid register
    - Lead: Monophonic, wide pitch range, phrase-like
    - Arp: High note rate, repetitive, broken chord patterns
    """

    # Pitch boundaries (MIDI note numbers)
    BASS_UPPER = 60  # C4
    MID_LOWER = 48   # C3
    MID_UPPER = 84   # C6

    # Feature thresholds
    HIGH_DENSITY = 8.0      # Notes per bar
    LOW_DENSITY = 2.0
    SHORT_DURATION = 0.25   # Quarter beat
    LONG_DURATION = 1.0     # One beat
    HIGH_POLYPHONY = 0.3
    LOW_POLYPHONY = 0.1
    HIGH_REPETITION = 0.3
    WIDE_RANGE = 24         # Two octaves

    def classify(self, track: Track) -> RoleProbabilities:
        """Classify a track's role based on its features.

        Args:
            track: Track with extracted features.

        Returns:
            RoleProbabilities with scores for each role.
        """
        features = track.features

        if features is None:
            return RoleProbabilities(other=1.0)

        # Calculate individual role scores
        drums_score = self._score_drums(features)
        bass_score = self._score_bass(features)
        chords_score = self._score_chords(features)
        pad_score = self._score_pad(features)
        lead_score = self._score_lead(features)
        arp_score = self._score_arp(features)

        # Normalize scores to probabilities
        total = drums_score + bass_score + chords_score + pad_score + lead_score + arp_score

        if total < 0.1:
            # No strong indicators, classify as other
            return RoleProbabilities(other=1.0)

        return RoleProbabilities(
            drums=drums_score / total,
            bass=bass_score / total,
            chords=chords_score / total,
            pad=pad_score / total,
            lead=lead_score / total,
            arp=arp_score / total,
            other=0.0,
        )

    def _score_drums(self, features: TrackFeatures) -> float:
        """Score likelihood of drum track."""
        score = 0.0

        # Strong indicator: MIDI channel 10
        if features.is_channel_10:
            score += 3.0

        # High note density
        if features.note_density > self.HIGH_DENSITY:
            score += 1.0

        # Short note durations
        if features.avg_duration < self.SHORT_DURATION:
            score += 0.5

        # Low pitch class entropy (few distinct pitches)
        if features.pitch_class_entropy < 0.5:
            score += 0.5

        # Limited pitch range (drum kits have fixed pitches)
        if features.pitch_range < 48:  # 4 octaves
            score += 0.3

        return score

    def _score_bass(self, features: TrackFeatures) -> float:
        """Score likelihood of bass track."""
        score = 0.0

        # Avoid drum channel
        if features.is_channel_10:
            return 0.0

        # Low register
        if features.pitch_median < self.BASS_UPPER:
            score += 1.5

        if features.pitch_max < self.BASS_UPPER + 12:
            score += 0.5

        # Mostly monophonic
        if features.polyphony_ratio < self.LOW_POLYPHONY:
            score += 1.0
        elif features.polyphony_ratio < self.HIGH_POLYPHONY:
            score += 0.3

        # Moderate density
        if self.LOW_DENSITY < features.note_density < self.HIGH_DENSITY:
            score += 0.5

        # Limited pitch range (bass lines don't jump octaves much)
        if features.pitch_range < 24:
            score += 0.3

        return score

    def _score_chords(self, features: TrackFeatures) -> float:
        """Score likelihood of chord/comping track."""
        score = 0.0

        # Avoid drum channel
        if features.is_channel_10:
            return 0.0

        # Polyphonic
        if features.polyphony_ratio > self.HIGH_POLYPHONY:
            score += 1.5

        # Mid register
        if self.MID_LOWER < features.pitch_median < self.MID_UPPER:
            score += 0.5

        # Moderate note duration
        if self.SHORT_DURATION < features.avg_duration < self.LONG_DURATION * 2:
            score += 0.5

        # Moderate density
        if features.note_density > self.LOW_DENSITY:
            score += 0.3

        return score

    def _score_pad(self, features: TrackFeatures) -> float:
        """Score likelihood of pad track."""
        score = 0.0

        # Avoid drum channel
        if features.is_channel_10:
            return 0.0

        # Polyphonic
        if features.polyphony_ratio > self.HIGH_POLYPHONY:
            score += 1.0

        # Long note durations
        if features.avg_duration > self.LONG_DURATION * 2:
            score += 1.5

        # Low density (sustained notes)
        if features.note_density < self.LOW_DENSITY:
            score += 0.5

        # Mid register
        if self.MID_LOWER < features.pitch_median < self.MID_UPPER:
            score += 0.3

        return score

    def _score_lead(self, features: TrackFeatures) -> float:
        """Score likelihood of lead/melody track."""
        score = 0.0

        # Avoid drum channel
        if features.is_channel_10:
            return 0.0

        # Mostly monophonic
        if features.polyphony_ratio < self.LOW_POLYPHONY:
            score += 1.0
        elif features.polyphony_ratio < self.HIGH_POLYPHONY:
            score += 0.3

        # Wide pitch range (melodies move around)
        if features.pitch_range > self.WIDE_RANGE:
            score += 1.0

        # Higher register
        if features.pitch_median > self.BASS_UPPER:
            score += 0.5

        # Moderate to high syncopation
        if features.syncopation_score > 0.2:
            score += 0.3

        # Variable durations (phrasing)
        # This is approximated by moderate average duration
        if self.SHORT_DURATION < features.avg_duration < self.LONG_DURATION:
            score += 0.3

        return score

    def _score_arp(self, features: TrackFeatures) -> float:
        """Score likelihood of arpeggiator track."""
        score = 0.0

        # Avoid drum channel
        if features.is_channel_10:
            return 0.0

        # High note density
        if features.note_density > self.HIGH_DENSITY:
            score += 1.5

        # Short note durations
        if features.avg_duration < self.SHORT_DURATION:
            score += 1.0

        # High repetition (arps repeat patterns)
        if features.repetition_score > self.HIGH_REPETITION:
            score += 1.0

        # Mostly monophonic (broken chords)
        if features.polyphony_ratio < self.HIGH_POLYPHONY:
            score += 0.5

        # Mid-high register
        if features.pitch_median > self.BASS_UPPER:
            score += 0.3

        return score


def classify_track_role(track: Track) -> RoleProbabilities:
    """Convenience function to classify a track's role.

    Args:
        track: Track with extracted features.

    Returns:
        RoleProbabilities with scores for each role.
    """
    classifier = RoleClassifier()
    return classifier.classify(track)
