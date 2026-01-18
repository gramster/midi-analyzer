"""GUI dialog windows for the MIDI Analyzer application."""

from midi_analyzer.gui.dialogs.export_dialog import ExportDialog
from midi_analyzer.gui.dialogs.metadata_dialog import MetadataDialog
from midi_analyzer.gui.dialogs.musicbrainz_dialog import MusicBrainzDialog
from midi_analyzer.gui.dialogs.similarity_dialog import SimilarityDialog
from midi_analyzer.gui.dialogs.stats_dialog import StatsDialog

__all__ = [
    "MetadataDialog",
    "MusicBrainzDialog",
    "ExportDialog",
    "StatsDialog",
    "SimilarityDialog",
]
