"""Core device management and location simulation via pymobiledevice3.

Handles iOS version detection and delegates to the appropriate API:
- iOS < 17: DtSimulateLocation (lockdown-based)
- iOS 17+: LocationSimulation via DvtProvider through tunneld
"""

import asyncio
import subprocess
import threading
import concurrent.futures
import os
import sys
import shutil
import time
import shlex
import socket
import tempfile
from dataclasses import dataclass


@dataclass
class DeviceInfo:
    udid: str
    name: str
    ios_version: str


# ── Internal Helpers ──


async def _get_lockdown(serial=None):
    from pymobiledevice3.lockdown import create_using_usbmux
    return await create_using_usbmux(serial=serial)


async def _get_lockdown_via_tunneld(udid=None):
    """Get lockdown client via tunneld (required for iOS 17+ DVT services)."""
    from pymobiledevice3.tunneld.api import (
        get_tunneld_devices, get_tunneld_device_by_udid, TUNNELD_DEFAULT_ADDRESS
    )
    last_error = None
    for _ in range(6):
        try:
            if udid:
                return await get_tunneld_device_by_udid(udid, TUNNELD_DEFAULT_ADDRESS)
            devices = await get_tunneld_devices(TUNNELD_DEFAULT_ADDRESS)
            if devices:
                return devices[0]
            last_error = ConnectionError("No devices found via tunneld")
        except Exception as exc:
            last_error = exc
        await asyncio.sleep(1.0)
    raise ConnectionError("tunneld started but the device channel was not ready") from last_error


async def _query_device_info(lockdown):
    """Extract (version, udid) from a lockdown client with multiple fallbacks."""
    version = "0"
    udid = None
    try:
        info = lockdown.short_info or {}
        version = info.get("ProductVersion") or ""
        udid = info.get("UniqueDeviceID") or lockdown.udid
    except Exception:
        pass
    if not version or version == "0":
        try:
            version = lockdown.product_version or "0"
        except Exception:
            pass
    if not udid:
        udid = lockdown.udid
    return version, udid


def _ios_major(version_str):
    try:
        return int(version_str.split(".")[0])
    except (ValueError, IndexError):
        return 0


async def _get_device_session_context(serial=None):
    """Unified device info: query version/udid, return (major, udid).

    Eliminates the duplicated lockdown-query-close pattern that was
    repeated in set_location, clear_location, and play_gpx_file.
    """
    lockdown = await _get_lockdown(serial=serial)
    try:
        version, udid = await _query_device_info(lockdown)
    finally:
        await lockdown.close()
    return _ios_major(version), udid


async def _open_dvt_session(udid):
    """Open DvtProvider + LocationSimulation for iOS 17+.

    Returns (provider, loc_sim) - caller must _close_dvt_session when done.
    """
    from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
    from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation

    rsd = await _get_lockdown_via_tunneld(udid)
    provider = DvtProvider(rsd)
    await provider.__aenter__()
    try:
        loc_sim = LocationSimulation(provider)
        await loc_sim.__aenter__()
    except Exception:
        try:
            await provider.__aexit__(None, None, None)
        except Exception:
            pass
        raise
    return provider, loc_sim


async def _close_dvt_session(provider, loc_sim):
    """Safely close a DVT session (best-effort cleanup)."""
    if loc_sim:
        try:
            await loc_sim.__aexit__(None, None, None)
        except Exception:
            pass
    if provider:
        try:
            await provider.__aexit__(None, None, None)
        except Exception:
            pass


# ── Public API ──


