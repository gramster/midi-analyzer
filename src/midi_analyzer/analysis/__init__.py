"""Track and song analysis modules."""

from midi_analyzer.analysis.arpeggios import (
    ArpAnalysis,
    ArpAnalyzer,
    ArpWindow,
    analyze_arp_track,
    extract_arp_patterns,
)
from midi_analyzer.analysis.features import FeatureExtractor
from midi_analyzer.analysis.roles import RoleClassifier, classify_track_role
from midi_analyzer.analysis.sections import (
    BarFeatures,
    Section,
    SectionAnalysis,
    SectionAnalyzer,
    SectionType,
    analyze_sections,
)

__all__ = [
    # Features
    "FeatureExtractor",
    # Roles
    "RoleClassifier",
    "classify_track_role",
    # Arpeggios (Stage 6)
    "ArpAnalyzer",
    "ArpAnalysis",
    "ArpWindow",
    "analyze_arp_track",
    "extract_arp_patterns",
    # Sections (Stage 7)
    "SectionAnalyzer",
    "SectionAnalysis",
    "Section",
    "SectionType",
    "BarFeatures",
    "analyze_sections",
]
