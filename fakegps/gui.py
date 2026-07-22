"""Web-based GUI for FakeGPS using pywebview (system native webview).

Replaces PyQt6-WebEngine to dramatically reduce bundle size.
Uses the system's native webview (WebKit on macOS, Edge on Windows)
instead of bundling Chromium (~200MB savings).
"""

import sys
import os
import json
import time
import threading
from pathlib import Path


def _resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / 'fakegps' / relative_path
    return Path(__file__).parent / relative_path


def app_log_path():
    """Persistent log file for full tracebacks (sidebar only shows one line)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "FakeGPS.log")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Logs/FakeGPS.log")
    return os.path.expanduser("~/.fakegps.log")


def _dump_traceback(context):
    """Append the current traceback to app_log_path() for post-mortem."""
    try:
        import traceback as _tb
        with open(app_log_path(), "a", encoding="utf-8") as fh:
            fh.write(f"--- {context} @ {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            fh.write(_tb.format_exc())
            fh.write("\n")
    except Exception:
        pass


_CONFIG_FILE = Path.home() / ".fakegps_config.json"


class API:
    """Python API exposed to JavaScript via pywebview bridge."""

    def __init__(self):
        self._window = None
        self._active_sim = None
        self._ready = threading.Event()

    def set_window(self, window):
        self._window = window

    def _cleanup_active_sim(self):
        """Close previous location simulation to free the DVT session."""
        if self._active_sim:
            try:
                from .core import run_async
                sim = self._active_sim
                ios_major = sim.get("ios_major", 0)
                if ios_major >= 17:
                    # iOS 17+: close LocationSimulation and DvtProvider
                    loc_sim = sim.get("sim")
                    provider = sim.get("provider")
                    if loc_sim:
                        run_async(loc_sim.__aexit__(None, None, None))
                    if provider:
                        run_async(provider.__aexit__(None, None, None))
                else:
                    # iOS <17: close lockdown
                    lockdown = sim.get("lockdown")
                    if lockdown:
                        run_async(lockdown.close())
            except Exception:
                pass
            self._active_sim = None

    def _js(self, code):
        """Evaluate JavaScript in the webview."""
        if self._window:
            self._window.evaluate_js(code)

    # ── Device Management ──

    def refresh_devices(self):
        """Scan for connected iOS devices and update the UI."""
        from .core import list_connected_devices, list_android_devices, run_async

        def _worker():
            try:
                devices = run_async(list_connected_devices())
                android = list_android_devices()
                if not devices and not android:
                    self._js("updateDeviceList([])")
                    self._js("logMsg('No devices found. Check Apple Devices/ADB and USB trust.')")
                    return
                for d in devices:
                    self._js(f"logMsg('Device: {d.name} | iOS {d.ios_version} | UDID: {d.udid[:12]}...')")
                devs_json = json.dumps([{
                    "udid": d.udid,
                    "name": d.name,
                    "ios_version": d.ios_version
                } for d in devices])
                self._js(f"updateDeviceList({devs_json})")
                if android:
                    self._js(f"logMsg('Android detected via ADB: {len(android)} device(s).', 'success')")
                self._js(f"logMsg('Found {len(devices)} iPhone(s).', 'success')")
            except Exception as e:
                err = str(e).replace(chr(39), chr(92) + chr(39)).replace("\n", " ")
                self._js(f"setDeviceError('{err}')")
                self._js(f"logMsg('Device scan error: {err}', 'error')")

        threading.Thread(target=_worker, daemon=True).start()

    # ── Location ──

    def set_location(self, lat, lng):
        """Set simulated GPS location on the connected iPhone."""
        from .core import set_location, check_tunneld_running, run_async

        # Clean up previous simulation if any
        self._cleanup_active_sim()

        # Coerce to float (JS might pass strings)
        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError) as e:
            self._js(f"logMsg('Invalid coordinates: {e}', 'error')")
            return

        def _worker():
            try:
                self._js(f"logMsg('Setting location: {lat}, {lng}')")
                result = run_async(set_location(lat, lng))
                # Keep references alive so the simulation persists
                self._active_sim = result
                ios_major = result.get("ios_major", "?")
                self._js(f"logMsg('Location set to ({lat}, {lng}) [iOS {ios_major}]', 'success')")
                self._js("showToast('Location set!', 'success')")
                self._js(f"showLocationActive({lat}, {lng})")
            except Exception as e:
                _dump_traceback("set_location")
                err = str(e).replace("'", "\\'").replace("\n", " ")
                self._js(f"logMsg('Set location error: {err}', 'error')")
                self._js(f"showToast('Failed: {err}', 'error')")
                self._js("locationFailed()")
                self._js(f"logMsg('Full traceback saved to {app_log_path()}', 'warn')")
                # Check tunneld only after failure, as a hint
                if not check_tunneld_running():
                    self._js("logMsg('tunneld could not start automatically. Approve the password/UAC prompt and retry.', 'warn')")
                else:
                    self._js("logMsg('tunneld is running. Check device connection and try again.', 'warn')")

        threading.Thread(target=_worker, daemon=True).start()

    def clear_location(self):
        """Clear simulated location (restore real GPS)."""
        from .core import clear_location, run_async

        # Clean up active simulation first
        self._cleanup_active_sim()

        def _worker():
            try:
                self._js("logMsg('Restoring real location...')")
                run_async(clear_location())
                self._js("logMsg('Real location restored.', 'success')")
                self._js("showToast('Real location restored', 'success')")
                self._js("document.getElementById('coordsHint').textContent = 'Real location active'")
            except Exception as e:
                _dump_traceback("clear_location")
                err = str(e).replace("'", "\\'")
                self._js(f"logMsg('Error: {err}', 'error')")

        threading.Thread(target=_worker, daemon=True).start()

    # ── GPX ──

    def browse_gpx(self):
        """Open file dialog to select a GPX file."""
        import webview

        def _worker():
            try:
                result = webview.windows[0].create_file_dialog(
                    webview.OPEN_DIALOG,
                    file_types=('GPX Files (*.gpx)',)
                )
                if result:
                    path = result[0] if isinstance(result, (list, tuple)) else str(result)
                    safe_path = path.replace("\\", "/").replace("'", "\\'")
                    self._js(f"setGpxPath('{safe_path}')")
            except Exception as e:
                self._js(f"logMsg('File dialog error: {e}', 'error')")

        threading.Thread(target=_worker, daemon=True).start()

    def play_gpx(self, path):
        """Play a GPX file trajectory on the device."""
        from .core import play_gpx_file, run_async

        def _worker():
            try:
                self._js(f"logMsg('Playing GPX: {path}')")
                run_async(play_gpx_file(path))
                self._js("gpxFinished()")
                self._js("logMsg('GPX playback finished.', 'success')")
            except Exception as e:
                _dump_traceback("play_gpx")
                err = str(e).replace("'", "\\'")
                self._js(f"logMsg('GPX error: {err}', 'error')")
                self._js("gpxFinished()")

        threading.Thread(target=_worker, daemon=True).start()

    # ── AMap Key ──

    def get_amap_key(self):
        """Return the saved AMap key (called from JS on init)."""
        if _CONFIG_FILE.exists():
            try:
                config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
                return config.get("amap_key", "")
            except Exception:
                pass
        return ""

    def save_amap_key(self, key):
        """Save AMap API key to config file."""
        config = {}
        if _CONFIG_FILE.exists():
            try:
                config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        config["amap_key"] = key
        _CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear_amap_key(self):
        """Remove AMap API key from config."""
        config = {}
        if _CONFIG_FILE.exists():
            try:
                config = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        config.pop("amap_key", None)
        _CONFIG_FILE.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Utilities ──

    def copy_text(self, text):
        """Copy text to clipboard using native OS clipboard (navigator.clipboard
        requires HTTPS secure context which pywebview local HTML doesn't have)."""
        import subprocess
        try:
            if sys.platform == 'darwin':
                process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
                process.communicate(text.encode('utf-8'))
            elif sys.platform == 'win32':
                process = subprocess.Popen(['clip.exe'], stdin=subprocess.PIPE)
                process.communicate(text.encode('utf-16-le'))
            else:
                process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE)
                process.communicate(text.encode('utf-8'))
        except Exception:
            pass


def main():
    import webview

    api = API()
    html_path = _resource_path("ui.html")
    html_content = html_path.read_text(encoding="utf-8")

    window = webview.create_window(
        title="FakeGPS v6.2.6",
        html=html_content,
        js_api=api,
        width=1280,
        height=800,
        min_size=(960, 600),
        background_color="#0a0e17",
    )
    api.set_window(window)

    def on_closed():
        # Cleanup active simulation and restore real GPS on close
        api._cleanup_active_sim()
        try:
            from .core import clear_location, run_async
            run_async(clear_location())
        except Exception:
            pass

    window.events.closed += on_closed

    webview.start(debug=False)


if __name__ == "__main__":
    main()