async def list_connected_devices():
    """List all connected iOS devices."""
    from pymobiledevice3.usbmux import list_devices
    devices = await list_devices()
    result = []
    for dev in devices:
        name = ""
        ios_version = ""
        udid = dev.serial
        try:
            lockdown = await _get_lockdown(serial=dev.serial)
            info = lockdown.short_info or {}
            name = info.get("DeviceName") or ""
            ios_version = info.get("ProductVersion") or ""
            udid = info.get("UniqueDeviceID") or dev.serial
            # Fallback: fresh query via get_value
            if not name or not ios_version:
                try:
                    name = name or await lockdown.get_value("DeviceName") or ""
                    ios_version = ios_version or await lockdown.get_value("ProductVersion") or ""
                except Exception:
                    pass
            if not name:
                try:
                    name = lockdown.product_type or ""
                except Exception:
                    pass
            if not name:
                name = f"iPhone ({dev.serial[:8]}...)"
            if not ios_version:
                ios_version = "Unknown"
            await lockdown.close()
        except Exception:
            name = name or f"Device ({dev.serial[:8]}...)"
            ios_version = ios_version or "Unknown"
        result.append(DeviceInfo(udid=udid, name=name, ios_version=ios_version))
    return result


def list_android_devices():
    """Return Android devices visible through the optional ADB executable."""
    adb = shutil.which("adb")
    if not adb:
        return []
    try:
        lines = subprocess.run([adb, "devices", "-l"], capture_output=True,
                               text=True, timeout=8, check=False).stdout.splitlines()
        return [line.split()[0] for line in lines[1:] if "\tdevice" in line]
    except (OSError, subprocess.SubprocessError):
        return []


_tunneld_process = None
_tunneld_error = ""

TUNNELD_HOST = "127.0.0.1"
TUNNELD_PORT = 49151


def _is_frozen():
    """True when running from a PyInstaller bundle."""
    return getattr(sys, "frozen", False)


