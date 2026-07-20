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


def ensure_tunneld():
    """Start tunneld from the app when iOS 17+ needs it."""
    global _tunneld_process
    if check_tunneld_running() and _tunnel_port_ready():
        return True
    command = [sys.executable, "-m", "pymobiledevice3", "remote", "tunneld", "--daemonize"]
    kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
              "stdin": subprocess.DEVNULL, "start_new_session": True}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        _tunneld_process = subprocess.Popen(command, **kwargs)
        for _ in range(15):
            if check_tunneld_running() and _tunnel_port_ready():
                return True
            time.sleep(0.8)
        return False
    except OSError:
        return False


def _tunnel_port_ready():
    """Check the local RSD endpoint, not just a matching process name."""
    try:
        with socket.create_connection(("127.0.0.1", 49151), timeout=0.5):
            return True
    except OSError:
        return False


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
            raise ConnectionError("tunneld is not ready on 127.0.0.1:49151")
        provider, loc_sim = await _open_dvt_session(udid)
        try:
            await loc_sim.set(latitude, longitude)
        except Exception:
            await _close_dvt_session(provider, loc_sim)
            raise
        return {"provider": provider, "sim": loc_sim, "ios_major": major}
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
        rsd = await _get_lockdown_via_tunneld(udid)
        from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
        async with DvtProvider(rsd) as provider:
            async with LocationSimulation(provider) as loc_sim:
                for attempt in range(3):
                    try:
                        await loc_sim.clear()
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(0.8)
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
        rsd = await _get_lockdown_via_tunneld(udid)
        from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
        from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
        async with DvtProvider(rsd) as provider:
            async with LocationSimulation(provider) as loc_sim:
                await loc_sim.play_gpx_file(filepath)
    else:
        lockdown = await _get_lockdown(serial=serial)
        from pymobiledevice3.services.simulate_location import DtSimulateLocation
        sim = DtSimulateLocation(lockdown)
        await sim.play_gpx_file(filepath)
        await lockdown.close()


def check_tunneld_running():
    """Check if pymobiledevice3 tunneld process is running."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "pymobiledevice3 remote tunneld"],
            capture_output=True, timeout=3
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
                capture_output=True, text=True, timeout=5
            )
            return "tunneld" in result.stdout.lower()
        except Exception:
            return False


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
