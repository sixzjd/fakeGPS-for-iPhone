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
# The official site is backed by R2 and is far faster than GitHub in mainland China,
# so it is tried first; the GitHub asset URL remains the canonical fallback.
_MIRROR_BASE_URL = "https://fakegps.sixzjd.sbs/dl"


def _download_first(urls, suffix):
    """Stream the first reachable URL into a temp file and return its path."""
    last_error = None
    for url in urls:
        fd, path = tempfile.mkstemp(prefix="fakegps-update-", suffix=suffix)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "FakeGPS"})
            with urllib.request.urlopen(request, timeout=30) as response:
                expected = int(response.headers.get("Content-Length") or 0)
                with os.fdopen(fd, "wb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
            size = os.path.getsize(path)
            if expected and size != expected:
                raise OSError(f"incomplete download ({size}/{expected} bytes)")
            return path
        except Exception as exc:
            last_error = exc
            try:
                os.close(fd)
            except OSError:
                pass
            os.unlink(path)
    raise last_error or RuntimeError("No download source available")


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


def _js_literal(value):
    """Render *value* as a JavaScript string literal, quotes included.

    ``json.dumps`` emits a JSON string, which is also a valid JavaScript one,
    so it escapes quotes, backslashes, newlines and control characters
    correctly.  The hand-rolled ``.replace("'", "\\'")`` escaping this
    replaces only covered quotes: an exception message containing a newline
    (pymobiledevice3 tracebacks do) or a Windows path containing a backslash
    produced a JavaScript syntax error, ``evaluate_js`` raised, and the
    message never reached the UI at all.
    """
    return json.dumps(str(value), ensure_ascii=False)


def _js_call(function, *args):
    """Build a ``function(arg, ...)`` statement with every argument quoted."""
    return function + "(" + ", ".join(_js_literal(arg) for arg in args) + ")"


def _exception_chain(exc):
    """Return *exc* and everything it was raised ``from``, outermost first."""
    chain = []
    seen = set()
    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _describe_error(exc):
    """Render an exception chain as a non-empty, human-readable string.

    ``core`` wraps device failures in ``ConnectionError("...: {last_error}")``,
    but some pymobiledevice3 exceptions (``StartServiceError``) call
    ``super().__init__()`` with no message at all, so that wrapped text came
    out empty and the user saw "failed after 3 attempts: " with nothing after
    it.  Naming the innermost exception fixes that.
    """
    root = _exception_chain(exc)[-1]
    name = type(root).__name__
    text = str(root).strip()
    return f"{name}: {text}" if text else name


def _device_failure_hint(exc, tunneld_ready):
    """Map a device-path exception onto the most likely actionable cause.

    The iOS 17+ path needs more than "a tunnel is running" -- Developer Mode
    and a mounted Developer Disk Image are separate prerequisites -- so
    reporting every failure as a tunneld problem sent users chasing the wrong
    thing.  Classifying on the innermost exception is what makes this
    reliable, because the outermost one is always our own generic wrapper.
    """
    chain = _exception_chain(exc)
    names = {type(item).__name__ for item in chain}
    text = " ".join(str(item) for item in chain)

    if names & {"StartServiceError", "InvalidServiceError", "DeviceFeatureNotSupportedError"}:
        return ("The iPhone refused the developer service. On iOS 16+ turn on "
                "Settings > Privacy & Security > Developer Mode, and make sure a "
                "Developer Disk Image is mounted (pymobiledevice3 mounter auto-mount), "
                "then retry.")
    if names & {"PasswordRequiredError", "PasswordProtectedError"} or "PasswordProtected" in text:
        return "Unlock the iPhone, tap Trust on the prompt, then retry."
    if names & {"UserDeniedPairingError", "InvalidHostIDError"} or "UserDenied" in text:
        return ("This computer is not trusted. On the iPhone open Settings > General > "
                "Transfer or Reset iPhone > Reset > Reset Location & Privacy, reconnect "
                "the cable and tap Trust, then retry.")
    if "NoDeviceConnectedError" in names:
        return "No iPhone found over USB. Reconnect the cable and retry."
    if "TunneldConnectionError" in names or not tunneld_ready():
        return ("tunneld could not start automatically. Approve the password/UAC "
                "prompt and retry.")
    return "tunneld is running. Check device connection and try again."


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

    def _log(self, message, level=None):
        """Append a line to the in-app log with safe quoting."""
        if level is None:
            self._js(_js_call("logMsg", message))
        else:
            self._js(_js_call("logMsg", message, level))

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
                    self._log('No devices found. Check Apple Devices/ADB and USB trust.')
                    return
                for d in devices:
                    # A device name is user-controlled and routinely contains an
                    # apostrophe ("John's iPhone"), which used to inject a syntax
                    # error here and abort the refresh before the list was sent.
                    self._log(f"Device: {d.name} | iOS {d.ios_version} | UDID: {d.udid[:12]}...")
                devs_json = json.dumps([{
                    "udid": d.udid,
                    "name": d.name,
                    "ios_version": d.ios_version
                } for d in devices])
                self._js(f"updateDeviceList({devs_json})")
                if android:
                    self._log(f"Android detected via ADB: {len(android)} device(s).", "success")
                self._log(f"Found {len(devices)} iPhone(s).", "success")
            except Exception as e:
                err = _describe_error(e)
                self._js(_js_call("setDeviceError", err))
                self._log(f"Device scan error: {err}", "error")

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
            self._log(f"Invalid coordinates: {e}", "error")
            return

        def _worker():
            try:
                self._log(f"Setting location: {lat}, {lng}")
                result = run_async(set_location(lat, lng))
                # Keep references alive so the simulation persists
                self._active_sim = result
                ios_major = result.get("ios_major", "?")
                self._log(f"Location set to ({lat}, {lng}) [iOS {ios_major}]", "success")
                self._js("showToast('Location set!', 'success')")
                self._js(f"showLocationActive({lat}, {lng})")
            except Exception as e:
                _dump_traceback("set_location")
                err = _describe_error(e)
                self._log(f"Set location error: {err}", "error")
                self._js(_js_call("showToast", f"Failed: {err}", "error"))
                self._js("locationFailed()")
                self._log(f"Full traceback saved to {app_log_path()}", "warn")
                # Point at the real cause rather than guessing at tunneld.
                self._log(_device_failure_hint(e, check_tunneld_running), "warn")

        threading.Thread(target=_worker, daemon=True).start()

    def clear_location(self):
        """Clear simulated location (restore real GPS)."""
        from .core import clear_location, run_async

        # Clean up active simulation first
        self._cleanup_active_sim()

        def _worker():
            try:
                self._log("Restoring real location...")
                run_async(clear_location())
                self._log("Real location restored.", "success")
                self._js("showToast('Real location restored', 'success')")
                self._js("document.getElementById('coordsHint').textContent = 'Real location active'")
            except Exception as e:
                _dump_traceback("clear_location")
                err = _describe_error(e)
                self._log(f"Error: {err}", "error")

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
                    # Forward slashes read better in the UI and are accepted by
                    # every OS path API the playback path goes through.
                    display_path = path.replace("\\", "/")
                    self._js(_js_call("setGpxPath", display_path))
            except Exception as e:
                self._log(f"File dialog error: {e}", "error")

        threading.Thread(target=_worker, daemon=True).start()

    def play_gpx(self, path, speed_kmh=5.0):
        """Play a GPX file trajectory on the device."""
        from .core import play_gpx_file, run_async_cancellable

        def _worker():
            import concurrent.futures
            future = run_async_cancellable(play_gpx_file(path))
            self._gpx_future = future
            try:
                self._log(f"Playing GPX: {path} @ default speed")
                future.result()
                self._js("gpxFinished()")
                self._log("GPX playback finished.", "success")
            except concurrent.futures.CancelledError:
                self._js("gpxFinished()")
                self._log("GPX playback stopped.", "success")
            except Exception as e:
                _dump_traceback("play_gpx")
                err = _describe_error(e)
                self._log(f"GPX error: {err}", "error")
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
        """Return latest release metadata and download URLs when a newer version exists."""
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
                "urls": [u for u in (f"{_MIRROR_BASE_URL}/{wanted}", asset.get("browser_download_url", "")) if u],
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
                suffix = ".dmg" if sys.platform == "darwin" else ".exe"
                download_path = _download_first(info["urls"], suffix)
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
                message = _describe_error(exc)
                self._js(_js_call("showToast", f"Update failed: {message}", "error"))

        threading.Thread(target=_worker, daemon=True).start()
        return {"ok": True, "started": True}


def main():
    import webview

    api = API()
    html_path = _resource_path("ui.html")
    html_content = html_path.read_text(encoding="utf-8").replace("__VERSION__", __version__)

    window = webview.create_window(
        title=f"FakeGPS v{__version__}",
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
