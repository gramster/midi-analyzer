"""Main application class for the MIDI Analyzer GUI."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class MidiAnalyzerApp:
    """Main application class managing the Qt application lifecycle."""

    def __init__(self, db_path: str | None = None) -> None:
        """Initialize the application.

        Args:
            db_path: Optional path to the database. If None, uses default.
        """
        self.db_path = db_path or self._default_db_path()
        self._app = None
        self._main_window = None

    def _default_db_path(self) -> str:
        """Get the default database path."""
        return str(Path.cwd() / "midi_library.db")

    def run(self) -> int:
        """Run the application.

        Returns:
            Exit code.
        """
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QApplication
        except ImportError as e:
            print("PyQt6 is required for the GUI. Install with: pip install PyQt6")
            print(f"Error: {e}")
            return 1

        # Enable high DPI scaling
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        self._app = QApplication(sys.argv)
        self._app.setApplicationName("MIDI Analyzer")
        self._app.setOrganizationName("MIDIAnalyzer")
        self._app.setOrganizationDomain("github.com/gramster/midi-analyzer")

        # Apply stylesheet
        self._apply_styles()

        # Create and show main window
        from midi_analyzer.gui.main_window import MainWindow

        self._main_window = MainWindow(db_path=self.db_path)
        self._main_window.show()

        return self._app.exec()

    def _apply_styles(self) -> None:
        """Apply application-wide styles."""
        if self._app is None:
            return

        # Modern dark theme
        stylesheet = """
        QMainWindow {
            background-color: #1e1e1e;
        }
        
        QWidget {
            background-color: #252526;
            color: #cccccc;
            font-family: "Segoe UI", "SF Pro Display", system-ui, sans-serif;
            font-size: 13px;
        }
        
        QMenuBar {
            background-color: #333333;
            border-bottom: 1px solid #454545;
        }
        
        QMenuBar::item {
            padding: 6px 12px;
        }
        
        QMenuBar::item:selected {
            background-color: #094771;
        }
        
        QMenu {
            background-color: #252526;
            border: 1px solid #454545;
        }
        
        QMenu::item {
            padding: 6px 30px 6px 20px;
        }
        
        QMenu::item:selected {
            background-color: #094771;
        }
        
        QToolBar {
            background-color: #333333;
            border: none;
            spacing: 4px;
            padding: 4px;
        }
        
        QToolButton {
            background-color: transparent;
            border: none;
            border-radius: 4px;
            padding: 6px;
        }
        
        QToolButton:hover {
            background-color: #454545;
        }
        
        QToolButton:pressed {
            background-color: #094771;
        }
        
        QTableView {
            background-color: #1e1e1e;
            alternate-background-color: #252526;
            gridline-color: #333333;
            border: 1px solid #333333;
            selection-background-color: #094771;
        }
        
        QTableView::item {
            padding: 4px;
        }
        
        QHeaderView::section {
            background-color: #333333;
            color: #cccccc;
            padding: 6px;
            border: none;
            border-right: 1px solid #454545;
            border-bottom: 1px solid #454545;
        }
        
        QTreeView {
            background-color: #1e1e1e;
            border: 1px solid #333333;
            selection-background-color: #094771;
        }
        
        QTreeView::item {
            padding: 4px;
        }
        
        QTreeView::branch:has-children:!has-siblings:closed,
        QTreeView::branch:closed:has-children:has-siblings {
            border-image: none;
        }
        
        QTreeView::branch:open:has-children:!has-siblings,
        QTreeView::branch:open:has-children:has-siblings {
            border-image: none;
        }
        
        QLineEdit, QTextEdit, QPlainTextEdit {
            background-color: #3c3c3c;
            border: 1px solid #454545;
            border-radius: 4px;
            padding: 6px;
            selection-background-color: #094771;
        }
        
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
            border-color: #007acc;
        }
        
        QComboBox {
            background-color: #3c3c3c;
            border: 1px solid #454545;
            border-radius: 4px;
            padding: 6px;
            min-width: 100px;
        }
        
        QComboBox:hover {
            border-color: #007acc;
        }
        
        QComboBox::drop-down {
            border: none;
            width: 20px;
        }
        
        QComboBox QAbstractItemView {
            background-color: #252526;
            border: 1px solid #454545;
            selection-background-color: #094771;
        }
        
        QPushButton {
            background-color: #0e639c;
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
            color: white;
            font-weight: 500;
        }
        
        QPushButton:hover {
            background-color: #1177bb;
        }
        
        QPushButton:pressed {
            background-color: #094771;
        }
        
        QPushButton:disabled {
            background-color: #454545;
            color: #808080;
        }
        
        QPushButton[secondary="true"] {
            background-color: #3c3c3c;
            color: #cccccc;
        }
        
        QPushButton[secondary="true"]:hover {
            background-color: #454545;
        }
        
        QTabWidget::pane {
            border: 1px solid #333333;
            background-color: #252526;
        }
        
        QTabBar::tab {
            background-color: #2d2d2d;
            padding: 8px 16px;
            border: none;
            border-bottom: 2px solid transparent;
        }
        
        QTabBar::tab:selected {
            background-color: #1e1e1e;
            border-bottom: 2px solid #007acc;
        }
        
        QTabBar::tab:hover:!selected {
            background-color: #383838;
        }
        
        QScrollBar:vertical {
            background-color: #1e1e1e;
            width: 12px;
            border: none;
        }
        
        QScrollBar::handle:vertical {
            background-color: #5a5a5a;
            min-height: 20px;
            border-radius: 6px;
            margin: 2px;
        }
        
        QScrollBar::handle:vertical:hover {
            background-color: #787878;
        }
        
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0px;
        }
        
        QScrollBar:horizontal {
            background-color: #1e1e1e;
            height: 12px;
            border: none;
        }
        
        QScrollBar::handle:horizontal {
            background-color: #5a5a5a;
            min-width: 20px;
            border-radius: 6px;
            margin: 2px;
        }
        
        QScrollBar::handle:horizontal:hover {
            background-color: #787878;
        }
        
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0px;
        }
        
        QSplitter::handle {
            background-color: #333333;
        }
        
        QStatusBar {
            background-color: #007acc;
            color: white;
        }
        
        QProgressBar {
            background-color: #3c3c3c;
            border: none;
            border-radius: 4px;
            text-align: center;
        }
        
        QProgressBar::chunk {
            background-color: #007acc;
            border-radius: 4px;
        }
        
        QSlider::groove:horizontal {
            background-color: #3c3c3c;
            height: 6px;
            border-radius: 3px;
        }
        
        QSlider::handle:horizontal {
            background-color: #007acc;
            width: 16px;
            height: 16px;
            margin: -5px 0;
            border-radius: 8px;
        }
        
        QSlider::handle:horizontal:hover {
            background-color: #1177bb;
        }
        
        QGroupBox {
            border: 1px solid #454545;
            border-radius: 4px;
            margin-top: 12px;
            padding-top: 8px;
        }
        
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }
        
        QDockWidget {
            titlebar-close-icon: none;
            titlebar-normal-icon: none;
        }
        
        QDockWidget::title {
            background-color: #333333;
            padding: 6px;
            border-bottom: 1px solid #454545;
        }
        
        QLabel[heading="true"] {
            font-size: 16px;
            font-weight: 600;
            color: #e0e0e0;
        }
        
        QLabel[subheading="true"] {
            font-size: 12px;
            color: #808080;
        }
        
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #454545;
            border-radius: 3px;
            background-color: #3c3c3c;
        }
        
        QCheckBox::indicator:checked {
            background-color: #007acc;
            border-color: #007acc;
        }
        
        QCheckBox::indicator:hover {
            border-color: #007acc;
        }
        
        QSpinBox, QDoubleSpinBox {
            background-color: #3c3c3c;
            border: 1px solid #454545;
            border-radius: 4px;
            padding: 4px;
        }
        
        QSpinBox:focus, QDoubleSpinBox:focus {
            border-color: #007acc;
        }
        """
        self._app.setStyleSheet(stylesheet)
