"""GUI widgets for the MIDI Analyzer application."""

from midi_analyzer.gui.widgets.pattern_view import PatternViewWidget
from midi_analyzer.gui.widgets.playback_controls import PlaybackControlsWidget
from midi_analyzer.gui.widgets.song_browser import SongBrowserWidget
from midi_analyzer.gui.widgets.song_detail import SongDetailWidget

__all__ = [
    "SongBrowserWidget",
    "SongDetailWidget",
    "PatternViewWidget",
    "PlaybackControlsWidget",
]
