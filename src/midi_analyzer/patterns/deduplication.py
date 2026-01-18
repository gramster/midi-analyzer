"""Pattern deduplication and clustering."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from midi_analyzer.patterns.chunking import BarChunk
    from midi_analyzer.patterns.fingerprinting import CombinedFingerprint


@dataclass
class PatternMatch:
    """A match between two pattern occurrences.

    Attributes:
        chunk1: First chunk.
        chunk2: Second chunk.
        similarity: Similarity score (0-1).
        transposition: Semitone difference for pitch matching.
    """

    chunk1: BarChunk
    chunk2: BarChunk
    similarity: float
    transposition: int = 0


@dataclass
class PatternCluster:
    """A cluster of similar pattern occurrences.

    Attributes:
        canonical: The representative pattern for this cluster.
        fingerprint: The fingerprint of the canonical pattern.
        members: All chunks in this cluster.
        confidence: Confidence that these patterns are truly the same.
    """

    canonical: BarChunk
    fingerprint: CombinedFingerprint
    members: list[BarChunk] = field(default_factory=list)
    confidence: float = 1.0

    @property
    def count(self) -> int:
        """Number of occurrences of this pattern."""
        return len(self.members)

    @property
    def bar_positions(self) -> list[int]:
        """Start bar positions of all occurrences."""
        return [chunk.start_bar for chunk in self.members]


@dataclass
class DeduplicationResult:
    """Result of pattern deduplication.

    Attributes:
        clusters: List of pattern clusters found.
        unique_patterns: Number of unique patterns.
        total_chunks: Total number of chunks analyzed.
        repetition_ratio: Ratio of repeated chunks to total.
    """

    clusters: list[PatternCluster]
    unique_patterns: int = 0
    total_chunks: int = 0
    repetition_ratio: float = 0.0


class PatternDeduplicator:
    """Finds repeated and similar patterns within tracks.

    Uses fingerprints to identify exact matches and fuzzy matching
    for similar patterns with transposition or minor variations.
    """

    def __init__(
        self,
        rhythm_threshold: float = 0.9,
        pitch_threshold: float = 0.85,
        allow_transposition: bool = True,
    ) -> None:
        """Initialize deduplicator.

        Args:
            rhythm_threshold: Minimum rhythm similarity (0-1).
            pitch_threshold: Minimum pitch similarity (0-1).
            allow_transposition: Whether to match transposed patterns.
        """
        self.rhythm_threshold = rhythm_threshold
        self.pitch_threshold = pitch_threshold
        self.allow_transposition = allow_transposition

    def deduplicate(
        self,
        chunks: list[BarChunk],
        fingerprints: list[CombinedFingerprint],
    ) -> DeduplicationResult:
        """Find repeated patterns in a list of chunks.

        Args:
            chunks: List of bar chunks.
            fingerprints: Fingerprints for each chunk (same order).

        Returns:
            DeduplicationResult with clusters of similar patterns.
        """
        if len(chunks) != len(fingerprints):
            raise ValueError("Chunks and fingerprints must have same length")

        if not chunks:
            return DeduplicationResult(clusters=[], total_chunks=0)

        # First pass: exact hash matching
        clusters = self._find_exact_matches(chunks, fingerprints)

        # Second pass: fuzzy matching for unclustered chunks
        if self.rhythm_threshold < 1.0 or self.pitch_threshold < 1.0:
            clusters = self._merge_similar_clusters(clusters, fingerprints)

        # Calculate stats
        total_chunks = len(chunks)
        unique_patterns = len(clusters)
        repeated_chunks = sum(c.count - 1 for c in clusters)
        repetition_ratio = repeated_chunks / total_chunks if total_chunks > 0 else 0.0

        return DeduplicationResult(
            clusters=clusters,
            unique_patterns=unique_patterns,
            total_chunks=total_chunks,
            repetition_ratio=repetition_ratio,
        )

    def _find_exact_matches(
        self,
        chunks: list[BarChunk],
        fingerprints: list[CombinedFingerprint],
    ) -> list[PatternCluster]:
        """Group chunks by exact fingerprint hash.

        Args:
            chunks: List of chunks.
            fingerprints: Corresponding fingerprints.

        Returns:
            List of clusters with exact matches.
        """
        # Group by hash
        hash_groups: dict[str, list[tuple[BarChunk, CombinedFingerprint]]] = defaultdict(list)

        for chunk, fp in zip(chunks, fingerprints):
            hash_groups[fp.hash_value].append((chunk, fp))

        # Create clusters
        clusters = []
        for hash_value, members in hash_groups.items():
            # First member is canonical
            canonical_chunk, canonical_fp = members[0]
            cluster = PatternCluster(
                canonical=canonical_chunk,
                fingerprint=canonical_fp,
                members=[m[0] for m in members],
                confidence=1.0,  # Exact match = full confidence
            )
            clusters.append(cluster)

        return clusters

    def _merge_similar_clusters(
        self,
        clusters: list[PatternCluster],
        fingerprints: list[CombinedFingerprint],
    ) -> list[PatternCluster]:
        """Merge clusters with similar but not identical fingerprints.

        Args:
            clusters: Initial clusters from exact matching.
            fingerprints: All fingerprints.

        Returns:
            Merged clusters.
        """
        if len(clusters) <= 1:
            return clusters

        # Calculate similarities between cluster representatives
        merged = []
        used = set()

        for i, cluster1 in enumerate(clusters):
            if i in used:
                continue

            # Find similar clusters
            similar_indices = [i]

            for j, cluster2 in enumerate(clusters[i + 1 :], start=i + 1):
                if j in used:
                    continue

                sim = self._calculate_similarity(
                    cluster1.fingerprint,
                    cluster2.fingerprint,
                )

                if sim >= min(self.rhythm_threshold, self.pitch_threshold):
                    similar_indices.append(j)
                    used.add(j)

            # Merge similar clusters
            if len(similar_indices) == 1:
                merged.append(cluster1)
            else:
                merged_cluster = self._merge_cluster_group(
                    [clusters[idx] for idx in similar_indices]
                )
                merged.append(merged_cluster)

            used.add(i)

        return merged

    def _merge_cluster_group(
        self,
        clusters: list[PatternCluster],
    ) -> PatternCluster:
        """Merge multiple clusters into one.

        Picks the most common pattern as canonical.

        Args:
            clusters: Clusters to merge.

        Returns:
            Merged cluster.
        """
        # Pick cluster with most members as canonical
        clusters_by_size = sorted(clusters, key=lambda c: c.count, reverse=True)
        canonical = clusters_by_size[0]

        # Gather all members
        all_members = []
        for cluster in clusters:
            all_members.extend(cluster.members)

        # Confidence decreases based on number of merged clusters
        confidence = 1.0 / len(clusters) if clusters else 1.0

        return PatternCluster(
            canonical=canonical.canonical,
            fingerprint=canonical.fingerprint,
            members=all_members,
            confidence=confidence,
        )

    def _calculate_similarity(
        self,
        fp1: CombinedFingerprint,
        fp2: CombinedFingerprint,
    ) -> float:
        """Calculate similarity between two fingerprints.

        Args:
            fp1: First fingerprint.
            fp2: Second fingerprint.

        Returns:
            Similarity score (0-1).
        """
        # Check rhythm similarity
        rhythm_sim = self._rhythm_similarity(fp1, fp2)
        if rhythm_sim < self.rhythm_threshold:
            return 0.0

        # Check pitch similarity
        pitch_sim = self._pitch_similarity(fp1, fp2)

        # Combined similarity
        return (rhythm_sim + pitch_sim) / 2

    def _rhythm_similarity(
        self,
        fp1: CombinedFingerprint,
        fp2: CombinedFingerprint,
    ) -> float:
        """Calculate rhythm similarity.

        Uses Jaccard similarity of onset grids.
        """
        grid1 = set(i for i, v in enumerate(fp1.rhythm.onset_grid) if v)
        grid2 = set(i for i, v in enumerate(fp2.rhythm.onset_grid) if v)

        if not grid1 and not grid2:
            return 1.0

        intersection = len(grid1 & grid2)
        union = len(grid1 | grid2)

        return intersection / union if union > 0 else 0.0

    def _pitch_similarity(
        self,
        fp1: CombinedFingerprint,
        fp2: CombinedFingerprint,
    ) -> float:
        """Calculate pitch similarity.

        Compares pitch class distributions and interval sequences.
        """
        # Compare pitch class distributions (Euclidean distance)
        pc1 = fp1.pitch.pitch_classes
        pc2 = fp2.pitch.pitch_classes

        if len(pc1) != len(pc2):
            return 0.0

        # Normalize pitch class vectors
        sum1 = sum(pc1) or 1
        sum2 = sum(pc2) or 1
        norm1 = [v / sum1 for v in pc1]
        norm2 = [v / sum2 for v in pc2]

        # Cosine similarity
        dot_product = sum(a * b for a, b in zip(norm1, norm2))
        mag1 = sum(a * a for a in norm1) ** 0.5
        mag2 = sum(a * a for a in norm2) ** 0.5

        pc_similarity = dot_product / (mag1 * mag2) if mag1 > 0 and mag2 > 0 else 0.0

        # Compare contours
        contour1 = fp1.pitch.contour
        contour2 = fp2.pitch.contour

        if len(contour1) == len(contour2) and len(contour1) > 0:
            matches = sum(1 for a, b in zip(contour1, contour2) if a == b)
            contour_sim = matches / len(contour1)
        else:
            contour_sim = 0.0 if len(contour1) != len(contour2) else 1.0

        return (pc_similarity + contour_sim) / 2

    def find_transposition(
        self,
        fp1: CombinedFingerprint,
        fp2: CombinedFingerprint,
    ) -> int | None:
        """Find the transposition between two patterns.

        Args:
            fp1: First fingerprint.
            fp2: Second fingerprint.

        Returns:
            Semitones to transpose fp2 to match fp1, or None if not similar.
        """
        if not self.allow_transposition:
            return None

        # Check rhythm similarity first
        rhythm_sim = self._rhythm_similarity(fp1, fp2)
        if rhythm_sim < self.rhythm_threshold:
            return None

        # Find transposition from mean pitch difference
        diff = round(fp1.pitch.mean_pitch - fp2.pitch.mean_pitch)

        return diff if abs(diff) <= 12 else None


def deduplicate_track(
    chunks: list[BarChunk],
    fingerprints: list[CombinedFingerprint],
    rhythm_threshold: float = 0.9,
    pitch_threshold: float = 0.85,
) -> DeduplicationResult:
    """Convenience function to deduplicate a track's patterns.

    Args:
        chunks: List of bar chunks from the track.
        fingerprints: Corresponding fingerprints.
        rhythm_threshold: Minimum rhythm similarity.
        pitch_threshold: Minimum pitch similarity.

    Returns:
        DeduplicationResult with pattern clusters.
    """
    deduplicator = PatternDeduplicator(
        rhythm_threshold=rhythm_threshold,
        pitch_threshold=pitch_threshold,
    )
    return deduplicator.deduplicate(chunks, fingerprints)


def find_repeated_patterns(
    clusters: list[PatternCluster],
    min_occurrences: int = 2,
) -> list[PatternCluster]:
    """Filter to only clusters with multiple occurrences.

    Args:
        clusters: All pattern clusters.
        min_occurrences: Minimum number of occurrences.

    Returns:
        Clusters with at least min_occurrences members.
    """
    return [c for c in clusters if c.count >= min_occurrences]
