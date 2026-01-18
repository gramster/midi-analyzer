"""Section segmentation for MIDI songs.

Detects section boundaries and clusters sections into forms (A/B/C).
Does not force labels like verse/chorus, but provides optional heuristics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from midi_analyzer.models.core import NoteEvent, RoleProbabilities, Song, Track


class SectionType(Enum):
    """Optional section type labels."""

    INTRO = "intro"
    VERSE = "verse"
    CHORUS = "chorus"
    BRIDGE = "bridge"
    BREAKDOWN = "breakdown"
    BUILD = "build"
    DROP = "drop"
    OUTRO = "outro"
    UNKNOWN = "unknown"


@dataclass
class BarFeatures:
    """Feature vector for a single bar.

    Attributes:
        bar_number: 0-indexed bar number.
        start_beat: Start beat of this bar.
        end_beat: End beat of this bar.
        active_track_count: Number of tracks with notes in this bar.
        total_note_count: Total notes across all tracks.
        density_by_role: Note density per role (bass, drums, lead, etc.).
        harmonic_rhythm: Number of chord changes in this bar.
        avg_velocity: Average note velocity.
        pitch_range: Range of pitches (max - min).
        unique_pitches: Count of unique pitches.
    """

    bar_number: int
    start_beat: float
    end_beat: float
    active_track_count: int = 0
    total_note_count: int = 0
    density_by_role: dict[str, float] = field(default_factory=dict)
    harmonic_rhythm: int = 0
    avg_velocity: float = 0.0
    pitch_range: int = 0
    unique_pitches: int = 0

    def to_vector(self) -> np.ndarray:
        """Convert to numpy vector for similarity computation.

        Returns:
            Feature vector as numpy array.
        """
        # Fixed order of roles for consistent vectorization
        roles = ["bass", "drums", "lead", "pad", "arp", "chords", "other"]
        role_densities = [self.density_by_role.get(r, 0.0) for r in roles]

        return np.array([
            self.active_track_count / 16.0,  # Normalize assuming max 16 tracks
            self.total_note_count / 100.0,   # Normalize assuming typical max
            *role_densities,
            self.harmonic_rhythm / 4.0,      # Normalize assuming max 4 per bar
            self.avg_velocity / 127.0,
            self.pitch_range / 88.0,         # Normalize to piano range
            self.unique_pitches / 12.0,      # Normalize to octave
        ], dtype=np.float32)


@dataclass
class Section:
    """A detected section of the song.

    Attributes:
        section_id: Unique identifier for this section instance.
        form_label: Cluster label (A, B, C, etc.).
        start_bar: Starting bar number (inclusive).
        end_bar: Ending bar number (exclusive).
        start_beat: Starting beat.
        end_beat: Ending beat.
        type_hint: Optional heuristic type label.
        type_confidence: Confidence in the type hint.
        avg_features: Average feature vector for this section.
    """

    section_id: int
    form_label: str = "A"
    start_bar: int = 0
    end_bar: int = 0
    start_beat: float = 0.0
    end_beat: float = 0.0
    type_hint: SectionType = SectionType.UNKNOWN
    type_confidence: float = 0.0
    avg_features: BarFeatures | None = None


@dataclass
class SectionAnalysis:
    """Complete section analysis for a song.

    Attributes:
        bar_features: Per-bar feature vectors.
        section_boundaries: Bar indices where sections change.
        sections: Detected sections with form labels.
        form_sequence: Sequence of form labels (e.g., ["A", "B", "A", "C"]).
    """

    bar_features: list[BarFeatures] = field(default_factory=list)
    section_boundaries: list[int] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    form_sequence: list[str] = field(default_factory=list)


class SectionAnalyzer:
    """Analyzes songs for section structure.

    Uses novelty detection on per-bar features to find section boundaries,
    then clusters similar sections into form labels (A/B/C).
    """

    # Minimum bars for a valid section
    MIN_SECTION_BARS = 4

    # Novelty threshold (as multiplier of mean novelty)
    NOVELTY_THRESHOLD_MULTIPLIER = 1.5

    # Maximum number of distinct form labels
    MAX_FORMS = 8

    def __init__(
        self,
        min_section_bars: int = MIN_SECTION_BARS,
        novelty_threshold: float = NOVELTY_THRESHOLD_MULTIPLIER,
    ) -> None:
        """Initialize the analyzer.

        Args:
            min_section_bars: Minimum bars for a valid section.
            novelty_threshold: Threshold multiplier for novelty peaks.
        """
        self.min_section_bars = min_section_bars
        self.novelty_threshold = novelty_threshold

    def analyze_song(self, song: Song) -> SectionAnalysis:
        """Analyze a song for section structure.

        Args:
            song: Song to analyze.

        Returns:
            SectionAnalysis with detected sections.
        """
        if not song.tracks:
            return SectionAnalysis()

        # Compute bar features
        bar_features = self._compute_bar_features(song)
        if len(bar_features) < self.min_section_bars:
            return SectionAnalysis(bar_features=bar_features)

        # Detect section boundaries via novelty
        boundaries = self._detect_boundaries(bar_features)

        # Create sections from boundaries
        sections = self._create_sections(bar_features, boundaries)

        # Cluster sections into forms
        sections = self._cluster_sections(sections)

        # Apply heuristic type labels
        sections = self._apply_type_hints(sections)

        # Build form sequence
        form_sequence = [s.form_label for s in sections]

        return SectionAnalysis(
            bar_features=bar_features,
            section_boundaries=boundaries,
            sections=sections,
            form_sequence=form_sequence,
        )

    def _compute_bar_features(self, song: Song) -> list[BarFeatures]:
        """Compute per-bar feature vectors.

        Args:
            song: Song to analyze.

        Returns:
            List of BarFeatures, one per bar.
        """
        # Determine bar structure from time signature
        beats_per_bar = 4.0
        if song.time_sig_map:
            beats_per_bar = song.time_sig_map[0].beats_per_bar

        # Find song end
        all_notes: list[NoteEvent] = []
        for track in song.tracks:
            all_notes.extend(track.notes)

        if not all_notes:
            return []

        max_beat = max(n.start_beat + n.duration_beats for n in all_notes)
        num_bars = int(np.ceil(max_beat / beats_per_bar))

        bar_features: list[BarFeatures] = []

        for bar_num in range(num_bars):
            start_beat = bar_num * beats_per_bar
            end_beat = start_beat + beats_per_bar

            features = self._compute_single_bar_features(
                song, bar_num, start_beat, end_beat
            )
            bar_features.append(features)

        return bar_features

    def _compute_single_bar_features(
        self,
        song: Song,
        bar_num: int,
        start_beat: float,
        end_beat: float,
    ) -> BarFeatures:
        """Compute features for a single bar.

        Args:
            song: Song being analyzed.
            bar_num: Bar number.
            start_beat: Start beat of bar.
            end_beat: End beat of bar.

        Returns:
            BarFeatures for this bar.
        """
        features = BarFeatures(
            bar_number=bar_num,
            start_beat=start_beat,
            end_beat=end_beat,
        )

        active_tracks = 0
        total_notes = 0
        all_velocities: list[int] = []
        all_pitches: list[int] = []
        density_by_role: dict[str, float] = {}

        for track in song.tracks:
            # Get notes in this bar
            bar_notes = [
                n for n in track.notes
                if start_beat <= n.start_beat < end_beat
            ]

            if bar_notes:
                active_tracks += 1
                total_notes += len(bar_notes)

                # Collect velocity and pitch data
                all_velocities.extend(n.velocity for n in bar_notes)
                all_pitches.extend(n.pitch for n in bar_notes)

                # Compute density by role
                role = self._get_track_role(track)
                bar_duration = end_beat - start_beat
                density = len(bar_notes) / bar_duration
                density_by_role[role] = density_by_role.get(role, 0.0) + density

        features.active_track_count = active_tracks
        features.total_note_count = total_notes
        features.density_by_role = density_by_role

        if all_velocities:
            features.avg_velocity = sum(all_velocities) / len(all_velocities)

        if all_pitches:
            features.pitch_range = max(all_pitches) - min(all_pitches)
            features.unique_pitches = len(set(all_pitches))

        # Harmonic rhythm would require chord analysis per bar
        # For now, estimate from note onset clustering
        features.harmonic_rhythm = self._estimate_harmonic_rhythm(
            song, start_beat, end_beat
        )

        return features

    def _get_track_role(self, track: Track) -> str:
        """Get the dominant role for a track.

        Args:
            track: Track to classify.

        Returns:
            Role name string.
        """
        if not track.role_probs:
            return "other"

        probs = track.role_probs
        roles = [
            ("bass", probs.bass),
            ("drums", probs.drums),
            ("lead", probs.lead),
            ("pad", probs.pad),
            ("arp", probs.arp),
            ("chords", probs.chords),
        ]

        best_role, best_prob = max(roles, key=lambda x: x[1])
        return best_role if best_prob > 0.3 else "other"

    def _estimate_harmonic_rhythm(
        self,
        song: Song,
        start_beat: float,
        end_beat: float,
    ) -> int:
        """Estimate harmonic rhythm from bass note changes.

        Args:
            song: Song being analyzed.
            start_beat: Start beat.
            end_beat: End beat.

        Returns:
            Estimated chord changes in this bar.
        """
        # Look for bass tracks and count distinct bass notes
        bass_notes: list[NoteEvent] = []

        for track in song.tracks:
            if track.role_probs and track.role_probs.bass > 0.5:
                bar_notes = [
                    n for n in track.notes
                    if start_beat <= n.start_beat < end_beat
                ]
                bass_notes.extend(bar_notes)

        if not bass_notes:
            return 0

        # Count pitch class changes (likely chord changes)
        bass_notes.sort(key=lambda n: n.start_beat)
        changes = 0
        prev_pc = None

        for note in bass_notes:
            pc = note.pitch % 12
            if prev_pc is not None and pc != prev_pc:
                changes += 1
            prev_pc = pc

        return changes

    def _detect_boundaries(self, bar_features: list[BarFeatures]) -> list[int]:
        """Detect section boundaries using novelty detection.

        Args:
            bar_features: Per-bar feature vectors.

        Returns:
            List of bar indices where sections start.
        """
        if len(bar_features) < 2:
            return [0]

        # Convert to feature matrix
        vectors = np.array([bf.to_vector() for bf in bar_features])

        # Compute novelty curve (distance between consecutive bars)
        novelty = np.zeros(len(bar_features))
        for i in range(1, len(vectors)):
            novelty[i] = np.linalg.norm(vectors[i] - vectors[i - 1])

        # Find peaks above threshold
        mean_novelty = np.mean(novelty[1:])  # Exclude first bar
        std_novelty = np.std(novelty[1:])
        threshold = mean_novelty + self.novelty_threshold * std_novelty

        # Always include bar 0 as a boundary
        boundaries = [0]

        # Find local maxima above threshold
        for i in range(1, len(novelty) - 1):
            if novelty[i] > threshold:
                # Check if local maximum
                if novelty[i] >= novelty[i - 1] and novelty[i] >= novelty[i + 1]:
                    # Ensure minimum distance from previous boundary
                    if i - boundaries[-1] >= self.min_section_bars:
                        boundaries.append(i)

        return boundaries

    def _create_sections(
        self,
        bar_features: list[BarFeatures],
        boundaries: list[int],
    ) -> list[Section]:
        """Create Section objects from boundaries.

        Args:
            bar_features: Per-bar features.
            boundaries: Bar indices where sections start.

        Returns:
            List of Section objects.
        """
        sections: list[Section] = []

        for i, start_bar in enumerate(boundaries):
            # End bar is next boundary or end of song
            if i + 1 < len(boundaries):
                end_bar = boundaries[i + 1]
            else:
                end_bar = len(bar_features)

            # Skip tiny sections
            if end_bar - start_bar < self.min_section_bars // 2:
                continue

            # Compute average features for this section
            section_bars = bar_features[start_bar:end_bar]
            avg_features = self._average_bar_features(section_bars)

            sections.append(Section(
                section_id=i,
                start_bar=start_bar,
                end_bar=end_bar,
                start_beat=bar_features[start_bar].start_beat,
                end_beat=bar_features[end_bar - 1].end_beat,
                avg_features=avg_features,
            ))

        return sections

    def _average_bar_features(self, bars: list[BarFeatures]) -> BarFeatures:
        """Compute average features across bars.

        Args:
            bars: List of BarFeatures.

        Returns:
            BarFeatures with averaged values.
        """
        if not bars:
            return BarFeatures(bar_number=-1, start_beat=0, end_beat=0)

        avg = BarFeatures(
            bar_number=-1,  # Not a real bar
            start_beat=bars[0].start_beat,
            end_beat=bars[-1].end_beat,
        )

        avg.active_track_count = int(
            sum(b.active_track_count for b in bars) / len(bars)
        )
        avg.total_note_count = int(
            sum(b.total_note_count for b in bars) / len(bars)
        )
        avg.avg_velocity = sum(b.avg_velocity for b in bars) / len(bars)
        avg.pitch_range = int(sum(b.pitch_range for b in bars) / len(bars))
        avg.unique_pitches = int(sum(b.unique_pitches for b in bars) / len(bars))
        avg.harmonic_rhythm = int(sum(b.harmonic_rhythm for b in bars) / len(bars))

        # Merge density by role
        all_roles: set[str] = set()
        for b in bars:
            all_roles.update(b.density_by_role.keys())

        for role in all_roles:
            densities = [b.density_by_role.get(role, 0.0) for b in bars]
            avg.density_by_role[role] = sum(densities) / len(densities)

        return avg

    def _cluster_sections(self, sections: list[Section]) -> list[Section]:
        """Cluster similar sections into forms (A/B/C).

        Args:
            sections: Sections to cluster.

        Returns:
            Sections with form_label assigned.
        """
        if not sections:
            return sections

        # Get feature vectors for each section
        vectors = []
        for section in sections:
            if section.avg_features:
                vectors.append(section.avg_features.to_vector())
            else:
                vectors.append(np.zeros(13, dtype=np.float32))

        vectors = np.array(vectors)

        # Simple greedy clustering
        form_labels = [""] * len(sections)
        form_centroids: list[np.ndarray] = []
        current_label = ord("A")

        for i, vec in enumerate(vectors):
            # Find closest existing cluster
            best_cluster = -1
            best_distance = float("inf")

            for j, centroid in enumerate(form_centroids):
                dist = np.linalg.norm(vec - centroid)
                if dist < best_distance:
                    best_distance = dist
                    best_cluster = j

            # Threshold for creating new cluster
            # Use mean distance between all pairs as reference
            threshold = 0.5  # Base threshold
            if len(form_centroids) >= 2:
                all_dists = []
                for j in range(len(form_centroids)):
                    for k in range(j + 1, len(form_centroids)):
                        all_dists.append(
                            np.linalg.norm(form_centroids[j] - form_centroids[k])
                        )
                if all_dists:
                    threshold = min(all_dists) * 0.7

            if best_cluster == -1 or (
                best_distance > threshold
                and len(form_centroids) < self.MAX_FORMS
            ):
                # Create new cluster
                form_labels[i] = chr(current_label)
                form_centroids.append(vec.copy())
                current_label += 1
            else:
                # Assign to existing cluster
                form_labels[i] = chr(ord("A") + best_cluster)
                # Update centroid (moving average)
                form_centroids[best_cluster] = (
                    form_centroids[best_cluster] * 0.8 + vec * 0.2
                )

        # Apply labels to sections
        for i, section in enumerate(sections):
            section.form_label = form_labels[i]

        return sections

    def _apply_type_hints(self, sections: list[Section]) -> list[Section]:
        """Apply heuristic type labels to sections.

        Args:
            sections: Sections to label.

        Returns:
            Sections with type_hint and type_confidence set.
        """
        if not sections:
            return sections

        # First section is likely intro if low energy
        if sections[0].avg_features:
            features = sections[0].avg_features
            if features.total_note_count < 20 or features.active_track_count < 3:
                sections[0].type_hint = SectionType.INTRO
                sections[0].type_confidence = 0.6

        # Last section is likely outro if energy decreases
        if len(sections) >= 2 and sections[-1].avg_features and sections[-2].avg_features:
            last = sections[-1].avg_features
            prev = sections[-2].avg_features
            if last.total_note_count < prev.total_note_count * 0.7:
                sections[-1].type_hint = SectionType.OUTRO
                sections[-1].type_confidence = 0.5

        # Look for breakdowns (sudden drop in energy)
        for i in range(1, len(sections)):
            if not sections[i].avg_features or not sections[i - 1].avg_features:
                continue

            curr = sections[i].avg_features
            prev_sec = sections[i - 1].avg_features

            # Breakdown: significant energy drop
            if curr.total_note_count < prev_sec.total_note_count * 0.4:
                if curr.density_by_role.get("drums", 0) < 0.5:
                    sections[i].type_hint = SectionType.BREAKDOWN
                    sections[i].type_confidence = 0.6

            # Build: increasing energy and density
            elif (
                curr.total_note_count > prev_sec.total_note_count * 1.3
                and curr.active_track_count > prev_sec.active_track_count
            ):
                sections[i].type_hint = SectionType.BUILD
                sections[i].type_confidence = 0.5

            # Drop: sudden high energy after build
            if sections[i - 1].type_hint == SectionType.BUILD:
                if curr.total_note_count > prev_sec.total_note_count:
                    sections[i].type_hint = SectionType.DROP
                    sections[i].type_confidence = 0.7

        # Label remaining unlabeled sections as verse/chorus based on form
        form_counts: dict[str, int] = {}
        for s in sections:
            form_counts[s.form_label] = form_counts.get(s.form_label, 0) + 1

        # Most common form is likely verse, second most common is chorus
        if form_counts:
            sorted_forms = sorted(form_counts.items(), key=lambda x: -x[1])
            verse_form = sorted_forms[0][0]
            chorus_form = sorted_forms[1][0] if len(sorted_forms) > 1 else None

            for s in sections:
                if s.type_hint != SectionType.UNKNOWN:
                    continue

                if s.form_label == verse_form:
                    s.type_hint = SectionType.VERSE
                    s.type_confidence = 0.4
                elif s.form_label == chorus_form:
                    s.type_hint = SectionType.CHORUS
                    s.type_confidence = 0.4
                else:
                    s.type_hint = SectionType.BRIDGE
                    s.type_confidence = 0.3

        return sections


def analyze_sections(song: Song) -> SectionAnalysis:
    """Convenience function to analyze song sections.

    Args:
        song: Song to analyze.

    Returns:
        SectionAnalysis with detected sections and forms.
    """
    analyzer = SectionAnalyzer()
    return analyzer.analyze_song(song)
