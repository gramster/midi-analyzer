"""Metadata editing dialog."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from midi_analyzer.library import ClipInfo, ClipLibrary


# Common genre tags for quick selection
COMMON_GENRES = [
    "electronic",
    "house",
    "techno",
    "trance",
    "ambient",
    "downtempo",
    "progressive house",
    "deep house",
    "melodic techno",
    "minimal",
    "drum and bass",
    "dubstep",
    "breakbeat",
    "electro",
    "synthwave",
    "chillout",
    "lofi",
    "hip hop",
    "jazz",
    "classical",
    "rock",
    "pop",
    "indie",
    "folk",
    "world",
]


class MetadataDialog(QDialog):
    """Dialog for editing song metadata."""

    def __init__(
        self,
        clip: ClipInfo,
        library: ClipLibrary | None,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._clip = clip
        self._library = library

        self.setWindowTitle("Edit Metadata")
        self.setMinimumWidth(500)
        self.setModal(True)

        self._setup_ui()
        self._load_data()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # File info (read-only)
        file_group = QGroupBox("File Information")
        file_layout = QFormLayout(file_group)

        self.name_label = QLabel()
        self.name_label.setWordWrap(True)
        file_layout.addRow("Name:", self.name_label)

        self.path_label = QLabel()
        self.path_label.setWordWrap(True)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        file_layout.addRow("Path:", self.path_label)

        layout.addWidget(file_group)

        # Editable metadata
        meta_group = QGroupBox("Metadata")
        meta_layout = QFormLayout(meta_group)

        self.artist_input = QLineEdit()
        self.artist_input.setPlaceholderText("Enter artist name...")
        meta_layout.addRow("Artist:", self.artist_input)

        layout.addWidget(meta_group)

        # Genre tags
        genre_group = QGroupBox("Genres")
        genre_layout = QVBoxLayout(genre_group)

        # Current genres list
        genre_layout.addWidget(QLabel("Current genres:"))
        self.genre_list = QListWidget()
        self.genre_list.setMaximumHeight(100)
        genre_layout.addWidget(self.genre_list)

        # Add genre controls
        add_layout = QHBoxLayout()

        self.genre_combo = QComboBox()
        self.genre_combo.setEditable(True)
        self.genre_combo.addItems(COMMON_GENRES)
        self.genre_combo.setCurrentText("")
        self.genre_combo.lineEdit().setPlaceholderText("Select or type a genre...")
        add_layout.addWidget(self.genre_combo, 1)

        self.add_genre_btn = QPushButton("Add")
        self.add_genre_btn.clicked.connect(self._on_add_genre)
        add_layout.addWidget(self.add_genre_btn)

        self.remove_genre_btn = QPushButton("Remove")
        self.remove_genre_btn.setProperty("secondary", True)
        self.remove_genre_btn.clicked.connect(self._on_remove_genre)
        add_layout.addWidget(self.remove_genre_btn)

        genre_layout.addLayout(add_layout)
        layout.addWidget(genre_group)

        # Tags
        tags_group = QGroupBox("Tags")
        tags_layout = QVBoxLayout(tags_group)

        self.tags_input = QLineEdit()
        self.tags_input.setPlaceholderText("Comma-separated tags...")
        tags_layout.addWidget(self.tags_input)

        layout.addWidget(tags_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("secondary", True)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_btn)

        layout.addLayout(button_layout)

    def _load_data(self) -> None:
        """Load current data into the form."""
        # Try to extract name from metadata
        from midi_analyzer.ingest.metadata import MetadataExtractor
        
        extractor = MetadataExtractor()
        metadata = extractor.extract(self._clip.source_path)
        
        # Use extracted title if available, otherwise fallback to filename
        name = metadata.title or Path(self._clip.source_path).stem
        if metadata.artist and not self._clip.artist:
            # Also pre-fill artist if we found one and there isn't one already
            self.artist_input.setText(metadata.artist)
        
        self.name_label.setText(name)
        self.path_label.setText(self._clip.source_path)
        if self._clip.artist:
            self.artist_input.setText(self._clip.artist)

        # Load genres
        self.genre_list.clear()
        for genre in self._clip.genres:
            item = QListWidgetItem(genre)
            self.genre_list.addItem(item)

        # Load tags
        self.tags_input.setText(", ".join(self._clip.tags) if self._clip.tags else "")

    def _on_add_genre(self) -> None:
        """Add a genre tag."""
        genre = self.genre_combo.currentText().strip().lower()
        if not genre:
            return

        # Check if already exists
        for i in range(self.genre_list.count()):
            if self.genre_list.item(i).text().lower() == genre:
                return

        self.genre_list.addItem(QListWidgetItem(genre))
        self.genre_combo.setCurrentText("")

    def _on_remove_genre(self) -> None:
        """Remove selected genre."""
        current = self.genre_list.currentItem()
        if current:
            row = self.genre_list.row(current)
            self.genre_list.takeItem(row)

    def _on_save(self) -> None:
        """Save the metadata."""
        if self._library is None:
            QMessageBox.warning(self, "Error", "No library connected.")
            return

        # Collect data
        artist = self.artist_input.text().strip()

        genres = []
        for i in range(self.genre_list.count()):
            genres.append(self.genre_list.item(i).text())

        tags_text = self.tags_input.text().strip()
        tags = [t.strip() for t in tags_text.split(",") if t.strip()] if tags_text else []

        try:
            # Update all clips from the same song
            from midi_analyzer.library import ClipQuery

            song_clips = self._library.query(ClipQuery(limit=1000))
            for clip in song_clips:
                if clip.song_id == self._clip.song_id:
                    self._library.update_metadata(
                        clip.clip_id,
                        genres=genres,
                        artist=artist,
                        tags=tags,
                    )

            QMessageBox.information(self, "Success", "Metadata saved successfully.")
            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save metadata: {e}")
