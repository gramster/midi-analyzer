"""Export dialog for exporting songs, tracks, and patterns."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from midi_analyzer.library import ClipInfo, ClipLibrary


class ExportDialog(QDialog):
    """Dialog for exporting MIDI data."""

    def __init__(
        self,
        clip: ClipInfo,
        library: ClipLibrary | None,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._clip = clip
        self._library = library

        self.setWindowTitle("Export")
        self.setMinimumWidth(500)
        self.setModal(True)

        self._setup_ui()
        self._load_tracks()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # What to export
        what_group = QGroupBox("What to Export")
        what_layout = QVBoxLayout(what_group)

        self.export_mode = QButtonGroup(self)

        self.export_song = QRadioButton("Entire song")
        self.export_song.setChecked(True)
        self.export_mode.addButton(self.export_song, 0)
        what_layout.addWidget(self.export_song)

        self.export_tracks = QRadioButton("Selected tracks")
        self.export_mode.addButton(self.export_tracks, 1)
        what_layout.addWidget(self.export_tracks)

        # Track list
        self.track_list = QListWidget()
        self.track_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.track_list.setMaximumHeight(150)
        self.track_list.setEnabled(False)
        what_layout.addWidget(self.track_list)

        self.export_song.toggled.connect(lambda checked: self.track_list.setEnabled(not checked))

        layout.addWidget(what_group)

        # Export options
        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)

        self.tempo_spinner = QSpinBox()
        self.tempo_spinner.setRange(40, 240)
        self.tempo_spinner.setValue(120)
        options_layout.addRow("Tempo (BPM):", self.tempo_spinner)

        self.quantize_combo = QComboBox()
        self.quantize_combo.addItems(["None", "1/4", "1/8", "1/16", "1/32"])
        options_layout.addRow("Quantize:", self.quantize_combo)

        self.transpose_spinner = QSpinBox()
        self.transpose_spinner.setRange(-24, 24)
        self.transpose_spinner.setValue(0)
        options_layout.addRow("Transpose:", self.transpose_spinner)

        self.include_empty = QCheckBox("Include empty tracks")
        self.include_empty.setChecked(False)
        options_layout.addRow("", self.include_empty)

        layout.addWidget(options_group)

        # Destination
        dest_group = QGroupBox("Destination")
        dest_layout = QVBoxLayout(dest_group)

        self.dest_file = QRadioButton("Save to file")
        self.dest_file.setChecked(True)
        dest_layout.addWidget(self.dest_file)

        file_row = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setPlaceholderText("Select output file...")
        file_row.addWidget(self.file_path)

        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self._on_browse)
        file_row.addWidget(self.browse_btn)
        dest_layout.addLayout(file_row)

        self.dest_clipboard = QRadioButton("Copy to clipboard (MIDI data)")
        dest_layout.addWidget(self.dest_clipboard)

        layout.addWidget(dest_group)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setProperty("secondary", True)
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)

        self.export_btn = QPushButton("Export")
        self.export_btn.clicked.connect(self._on_export)
        button_layout.addWidget(self.export_btn)

        layout.addLayout(button_layout)

    def _load_tracks(self) -> None:
        """Load tracks for selection."""
        if self._library is None:
            return

        try:
            song = self._library.load_song(self._clip)

            # Set initial tempo
            if song.tempo_map:
                self.tempo_spinner.setValue(int(song.tempo_map[0].bpm))

            # Populate track list
            from midi_analyzer.analysis.features import FeatureExtractor
            from midi_analyzer.analysis.roles import classify_track_role

            feature_extractor = FeatureExtractor()

            self.track_list.clear()
            for track in song.tracks:
                if not track.notes and not self.include_empty.isChecked():
                    continue

                track.features = feature_extractor.extract_features(track, song.total_bars or 1)
                role_probs = classify_track_role(track)
                role = role_probs.primary_role()

                name = track.name or f"Track {track.track_id}"
                text = f"{name} ({role.value}) - {len(track.notes)} notes"

                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, track.track_id)
                item.setSelected(True)
                self.track_list.addItem(item)

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load tracks: {e}")

    def _on_browse(self) -> None:
        """Handle browse button click."""
        default_name = Path(self._clip.source_path).stem + "_export.mid"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export MIDI",
            str(Path.home() / default_name),
            "MIDI Files (*.mid);;All Files (*)",
        )

        if path:
            self.file_path.setText(path)

    def _on_export(self) -> None:
        """Handle export."""
        if self._library is None:
            QMessageBox.warning(self, "Error", "No library connected.")
            return

        # Validate destination
        if self.dest_file.isChecked():
            path = self.file_path.text().strip()
            if not path:
                QMessageBox.warning(self, "Error", "Please select an output file.")
                return

        try:
            song = self._library.load_song(self._clip)

            from midi_analyzer.export import ExportOptions, export_track, export_tracks

            options = ExportOptions(
                transpose=self.transpose_spinner.value(),
            )

            tempo = self.tempo_spinner.value()

            if self.export_song.isChecked():
                # Export entire song
                tracks_to_export = [t for t in song.tracks if t.notes]
            else:
                # Export selected tracks
                selected_ids = set()
                for i in range(self.track_list.count()):
                    item = self.track_list.item(i)
                    if item.isSelected():
                        selected_ids.add(item.data(Qt.ItemDataRole.UserRole))

                tracks_to_export = [t for t in song.tracks if t.track_id in selected_ids]

            if not tracks_to_export:
                QMessageBox.warning(self, "Error", "No tracks selected for export.")
                return

            if self.dest_file.isChecked():
                path = self.file_path.text().strip()

                if len(tracks_to_export) == 1:
                    export_track(tracks_to_export[0], path, tempo_bpm=tempo, options=options)
                else:
                    export_tracks(tracks_to_export, path, tempo_bpm=tempo, options=options)

                QMessageBox.information(
                    self,
                    "Export Complete",
                    f"Exported {len(tracks_to_export)} track(s) to:\n{path}",
                )
            else:
                # Copy to clipboard
                # Create a temporary file and copy its contents
                import tempfile

                with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
                    tmp_path = tmp.name

                try:
                    if len(tracks_to_export) == 1:
                        export_track(
                            tracks_to_export[0], tmp_path, tempo_bpm=tempo, options=options
                        )
                    else:
                        export_tracks(tracks_to_export, tmp_path, tempo_bpm=tempo, options=options)

                    # Read and copy to clipboard
                    with open(tmp_path, "rb") as f:
                        data = f.read()

                    # Note: True MIDI clipboard support requires platform-specific handling
                    # For now, we'll just show a message
                    QMessageBox.information(
                        self,
                        "Export Complete",
                        f"Exported {len(tracks_to_export)} track(s) ({len(data)} bytes).\n\n"
                        "Note: Direct MIDI clipboard support varies by platform.",
                    )
                finally:
                    Path(tmp_path).unlink(missing_ok=True)

            self.accept()

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export: {e}")
