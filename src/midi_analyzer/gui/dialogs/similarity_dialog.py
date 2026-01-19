"""Similarity search dialog for finding similar patterns."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from midi_analyzer.library import ClipInfo, ClipLibrary


class SimilaritySearchThread(QThread):
    """Thread for running similarity search."""

    search_complete = pyqtSignal(list)  # List of results
    search_error = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # current, total

    def __init__(
        self,
        source_clip: ClipInfo,
        library: ClipLibrary,
        track_id: int | None,
        max_results: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source_clip = source_clip
        self.library = library
        self.track_id = track_id
        self.max_results = max_results

    def run(self) -> None:
        """Run the similarity search."""
        try:
            from midi_analyzer.analysis.features import FeatureExtractor
            from midi_analyzer.library import ClipQuery

            # Load source song
            source_song = self.library.load_song(self.source_clip)

            # Get source tracks to compare
            if self.track_id is not None:
                source_tracks = [t for t in source_song.tracks if t.track_id == self.track_id]
            else:
                source_tracks = [t for t in source_song.tracks if t.notes]

            if not source_tracks:
                self.search_error.emit("No tracks to compare")
                return

            # Extract features from source
            feature_extractor = FeatureExtractor()
            source_features = []
            for track in source_tracks:
                track.features = feature_extractor.extract_features(
                    track, source_song.total_bars or 1
                )
                source_features.append(track.features)

            # Get all clips
            all_clips = self.library.query(ClipQuery(limit=10000))

            # Filter out source song
            other_clips = [c for c in all_clips if c.song_id != self.source_clip.song_id]

            # Group by song
            songs_to_check: dict[str, ClipInfo] = {}
            for clip in other_clips:
                if clip.song_id not in songs_to_check:
                    songs_to_check[clip.song_id] = clip

            results = []
            total = len(songs_to_check)

            for i, (song_id, clip) in enumerate(songs_to_check.items()):
                self.progress.emit(i + 1, total)

                try:
                    song = self.library.load_song(clip)

                    # Compare tracks
                    for track in song.tracks:
                        if not track.notes:
                            continue

                        track.features = feature_extractor.extract_features(
                            track, song.total_bars or 1
                        )

                        # Calculate similarity
                        for src_feat in source_features:
                            if src_feat is None or track.features is None:
                                continue

                            similarity = self._calculate_similarity(src_feat, track.features)

                            if similarity > 0.5:  # Threshold
                                results.append(
                                    {
                                        "clip": clip,
                                        "track_id": track.track_id,
                                        "track_name": track.name or f"Track {track.track_id}",
                                        "similarity": similarity,
                                    }
                                )
                except Exception:
                    # Skip problematic files
                    continue

            # Sort by similarity and limit
            results.sort(key=lambda x: -x["similarity"])
            results = results[: self.max_results]

            self.search_complete.emit(results)

        except Exception as e:
            self.search_error.emit(str(e))

    def _calculate_similarity(self, feat1, feat2) -> float:
        """Calculate similarity between two feature sets."""
        # Simple similarity based on key features
        similarity = 0.0
        weight_sum = 0.0

        # Note density similarity
        if feat1.note_density > 0 and feat2.note_density > 0:
            ratio = min(feat1.note_density, feat2.note_density) / max(
                feat1.note_density, feat2.note_density
            )
            similarity += ratio * 0.3
            weight_sum += 0.3

        # Pitch range similarity
        range1 = feat1.pitch_max - feat1.pitch_min if feat1.pitch_max > feat1.pitch_min else 1
        range2 = feat2.pitch_max - feat2.pitch_min if feat2.pitch_max > feat2.pitch_min else 1
        ratio = min(range1, range2) / max(range1, range2)
        similarity += ratio * 0.2
        weight_sum += 0.2

        # Velocity similarity
        if feat1.velocity_mean > 0 and feat2.velocity_mean > 0:
            ratio = min(feat1.velocity_mean, feat2.velocity_mean) / max(
                feat1.velocity_mean, feat2.velocity_mean
            )
            similarity += ratio * 0.2
            weight_sum += 0.2

        # Duration similarity
        if feat1.duration_mean > 0 and feat2.duration_mean > 0:
            ratio = min(feat1.duration_mean, feat2.duration_mean) / max(
                feat1.duration_mean, feat2.duration_mean
            )
            similarity += ratio * 0.3
            weight_sum += 0.3

        return similarity / weight_sum if weight_sum > 0 else 0.0


class SimilarityDialog(QDialog):
    """Dialog for finding similar patterns in other songs."""

    def __init__(
        self,
        clip: ClipInfo,
        library: ClipLibrary | None,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._clip = clip
        self._library = library
        self._search_thread: SimilaritySearchThread | None = None

        self.setWindowTitle("Find Similar Patterns")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        self.setModal(True)

        self._setup_ui()
        self._load_tracks()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)

        # Source info
        source_group = QGroupBox("Source")
        source_layout = QFormLayout(source_group)

        self.source_label = QLabel()
        source_layout.addRow("Song:", self.source_label)

        self.track_combo = QComboBox()
        self.track_combo.addItem("All Tracks", None)
        source_layout.addRow("Compare Track:", self.track_combo)

        layout.addWidget(source_group)

        # Search options
        options_group = QGroupBox("Search Options")
        options_layout = QFormLayout(options_group)

        self.max_results = QSpinBox()
        self.max_results.setRange(10, 500)
        self.max_results.setValue(50)
        options_layout.addRow("Max Results:", self.max_results)

        search_btn_layout = QHBoxLayout()
        search_btn_layout.addStretch()

        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._on_search)
        search_btn_layout.addWidget(self.search_btn)

        options_layout.addRow("", search_btn_layout)

        layout.addWidget(options_group)

        # Progress
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # Results
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)

        self.results_table = QTableWidget()
        self.results_table.setColumnCount(4)
        self.results_table.setHorizontalHeaderLabels(["Song", "Artist", "Track", "Similarity"])
        self.results_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Interactive
        )
        self.results_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Interactive
        )
        self.results_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.results_table.setColumnWidth(1, 120)
        self.results_table.setColumnWidth(2, 100)
        self.results_table.setColumnWidth(3, 80)
        self.results_table.verticalHeader().setVisible(False)
        self.results_table.setAlternatingRowColors(True)
        self.results_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.results_table.setSortingEnabled(True)
        results_layout.addWidget(self.results_table)

        layout.addWidget(results_group)

        # Buttons
        button_layout = QHBoxLayout()

        self.play_btn = QPushButton("Play Selected")
        self.play_btn.setEnabled(False)
        self.play_btn.clicked.connect(self._on_play)
        button_layout.addWidget(self.play_btn)

        button_layout.addStretch()

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def _load_tracks(self) -> None:
        """Load tracks for the source song."""
        if self._library is None or self._clip is None:
            return

        # Set source label
        self.source_label.setText(
            f"{self._clip.artist or 'Unknown'} - {Path(self._clip.source_path).stem}"
        )

        try:
            song = self._library.load_song(self._clip)

            from midi_analyzer.analysis.features import FeatureExtractor
            from midi_analyzer.analysis.roles import classify_track_role

            feature_extractor = FeatureExtractor()

            self.track_combo.clear()
            self.track_combo.addItem("All Tracks", None)

            for track in song.tracks:
                if not track.notes:
                    continue

                track.features = feature_extractor.extract_features(track, song.total_bars or 1)
                role_probs = classify_track_role(track)
                role = role_probs.primary_role()

                name = track.name or f"Track {track.track_id}"
                self.track_combo.addItem(f"{name} ({role.value})", track.track_id)

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not load tracks: {e}")

    def _on_search(self) -> None:
        """Start similarity search."""
        if self._library is None:
            return

        # Clear previous results
        self.results_table.setRowCount(0)
        self.play_btn.setEnabled(False)

        # Show progress
        self.progress.setVisible(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.search_btn.setEnabled(False)

        # Start search thread
        track_id = self.track_combo.currentData()

        self._search_thread = SimilaritySearchThread(
            self._clip,
            self._library,
            track_id,
            self.max_results.value(),
        )
        self._search_thread.search_complete.connect(self._on_search_complete)
        self._search_thread.search_error.connect(self._on_search_error)
        self._search_thread.progress.connect(self._on_progress)
        self._search_thread.finished.connect(self._on_search_finished)
        self._search_thread.start()

    def _on_search_complete(self, results: list) -> None:
        """Handle search completion."""
        self.results_table.setRowCount(0)

        for result in results:
            row = self.results_table.rowCount()
            self.results_table.insertRow(row)

            clip = result["clip"]

            # Song name
            name_item = QTableWidgetItem(Path(clip.source_path).stem)
            name_item.setData(Qt.ItemDataRole.UserRole, result)
            self.results_table.setItem(row, 0, name_item)

            # Artist
            self.results_table.setItem(row, 1, QTableWidgetItem(clip.artist or "Unknown"))

            # Track
            self.results_table.setItem(row, 2, QTableWidgetItem(result["track_name"]))

            # Similarity
            sim_item = QTableWidgetItem(f"{result['similarity']:.1%}")
            sim_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.results_table.setItem(row, 3, sim_item)

        self.play_btn.setEnabled(len(results) > 0)

    def _on_search_error(self, error: str) -> None:
        """Handle search error."""
        QMessageBox.warning(self, "Search Error", f"Search failed: {error}")

    def _on_progress(self, current: int, total: int) -> None:
        """Handle progress update."""
        if total > 0:
            self.progress.setValue(int(current * 100 / total))

    def _on_search_finished(self) -> None:
        """Handle search thread completion."""
        self.progress.setVisible(False)
        self.search_btn.setEnabled(True)
        self._search_thread = None

    def _on_play(self) -> None:
        """Play the selected result."""
        selected = self.results_table.selectedItems()
        if not selected or self._library is None:
            return

        row = selected[0].row()
        item = self.results_table.item(row, 0)
        if item is None:
            return

        result = item.data(Qt.ItemDataRole.UserRole)
        if result is None:
            return

        try:
            from midi_analyzer.player import MidiPlayer, PlaybackOptions

            song = self._library.load_song(result["clip"])
            track = None
            for t in song.tracks:
                if t.track_id == result["track_id"]:
                    track = t
                    break

            if track:
                player = MidiPlayer()
                options = PlaybackOptions(tempo_bpm=120, use_role_instrument=True)
                player.play_track(track, options)

        except Exception as e:
            QMessageBox.warning(self, "Playback Error", f"Could not play track: {e}")

    def closeEvent(self, event) -> None:
        """Handle dialog close."""
        if self._search_thread and self._search_thread.isRunning():
            self._search_thread.quit()
            self._search_thread.wait(1000)
        super().closeEvent(event)