def _tunneld_log_path():
    """Where tunneld stdout/stderr is kept for post-mortem debugging."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "FakeGPS-tunneld.log")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Logs/FakeGPS-tunneld.log")
    return os.path.expanduser("~/.fakegps-tunneld.log")


def _tunneld_command():
    """Command line that starts the pymobiledevice3 tunneld server.

    Inside a frozen bundle ``sys.executable`` is the FakeGPS binary itself,
    so it is re-executed with the ``--tunneld`` helper flag (handled in
    run_gui.py).  Using ``-m pymobiledevice3`` there would launch a second
    GUI window instead of the daemon.
    """
    if _is_frozen():
        return [sys.executable, "--tunneld"]
    return [sys.executable, "-m", "pymobiledevice3", "remote", "tunneld"]


def _is_elevated():
    """True when the current process already has root/admin rights."""
    if os.name == "nt":
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return True


def _spawn_detached(command):
    """Spawn tunneld as a detached background process (already elevated).

    Output goes to _tunneld_log_path() so a failing daemon can be diagnosed.
    """
    global _tunneld_process
    try:
        log_fh = open(_tunneld_log_path(), "ab")
    except OSError:
        log_fh = subprocess.DEVNULL
    kwargs = {"stdout": log_fh, "stderr": log_fh,
              "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    else:
        kwargs["start_new_session"] = True
    try:
        _tunneld_process = subprocess.Popen(command, **kwargs)
        return True
    except OSError:
        return False
    finally:
        if log_fh is not subprocess.DEVNULL:
            log_fh.close()


def _launchdaemon_plist(command, log_path, label):
    """Generate a LaunchDaemon plist XML for the tunneld helper.

    launchd keeps the daemon alive independently of the osascript
    privileged-helper session that installed it.
    """
    args_xml = "\n".join("        <string>" + a + "</string>" for a in command)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        "    <key>Label</key>\n    <string>" + label + "</string>\n"
        "    <key>ProgramArguments</key>\n    <array>\n"
        + args_xml + "\n    </array>\n"
        "    <key>RunAtLoad</key>\n    <true/>\n"
        "    <key>KeepAlive</key>\n    <false/>\n"
        "    <key>StandardOutPath</key>\n    <string>" + log_path + "</string>\n"
        "    <key>StandardErrorPath</key>\n    <string>" + log_path + "</string>\n"
        "</dict>\n</plist>\n"
    )


def ensure_tunneld():
    """Make sure the pymobiledevice3 tunneld server is up (iOS 17+).

    tunneld needs root/admin rights to create the tunnel interface, so when
    the app itself is not elevated it is started with elevation:

    - macOS:   native administrator password prompt (osascript)
    - Windows: UAC elevation prompt (ShellExecuteW "runas")

    Returns True once the server answers on 127.0.0.1:49151.  On failure
    the module-level _tunneld_error explains why (shown to the user).
    """
    global _tunneld_error
    _tunneld_error = ""

    if _tunnel_port_ready():
        return True

    command = _tunneld_command()
    log_path = _tunneld_log_path()

    if _is_elevated():
        if not _spawn_detached(command):
            _tunneld_error = "Failed to spawn the tunneld helper process"
            return False
    elif sys.platform == "darwin":
        # Launch via LaunchDaemon plist + launchctl.  The old nohup+&
        # approach failed because osascript's privileged helper kills
        # background children when its session exits.  With launchctl
        # the daemon is managed by launchd and survives independently.
        plist_label = "com.fakegps.tunneld"
        plist_dest = "/Library/LaunchDaemons/" + plist_label + ".plist"
        plist_content = _launchdaemon_plist(command, log_path, plist_label)

        # Write plist to temp (no elevation needed for /tmp).
        plist_tmp = os.path.join(tempfile.gettempdir(), plist_label + ".plist")
        try:
            with open(plist_tmp, "w") as fh:
                fh.write(plist_content)
        except OSError:
            _tunneld_error = "Could not write the tunneld launch configuration"
            return False

        # Privileged step: install plist + (re)start the daemon.
        # bootout first (ignore failure if not loaded), then bootstrap.
        shell_command = (
            "cp " + shlex.quote(plist_tmp) + " " + shlex.quote(plist_dest)
            + " && launchctl bootout system/" + plist_label + " 2>/dev/null; "
            + "launchctl bootstrap system " + shlex.quote(plist_dest)
        )
        apple_script = ('do shell script "'
                        + shell_command.replace('"', '\\"')
                        + '" with administrator privileges')
        try:
            prompt = subprocess.run(
                ["osascript", "-e", apple_script],
                capture_output=True, text=True, timeout=180, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            _tunneld_error = "Could not show the administrator password prompt"
            return False
        if prompt.returncode != 0:
            # User cancelled the password prompt (or osascript failed).
            _tunneld_error = ("Administrator password prompt was cancelled — "
                              "click Set Location again and enter your Mac password "
                              "when the system dialog appears")
            return False
    elif os.name == "nt":
        # UAC elevation on Windows.  SW_HIDE (0) keeps the helper invisible.
        try:
            import ctypes
            params = " ".join('"%s"' % arg for arg in command[1:])
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", command[0], params, None, 0)
            if result <= 32:
                # User declined the UAC prompt or the launch failed.
                _tunneld_error = ("UAC elevation was declined — click Set Location "
                                  "again and approve the administrator prompt")
                return False
        except Exception:
            _tunneld_error = "Could not launch the elevated tunneld helper"
            return False
    else:
        # Linux and others: best effort without elevation.
        if not _spawn_detached(command):
            _tunneld_error = "Failed to spawn the tunneld helper process"
            return False

    # Wait until the RSD endpoint answers (first tunnel can take a while).
    for _ in range(25):
        if _tunnel_port_ready():
            return True
        time.sleep(0.8)
    _tunneld_error = ("tunneld did not come up on 127.0.0.1:49151 — "
                      "see " + log_path + " for details")
    return False


def _tunnel_port_ready():
    """Check the local RSD endpoint, not just a matching process name."""
    try:
        with socket.create_connection((TUNNELD_HOST, TUNNELD_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def run_tunneld_forever():
    """Run the tunneld server in the foreground (--tunneld helper mode).

    This is what the frozen bundle executes when re-launched (elevated) by
    ensure_tunneld(), so the daemon runs without opening a second GUI.
    """
    from pymobiledevice3.remote.common import TunnelProtocol
    from pymobiledevice3.tunneld.server import TunneldRunner

    TunneldRunner.create(TUNNELD_HOST, TUNNELD_PORT, protocol=TunnelProtocol.DEFAULT)


async def set_location(latitude, longitude, serial=None):
    """Set simulated GPS location on connected iPhone.

    Returns a session dict that must be kept alive for the spoof to persist.
    For iOS 17+: {"provider", "sim", "ios_major"}
    For iOS <17:  {"lockdown", "sim", "ios_major"}
    """
    latitude = float(latitude)
    longitude = float(longitude)
    major, udid = await _get_device_session_context(serial)

    if major >= 17:
        if not ensure_tunneld():
            raise ConnectionError(_tunneld_error or "tunneld is not ready on 127.0.0.1:49151")
        # The RemoteXPC/DTX channel occasionally dies mid-flight (e.g. zlib
        # "incorrect header check" on a corrupted stream).  Such errors poison
        # the whole session, so retry by rebuilding the session from scratch.
        last_error = None
        for attempt in range(3):
            provider = loc_sim = None
            try:
                provider, loc_sim = await _open_dvt_session(udid)
                await loc_sim.set(latitude, longitude)
                return {"provider": provider, "sim": loc_sim, "ios_major": major}
            except Exception as exc:
                last_error = exc
                await _close_dvt_session(provider, loc_sim)
                if attempt < 2:
                    await asyncio.sleep(1.0 + attempt)
        raise ConnectionError(
            f"Location update failed after 3 attempts: {last_error}") from last_error
    else:
        lockdown = await _get_lockdown(serial=serial)
        from pymobiledevice3.services.simulate_location import DtSimulateLocation
        sim = DtSimulateLocation(lockdown)
        await sim.set(latitude, longitude)
        return {"lockdown": lockdown, "sim": sim, "ios_major": major}


async def clear_location(serial=None):
    """Clear simulated location (restore real GPS)."""
    major, udid = await _get_device_session_context(serial)

    if major >= 17:
        ensure_tunneld()
        from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
        # Rebuild the whole session on failure — a corrupted channel cannot
        # be recovered from inside the same session.
        last_error = None
        for attempt in range(3):
            try:
                rsd = await _get_lockdown_via_tunneld(udid)
                async with DvtProvider(rsd) as provider:
                    async with LocationSimulation(provider) as loc_sim:
                        await loc_sim.clear()
                        return
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(1.0 + attempt)
        raise ConnectionError(
            f"Clear failed after 3 attempts: {last_error}") from last_error
    else:
        lockdown = await _get_lockdown(serial=serial)
        from pymobiledevice3.services.simulate_location import DtSimulateLocation
        sim = DtSimulateLocation(lockdown)
        await sim.clear()
        await lockdown.close()


async def play_gpx_file(filepath, serial=None):
    """Play a GPX file trajectory on the device."""
    major, udid = await _get_device_session_context(serial)

    if major >= 17:
        from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
        last_error = None
        for attempt in range(3):
            try:
                rsd = await _get_lockdown_via_tunneld(udid)
                async with DvtProvider(rsd) as provider:
                    async with LocationSimulation(provider) as loc_sim:
                        await loc_sim.play_gpx_file(filepath)
                        return
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(1.0 + attempt)
        raise ConnectionError(
            f"GPX playback failed after 3 attempts: {last_error}") from last_error
    else:
        lockdown = await _get_lockdown(serial=serial)
        from pymobiledevice3.services.simulate_location import DtSimulateLocation
        sim = DtSimulateLocation(lockdown)
        await sim.play_gpx_file(filepath)
        await lockdown.close()


def check_tunneld_running():
    """Check whether the tunneld server is up.

    The listening RSD port is the authoritative signal on every platform:
    process-name scans miss the frozen helper (FakeGPS.exe --tunneld) and
    can match stale processes.
    """
    return _tunnel_port_ready()


_loop = None
_loop_thread = None


def _get_persistent_loop():
    """Get (or create) a persistent background event loop."""
    global _loop, _loop_thread
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        _loop_thread = threading.Thread(target=_loop.run_forever, daemon=True)
        _loop_thread.start()
    return _loop


def run_async(coro):
    """Run an async function synchronously on a persistent event loop."""
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running and running.is_running():
        future = concurrent.futures.Future()

        async def _wrapper():
            try:
                result = await coro
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)

        running.create_task(_wrapper())
        return future.result()
    else:
        loop = _get_persistent_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()
