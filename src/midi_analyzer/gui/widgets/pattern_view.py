"""Pattern visualization widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from midi_analyzer.analysis.arpeggios import ArpAnalysis
    from midi_analyzer.models.core import NoteEvent, Song, Track


# Color palette for track roles
ROLE_COLORS = {
    "drums": QColor("#ff6b6b"),
    "bass": QColor("#4ecdc4"),
    "chords": QColor("#ffe66d"),
    "pad": QColor("#95e1d3"),
    "lead": QColor("#f38181"),
    "arp": QColor("#aa96da"),
    "other": QColor("#888888"),
}


class PianoRollWidget(QWidget):
    """Widget for displaying notes in piano roll format."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._notes: list[NoteEvent] = []
        self._bars: int = 16
        self._min_pitch: int = 36
        self._max_pitch: int = 84
        self._role: str = "other"
        self._beats_per_bar: float = 4.0

        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_notes(
        self,
        notes: list[NoteEvent],
        bars: int = 16,
        role: str = "other",
        beats_per_bar: float = 4.0,
    ) -> None:
        """Set notes to display.

        Args:
            notes: List of note events.
            bars: Number of bars to display.
            role: Track role for coloring.
            beats_per_bar: Beats per bar.
        """
        self._notes = notes
        self._bars = max(1, bars)
        self._role = role
        self._beats_per_bar = beats_per_bar

        # Calculate pitch range from notes
        if notes:
            pitches = [n.pitch for n in notes]
            self._min_pitch = max(0, min(pitches) - 2)
            self._max_pitch = min(127, max(pitches) + 2)
        else:
            self._min_pitch = 36
            self._max_pitch = 84

        self.update()

    def clear(self) -> None:
        """Clear the display."""
        self._notes = []
        self.update()

    def paintEvent(self, event) -> None:
        """Paint the piano roll."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        width = rect.width()
        height = rect.height()

        # Background
        painter.fillRect(rect, QColor("#1e1e1e"))

        pitch_range = self._max_pitch - self._min_pitch + 1
        total_beats = self._bars * self._beats_per_bar

        if pitch_range <= 0 or total_beats <= 0:
            return

        # Grid
        note_height = height / pitch_range
        beat_width = width / total_beats

        # Draw horizontal grid lines (pitches)
        painter.setPen(QPen(QColor("#333333"), 1))
        for i in range(pitch_range + 1):
            y = i * note_height
            # Highlight octave lines
            pitch = self._max_pitch - i
            if pitch % 12 == 0:
                painter.setPen(QPen(QColor("#555555"), 1))
            else:
                painter.setPen(QPen(QColor("#333333"), 1))
            painter.drawLine(0, int(y), width, int(y))

        # Draw vertical grid lines (beats/bars)
        for i in range(int(total_beats) + 1):
            x = i * beat_width
            # Highlight bar lines
            if i % int(self._beats_per_bar) == 0:
                painter.setPen(QPen(QColor("#555555"), 1))
            else:
                painter.setPen(QPen(QColor("#333333"), 1))
            painter.drawLine(int(x), 0, int(x), height)

        # Draw notes
        color = ROLE_COLORS.get(self._role, ROLE_COLORS["other"])
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(120), 1))

        for note in self._notes:
            # Position
            x = note.start_beat * beat_width
            y = (self._max_pitch - note.pitch) * note_height
            w = max(2, note.duration_beats * beat_width - 1)
            h = max(2, note_height - 1)

            # Skip if out of bounds
            if x < 0 or x > width or y < 0 or y > height:
                continue

            # Draw rounded rect
            painter.drawRoundedRect(QRectF(x, y, w, h), 2, 2)

        # Draw pitch labels on left
        painter.setPen(QPen(QColor("#888888")))
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)

        for i in range(pitch_range):
            pitch = self._max_pitch - i
            if pitch % 12 == 0:  # C notes
                y = (i + 0.5) * note_height
                octave = pitch // 12 - 1
                painter.drawText(4, int(y + 4), f"C{octave}")


class ArpVisualizerWidget(QWidget):
    """Widget for visualizing arpeggio patterns."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._analysis: ArpAnalysis | None = None

        self.setMinimumHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_analysis(self, analysis: ArpAnalysis) -> None:
        """Set arpeggio analysis to display."""
        self._analysis = analysis
        self.update()

    def clear(self) -> None:
        """Clear the display."""
        self._analysis = None
        self.update()

    def paintEvent(self, event) -> None:
        """Paint the arpeggio visualization."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, QColor("#1e1e1e"))

        if self._analysis is None or not self._analysis.patterns:
            painter.setPen(QColor("#888888"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No arpeggio patterns detected")
            return

        # Draw pattern summary
        width = rect.width()
        height = rect.height()
        padding = 20

        # Display each pattern as a sequence of blocks
        color = ROLE_COLORS["arp"]
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(color.darker(120), 1))

        y = padding
        for i, pattern in enumerate(self._analysis.patterns[:5]):  # Max 5 patterns
            # Draw label
            painter.setPen(QColor("#cccccc"))
            painter.drawText(padding, y + 15, f"Pattern {i + 1}: {pattern.rate}")

            # Draw interval sequence
            seq = pattern.interval_sequence
            if seq:
                block_width = min(30, (width - 150) / max(1, len(seq)))
                x = 120
                for j, interval in enumerate(seq):
                    # Height based on interval
                    h = 20 + abs(interval) * 3
                    block_y = y + 10 + (20 - h) / 2

                    painter.setBrush(QBrush(color))
                    painter.setPen(QPen(color.darker(120), 1))
                    painter.drawRoundedRect(QRectF(x, block_y, block_width - 2, h), 3, 3)

                    # Show interval value
                    painter.setPen(QColor("#ffffff"))
                    font = QFont()
                    font.setPointSize(8)
                    painter.setFont(font)
                    painter.drawText(int(x + 2), int(block_y + h - 4), str(interval))

                    x += block_width

            y += 40


class PatternViewWidget(QWidget):
    """Widget for viewing and visualizing patterns."""

    # Signals
    pattern_selected = pyqtSignal(str)  # pattern_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._song: Song | None = None
        self._track: Track | None = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Title
        title = QLabel("Pattern View")
        title.setProperty("heading", True)
        layout.addWidget(title)

        # Controls row
        controls = QHBoxLayout()

        controls.addWidget(QLabel("Track:"))
        self.track_selector = QComboBox()
        self.track_selector.setMinimumWidth(150)
        controls.addWidget(self.track_selector)

        controls.addWidget(QLabel("Bars:"))
        self.bars_spinner = QSpinBox()
        self.bars_spinner.setRange(1, 128)
        self.bars_spinner.setValue(16)
        controls.addWidget(self.bars_spinner)

        self.show_velocity = QCheckBox("Velocity")
        self.show_velocity.setChecked(False)
        controls.addWidget(self.show_velocity)

        controls.addStretch()

        self.export_btn = QPushButton("Export Pattern")
        self.export_btn.setProperty("secondary", True)
        controls.addWidget(self.export_btn)

        layout.addLayout(controls)

        # Tab widget
        self.tabs = QTabWidget()

        # Piano roll tab
        piano_scroll = QScrollArea()
        piano_scroll.setWidgetResizable(True)
        piano_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.piano_roll = PianoRollWidget()
        piano_scroll.setWidget(self.piano_roll)

        self.tabs.addTab(piano_scroll, "Piano Roll")

        # Arp patterns tab
        arp_scroll = QScrollArea()
        arp_scroll.setWidgetResizable(True)

        self.arp_view = ArpVisualizerWidget()
        arp_scroll.setWidget(self.arp_view)

        self.tabs.addTab(arp_scroll, "Arpeggios")

        # Pattern list tab
        pattern_widget = QWidget()
        pattern_layout = QVBoxLayout(pattern_widget)

        self.pattern_info = QLabel("Select a track to view patterns")
        self.pattern_info.setWordWrap(True)
        self.pattern_info.setAlignment(Qt.AlignmentFlag.AlignTop)
        pattern_layout.addWidget(self.pattern_info)
        pattern_layout.addStretch()

        self.tabs.addTab(pattern_widget, "Patterns")

        layout.addWidget(self.tabs)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.track_selector.currentIndexChanged.connect(self._on_track_changed)
        self.bars_spinner.valueChanged.connect(self._on_bars_changed)

    def show_song_analysis(self, song: Song) -> None:
        """Show analysis for an entire song.

        Args:
            song: Song to analyze.
        """
        self._song = song
        self._track = None

        # Populate track selector
        self.track_selector.clear()
        self.track_selector.addItem("All Tracks", None)

        from midi_analyzer.analysis.features import FeatureExtractor
        from midi_analyzer.analysis.roles import classify_track_role

        feature_extractor = FeatureExtractor()

        for track in song.tracks:
            if not track.notes:
                continue
            track.features = feature_extractor.extract_features(track, song.total_bars or 1)
            role_probs = classify_track_role(track)
            role = role_probs.primary_role()
            name = track.name or f"Track {track.track_id}"
            self.track_selector.addItem(f"{name} ({role.value})", track.track_id)

        # Show all tracks combined
        self._show_all_tracks()

    def show_track_patterns(self, track: Track, song: Song) -> None:
        """Show patterns for a specific track.

        Args:
            track: Track to visualize.
            song: Parent song for context.
        """
        self._song = song
        self._track = track

        # Update piano roll
        from midi_analyzer.analysis.features import FeatureExtractor
        from midi_analyzer.analysis.roles import classify_track_role

        feature_extractor = FeatureExtractor()
        track.features = feature_extractor.extract_features(track, song.total_bars or 1)
        role_probs = classify_track_role(track)
        role = role_probs.primary_role()

        bars = min(self.bars_spinner.value(), song.total_bars or 16)
        self.piano_roll.set_notes(track.notes, bars, role.value)

        # Update arp view if arp role
        if role_probs.arp > 0.3:
            self._show_arp_analysis(track, song)
        else:
            self.arp_view.clear()

        # Update pattern info
        self._update_pattern_info(track, role.value)

    def clear(self) -> None:
        """Clear all views."""
        self._song = None
        self._track = None
        self.track_selector.clear()
        self.piano_roll.clear()
        self.arp_view.clear()
        self.pattern_info.setText("Select a track to view patterns")

    def _show_all_tracks(self) -> None:
        """Show all tracks combined."""
        if self._song is None:
            return

        # Combine all notes
        all_notes = []
        for track in self._song.tracks:
            all_notes.extend(track.notes)

        bars = min(self.bars_spinner.value(), self._song.total_bars or 16)
        self.piano_roll.set_notes(all_notes, bars, "other")
        self.arp_view.clear()
        self.pattern_info.setText(
            f"Showing all {len(self._song.tracks)} tracks\nTotal notes: {len(all_notes)}"
        )

    def _show_arp_analysis(self, track: Track, song: Song) -> None:
        """Show arpeggio analysis for a track."""
        try:
            from midi_analyzer.analysis.arpeggios import ArpAnalyzer

            analyzer = ArpAnalyzer()
            analysis = analyzer.analyze_track(track, song)
            self.arp_view.set_analysis(analysis)
        except Exception:
            self.arp_view.clear()

    def _update_pattern_info(self, track: Track, role: str) -> None:
        """Update pattern info display."""
        lines = [
            f"Track: {track.name or f'Track {track.track_id}'}",
            f"Role: {role}",
            f"Notes: {len(track.notes)}",
            f"Channel: {track.channel}",
        ]

        if track.notes:
            pitches = [n.pitch for n in track.notes]
            lines.append(f"Pitch range: {min(pitches)} - {max(pitches)}")

            durations = [n.duration_beats for n in track.notes]
            avg_dur = sum(durations) / len(durations)
            lines.append(f"Avg duration: {avg_dur:.2f} beats")

        self.pattern_info.setText("\n".join(lines))

    def _on_track_changed(self, index: int) -> None:
        """Handle track selector change."""
        if self._song is None:
            return

        track_id = self.track_selector.currentData()
        if track_id is None:
            self._show_all_tracks()
        else:
            for track in self._song.tracks:
                if track.track_id == track_id:
                    self.show_track_patterns(track, self._song)
                    break

    def _on_bars_changed(self, bars: int) -> None:
        """Handle bars spinner change."""
        if self._track and self._song:
            self.show_track_patterns(self._track, self._song)
        elif self._song:
            self._show_all_tracks()
