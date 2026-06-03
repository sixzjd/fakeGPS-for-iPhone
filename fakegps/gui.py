"""PyQt6 graphical interface for FakeGPS."""

import sys
from pathlib import Path


def _resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / 'fakegps' / relative_path
    return Path(__file__).parent / relative_path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QComboBox, QGroupBox, QFileDialog,
    QMessageBox, QSplitter, QTextEdit, QScrollArea
)
from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView

import json
from .core import list_connected_devices, set_location, clear_location, play_gpx_file, check_tunneld_running, run_async
from .places import BUILTIN_PLACES

_CONFIG_FILE = Path.home() / ".fakegps_config.json"


class WorkerThread(QThread):
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


class FakeGPSWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FakeGPS v6.0")
        self.setMinimumSize(1100, 700)
        self._active_sim = None
        self._worker = None
        self._setup_ui()
        self._refresh_devices()
        self._check_windows_driver()

        # Poll document.title every 300ms for JS -> Python communication
        self._title_timer = QTimer(self)
        self._title_timer.timeout.connect(self._poll_map_title)
        self._title_timer.start(300)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)

        # Left: Map
        self._map_view = QWebEngineView()
        map_path = _resource_path("map.html")
        html_content = map_path.read_text(encoding="utf-8")
        self._map_view.setHtml(html_content, QUrl("https://fakegps.local"))
        self._map_view.loadFinished.connect(self._on_map_loaded)
        splitter.addWidget(self._map_view)

        # Right: Control panel with scroll
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 12, 12, 12)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(panel)
        scroll_area.setFixedWidth(340)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 6px; background: rgba(255,255,255,0.05); border-radius: 3px; }
            QScrollBar::handle:vertical { background: rgba(0,212,255,0.4); border-radius: 3px; min-height: 30px; }
            QScrollBar::handle:vertical:hover { background: rgba(0,212,255,0.7); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

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

        # AMap API Key group
        api_group = QGroupBox("AMap API Key (for search)")
        api_layout = QVBoxLayout(api_group)

        api_row = QHBoxLayout()
        api_row.setSpacing(6)

        self._amap_key_input = QLineEdit()
        self._amap_key_input.setPlaceholderText("Enter AMap REST API Key")
        self._amap_key_input.setFixedHeight(30)
        self._amap_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        api_row.addWidget(self._amap_key_input)

        self._save_key_btn = QPushButton("Save")
        self._save_key_btn.setStyleSheet("""
            QPushButton { background: #00d4ff; color: #1a1a2e; font-weight: bold; padding: 6px 12px; border-radius: 6px; }
            QPushButton:hover { background: #009fcc; }
            QPushButton:pressed { background: #007a99; }
        """)
        self._save_key_btn.setFixedHeight(30)
        self._save_key_btn.clicked.connect(self._save_amap_key)
        api_row.addWidget(self._save_key_btn)

        self._clear_key_btn = QPushButton("Clear")
        self._clear_key_btn.setStyleSheet("""
            QPushButton { background: #ff4757; color: #fff; font-weight: bold; padding: 6px 12px; border-radius: 6px; }
            QPushButton:hover { background: #cc3945; }
            QPushButton:pressed { background: #a52e38; }
        """)
        self._clear_key_btn.setFixedHeight(30)
        self._clear_key_btn.clicked.connect(self._clear_amap_key)
        self._clear_key_btn.setVisible(False)
        api_row.addWidget(self._clear_key_btn)

        api_layout.addLayout(api_row)

        self._api_status = QLabel("")
        self._api_status.setStyleSheet("color: #aaa; font-size: 11px;")
        api_layout.addWidget(self._api_status)

        panel_layout.addWidget(api_group)

        # Load saved AMap key
        self._load_amap_key()

        # Hidden inputs for map SELECT: handler
        self._lat_input = QLineEdit()
        self._lng_input = QLineEdit()

        # Tunneld group
        tunneld_group = QGroupBox("tunneld (iOS 17+)")
        tunneld_layout = QVBoxLayout(tunneld_group)

        tunneld_cmd = QLineEdit("sudo python3 -m pymobiledevice3 remote tunneld")
        tunneld_cmd.setReadOnly(True)
        tunneld_cmd.setFixedHeight(30)
        tunneld_cmd.setStyleSheet("font-family: monospace; font-size: 12px;")
        tunneld_layout.addWidget(tunneld_cmd)

        self._copy_btn = QPushButton("Copy Command")
        self._copy_btn.setStyleSheet("""
            QPushButton { background: #00d4ff; color: #1a1a2e; font-weight: bold; padding: 8px; border-radius: 6px; }
            QPushButton:hover { background: #009fcc; }
            QPushButton:pressed { background: #007a99; }
        """)
        self._copy_btn.setFixedHeight(36)
        self._copy_btn.clicked.connect(lambda: self._copy_tunneld_cmd(tunneld_cmd.text()))
        tunneld_layout.addWidget(self._copy_btn)

        panel_layout.addWidget(tunneld_group)

        # Quick places group
        places_group = QGroupBox("Quick Places")
        places_layout = QVBoxLayout(places_group)
        for name, (lat, lng, label) in BUILTIN_PLACES.items():
            btn = QPushButton(f"{label}  ({lat}, {lng})")
            btn.setStyleSheet("""
                QPushButton { text-align: left; padding: 5px 8px; font-size: 12px; background: transparent; border: 1px solid transparent; border-radius: 4px; }
                QPushButton:hover { background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.2); }
                QPushButton:pressed { background: rgba(0,212,255,0.2); }
            """)
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
        splitter.addWidget(scroll_area)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

    def _on_map_loaded(self, ok):
        if not ok:
            self._log_msg("Map failed to load. Check internet connection.")
        # Inject saved AMap key into map page
        key = self._load_amap_key_value()
        if key:
            self._map_view.page().runJavaScript(f"AMAP_KEY = '{key}';")

    def _check_windows_driver(self):
        """On Windows, check if Apple Mobile Device USB driver is installed."""
        if sys.platform != 'win32':
            return
        import subprocess
        service_names = [
            'Apple Mobile Device Service',
            'AppleMobileDeviceService',
            'Apple Devices Service',
        ]
        for name in service_names:
            try:
                result = subprocess.run(
                    ['sc', 'query', name],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    return
            except Exception:
                pass
        # Check registry for Apple Mobile Device USB Driver
        try:
            result = subprocess.run(
                ['reg', 'query', r'HKLM\SYSTEM\CurrentControlset\Services\Apple Mobile Device Service'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return
        except Exception:
            pass
        self._show_driver_warning()

    def _show_driver_warning(self):
        from PyQt6.QtWidgets import QMessageBox
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        msg = QMessageBox(self)
        msg.setWindowTitle("Apple Driver Required")
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText("Apple Mobile Device USB driver not found.")
        msg.setInformativeText(
            "iPhone requires Apple drivers to connect via USB.\n\n"
            "Please install Apple Devices from Microsoft Store (lightweight, ~50MB).\n"
            "After installation, restart this app."
        )
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        download_btn = msg.addButton("Open Microsoft Store", QMessageBox.ButtonRole.ActionRole)
        msg.exec()
        if msg.clickedButton() == download_btn:
            QDesktopServices.openUrl(QUrl(
                "https://apps.microsoft.com/store/detail/apple-devices/9NP83LWLPZ9K"
            ))

    def _load_amap_key_value(self):
        if _CONFIG_FILE.exists():
            try:
                config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
                return config.get("amap_key", "")
            except Exception:
                pass
        return ""

    def _load_amap_key(self):
        key = self._load_amap_key_value()
        if key:
            self._amap_key_input.setText(key)
            self._set_key_saved_ui(key)
        else:
            self._api_status.setText("Search requires AMap Key.")
            self._save_key_btn.setVisible(True)
            self._clear_key_btn.setVisible(False)

    def _set_key_saved_ui(self, key):
        masked = key[:4] + "****" + key[-4:] if len(key) > 8 else "****"
        self._api_status.setText(f"Key: {masked}")
        self._amap_key_input.setVisible(False)
        self._save_key_btn.setVisible(False)
        self._clear_key_btn.setVisible(True)

    def _save_amap_key(self):
        key = self._amap_key_input.text().strip()
        if not key:
            self._api_status.setText("Please enter a key.")
            return
        config = {}
        if _CONFIG_FILE.exists():
            try:
                config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        config["amap_key"] = key
        _CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        self._map_view.page().runJavaScript(f"AMAP_KEY = '{key}';")
        self._set_key_saved_ui(key)
        self._log_msg("AMap Key saved.")

    def _clear_amap_key(self):
        self._amap_key_input.clear()
        self._amap_key_input.setPlaceholderText("Enter AMap REST API Key")
        config = {}
        if _CONFIG_FILE.exists():
            try:
                config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        config.pop("amap_key", None)
        _CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        self._map_view.page().runJavaScript("AMAP_KEY = '';")
        self._api_status.setText("Search requires AMap Key.")
        self._amap_key_input.setVisible(True)
        self._save_key_btn.setVisible(True)
        self._clear_key_btn.setVisible(False)
        self._log_msg("AMap Key cleared.")


    def _poll_map_title(self):
        """Poll document.title for JS -> Python messages."""
        self._map_view.page().runJavaScript("document.title", self._handle_title)

    def _handle_title(self, title):
        if not title:
            return
        if title.startswith("SELECT:"):
            coords = title[len("SELECT:"):]
            try:
                lat, lng = coords.split(",")
                self._lat_input.setText(lat.strip())
                self._lng_input.setText(lng.strip())
            except ValueError:
                pass
        elif title.startswith("SET:"):
            coords = title[len("SET:"):]
            try:
                lat, lng = coords.split(",")
                self._do_set_location(float(lat.strip()), float(lng.strip()))
            except ValueError:
                pass
            # Reset title to avoid re-triggering
            self._map_view.page().runJavaScript("document.title = 'FakeGPS'")
        elif title.startswith("CLEAR:"):
            self._clear_location()
            self._map_view.page().runJavaScript("document.title = 'FakeGPS'")

    def _log_msg(self, msg):
        self._log.append(msg)

    def _refresh_devices(self):
        self._device_combo.clear()
        self._device_status.setText("Scanning...")
        self._log_msg("Scanning for devices...")

        def _on_done(devices):
            self._device_combo.clear()
            if not devices:
                self._device_status.setText("No device found.")
                self._log_msg("No devices found.")
                return
            for dev in devices:
                self._device_combo.addItem(f"{dev.name} (iOS {dev.ios_version})", dev.udid)
            self._device_status.setText(f"{len(devices)} device(s) connected")
            d = devices[0]
            self._map_view.page().runJavaScript(f'updateDeviceInfo("{d.name}", "{d.ios_version}")')
            self._log_msg(f"Found: {d.name} (iOS {d.ios_version})")

        def _on_error(err):
            self._device_status.setText(f"Error: {err}")
            self._log_msg(f"Error: {err}")

        self._worker = WorkerThread(list_connected_devices)
        self._worker.finished.connect(_on_done)
        self._worker.error.connect(_on_error)
        self._worker.start()

    def _get_selected_udid(self):
        idx = self._device_combo.currentIndex()
        return self._device_combo.currentData() if idx >= 0 else None

    def _set_location_manual(self):
        try:
            lat = float(self._lat_input.text())
            lng = float(self._lng_input.text())
        except ValueError:
            QMessageBox.warning(self, "Invalid", "Please enter valid coordinates.")
            return
        self._do_set_location(lat, lng)

    def _copy_tunneld_cmd(self, text):
        QApplication.clipboard().setText(text)
        self._copy_btn.setText("Copied!")
        self._copy_btn.setStyleSheet("""
            QPushButton { background: #27ae60; color: #fff; font-weight: bold; padding: 8px; border-radius: 6px; }
            QPushButton:hover { background: #1e8449; }
            QPushButton:pressed { background: #166b3a; }
        """)
        QTimer.singleShot(1500, self._reset_copy_btn)

    def _reset_copy_btn(self):
        self._copy_btn.setText("Copy Command")
        self._copy_btn.setStyleSheet("""
            QPushButton { background: #00d4ff; color: #1a1a2e; font-weight: bold; padding: 8px; border-radius: 6px; }
            QPushButton:hover { background: #009fcc; }
            QPushButton:pressed { background: #007a99; }
        """)

    def _do_set_location(self, lat, lng):
        serial = self._get_selected_udid()
        if not check_tunneld_running():
            self._log_msg("Warning: tunneld not running. For iOS 17+, start it:")
            self._log_msg("  sudo python3 -m pymobiledevice3 remote tunneld")
            QMessageBox.warning(self, "tunneld Not Running",
                "tunneld is required for iOS 17+ devices.\n\n"
                "Start it in a terminal:\n"
                "  sudo python3 -m pymobiledevice3 remote tunneld\n\n"
                "Then try setting the location again.")
            return
        self._log_msg(f"Setting location: {lat}, {lng}")

        def _on_done(result):
            self._active_sim = result
            self._log_msg(f"Location set to ({lat}, {lng})")

        def _on_error(err):
            self._log_msg(f"Error: {err}")
            QMessageBox.critical(self, "Error", f"Failed to set location:\n{err}")

        self._worker = WorkerThread(set_location, lat, lng, serial)
        self._worker.finished.connect(_on_done)
        self._worker.error.connect(_on_error)
        self._worker.start()

    def _clear_location(self):
        serial = self._get_selected_udid()
        self._log_msg("Restoring real location...")

        def _on_done(_):
            self._active_sim = None
            self._log_msg("Real location restored.")

        def _on_error(err):
            self._log_msg(f"Error: {err}")

        self._worker = WorkerThread(clear_location, serial)
        self._worker.finished.connect(_on_done)
        self._worker.error.connect(_on_error)
        self._worker.start()

    def _quick_place(self, lat, lng):
        self._lat_input.setText(str(lat))
        self._lng_input.setText(str(lng))
        self._do_set_location(lat, lng)
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
