"""Song detail widget for showing song information and tracks."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from midi_analyzer.library import ClipInfo
    from midi_analyzer.models.core import Song, Track


class SongDetailWidget(QWidget):
    """Widget showing detailed information about a song."""

    # Signals
    track_selected = pyqtSignal(int)  # track_id
    play_track_requested = pyqtSignal(int)  # track_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._song: Song | None = None
        self._clip: ClipInfo | None = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Title
        title = QLabel("Song Details")
        title.setProperty("heading", True)
        layout.addWidget(title)

        # Tab widget for different views
        self.tabs = QTabWidget()

        # Info tab
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(8, 8, 8, 8)

        # Metadata group
        meta_group = QGroupBox("Metadata")
        meta_layout = QFormLayout(meta_group)
        meta_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        meta_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)

        self.name_label = QLabel("-")
        self.name_label.setWordWrap(True)
        self.name_label.setMinimumWidth(200)
        meta_layout.addRow("Name:", self.name_label)

        self.artist_label = QLabel("-")
        meta_layout.addRow("Artist:", self.artist_label)

        self.genres_label = QLabel("-")
        self.genres_label.setWordWrap(True)
        meta_layout.addRow("Genres:", self.genres_label)

        self.path_label = QLabel("-")
        self.path_label.setWordWrap(True)
        self.path_label.setMinimumWidth(200)
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        meta_layout.addRow("Path:", self.path_label)

        info_layout.addWidget(meta_group)

        # Stats group
        stats_group = QGroupBox("Statistics")
        stats_layout = QFormLayout(stats_group)
        stats_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.tempo_label = QLabel("-")
        stats_layout.addRow("Tempo:", self.tempo_label)

        self.time_sig_label = QLabel("-")
        stats_layout.addRow("Time Sig:", self.time_sig_label)

        self.bars_label = QLabel("-")
        stats_layout.addRow("Bars:", self.bars_label)

        self.tracks_label = QLabel("-")
        stats_layout.addRow("Tracks:", self.tracks_label)

        self.notes_label = QLabel("-")
        stats_layout.addRow("Total Notes:", self.notes_label)

        info_layout.addWidget(stats_group)
        info_layout.addStretch()

        self.tabs.addTab(info_widget, "Info")

        # Tracks tab
        tracks_widget = QWidget()
        tracks_layout = QVBoxLayout(tracks_widget)
        tracks_layout.setContentsMargins(8, 8, 8, 8)

        # Track table
        self.track_table = QTableWidget()
        self.track_table.setColumnCount(6)
        self.track_table.setHorizontalHeaderLabels(["Name", "Role", "Ch", "Notes", "Bars", ""])
        self.track_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.track_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.track_table.setAlternatingRowColors(True)
        self.track_table.setShowGrid(False)
        self.track_table.verticalHeader().setVisible(False)

        header = self.track_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 80)
        header.resizeSection(2, 40)
        header.resizeSection(3, 60)
        header.resizeSection(4, 50)
        header.resizeSection(5, 60)

        tracks_layout.addWidget(self.track_table)

        self.tabs.addTab(tracks_widget, "Tracks")

        # Sections tab
        sections_widget = QWidget()
        sections_layout = QVBoxLayout(sections_widget)
        sections_layout.setContentsMargins(8, 8, 8, 8)

        self.sections_text = QTextEdit()
        self.sections_text.setReadOnly(True)
        self.sections_text.setPlaceholderText("Click 'Analyze' to see song sections...")
        sections_layout.addWidget(self.sections_text)

        self.tabs.addTab(sections_widget, "Sections")

        layout.addWidget(self.tabs)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.track_table.itemSelectionChanged.connect(self._on_track_selection_changed)

    def set_song(self, song: Song, clip: ClipInfo) -> None:
        """Set the song to display.

        Args:
            song: Song object with full data.
            clip: Clip info from library.
        """
        self._song = song
        self._clip = clip
        self._update_info()
        self._update_tracks()
        self._update_sections()

    def refresh(self) -> None:
        """Refresh the display."""
        if self._song and self._clip:
            self._update_info()

    def clear(self) -> None:
        """Clear the display."""
        self._song = None
        self._clip = None

        self.name_label.setText("-")
        self.artist_label.setText("-")
        self.genres_label.setText("-")
        self.path_label.setText("-")
        self.tempo_label.setText("-")
        self.time_sig_label.setText("-")
        self.bars_label.setText("-")
        self.tracks_label.setText("-")
        self.notes_label.setText("-")

        self.track_table.setRowCount(0)
        self.sections_text.clear()

    def _update_info(self) -> None:
        """Update the info display."""
        if self._song is None or self._clip is None:
            return

        song = self._song
        clip = self._clip

        # Extract proper title from metadata
        from midi_analyzer.ingest.metadata import MetadataExtractor

        extractor = MetadataExtractor()
        try:
            import mido

            midi_file = mido.MidiFile(clip.source_path)
            metadata = extractor.extract(clip.source_path, midi_file)
        except Exception:
            metadata = extractor.extract(clip.source_path)

        # Metadata - use extracted title or fallback to filename
        name = metadata.title or Path(clip.source_path).stem
        self.name_label.setText(name)
        self.artist_label.setText(clip.artist or metadata.artist or "Unknown")
        self.genres_label.setText(", ".join(clip.genres) if clip.genres else "None")
        self.path_label.setText(clip.source_path)

        # Stats
        tempo = song.tempo_map[0].tempo_bpm if song.tempo_map else 120.0
        self.tempo_label.setText(f"{tempo:.1f} BPM")

        if song.time_sig_map:
            ts = song.time_sig_map[0]
            self.time_sig_label.setText(f"{ts.numerator}/{ts.denominator}")
        else:
            self.time_sig_label.setText("4/4")

        self.bars_label.setText(str(song.total_bars or 0))
        self.tracks_label.setText(str(len(song.tracks)))

        total_notes = sum(len(t.notes) for t in song.tracks)
        self.notes_label.setText(str(total_notes))

    def _update_tracks(self) -> None:
        """Update the tracks table."""
        if self._song is None:
            return

        self.track_table.setRowCount(0)

        from midi_analyzer.analysis.features import FeatureExtractor
        from midi_analyzer.analysis.roles import classify_track_role

        feature_extractor = FeatureExtractor()

        for track in self._song.tracks:
            if not track.notes:
                continue

            row = self.track_table.rowCount()
            self.track_table.insertRow(row)

            # Name
            name_item = QTableWidgetItem(track.name or f"Track {track.track_id}")
            name_item.setData(Qt.ItemDataRole.UserRole, track.track_id)
            self.track_table.setItem(row, 0, name_item)

            # Role
            track.features = feature_extractor.extract_features(track, self._song.total_bars or 1)
            role_probs = classify_track_role(track)
            role = role_probs.primary_role()
            role_item = QTableWidgetItem(role.value)
            self.track_table.setItem(row, 1, role_item)

            # Channel
            ch_item = QTableWidgetItem(str(track.channel))
            ch_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.track_table.setItem(row, 2, ch_item)

            # Notes
            notes_item = QTableWidgetItem(str(len(track.notes)))
            notes_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.track_table.setItem(row, 3, notes_item)

            # Bars - estimate from notes
            if track.notes:
                max_beat = max(n.start_beat + n.duration_beats for n in track.notes)
                bars = int(max_beat / 4) + 1  # Assuming 4/4
            else:
                bars = 0
            bars_item = QTableWidgetItem(str(bars))
            bars_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.track_table.setItem(row, 4, bars_item)

            # Play button
            play_btn = QPushButton("▶")
            play_btn.setMaximumWidth(50)
            play_btn.clicked.connect(lambda checked, tid=track.track_id: self._on_play_track(tid))
            self.track_table.setCellWidget(row, 5, play_btn)

    def _update_sections(self) -> None:
        """Update the sections display."""
        if self._song is None:
            self.sections_text.clear()
            return

        try:
            from midi_analyzer.analysis.sections import analyze_sections

            sections_result = analyze_sections(self._song)

            lines = []
            lines.append(f"Total Sections: {len(sections_result.sections)}")
            lines.append(
                f"Form Labels: {sorted(set(s.form_label for s in sections_result.sections))}"
            )
            lines.append("")

            for section in sections_result.sections:
                type_str = f" ({section.type_hint.value})" if section.type_hint else ""
                lines.append(
                    f"[{section.form_label}]{type_str}: Bars {section.start_bar + 1}-{section.end_bar}"
                )

            self.sections_text.setPlainText("\n".join(lines))
        except Exception as e:
            self.sections_text.setPlainText(f"Error analyzing sections: {e}")

    def _on_track_selection_changed(self) -> None:
        """Handle track selection change."""
        selected = self.track_table.selectedItems()
        if selected:
            row = selected[0].row()
            name_item = self.track_table.item(row, 0)
            if name_item:
                track_id = name_item.data(Qt.ItemDataRole.UserRole)
                if track_id is not None:
                    self.track_selected.emit(track_id)

    def _on_play_track(self, track_id: int) -> None:
        """Handle play track button click."""
        self.play_track_requested.emit(track_id)

    def get_selected_track(self) -> Track | None:
        """Get the currently selected track."""
        if self._song is None:
            return None

        selected = self.track_table.selectedItems()
        if selected:
            row = selected[0].row()
            name_item = self.track_table.item(row, 0)
            if name_item:
                track_id = name_item.data(Qt.ItemDataRole.UserRole)
                for track in self._song.tracks:
                    if track.track_id == track_id:
                        return track
        return None
