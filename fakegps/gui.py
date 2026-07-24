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
import tempfile
import subprocess
import urllib.request
import urllib.error
import shlex
from pathlib import Path

from . import __version__


_LATEST_RELEASE_URL = "https://api.github.com/repos/sixzjd/fakeGPS-for-iPhone/releases/latest"


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
        self._gpx_future = None
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

    def play_gpx(self, path, speed_kmh=5.0):
        """Play a GPX file trajectory on the device."""
        from .core import play_gpx_file, run_async_cancellable

        def _worker():
            import concurrent.futures
            future = run_async_cancellable(play_gpx_file(path))
            self._gpx_future = future
            try:
                self._js(f"logMsg('Playing GPX: {path} @ default speed')")
                future.result()
                self._js("gpxFinished()")
                self._js("logMsg('GPX playback finished.', 'success')")
            except concurrent.futures.CancelledError:
                self._js("gpxFinished()")
                self._js("logMsg('GPX playback stopped.', 'success')")
            except Exception as e:
                _dump_traceback("play_gpx")
                err = str(e).replace("'", "\\'")
                self._js(f"logMsg('GPX error: {err}', 'error')")
                self._js("gpxFinished()")
            finally:
                if self._gpx_future is future:
                    self._gpx_future = None

        threading.Thread(target=_worker, daemon=True).start()

    def stop_gpx(self):
        """Cancel an active GPX playback immediately."""
        future = self._gpx_future
        if future and not future.done():
            future.cancel()
        else:
            self._js("gpxFinished()")

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

    # ── Updates ──

    @staticmethod
    def _version_tuple(value):
        """Return a comparable version tuple without adding a runtime dependency."""
        parts = str(value or "").lstrip("vV").split(".")
        numbers = []
        for part in parts[:4]:
            digits = "".join(ch for ch in part if ch.isdigit())
            numbers.append(int(digits or 0))
        return tuple(numbers + [0] * (4 - len(numbers)))

    def check_for_update(self):
        """Return latest GitHub release metadata when a newer version exists."""
        request = urllib.request.Request(
            _LATEST_RELEASE_URL,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "FakeGPS"},
        )
        try:
            with urllib.request.urlopen(request, timeout=6) as response:
                release = json.load(response)
            tag = str(release.get("tag_name", ""))
            version = tag.lstrip("vV")
            if not tag or self._version_tuple(version) <= self._version_tuple(__version__):
                return {"available": False, "version": __version__}
            wanted = "FakeGPS-macOS.dmg" if sys.platform == "darwin" else "FakeGPS-Windows-Setup.exe"
            asset = next((a for a in release.get("assets", []) if a.get("name") == wanted), None)
            if not asset:
                return {"available": False, "version": version, "error": "No compatible update package"}
            return {
                "available": True,
                "version": version,
                "tag": tag,
                "asset_name": wanted,
                "asset_url": asset.get("browser_download_url", ""),
            }
        except (OSError, ValueError, urllib.error.URLError) as exc:
            return {"available": False, "version": __version__, "error": str(exc)}

    def update_app(self):
        """Download and install the selected platform update in the background."""
        def _worker():
            info = self.check_for_update()
            if not info.get("available"):
                self._js("showToast('No newer version is available', 'info')")
                return
            try:
                with urllib.request.urlopen(info["asset_url"], timeout=30) as response:
                    suffix = ".dmg" if sys.platform == "darwin" else ".exe"
                    fd, download_path = tempfile.mkstemp(prefix="fakegps-update-", suffix=suffix)
                    with os.fdopen(fd, "wb") as output:
                        while True:
                            chunk = response.read(1024 * 1024)
                            if not chunk:
                                break
                            output.write(chunk)
                if sys.platform == "win32":
                    subprocess.Popen([
                        download_path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                        "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS",
                    ], close_fds=True)
                    self._js("showToast('Update downloaded. FakeGPS will restart shortly.', 'success')")
                    threading.Timer(1.0, lambda: os._exit(0)).start()
                elif sys.platform == "darwin":
                    app_path = Path(sys.executable).resolve().parents[2]
                    mount_path = tempfile.mkdtemp(prefix="fakegps-update-mount-")
                    helper = "\n".join([
                        "#!/bin/sh", "set -eu",
                        f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 1; done",
                        f"hdiutil attach -nobrowse -readonly -mountpoint {shlex.quote(mount_path)} {shlex.quote(download_path)} >/dev/null",
                        f"ditto {shlex.quote(mount_path + '/FakeGPS.app')} {shlex.quote(str(app_path))}",
                        f"hdiutil detach {shlex.quote(mount_path)} >/dev/null || true",
                        f"rm -f {shlex.quote(download_path)}",
                        f"open {shlex.quote(str(app_path))}",
                        'rm -f "$0"', "",
                    ])
                    helper_fd, helper_name = tempfile.mkstemp(prefix="fakegps-update-", suffix=".sh")
                    os.close(helper_fd)
                    helper_path = Path(helper_name)
                    helper_path.write_text(helper, encoding="utf-8")
                    helper_path.chmod(0o700)
                    subprocess.Popen(["/bin/sh", str(helper_path)], start_new_session=True)
                    self._js("showToast('Update downloaded. FakeGPS will restart shortly.', 'success')")
                    threading.Timer(0.5, lambda: os._exit(0)).start()
                else:
                    subprocess.Popen(["xdg-open", download_path])
            except Exception as exc:
                _dump_traceback("update_app")
                message = str(exc).replace("'", "\\'").replace("\n", " ")
                self._js(f"showToast('Update failed: {message}', 'error')")

        threading.Thread(target=_worker, daemon=True).start()
        return {"ok": True, "started": True}


def main():
    import webview

    api = API()
    html_path = _resource_path("ui.html")
    html_content = html_path.read_text(encoding="utf-8")

    window = webview.create_window(
        title="FakeGPS v6.2.2",
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
