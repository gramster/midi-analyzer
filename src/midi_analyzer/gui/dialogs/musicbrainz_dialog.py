"""MusicBrainz lookup dialog for fetching metadata."""

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
    QLabel,
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
                    artist_sort_name = ""
                    disambiguation = recording.get("disambiguation", "")
                    
                    if "artist-credit" in recording:
                        artists = recording["artist-credit"]
                        if artists:
                            artist_data = artists[0].get("artist", {})
                            artist = artist_data.get("name", "")
                            artist_sort_name = artist_data.get("sort-name", "")

                    # Get tags/genres from recording
                    tags = []
                    genres = []
                    if "tag-list" in recording:
                        for tag in recording["tag-list"]:
                            tag_name = tag.get("name", "")
                            tag_count = int(tag.get("count", 0))
                            if tag_name:
                                tags.append({"name": tag_name, "count": tag_count})

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
                                                tag_count = int(tag.get("count", 0))
                                                if tag_name:
                                                    # Check if already in tags
                                                    existing = [t for t in tags if t["name"] == tag_name]
                                                    if existing:
                                                        existing[0]["count"] = max(existing[0]["count"], tag_count)
                                                    else:
                                                        tags.append({"name": tag_name, "count": tag_count, "from_artist": True})
                                    except Exception:
                                        pass

                    # Sort tags by count (most popular first) and extract names
                    tags.sort(key=lambda t: -t["count"])
                    
                    # Separate genre-like tags from descriptive tags
                    genre_keywords = {"rock", "pop", "jazz", "electronic", "classical", "metal", 
                                     "hip hop", "r&b", "country", "folk", "blues", "soul", "funk",
                                     "reggae", "punk", "indie", "alternative", "dance", "house",
                                     "techno", "trance", "ambient", "soundtrack", "world"}
                    
                    for tag in tags:
                        tag_lower = tag["name"].lower()
                        # Consider it a genre if it contains genre keywords or is short
                        is_genre = any(kw in tag_lower for kw in genre_keywords) or len(tag["name"]) < 15
                        if is_genre:
                            genres.append(tag["name"])
                        
                    results.append(
                        {
                            "title": title,
                            "artist": artist,
                            "artist_sort": artist_sort_name,
                            "disambiguation": disambiguation,
                            "genres": genres[:15],
                            "tags": [t["name"] for t in tags[:20]],
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
                            artist_sort = artist.get("sort-name", "")
                            tags = []
                            if "tag-list" in artist:
                                for tag in artist["tag-list"]:
                                    tags.append(tag.get("name", ""))

                            results.append(
                                {
                                    "title": "(Artist match only)",
                                    "artist": artist_name,
                                    "artist_sort": artist_sort,
                                    "disambiguation": artist.get("disambiguation", ""),
                                    "genres": tags[:15],
                                    "tags": tags[:20],
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
    """Dialog for looking up metadata from MusicBrainz."""

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
        self._selected_result: dict | None = None

        self.setWindowTitle("Lookup Metadata from MusicBrainz")
        self.setMinimumWidth(650)
        self.setMinimumHeight(600)
        self.setModal(True)

        self._setup_ui()
        self._load_initial_data()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

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
        results_group = QGroupBox("Search Results (click to select)")
        results_layout = QVBoxLayout(results_group)

        self.results_list = QListWidget()
        self.results_list.setMaximumHeight(120)
        self.results_list.itemSelectionChanged.connect(self._on_result_selected)
        results_layout.addWidget(self.results_list)

        layout.addWidget(results_group)

        # Metadata to apply
        apply_group = QGroupBox("Metadata to Apply")
        apply_layout = QVBoxLayout(apply_group)

        # Artist/Title updates
        names_layout = QFormLayout()
        
        artist_row = QHBoxLayout()
        self.update_artist_cb = QCheckBox()
        self.new_artist_input = QLineEdit()
        self.new_artist_input.setPlaceholderText("Artist name from MusicBrainz...")
        self.new_artist_input.setEnabled(False)
        artist_row.addWidget(self.update_artist_cb)
        artist_row.addWidget(self.new_artist_input)
        names_layout.addRow("Update Artist:", artist_row)
        
        title_row = QHBoxLayout()
        self.update_title_cb = QCheckBox()
        self.new_title_input = QLineEdit()
        self.new_title_input.setPlaceholderText("Title from MusicBrainz...")
        self.new_title_input.setEnabled(False)
        title_row.addWidget(self.update_title_cb)
        title_row.addWidget(self.new_title_input)
        names_layout.addRow("Update Title:", title_row)
        
        apply_layout.addLayout(names_layout)
        
        # Connect checkboxes to enable/disable inputs
        self.update_artist_cb.toggled.connect(self.new_artist_input.setEnabled)
        self.update_title_cb.toggled.connect(self.new_title_input.setEnabled)

        # Genre/Tag selection
        genre_label = QLabel("Genres/Tags (select to apply):")
        apply_layout.addWidget(genre_label)

        self.genre_list = QListWidget()
        self.genre_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.genre_list.setMaximumHeight(150)
        apply_layout.addWidget(self.genre_list)

        # Select All/None buttons for genres
        genre_btn_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._on_select_all_genres)
        genre_btn_layout.addWidget(self.select_all_btn)
        
        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.clicked.connect(self._on_select_no_genres)
        genre_btn_layout.addWidget(self.select_none_btn)
        genre_btn_layout.addStretch()
        apply_layout.addLayout(genre_btn_layout)

        # Options
        options_layout = QHBoxLayout()
        self.replace_genres = QCheckBox("Replace existing genres")
        self.replace_genres.setChecked(False)
        options_layout.addWidget(self.replace_genres)
        options_layout.addStretch()
        apply_layout.addLayout(options_layout)

        layout.addWidget(apply_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("secondary", True)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.apply_btn = QPushButton("Apply Selected Metadata")
        self.apply_btn.clicked.connect(self._on_apply)
        self.apply_btn.setEnabled(False)
        button_layout.addWidget(self.apply_btn)

        layout.addLayout(button_layout)

    def _on_select_all_genres(self) -> None:
        """Select all genres in the list."""
        self.genre_list.selectAll()

    def _on_select_no_genres(self) -> None:
        """Deselect all genres in the list."""
        self.genre_list.clearSelection()

    def _load_initial_data(self) -> None:
        """Load initial data into the form."""
        # Use MetadataExtractor to get better initial values
        from midi_analyzer.ingest.metadata import MetadataExtractor

        extractor = MetadataExtractor()
        try:
            import mido
            midi_file = mido.MidiFile(self._clip.source_path)
            metadata = extractor.extract(self._clip.source_path, midi_file)
        except Exception:
            metadata = extractor.extract(self._clip.source_path)

        # Set artist - prefer clip's stored artist, then extracted
        self.artist_input.setText(self._clip.artist or metadata.artist or "")

        # Set title - prefer extracted title
        self.title_input.setText(metadata.title or Path(self._clip.source_path).stem)

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
        self.new_artist_input.clear()
        self.new_title_input.clear()
        self.update_artist_cb.setChecked(False)
        self.update_title_cb.setChecked(False)
        self.apply_btn.setEnabled(False)
        self._selected_result = None

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
            if result.get("disambiguation"):
                text += f" ({result['disambiguation']})"
            if result["genres"]:
                text += f" [{', '.join(result['genres'][:3])}...]"

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

        self._selected_result = result

        # Populate artist/title fields
        mb_artist = result.get("artist", "")
        mb_title = result.get("title", "")
        
        self.new_artist_input.setText(mb_artist)
        self.new_title_input.setText(mb_title)
        
        # Auto-check if different from current
        current_artist = self._clip.artist or ""
        if mb_artist and mb_artist.lower() != current_artist.lower():
            self.update_artist_cb.setChecked(True)
        else:
            self.update_artist_cb.setChecked(False)
            
        if mb_title and mb_title != "(Artist match only)":
            self.update_title_cb.setChecked(True)
        else:
            self.update_title_cb.setChecked(False)

        # Populate genre/tag list - combine genres and tags, removing duplicates
        self.genre_list.clear()
        seen = set()
        
        # Add genres first (they're more likely to be relevant)
        for genre in result.get("genres", []):
            if genre.lower() not in seen:
                seen.add(genre.lower())
                item = QListWidgetItem(genre)
                item.setSelected(True)  # Select genres by default
                self.genre_list.addItem(item)
        
        # Add other tags (not selected by default)
        for tag in result.get("tags", []):
            if tag.lower() not in seen:
                seen.add(tag.lower())
                item = QListWidgetItem(tag)
                item.setSelected(False)
                self.genre_list.addItem(item)

        self.apply_btn.setEnabled(True)

    def _on_apply(self) -> None:
        """Apply selected metadata."""
        if self._library is None:
            QMessageBox.warning(self, "Error", "No library connected.")
            return

        # Gather what to update
        new_artist = None
        new_title = None
        selected_genres = []
        
        if self.update_artist_cb.isChecked():
            new_artist = self.new_artist_input.text().strip()
            if not new_artist:
                QMessageBox.warning(self, "Invalid", "Artist name cannot be empty.")
                return
                
        if self.update_title_cb.isChecked():
            new_title = self.new_title_input.text().strip()
            if not new_title or new_title == "(Artist match only)":
                QMessageBox.warning(self, "Invalid", "Title cannot be empty.")
                return
        
        # Get selected genres/tags
        for i in range(self.genre_list.count()):
            item = self.genre_list.item(i)
            if item.isSelected():
                selected_genres.append(item.text())

        # Check if anything to apply
        if not new_artist and not new_title and not selected_genres:
            QMessageBox.warning(self, "No Selection", "Please select at least one field to update.")
            return

        try:
            # Handle genres - merge or replace
            if selected_genres:
                if not self.replace_genres.isChecked():
                    existing = list(self._clip.genres)
                    for genre in selected_genres:
                        if genre.lower() not in [g.lower() for g in existing]:
                            existing.append(genre)
                    selected_genres = existing

            # Update all clips from the same song
            from midi_analyzer.library import ClipQuery

            song_clips = self._library.query(ClipQuery(limit=1000))
            updated_count = 0
            for clip in song_clips:
                if clip.song_id == self._clip.song_id:
                    update_kwargs = {}
                    if new_artist:
                        update_kwargs["artist"] = new_artist
                    if new_title:
                        update_kwargs["title"] = new_title
                    if selected_genres:
                        update_kwargs["genres"] = selected_genres
                    
                    if update_kwargs:
                        self._library.update_metadata(clip.clip_id, **update_kwargs)
                        updated_count += 1

            # Build success message
            changes = []
            if new_artist:
                changes.append(f"artist to '{new_artist}'")
            if new_title:
                changes.append(f"title to '{new_title}'")
            if selected_genres:
                changes.append(f"{len(selected_genres)} genres")
            
            QMessageBox.information(
                self, "Success", 
                f"Updated {', '.join(changes)} for {updated_count} clip(s)."
            )
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to apply metadata: {e}")

    def closeEvent(self, event) -> None:
        """Handle dialog close."""
        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.quit()
            self._search_thread.wait(1000)
        super().closeEvent(event)
