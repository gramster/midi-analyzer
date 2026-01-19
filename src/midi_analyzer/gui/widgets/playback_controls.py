"""Playback controls widget."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QWidget,
)

if TYPE_CHECKING:
    from midi_analyzer.models.core import Song, Track


class PlaybackControlsWidget(QWidget):
    """Widget for playback controls."""

    # Signals
    play_clicked = pyqtSignal()
    stop_clicked = pyqtSignal()
    tempo_changed = pyqtSignal(float)
    position_changed = pyqtSignal(float, float)  # (position_seconds, tempo_bpm)
    _playback_finished = pyqtSignal()  # Internal signal for thread completion

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._song: Song | None = None
        self._track: Track | None = None
        self._playing: bool = False
        self._player = None
        self._playback_thread: threading.Thread | None = None

        self._setup_ui()
        self._connect_signals()

        # Position update timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_position)
        self._timer.setInterval(100)
        
        # Connect internal signal
        self._playback_finished.connect(self._on_playback_finished)

    def _setup_ui(self) -> None:
        """Set up the UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(8)

        # Play/Pause button
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedWidth(40)
        self.play_btn.setToolTip("Play/Pause (Space)")
        layout.addWidget(self.play_btn)

        # Stop button
        self.stop_btn = QPushButton("⬛")
        self.stop_btn.setFixedWidth(40)
        self.stop_btn.setProperty("secondary", True)
        self.stop_btn.setToolTip("Stop (Esc)")
        layout.addWidget(self.stop_btn)

        layout.addSpacing(8)

        # Position slider
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.setValue(0)
        self.position_slider.setEnabled(False)
        layout.addWidget(self.position_slider, 1)

        # Time label
        self.time_label = QLabel("0:00 / 0:00")
        self.time_label.setMinimumWidth(80)
        layout.addWidget(self.time_label)

        layout.addSpacing(8)

        # Tempo control
        layout.addWidget(QLabel("BPM:"))
        self.tempo_spinner = QSpinBox()
        self.tempo_spinner.setRange(40, 240)
        self.tempo_spinner.setValue(120)
        self.tempo_spinner.setToolTip("Playback tempo")
        layout.addWidget(self.tempo_spinner)

        layout.addSpacing(8)

        # Track selector for playback
        layout.addWidget(QLabel("Play:"))
        self.track_selector = QComboBox()
        self.track_selector.setMinimumWidth(120)
        self.track_selector.addItem("All Tracks", None)
        self.track_selector.setToolTip("Select track to play")
        layout.addWidget(self.track_selector)

    def _connect_signals(self) -> None:
        """Connect widget signals."""
        self.play_btn.clicked.connect(self._on_play_clicked)
        self.stop_btn.clicked.connect(self._on_stop_clicked)
        self.tempo_spinner.valueChanged.connect(self._on_tempo_changed)

    def set_song(self, song: Song) -> None:
        """Set the song for playback.

        Args:
            song: Song to play.
        """
        self._song = song
        self._track = None

        # Update tempo from song
        if song.tempo_map:
            tempo = int(song.tempo_map[0].tempo_bpm)
            self.tempo_spinner.setValue(tempo)

        # Populate track selector
        self.track_selector.clear()
        self.track_selector.addItem("All Tracks", None)

        for track in song.tracks:
            if track.notes:
                name = track.name or f"Track {track.track_id}"
                self.track_selector.addItem(name, track.track_id)

        # Update time label
        self._update_duration()

        # Enable controls
        self.position_slider.setEnabled(True)

    def play_track(self, track: Track, song: Song) -> None:
        """Play a specific track.

        Args:
            track: Track to play.
            song: Parent song.
        """
        self._song = song
        self._track = track

        # Start playback
        self._start_playback(track_only=True)

    def toggle_playback(self) -> None:
        """Toggle play/pause."""
        if self._playing:
            self._pause_playback()
        else:
            self._start_playback()

    def stop(self) -> None:
        """Stop playback."""
        self._stop_playback()

    def _start_playback(self, track_only: bool = False) -> None:
        """Start playback."""
        if self._song is None:
            return

        # Wait for any previous playback thread to finish
        if self._playback_thread is not None and self._playback_thread.is_alive():
            if self._player:
                self._player.stop()
            self._playback_thread.join(timeout=1.0)

        try:
            from midi_analyzer.player import MidiPlayer, PlaybackOptions

            if self._player is None:
                self._player = MidiPlayer()

            tempo = self.tempo_spinner.value()
            options = PlaybackOptions(tempo_bpm=tempo, use_role_instrument=True)

            # Determine what to play
            if track_only and self._track:
                target_track = self._track
                play_song = False
            else:
                # Get selected track or play all
                track_id = self.track_selector.currentData()
                if track_id is not None:
                    target_track = None
                    for track in self._song.tracks:
                        if track.track_id == track_id:
                            target_track = track
                            break
                    play_song = False
                else:
                    target_track = None
                    play_song = True

            # Start playback in a background thread
            def play_in_thread():
                try:
                    if play_song:
                        self._player.play_song(self._song, options)
                    elif target_track:
                        self._player.play_track(target_track, options)
                except Exception as e:
                    print(f"Playback error: {e}", flush=True)
                finally:
                    self._playback_finished.emit()

            self._playback_thread = threading.Thread(target=play_in_thread, daemon=True)
            self._playback_thread.start()

            self._playing = True
            self.play_btn.setText("⏸")
            self._timer.start()

        except Exception as e:
            print(f"Playback error: {e}")
            self._playing = False
            self.play_btn.setText("▶")

    def _on_playback_finished(self) -> None:
        """Handle playback thread completion."""
        self._playing = False
        self.play_btn.setText("▶")
        self._timer.stop()

    def _pause_playback(self) -> None:
        """Pause playback."""
        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass

        self._playing = False
        self.play_btn.setText("▶")
        self._timer.stop()

    def _stop_playback(self) -> None:
        """Stop playback completely."""
        if self._player:
            try:
                self._player.stop()
            except Exception:
                pass

        self._playing = False
        self.play_btn.setText("▶")
        self._timer.stop()
        self.position_slider.setValue(0)
        self._update_time_label(0, self._get_duration())

    def _update_position(self) -> None:
        """Update position display during playback."""
        if self._player is None or not self._playing:
            return
        
        try:
            position = self._player.position
            duration = self._player.duration or self._get_duration()
            
            # Update time label
            self._update_time_label(position, duration)
            
            # Update slider
            if duration > 0:
                slider_value = int((position / duration) * 1000)
                slider_value = min(1000, max(0, slider_value))
                self.position_slider.setValue(slider_value)
            
            # Emit position for piano roll and other displays
            tempo = self.tempo_spinner.value()
            self.position_changed.emit(position, float(tempo))
        except Exception as e:
            print(f"Position update error: {e}", flush=True)

    def _update_duration(self) -> None:
        """Update the duration display."""
        duration = self._get_duration()
        self._update_time_label(0, duration)

    def _get_duration(self) -> float:
        """Get song duration in seconds."""
        if self._song is None:
            return 0.0

        # Calculate from notes and tempo
        max_beat = 0.0
        for track in self._song.tracks:
            for note in track.notes:
                end_beat = note.start_beat + note.duration_beats
                if end_beat > max_beat:
                    max_beat = end_beat

        tempo = self.tempo_spinner.value()
        return max_beat * 60.0 / tempo

    def _update_time_label(self, current: float, total: float) -> None:
        """Update the time label.

        Args:
            current: Current position in seconds.
            total: Total duration in seconds.
        """
        curr_min = int(current) // 60
        curr_sec = int(current) % 60
        total_min = int(total) // 60
        total_sec = int(total) % 60

        self.time_label.setText(f"{curr_min}:{curr_sec:02d} / {total_min}:{total_sec:02d}")

    def _on_play_clicked(self) -> None:
        """Handle play button click."""
        self.toggle_playback()
        self.play_clicked.emit()

    def _on_stop_clicked(self) -> None:
        """Handle stop button click."""
        self._stop_playback()
        self.stop_clicked.emit()

    def _on_tempo_changed(self, tempo: int) -> None:
        """Handle tempo change."""
        self.tempo_changed.emit(float(tempo))
        self._update_duration()

    def closeEvent(self, event) -> None:
        """Handle widget close."""
        self._stop_playback()
        if self._player:
            try:
                self._player.close()
            except Exception:
                pass
        super().closeEvent(event)
