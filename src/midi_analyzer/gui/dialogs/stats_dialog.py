"""Statistics dialog showing library overview."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from midi_analyzer.library import ClipLibrary


class StatsDialog(QDialog):
    """Dialog showing library statistics."""

    def __init__(
        self,
        library: ClipLibrary,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._library = library

        self.setWindowTitle("Library Statistics")
        self.setMinimumWidth(500)
        self.setMinimumHeight(400)
        self.setModal(True)

        self._setup_ui()
        self._load_stats()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Overview
        overview_group = QGroupBox("Overview")
        overview_layout = QFormLayout(overview_group)

        self.songs_label = QLabel("-")
        overview_layout.addRow("Total Songs:", self.songs_label)

        self.clips_label = QLabel("-")
        overview_layout.addRow("Total Clips:", self.clips_label)

        self.artists_label = QLabel("-")
        overview_layout.addRow("Unique Artists:", self.artists_label)

        self.genres_label = QLabel("-")
        overview_layout.addRow("Unique Genres:", self.genres_label)

        layout.addWidget(overview_group)

        # Tabs for detailed stats
        tabs = QTabWidget()

        # Roles tab
        roles_widget = QWidget()
        roles_layout = QVBoxLayout(roles_widget)

        self.roles_table = QTableWidget()
        self.roles_table.setColumnCount(2)
        self.roles_table.setHorizontalHeaderLabels(["Role", "Count"])
        self.roles_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.roles_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.roles_table.setColumnWidth(1, 80)
        self.roles_table.verticalHeader().setVisible(False)
        self.roles_table.setAlternatingRowColors(True)
        roles_layout.addWidget(self.roles_table)

        tabs.addTab(roles_widget, "By Role")

        # Genres tab
        genres_widget = QWidget()
        genres_layout = QVBoxLayout(genres_widget)

        self.genres_table = QTableWidget()
        self.genres_table.setColumnCount(2)
        self.genres_table.setHorizontalHeaderLabels(["Genre", "Count"])
        self.genres_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.genres_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.genres_table.setColumnWidth(1, 80)
        self.genres_table.verticalHeader().setVisible(False)
        self.genres_table.setAlternatingRowColors(True)
        self.genres_table.setSortingEnabled(True)
        genres_layout.addWidget(self.genres_table)

        tabs.addTab(genres_widget, "By Genre")

        # Artists tab
        artists_widget = QWidget()
        artists_layout = QVBoxLayout(artists_widget)

        self.artists_table = QTableWidget()
        self.artists_table.setColumnCount(2)
        self.artists_table.setHorizontalHeaderLabels(["Artist", "Songs"])
        self.artists_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.artists_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.artists_table.setColumnWidth(1, 80)
        self.artists_table.verticalHeader().setVisible(False)
        self.artists_table.setAlternatingRowColors(True)
        self.artists_table.setSortingEnabled(True)
        artists_layout.addWidget(self.artists_table)

        tabs.addTab(artists_widget, "By Artist")

        layout.addWidget(tabs)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def _load_stats(self) -> None:
        """Load and display statistics."""
        stats = self._library.get_stats()

        # Overview
        self.songs_label.setText(str(stats.total_songs))
        self.clips_label.setText(str(stats.total_clips))
        self.artists_label.setText(str(len(stats.artists)))
        self.genres_label.setText(str(len(stats.clips_by_genre)))

        # Roles table
        self.roles_table.setRowCount(0)
        for role, count in sorted(stats.clips_by_role.items(), key=lambda x: -x[1]):
            row = self.roles_table.rowCount()
            self.roles_table.insertRow(row)
            self.roles_table.setItem(row, 0, QTableWidgetItem(role))
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.roles_table.setItem(row, 1, count_item)

        # Genres table
        self.genres_table.setRowCount(0)
        for genre, count in sorted(stats.clips_by_genre.items(), key=lambda x: -x[1]):
            row = self.genres_table.rowCount()
            self.genres_table.insertRow(row)
            self.genres_table.setItem(row, 0, QTableWidgetItem(genre))
            count_item = QTableWidgetItem(str(count))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.genres_table.setItem(row, 1, count_item)

        # Artists table - count songs per artist
        from midi_analyzer.library import ClipQuery

        all_clips = self._library.query(ClipQuery(limit=100000))
        artist_songs: dict[str, set[str]] = {}

        for clip in all_clips:
            artist = clip.artist or "Unknown"
            if artist not in artist_songs:
                artist_songs[artist] = set()
            artist_songs[artist].add(clip.song_id)

        self.artists_table.setRowCount(0)
        for artist, songs in sorted(artist_songs.items(), key=lambda x: -len(x[1])):
            row = self.artists_table.rowCount()
            self.artists_table.insertRow(row)
            self.artists_table.setItem(row, 0, QTableWidgetItem(artist))
            count_item = QTableWidgetItem(str(len(songs)))
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.artists_table.setItem(row, 1, count_item)
