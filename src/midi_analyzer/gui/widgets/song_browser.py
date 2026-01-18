"""Song browser widget for browsing and filtering songs."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QModelIndex, QSortFilterProxyModel, Qt, pyqtSignal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from midi_analyzer.library import ClipInfo, ClipLibrary


class SongFilterProxyModel(QSortFilterProxyModel):
    """Proxy model for filtering songs."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.artist_filter = ""
        self.genre_filter = ""
        self.search_text = ""
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def set_artist_filter(self, artist: str) -> None:
        """Set artist filter."""
        self.artist_filter = artist.lower()
        self.invalidateFilter()

    def set_genre_filter(self, genre: str) -> None:
        """Set genre filter."""
        self.genre_filter = genre.lower()
        self.invalidateFilter()

    def set_search_text(self, text: str) -> None:
        """Set search text filter."""
        self.search_text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """Check if row passes filters."""
        model = self.sourceModel()
        if model is None:
            return True

        # Get data from each column
        name_idx = model.index(source_row, 0, source_parent)
        artist_idx = model.index(source_row, 1, source_parent)
        genres_idx = model.index(source_row, 2, source_parent)

        name = model.data(name_idx, Qt.ItemDataRole.DisplayRole) or ""
        artist = model.data(artist_idx, Qt.ItemDataRole.DisplayRole) or ""
        genres = model.data(genres_idx, Qt.ItemDataRole.DisplayRole) or ""

        # Apply filters
        if self.artist_filter and self.artist_filter not in artist.lower():
            return False

        if self.genre_filter and self.genre_filter not in genres.lower():
            return False

        if self.search_text:
            search_text = self.search_text
            if (
                search_text not in name.lower()
                and search_text not in artist.lower()
                and search_text not in genres.lower()
            ):
                return False

        return True


