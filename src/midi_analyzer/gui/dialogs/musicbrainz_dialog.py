"""MusicBrainz lookup dialog for fetching genre information."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from midi_analyzer.library import ClipInfo, ClipLibrary


class MusicBrainzSearchThread(QThread):
    """Thread for searching MusicBrainz."""

    search_complete = pyqtSignal(list)  # List of results
    search_error = pyqtSignal(str)  # Error message

    def __init__(self, artist: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.artist = artist
        self.title = title

    def run(self) -> None:
        """Run the search."""
        try:
            import musicbrainzngs

            musicbrainzngs.set_useragent(
                "MIDI Analyzer", "0.1.0", "https://github.com/gramster/midi-analyzer"
            )

            results = []

            # Search for recordings
            query = f'"{self.title}"'
            if self.artist:
                query += f' AND artist:"{self.artist}"'

            try:
                search_result = musicbrainzngs.search_recordings(
                    query=query,
                    limit=10,
                )

                for recording in search_result.get("recording-list", []):
                    title = recording.get("title", "Unknown")
                    artist = ""
                    if "artist-credit" in recording:
                        artists = recording["artist-credit"]
                        if artists:
                            artist = artists[0].get("artist", {}).get("name", "")

                    # Get tags/genres
                    genres = []
                    if "tag-list" in recording:
                        for tag in recording["tag-list"]:
                            genres.append(tag.get("name", ""))

                    # Also try to get artist tags
                    if "artist-credit" in recording:
                        for ac in recording["artist-credit"]:
                            if isinstance(ac, dict) and "artist" in ac:
                                artist_id = ac["artist"].get("id")
                                if artist_id:
                                    try:
                                        artist_info = musicbrainzngs.get_artist_by_id(
                                            artist_id, includes=["tags"]
                                        )
                                        if (
                                            "artist" in artist_info
                                            and "tag-list" in artist_info["artist"]
                                        ):
                                            for tag in artist_info["artist"]["tag-list"]:
                                                tag_name = tag.get("name", "")
                                                if tag_name and tag_name not in genres:
                                                    genres.append(tag_name)
                                    except Exception:
                                        pass

                    results.append(
                        {
                            "title": title,
                            "artist": artist,
                            "genres": genres[:10],  # Limit genres
                            "id": recording.get("id", ""),
                        }
                    )
            except Exception:
                # Try artist search as fallback
                if self.artist:
                    try:
                        artist_result = musicbrainzngs.search_artists(
                            artist=self.artist,
                            limit=5,
                        )
                        for artist in artist_result.get("artist-list", []):
                            artist_name = artist.get("name", "")
                            genres = []
                            if "tag-list" in artist:
                                for tag in artist["tag-list"]:
                                    genres.append(tag.get("name", ""))

                            results.append(
                                {
                                    "title": "(Artist match)",
                                    "artist": artist_name,
                                    "genres": genres[:10],
                                    "id": artist.get("id", ""),
                                }
                            )
                    except Exception:
                        pass

            self.search_complete.emit(results)

        except ImportError:
            self.search_error.emit("musicbrainzngs library not installed")
        except Exception as e:
            self.search_error.emit(str(e))


class MusicBrainzDialog(QDialog):
    """Dialog for looking up genre information from MusicBrainz."""

    def __init__(
        self,
        clip: ClipInfo,
        library: ClipLibrary | None,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._clip = clip
        self._library = library
        self._search_thread: MusicBrainzSearchThread | None = None
        self._selected_genres: list[str] = []

        self.setWindowTitle("Fetch Genres from MusicBrainz")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.setModal(True)

        self._setup_ui()
        self._load_initial_data()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Search inputs
        search_group = QGroupBox("Search")
        search_layout = QFormLayout(search_group)

        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("Artist name...")
        search_layout.addRow("Artist:", self.artist_input)

        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Song title...")
        search_layout.addRow("Title:", self.title_input)

        search_btn_layout = QHBoxLayout()
        self.search_btn = QPushButton("Search MusicBrainz")
        self.search_btn.clicked.connect(self._on_search)
        search_btn_layout.addStretch()
        search_btn_layout.addWidget(self.search_btn)
        search_layout.addRow("", search_btn_layout)

        layout.addWidget(search_group)

        # Progress bar
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)  # Indeterminate
        layout.addWidget(self.progress)

        # Results
        results_group = QGroupBox("Search Results")
        results_layout = QVBoxLayout(results_group)

        self.results_list = QListWidget()
        self.results_list.itemSelectionChanged.connect(self._on_result_selected)
        results_layout.addWidget(self.results_list)

        layout.addWidget(results_group)

        # Genre selection
        genre_group = QGroupBox("Select Genres to Apply")
        genre_layout = QVBoxLayout(genre_group)

        self.genre_list = QListWidget()
        self.genre_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.genre_list.setMaximumHeight(150)
        genre_layout.addWidget(self.genre_list)

        # Options
        options_layout = QHBoxLayout()
        self.replace_genres = QCheckBox("Replace existing genres")
        self.replace_genres.setChecked(False)
        options_layout.addWidget(self.replace_genres)
        options_layout.addStretch()
        genre_layout.addLayout(options_layout)

        layout.addWidget(genre_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("secondary", True)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.apply_btn = QPushButton("Apply Selected Genres")
        self.apply_btn.clicked.connect(self._on_apply)
        self.apply_btn.setEnabled(False)
        button_layout.addWidget(self.apply_btn)

        layout.addLayout(button_layout)

    def _load_initial_data(self) -> None:
        """Load initial data into the form."""
        # Try to extract title and artist from filename
        filename = Path(self._clip.source_path).stem

        # Set artist from clip if available
        self.artist_input.setText(self._clip.artist or "")

        # Try to parse title from filename
        # Common formats: "Artist - Title", "Title", etc.
        if " - " in filename:
            parts = filename.split(" - ", 1)
            if not self._clip.artist:
                self.artist_input.setText(parts[0])
            self.title_input.setText(parts[1] if len(parts) > 1 else parts[0])
        else:
            self.title_input.setText(filename)

    def _on_search(self) -> None:
        """Start MusicBrainz search."""
        artist = self.artist_input.text().strip()
        title = self.title_input.text().strip()

        if not title and not artist:
            QMessageBox.warning(self, "Search", "Please enter at least a title or artist.")
            return

        # Clear previous results
        self.results_list.clear()
        self.genre_list.clear()
        self.apply_btn.setEnabled(False)

        # Show progress
        self.progress.setVisible(True)
        self.search_btn.setEnabled(False)

        # Start search thread
        self._search_thread = MusicBrainzSearchThread(artist, title)
        self._search_thread.search_complete.connect(self._on_search_complete)
        self._search_thread.search_error.connect(self._on_search_error)
        self._search_thread.finished.connect(self._on_search_finished)
        self._search_thread.start()

    def _on_search_complete(self, results: list) -> None:
        """Handle search results."""
        self.results_list.clear()

        if not results:
            self.results_list.addItem(QListWidgetItem("No results found"))
            return

        for result in results:
            text = f"{result['artist']} - {result['title']}"
            if result["genres"]:
                text += f" [{', '.join(result['genres'][:5])}]"

            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, result)
            self.results_list.addItem(item)

    def _on_search_error(self, error: str) -> None:
        """Handle search error."""
        QMessageBox.warning(self, "Search Error", f"Search failed: {error}")

    def _on_search_finished(self) -> None:
        """Handle search thread completion."""
        self.progress.setVisible(False)
        self.search_btn.setEnabled(True)
        self._search_thread = None

    def _on_result_selected(self) -> None:
        """Handle result selection."""
        current = self.results_list.currentItem()
        if current is None:
            return

        result = current.data(Qt.ItemDataRole.UserRole)
        if result is None:
            return

        # Populate genre list
        self.genre_list.clear()
        for genre in result.get("genres", []):
            item = QListWidgetItem(genre)
            item.setSelected(True)  # Select all by default
            self.genre_list.addItem(item)

        self.apply_btn.setEnabled(self.genre_list.count() > 0)

    def _on_apply(self) -> None:
        """Apply selected genres."""
        if self._library is None:
            QMessageBox.warning(self, "Error", "No library connected.")
            return

        # Get selected genres
        selected_genres = []
        for i in range(self.genre_list.count()):
            item = self.genre_list.item(i)
            if item.isSelected():
                selected_genres.append(item.text())

        if not selected_genres:
            QMessageBox.warning(self, "No Selection", "Please select at least one genre.")
            return

        try:
            # Get existing genres if not replacing
            if not self.replace_genres.isChecked():
                existing = list(self._clip.genres)
                for genre in selected_genres:
                    if genre.lower() not in [g.lower() for g in existing]:
                        existing.append(genre)
                selected_genres = existing

            # Update all clips from the same song
            from midi_analyzer.library import ClipQuery

            song_clips = self._library.query(ClipQuery(limit=1000))
            for clip in song_clips:
                if clip.song_id == self._clip.song_id:
                    self._library.update_metadata(
                        clip.clip_id,
                        genres=selected_genres,
                    )

            QMessageBox.information(
                self, "Success", f"Applied {len(selected_genres)} genres to the song."
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply genres: {e}")

    def closeEvent(self, event) -> None:
        """Handle dialog close."""
        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.quit()
            self._search_thread.wait(1000)
        super().closeEvent(event)
