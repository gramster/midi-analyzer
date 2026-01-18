"""MIDI Analyzer GUI application.

A PyQt6-based graphical interface for browsing, analyzing, and managing
MIDI files and their extracted patterns.
"""

from __future__ import annotations

__all__ = ["main", "run_gui"]


def main() -> int:
    """Main entry point for the GUI application.

    Returns:
        Exit code (0 for success).
    """
    from midi_analyzer.gui.app import MidiAnalyzerApp

    app = MidiAnalyzerApp()
    return app.run()


def run_gui(db_path: str | None = None) -> int:
    """Run the GUI with an optional database path.

    Args:
        db_path: Path to the MIDI library database.

    Returns:
        Exit code (0 for success).
    """
    from midi_analyzer.gui.app import MidiAnalyzerApp

    app = MidiAnalyzerApp(db_path=db_path)
    return app.run()
