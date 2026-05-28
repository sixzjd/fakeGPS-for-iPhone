"""PyQt6 graphical interface for FakeGPS."""

import sys
import os
import asyncio
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QGroupBox, QFileDialog,
    QMessageBox, QSplitter, QTextEdit
)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal, QObject, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel

from .core import list_connected_devices, set_location, clear_location, play_gpx_file, run_async, DeviceInfo
from .places import list_places, BUILTIN_PLACES


class WorkerThread(QThread):
    """Background thread for async pymobiledevice3 operations."""
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, coro_func, *args, **kwargs):
        super().__init__()
        self._coro_func = coro_func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        try:
            result = run_async(self._coro_func(*self._args, **self._kwargs))
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class Bridge(QObject):
    """QWebChannel bridge for JS <-> Python communication."""

    def __init__(self, window):
        super().__init__()
        self._window = window

    def setLocation(self, lat, lng):
        self._window._set_location_from_map(float(lat), float(lng))

    def clearLocation(self):
        self._window._clear_location()


class FakeGPSWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FakeGPS v6.0")
        self.setMinimumSize(1100, 700)
        self._active_sim = None  # Keep location simulation connection alive
        self._worker = None
        self._setup_ui()
        self._refresh_devices()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left: Map
        self._map_view = QWebEngineView()
        self._channel = QWebChannel()
        self._bridge = Bridge(self)
        self._channel.registerObject("bridge", self._bridge)
        self._map_view.page().setWebChannel(self._channel)

        map_path = Path(__file__).parent / "map.html"
        self._map_view.setUrl(QUrl.fromLocalFile(str(map_path.resolve())))

        splitter.addWidget(self._map_view)

        # Right: Control panel
        panel = QWidget()
        panel.setFixedWidth(320)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)

        # Device group
        dev_group = QGroupBox("Device")
        dev_layout = QVBoxLayout(dev_group)
        self._device_combo = QComboBox()
        self._device_combo.setMinimumHeight(30)
        dev_layout.addWidget(self._device_combo)

        dev_btn_layout = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh_devices)
        dev_btn_layout.addWidget(self._refresh_btn)
        dev_layout.addLayout(dev_btn_layout)

        self._device_status = QLabel("No device connected")
        self._device_status.setStyleSheet("color: #aaa; font-size: 12px;")
        dev_layout.addWidget(self._device_status)
        panel_layout.addWidget(dev_group)

        # Location group
        loc_group = QGroupBox("Location")
        loc_layout = QVBoxLayout(loc_group)

        coord_layout = QHBoxLayout()
        self._lat_input = QLineEdit()
        self._lat_input.setPlaceholderText("Latitude")
        self._lat_input.setFixedHeight(30)
        self._lng_input = QLineEdit()
        self._lng_input.setPlaceholderText("Longitude")
        self._lng_input.setFixedHeight(30)
        coord_layout.addWidget(self._lat_input)
        coord_layout.addWidget(self._lng_input)
        loc_layout.addLayout(coord_layout)

        self._set_btn = QPushButton("Set Location")
        self._set_btn.setStyleSheet("background: #00d4ff; color: #1a1a2e; font-weight: bold; padding: 8px; border-radius: 6px;")
        self._set_btn.clicked.connect(self._set_location_manual)
        self._set_btn.setFixedHeight(36)
        loc_layout.addWidget(self._set_btn)

        self._clear_btn = QPushButton("Restore Real Location")
        self._clear_btn.setStyleSheet("background: #ff4757; color: #fff; font-weight: bold; padding: 8px; border-radius: 6px;")
        self._clear_btn.clicked.connect(self._clear_location)
        self._clear_btn.setFixedHeight(36)
        loc_layout.addWidget(self._clear_btn)

        self._current_loc_label = QLabel("Current: -")
        self._current_loc_label.setStyleSheet("color: #00d4ff; font-size: 12px;")
        loc_layout.addWidget(self._current_loc_label)
        panel_layout.addWidget(loc_group)

        # Quick places group
        places_group = QGroupBox("Quick Places")
        places_layout = QVBoxLayout(places_group)

        for name, (lat, lng, label) in BUILTIN_PLACES.items():
            btn = QPushButton(f"{label}  ({lat}, {lng})")
            btn.setStyleSheet("text-align: left; padding: 5px 8px; font-size: 12px;")
            btn.clicked.connect(lambda checked, n=name, la=lat, lo=lng: self._quick_place(la, lo))
            places_layout.addWidget(btn)

        panel_layout.addWidget(places_group)

        # GPX group
        gpx_group = QGroupBox("GPX Playback")
        gpx_layout = QVBoxLayout(gpx_group)

        gpx_btn_layout = QHBoxLayout()
        self._gpx_path = QLineEdit()
        self._gpx_path.setPlaceholderText("Select .gpx file...")
        self._gpx_path.setReadOnly(True)
        self._gpx_path.setFixedHeight(30)
        gpx_btn_layout.addWidget(self._gpx_path)

        gpx_browse = QPushButton("Browse")
        gpx_browse.setFixedHeight(30)
        gpx_browse.clicked.connect(self._browse_gpx)
        gpx_btn_layout.addWidget(gpx_browse)
        gpx_layout.addLayout(gpx_btn_layout)

        self._play_gpx_btn = QPushButton("Play GPX")
        self._play_gpx_btn.setStyleSheet("background: #ffa502; color: #1a1a2e; font-weight: bold; padding: 8px; border-radius: 6px;")
        self._play_gpx_btn.clicked.connect(self._play_gpx)
        self._play_gpx_btn.setFixedHeight(36)
        gpx_layout.addWidget(self._play_gpx_btn)
        panel_layout.addWidget(gpx_group)

        # Log area
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(120)
        self._log.setStyleSheet("background: #1a1a2e; color: #aaa; font-size: 11px; border-radius: 6px;")
        log_layout.addWidget(self._log)
        panel_layout.addWidget(log_group)

        panel_layout.addStretch()
        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

    def _log_msg(self, msg):
        self._log.append(msg)
        # Also push to map's toast if available
        js = f'showStatus("{msg.replace(chr(10), " ").replace(chr(34), chr(39))}")'
        self._map_view.page().runJavaScript(js)

    def _refresh_devices(self):
        self._device_combo.clear()
        self._device_status.setText("Scanning...")
        self._log_msg("Scanning for devices...")

        def _on_done(devices):
            self._device_combo.clear()
            if not devices:
                self._device_status.setText("No device found. Connect via USB and trust this computer.")
                self._log_msg("No devices found.")
                return
            for dev in devices:
                self._device_combo.addItem(f"{dev.name} (iOS {dev.ios_version})", dev.udid)
            self._device_status.setText(f"{len(devices)} device(s) connected")
            # Update map device info
            d = devices[0]
            js = f'updateDeviceInfo("{d.name}", "{d.ios_version}")'
            self._map_view.page().runJavaScript(js)
            self._log_msg(f"Found: {d.name} (iOS {d.ios_version})")

        def _on_error(err):
            self._device_status.setText(f"Error: {err}")
            self._log_msg(f"Error scanning: {err}")

        self._worker = WorkerThread(list_connected_devices)
        self._worker.finished.connect(_on_done)
        self._worker.error.connect(_on_error)
        self._worker.start()

    def _get_selected_udid(self):
        idx = self._device_combo.currentIndex()
        if idx < 0:
            return None
        return self._device_combo.currentData()

    def _set_location_from_map(self, lat, lng):
        self._lat_input.setText(str(lat))
        self._lng_input.setText(str(lng))
        self._do_set_location(lat, lng)

    def _set_location_manual(self):
        try:
            lat = float(self._lat_input.text())
            lng = float(self._lng_input.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid", "Please enter valid coordinates.")
            return
        self._do_set_location(lat, lng)

    def _do_set_location(self, lat, lng):
        serial = self._get_selected_udid()
        self._set_btn.setEnabled(False)
        self._log_msg(f"Setting location: {lat}, {lng}")

        def _on_done(result):
            self._active_sim = result  # Keep connection alive
            self._set_btn.setEnabled(True)
            self._current_loc_label.setText(f"Current: {lat}, {lng}")
            self._log_msg(f"Location set to ({lat}, {lng})")
            self._map_view.page().runJavaScript(f'showStatus("Location set: {lat}, {lng}")')

        def _on_error(err):
            self._set_btn.setEnabled(True)
            self._log_msg(f"Error: {err}")
            QMessageBox.critical(self, "Error", f"Failed to set location:\n{err}")

        self._worker = WorkerThread(set_location, lat, lng, serial)
        self._worker.finished.connect(_on_done)
        self._worker.error.connect(_on_error)
        self._worker.start()

    def _clear_location(self):
        serial = self._get_selected_udid()
        self._clear_btn.setEnabled(False)
        self._log_msg("Restoring real location...")

        def _on_done(_):
            self._active_sim = None
            self._clear_btn.setEnabled(True)
            self._current_loc_label.setText("Current: - (real)")
            self._log_msg("Real location restored.")
            self._map_view.page().runJavaScript('showStatus("Real location restored")')

        def _on_error(err):
            self._clear_btn.setEnabled(True)
            self._log_msg(f"Error: {err}")

        self._worker = WorkerThread(clear_location, serial)
        self._worker.finished.connect(_on_done)
        self._worker.error.connect(_on_error)
        self._worker.start()

    def _quick_place(self, lat, lng):
        self._lat_input.setText(str(lat))
        self._lng_input.setText(str(lng))
        self._do_set_location(lat, lng)
        # Fly map to location
        self._map_view.page().runJavaScript(f'map.setView([{lat}, {lng}], 15)')

    def _browse_gpx(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select GPX File", "", "GPX Files (*.gpx)")
        if path:
            self._gpx_path.setText(path)

    def _play_gpx(self):
        path = self._gpx_path.text()
        if not path:
            QMessageBox.warning(self, "No File", "Please select a GPX file first.")
            return
        serial = self._get_selected_udid()
        self._play_gpx_btn.setEnabled(False)
        self._log_msg(f"Playing GPX: {path}")

        def _on_done(_):
            self._play_gpx_btn.setEnabled(True)
            self._log_msg("GPX playback finished.")

        def _on_error(err):
            self._play_gpx_btn.setEnabled(True)
            self._log_msg(f"GPX error: {err}")

        self._worker = WorkerThread(play_gpx_file, path, serial)
        self._worker.finished.connect(_on_done)
        self._worker.error.connect(_on_error)
        self._worker.start()

    def closeEvent(self, event):
        """Clean up on window close."""
        if self._active_sim:
            try:
                run_async(clear_location())
            except Exception:
                pass
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("FakeGPS")
    app.setStyle("Fusion")

    # Dark palette
    from PyQt6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 50))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 45))
    palette.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Button, QColor(40, 40, 60))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(0, 212, 255))
    app.setPalette(palette)

    window = FakeGPSWindow()
    window.show()
    sys.exit(app.exec())
