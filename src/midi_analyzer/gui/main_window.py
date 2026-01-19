"""Main window for the MIDI Analyzer GUI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from midi_analyzer.gui.widgets.pattern_view import PatternViewWidget
from midi_analyzer.gui.widgets.playback_controls import PlaybackControlsWidget
from midi_analyzer.gui.widgets.song_browser import SongBrowserWidget
from midi_analyzer.gui.widgets.song_detail import SongDetailWidget

if TYPE_CHECKING:
    from midi_analyzer.library import ClipInfo, ClipLibrary
    from midi_analyzer.models.core import Song


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, db_path: str | None = None, parent: QWidget | None = None) -> None:
        """Initialize the main window.

        Args:
            db_path: Path to the MIDI library database.
            parent: Parent widget.
        """
        super().__init__(parent)

        self.db_path = db_path or str(Path.cwd() / "midi_library.db")
        self._library: ClipLibrary | None = None
        self._current_song: ClipInfo | None = None

        self._setup_ui()
        self._setup_menus()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()

        # Load library on next event loop iteration
        QTimer.singleShot(0, self._load_library)

    def _setup_ui(self) -> None:
        """Set up the main UI layout."""
        self.setWindowTitle("MIDI Analyzer")
        self.setMinimumSize(1200, 800)

        # Central widget with splitters
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Main horizontal splitter
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel - Song browser
        self.song_browser = SongBrowserWidget()
        self.main_splitter.addWidget(self.song_browser)

        # Right panel - vertical splitter for detail and pattern views
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Song detail view
        self.song_detail = SongDetailWidget()
        right_splitter.addWidget(self.song_detail)

        # Pattern visualization
        self.pattern_view = PatternViewWidget()
        right_splitter.addWidget(self.pattern_view)

        right_splitter.setSizes([400, 400])
        self.main_splitter.addWidget(right_splitter)

        # Set initial splitter sizes (30% / 70%)
        self.main_splitter.setSizes([350, 850])

        layout.addWidget(self.main_splitter)

        # Playback controls at bottom
        self.playback_controls = PlaybackControlsWidget()
        layout.addWidget(self.playback_controls)

    def _setup_menus(self) -> None:
        """Set up the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        self.action_open_db = QAction("&Open Database...", self)
        self.action_open_db.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open_db.triggered.connect(self._on_open_database)
        file_menu.addAction(self.action_open_db)

        self.action_new_db = QAction("&New Database...", self)
        self.action_new_db.setShortcut(QKeySequence("Ctrl+Shift+N"))
        self.action_new_db.triggered.connect(self._on_new_database)
        file_menu.addAction(self.action_new_db)

        file_menu.addSeparator()

        self.action_import = QAction("&Import Folder...", self)
        self.action_import.setShortcut(QKeySequence("Ctrl+I"))
        self.action_import.triggered.connect(self._on_import_folder)
        file_menu.addAction(self.action_import)

        self.action_import_files = QAction("Import &Files...", self)
        self.action_import_files.triggered.connect(self._on_import_files)
        file_menu.addAction(self.action_import_files)

        file_menu.addSeparator()

        self.action_export = QAction("&Export Selected...", self)
        self.action_export.setShortcut(QKeySequence("Ctrl+E"))
        self.action_export.triggered.connect(self._on_export)
        file_menu.addAction(self.action_export)

        file_menu.addSeparator()

        self.action_quit = QAction("&Quit", self)
        self.action_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_quit.triggered.connect(self.close)
        file_menu.addAction(self.action_quit)

        # Edit menu
        edit_menu = menubar.addMenu("&Edit")

        self.action_edit_metadata = QAction("Edit &Metadata...", self)
        self.action_edit_metadata.setShortcut(QKeySequence("Ctrl+M"))
        self.action_edit_metadata.triggered.connect(self._on_edit_metadata)
        edit_menu.addAction(self.action_edit_metadata)

        self.action_fetch_genres = QAction("Lookup on &MusicBrainz...", self)
        self.action_fetch_genres.setShortcut(QKeySequence("Ctrl+G"))
        self.action_fetch_genres.triggered.connect(self._on_fetch_genres)
        edit_menu.addAction(self.action_fetch_genres)

        edit_menu.addSeparator()

        self.action_delete = QAction("&Delete Song", self)
        self.action_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self.action_delete.triggered.connect(self._on_delete_song)
        edit_menu.addAction(self.action_delete)

        # View menu
        view_menu = menubar.addMenu("&View")

        self.action_refresh = QAction("&Refresh", self)
        self.action_refresh.setShortcut(QKeySequence.StandardKey.Refresh)
        self.action_refresh.triggered.connect(self._on_refresh)
        view_menu.addAction(self.action_refresh)

        view_menu.addSeparator()

        self.action_stats = QAction("Library &Statistics...", self)
        self.action_stats.triggered.connect(self._on_show_stats)
        view_menu.addAction(self.action_stats)

        # Playback menu
        playback_menu = menubar.addMenu("&Playback")

        self.action_play = QAction("&Play/Pause", self)
        self.action_play.setShortcut(QKeySequence("Space"))
        self.action_play.triggered.connect(self._on_play_pause)
        playback_menu.addAction(self.action_play)

        self.action_stop = QAction("&Stop", self)
        self.action_stop.setShortcut(QKeySequence("Escape"))
        self.action_stop.triggered.connect(self._on_stop)
        playback_menu.addAction(self.action_stop)

        # Analysis menu
        analysis_menu = menubar.addMenu("&Analysis")

        self.action_analyze = QAction("Analyze &All", self)
        self.action_analyze.setShortcut(QKeySequence("Ctrl+Shift+A"))
        self.action_analyze.triggered.connect(self._on_analyze_all)
        analysis_menu.addAction(self.action_analyze)

        self.action_find_similar = QAction("Find &Similar Patterns...", self)
        self.action_find_similar.setShortcut(QKeySequence("Ctrl+F"))
        self.action_find_similar.triggered.connect(self._on_find_similar)
        analysis_menu.addAction(self.action_find_similar)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        self.action_about = QAction("&About", self)
        self.action_about.triggered.connect(self._on_about)
        help_menu.addAction(self.action_about)

    def _setup_toolbar(self) -> None:
        """Set up the toolbar."""
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)

        toolbar.addAction(self.action_import)
        toolbar.addAction(self.action_refresh)
        toolbar.addSeparator()
        toolbar.addAction(self.action_play)
        toolbar.addAction(self.action_stop)
        toolbar.addSeparator()
        toolbar.addAction(self.action_analyze)
        toolbar.addAction(self.action_find_similar)

    def _setup_statusbar(self) -> None:
        """Set up the status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.song_browser.song_selected.connect(self._on_song_selected)
        self.song_browser.song_double_clicked.connect(self._on_song_double_clicked)
        self.song_detail.track_selected.connect(self._on_track_selected)
        self.song_detail.play_track_requested.connect(self._on_play_track)
        self.song_detail.fetch_genres_requested.connect(self._on_fetch_genres)
        # Note: Don't connect play_clicked to _on_play_pause - that causes double-toggle
        # The playback_controls widget already handles its own button clicks internally
        self.playback_controls.stop_clicked.connect(self._on_stop)
        self.playback_controls.position_changed.connect(self._on_playback_position_changed)

    def _load_library(self) -> None:
        """Load the clip library."""
        try:
            from midi_analyzer.library import ClipLibrary

            self._library = ClipLibrary(self.db_path)
            self.song_browser.set_library(self._library)

            stats = self._library.get_stats()
            self.status_bar.showMessage(
                f"Loaded {stats.total_songs} songs, {stats.total_clips} clips"
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Database Error",
                f"Could not load database: {e}\n\nA new database will be created.",
            )
            self._create_new_database()

    def _create_new_database(self) -> None:
        """Create a new empty database."""
        try:
            from midi_analyzer.library import ClipLibrary

            self._library = ClipLibrary(self.db_path)
            self.song_browser.set_library(self._library)
            self.status_bar.showMessage("New database created")
        except Exception as e:
            QMessageBox.critical(self, "Database Error", f"Could not create database: {e}")

    # Menu action handlers
    def _on_open_database(self) -> None:
        """Handle open database action."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Database", str(Path.home()), "SQLite Database (*.db);;All Files (*)"
        )
        if path:
            self.db_path = path
            self._load_library()

    def _on_new_database(self) -> None:
        """Handle new database action."""
        path, _ = QFileDialog.getSaveFileName(
            self,
            "New Database",
            str(Path.home() / "midi_library.db"),
            "SQLite Database (*.db);;All Files (*)",
        )
        if path:
            self.db_path = path
            self._create_new_database()

    def _on_import_folder(self) -> None:
        """Handle import folder action."""
        if self._library is None:
            return

        folder = QFileDialog.getExistingDirectory(self, "Select MIDI Folder", str(Path.home()))
        if not folder:
            return

        # Show progress dialog
        progress = QProgressDialog("Importing MIDI files...", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setAutoClose(True)
        progress.setMinimumDuration(0)

        files_processed = [0]
        total_files = [0]
        cancelled = [False]

        def progress_callback(current: int, total: int, filename: str) -> bool:
            """Update progress. Returns False to cancel the import."""
            files_processed[0] = current
            total_files[0] = total
            if total > 0:
                progress.setValue(int(current * 100 / total))
                progress.setLabelText(f"Importing: {filename}")
            QApplication.processEvents()
            if progress.wasCanceled():
                cancelled[0] = True
                return False  # Signal to stop importing
            return True  # Continue importing

        def error_callback(path: Path, error: Exception) -> None:
            # Log errors but continue
            pass

        try:
            count = self._library.index_directory(
                folder,
                recursive=True,
                progress_callback=progress_callback,
                error_callback=error_callback,
            )
            progress.close()

            if cancelled[0]:
                self.song_browser.refresh()
                self.status_bar.showMessage(f"Import cancelled after {files_processed[0]} files")
                return

            self.song_browser.refresh()
            self.status_bar.showMessage(f"Imported {count} clips from {files_processed[0]} files")

            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully imported {count} clips from {files_processed[0]} files.",
            )
        except Exception as e:
            progress.close()
            QMessageBox.critical(self, "Import Error", f"Error importing files: {e}")

    def _on_import_files(self) -> None:
        """Handle import files action."""
        if self._library is None:
            return

        files, _ = QFileDialog.getOpenFileNames(
            self, "Select MIDI Files", str(Path.home()), "MIDI Files (*.mid *.midi);;All Files (*)"
        )
        if not files:
            return

        count = 0
        errors = []
        for file_path in files:
            try:
                clips = self._library.index_file(file_path)
                count += len(clips)
            except Exception as e:
                errors.append(f"{file_path}: {e}")

        self.song_browser.refresh()
        self.status_bar.showMessage(f"Imported {count} clips from {len(files)} files")

        if errors:
            QMessageBox.warning(
                self,
                "Import Warnings",
                f"Imported {count} clips. Some files had errors:\n\n" + "\n".join(errors[:5]),
            )
        else:
            QMessageBox.information(
                self,
                "Import Complete",
                f"Successfully imported {count} clips from {len(files)} files.",
            )

    def _on_export(self) -> None:
        """Handle export action."""
        if self._current_song is None:
            QMessageBox.information(self, "Export", "Please select a song to export.")
            return

        from midi_analyzer.gui.dialogs.export_dialog import ExportDialog

        dialog = ExportDialog(self._current_song, self._library, self)
        dialog.exec()

    def _on_edit_metadata(self) -> None:
        """Handle edit metadata action."""
        if self._current_song is None:
            QMessageBox.information(self, "Edit Metadata", "Please select a song first.")
            return

        from midi_analyzer.gui.dialogs.metadata_dialog import MetadataDialog

        dialog = MetadataDialog(self._current_song, self._library, self)
        if dialog.exec():
            self.song_browser.refresh()
            self.song_detail.refresh()

    def _on_fetch_genres(self) -> None:
        """Handle fetch genres from MusicBrainz action."""
        if self._current_song is None:
            QMessageBox.information(self, "Fetch Genres", "Please select a song first.")
            return

        from midi_analyzer.gui.dialogs.musicbrainz_dialog import MusicBrainzDialog

        dialog = MusicBrainzDialog(self._current_song, self._library, self)
        if dialog.exec():
            # Refresh the browser to show updated metadata
            self.song_browser.refresh()
            
            # Re-select the current song to reload its metadata
            if self._library and self._current_song:
                # Get fresh clip data from the library
                from midi_analyzer.library import ClipQuery
                clips = self._library.query(ClipQuery(clip_id=self._current_song.clip_id))
                if clips:
                    self._current_song = clips[0]
                    song = self._library.load_song(self._current_song)
                    self.song_detail.set_song(song, self._current_song)

    def _on_delete_song(self) -> None:
        """Handle delete song action."""
        if self._current_song is None:
            return

        result = QMessageBox.question(
            self,
            "Delete Song",
            f"Are you sure you want to delete '{self._current_song.artist} - {Path(self._current_song.source_path).stem}' from the library?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if result == QMessageBox.StandardButton.Yes and self._library:
            self._library.delete_song(self._current_song.song_id)
            self._current_song = None
            self.song_browser.refresh()
            self.song_detail.clear()
            self.pattern_view.clear()

    def _on_refresh(self) -> None:
        """Handle refresh action."""
        self.song_browser.refresh()
        self.status_bar.showMessage("Refreshed")

    def _on_show_stats(self) -> None:
        """Handle show statistics action."""
        if self._library is None:
            return

        from midi_analyzer.gui.dialogs.stats_dialog import StatsDialog

        dialog = StatsDialog(self._library, self)
        dialog.exec()

    def _on_play_pause(self) -> None:
        """Handle play/pause action from menu/keyboard shortcut."""
        self.playback_controls.toggle_playback()

    def _on_stop(self) -> None:
        """Handle stop action."""
        self.playback_controls.stop()
        # Reset piano roll position
        if hasattr(self.pattern_view, 'piano_roll'):
            self.pattern_view.piano_roll.set_playback_position(0.0)

    def _on_playback_position_changed(self, position: float, tempo: float) -> None:
        """Handle playback position updates.
        
        Args:
            position: Current position in seconds.
            tempo: Current tempo in BPM.
        """
        if hasattr(self.pattern_view, 'piano_roll'):
            self.pattern_view.piano_roll.set_playback_position(position, tempo)

    def _on_analyze_all(self) -> None:
        """Handle analyze all songs action."""
        if self._library is None:
            QMessageBox.information(self, "Analyze All", "Please open a library first.")
            return

        clips = self._library.list_clips()
        if not clips:
            QMessageBox.information(self, "Analyze All", "No songs in library.")
            return

        from PyQt6.QtWidgets import QProgressDialog

        progress = QProgressDialog("Analyzing songs...", "Cancel", 0, len(clips), self)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        analyzed = 0
        for i, clip in enumerate(clips):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            progress.setLabelText(f"Analyzing: {clip.artist} - {Path(clip.source_path).stem}")

            try:
                song = self._library.load_song(clip)
                self._ensure_song_analyzed(song)
                analyzed += 1
            except Exception:
                pass  # Skip failed songs

        progress.setValue(len(clips))
        self.status_bar.showMessage(f"Analyzed {analyzed} of {len(clips)} songs")

    def _on_find_similar(self) -> None:
        """Handle find similar action."""
        if self._current_song is None:
            QMessageBox.information(self, "Find Similar", "Please select a song first.")
            return

        from midi_analyzer.gui.dialogs.similarity_dialog import SimilarityDialog

        dialog = SimilarityDialog(self._current_song, self._library, self)
        dialog.exec()

    def _on_about(self) -> None:
        """Handle about action."""
        QMessageBox.about(
            self,
            "About MIDI Analyzer",
            "<h2>MIDI Analyzer</h2>"
            "<p>A tool for analyzing MIDI files and extracting reusable musical patterns.</p>"
            "<p>Version 0.1.0</p>"
            "<p><a href='https://github.com/gramster/midi-analyzer'>GitHub Repository</a></p>",
        )

    # Signal handlers
    def _on_song_selected(self, clip: ClipInfo) -> None:
        """Handle song selection."""
        self._current_song = clip

        if self._library:
            try:
                song = self._library.load_song(clip)
                
                # Analyze tracks if not already analyzed
                self._ensure_song_analyzed(song)
                
                self.song_detail.set_song(song, clip)
                self.playback_controls.set_song(song)
                self.pattern_view.show_song_analysis(song)
                self.status_bar.showMessage(
                    f"Selected: {clip.artist} - {Path(clip.source_path).stem}"
                )
            except Exception as e:
                self.status_bar.showMessage(f"Error loading song: {e}")

    def _ensure_song_analyzed(self, song: Song) -> None:
        """Ensure all tracks in the song have been analyzed."""
        from midi_analyzer.analysis.features import FeatureExtractor
        from midi_analyzer.analysis.roles import classify_track_role
        
        needs_analysis = any(
            track.notes and track.features is None
            for track in song.tracks
        )
        
        if not needs_analysis:
            return
        
        feature_extractor = FeatureExtractor()
        total_bars = song.total_bars or 1
        
        for track in song.tracks:
            if track.notes and track.features is None:
                track.features = feature_extractor.extract_features(track, total_bars)
                track.role_probs = classify_track_role(track)

    def _on_song_double_clicked(self, clip: ClipInfo) -> None:
        """Handle song double-click (play)."""
        self._on_song_selected(clip)
        self._on_play_pause()

    def _on_track_selected(self, track_id: int) -> None:
        """Handle track selection in detail view."""
        if self._library and self._current_song:
            try:
                song = self._library.load_song(self._current_song)
                for track in song.tracks:
                    if track.track_id == track_id:
                        self.pattern_view.show_track_patterns(track, song)
                        break
            except Exception as e:
                self.status_bar.showMessage(f"Error loading track: {e}")

    def _on_play_track(self, track_id: int) -> None:
        """Handle play track request."""
        if self._library and self._current_song:
            try:
                song = self._library.load_song(self._current_song)
                for track in song.tracks:
                    if track.track_id == track_id:
                        self.playback_controls.play_track(track, song)
                        break
            except Exception as e:
                self.status_bar.showMessage(f"Error playing track: {e}")

    def closeEvent(self, event) -> None:
        """Handle window close."""
        self.playback_controls.stop()
        if self._library:
            self._library.close()
        super().closeEvent(event)