class SongBrowserWidget(QWidget):
    """Widget for browsing songs in the library."""

    # Signals
    song_selected = pyqtSignal(object)  # ClipInfo
    song_double_clicked = pyqtSignal(object)  # ClipInfo

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._library: ClipLibrary | None = None
        self._clips: list[ClipInfo] = []

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Title
        title = QLabel("Songs")
        title.setProperty("heading", True)
        layout.addWidget(title)

        # Search box
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search songs...")
        self.search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)

        # Filter row
        filter_layout = QHBoxLayout()

        filter_layout.addWidget(QLabel("Artist:"))
        self.artist_filter = QComboBox()
        self.artist_filter.setMinimumWidth(150)
        self.artist_filter.addItem("All Artists", "")
        filter_layout.addWidget(self.artist_filter)

        filter_layout.addWidget(QLabel("Genre:"))
        self.genre_filter = QComboBox()
        self.genre_filter.setMinimumWidth(150)
        self.genre_filter.addItem("All Genres", "")
        filter_layout.addWidget(self.genre_filter)

        filter_layout.addStretch()

        self.clear_filters_btn = QPushButton("Clear")
        self.clear_filters_btn.setProperty("secondary", True)
        self.clear_filters_btn.setMaximumWidth(80)
        filter_layout.addWidget(self.clear_filters_btn)

        layout.addLayout(filter_layout)

        # Song table
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["Name", "Artist", "Genres", "Tracks", "Bars"])

        self.proxy_model = SongFilterProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setDynamicSortFilter(True)

        self.table = QTableView()
        self.table.setModel(self.proxy_model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)

        # Set column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 150)
        header.resizeSection(2, 150)
        header.resizeSection(3, 60)
        header.resizeSection(4, 60)

        layout.addWidget(self.table)

        # Status row
        status_layout = QHBoxLayout()
        self.status_label = QLabel("0 songs")
        self.status_label.setProperty("subheading", True)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.search_input.textChanged.connect(self._on_search_changed)
        self.artist_filter.currentIndexChanged.connect(self._on_artist_filter_changed)
        self.genre_filter.currentIndexChanged.connect(self._on_genre_filter_changed)
        self.clear_filters_btn.clicked.connect(self._on_clear_filters)
        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self.table.doubleClicked.connect(self._on_double_click)

    def set_library(self, library: ClipLibrary) -> None:
        """Set the clip library.

        Args:
            library: The clip library to browse.
        """
        self._library = library
        self._populate_filters()
        self.refresh()

    def refresh(self) -> None:
        """Refresh the song list."""
        if self._library is None:
            return

        # Get all clips, grouped by song
        from midi_analyzer.library import ClipQuery

        # Query with high limit to get all
        all_clips = self._library.query(ClipQuery(limit=100000))

        # Group by song_id and keep one representative clip per song
        songs: dict[str, ClipInfo] = {}
        song_track_counts: dict[str, int] = {}

        for clip in all_clips:
            if clip.song_id not in songs:
                songs[clip.song_id] = clip
                song_track_counts[clip.song_id] = 1
            else:
                song_track_counts[clip.song_id] += 1

        self._clips = list(songs.values())

        # Update table
        self.model.removeRows(0, self.model.rowCount())

        for clip in self._clips:
            name_item = QStandardItem(Path(clip.source_path).stem)
            name_item.setData(clip, Qt.ItemDataRole.UserRole)

            artist_item = QStandardItem(clip.artist or "Unknown")
            genres_item = QStandardItem(", ".join(clip.genres) if clip.genres else "")
            tracks_item = QStandardItem(str(song_track_counts.get(clip.song_id, 1)))
            tracks_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            bars_item = QStandardItem(str(clip.duration_bars))
            bars_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.model.appendRow([name_item, artist_item, genres_item, tracks_item, bars_item])

        # Update status
        self._update_status()

    def _populate_filters(self) -> None:
        """Populate filter dropdowns."""
        if self._library is None:
            return

        # Populate artists
        self.artist_filter.clear()
        self.artist_filter.addItem("All Artists", "")
        for artist in self._library.list_artists():
            self.artist_filter.addItem(artist, artist)

        # Populate genres
        self.genre_filter.clear()
        self.genre_filter.addItem("All Genres", "")
        for genre in self._library.list_genres():
            self.genre_filter.addItem(genre, genre)

    def _update_status(self) -> None:
        """Update the status label."""
        visible = self.proxy_model.rowCount()
        total = self.model.rowCount()

        if visible == total:
            self.status_label.setText(f"{total} songs")
        else:
            self.status_label.setText(f"{visible} of {total} songs")

    def _on_search_changed(self, text: str) -> None:
        """Handle search text change."""
        self.proxy_model.set_search_text(text)
        self._update_status()

    def _on_artist_filter_changed(self, index: int) -> None:
        """Handle artist filter change."""
        artist = self.artist_filter.currentData() or ""
        self.proxy_model.set_artist_filter(artist)
        self._update_status()

    def _on_genre_filter_changed(self, index: int) -> None:
        """Handle genre filter change."""
        genre = self.genre_filter.currentData() or ""
        self.proxy_model.set_genre_filter(genre)
        self._update_status()

    def _on_clear_filters(self) -> None:
        """Clear all filters."""
        self.search_input.clear()
        self.artist_filter.setCurrentIndex(0)
        self.genre_filter.setCurrentIndex(0)

    def _on_selection_changed(self) -> None:
        """Handle selection change."""
        indexes = self.table.selectionModel().selectedRows()
        if indexes:
            # Map from proxy to source
            source_index = self.proxy_model.mapToSource(indexes[0])
            item = self.model.item(source_index.row(), 0)
            if item:
                clip = item.data(Qt.ItemDataRole.UserRole)
                if clip:
                    self.song_selected.emit(clip)

    def _on_double_click(self, index: QModelIndex) -> None:
        """Handle double-click on row."""
        source_index = self.proxy_model.mapToSource(index)
        item = self.model.item(source_index.row(), 0)
        if item:
            clip = item.data(Qt.ItemDataRole.UserRole)
            if clip:
                self.song_double_clicked.emit(clip)

    def get_selected_song(self) -> ClipInfo | None:
        """Get the currently selected song."""
        indexes = self.table.selectionModel().selectedRows()
        if indexes:
            source_index = self.proxy_model.mapToSource(indexes[0])
            item = self.model.item(source_index.row(), 0)
            if item:
                return item.data(Qt.ItemDataRole.UserRole)
        return None
