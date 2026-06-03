"""Core device management and location simulation via pymobiledevice3.

Handles iOS version detection and delegates to the appropriate API:
- iOS < 17: DtSimulateLocation (lockdown-based)
- iOS 17+: LocationSimulation via DvtProvider through tunneld
"""

import asyncio
import subprocess
import threading
import concurrent.futures
from dataclasses import dataclass


@dataclass
class DeviceInfo:
    udid: str
    name: str
    ios_version: str


async def _get_lockdown(serial=None):
    from pymobiledevice3.lockdown import create_using_usbmux
    return await create_using_usbmux(serial=serial)


async def _get_lockdown_via_tunneld(udid=None):
    """Get lockdown client via tunneld (required for iOS 17+ DVT services)."""
    from pymobiledevice3.tunneld.api import get_tunneld_devices, get_tunneld_device_by_udid, TUNNELD_DEFAULT_ADDRESS
    if udid:
        rsd = await get_tunneld_device_by_udid(udid, TUNNELD_DEFAULT_ADDRESS)
    else:
        devices = await get_tunneld_devices(TUNNELD_DEFAULT_ADDRESS)
        if not devices:
            raise ConnectionError("No devices found via tunneld. Make sure tunneld is running.")
        rsd = devices[0]
    return rsd


async def list_connected_devices():
    """List all connected iOS devices."""
    from pymobiledevice3.usbmux import list_devices
    devices = await list_devices()
    result = []
    for dev in devices:
        try:
            lockdown = await _get_lockdown(serial=dev.serial)
            info = lockdown.short_info
            result.append(DeviceInfo(
                udid=info.get("UniqueDeviceID", dev.serial),
                name=info.get("DeviceName", "Unknown"),
                ios_version=info.get("ProductVersion", "Unknown"),
            ))
            await lockdown.close()
        except Exception:
            result.append(DeviceInfo(
                udid=dev.serial,
                name="Unknown",
                ios_version="Unknown",
            ))
    return result


def _ios_major(version_str):
    try:
        return int(version_str.split(".")[0])
    except (ValueError, IndexError):
        return 0


async def set_location(latitude, longitude, serial=None):
    """Set simulated GPS location on connected iPhone."""
    lockdown = await _get_lockdown(serial=serial)
    try:
        version = lockdown.short_info.get("ProductVersion", "0")
        major = _ios_major(version)
        udid = lockdown.short_info.get("UniqueDeviceID")
        await lockdown.close()

        if major >= 17:
            # iOS 17+ requires tunneld for DVT services
            rsd = await _get_lockdown_via_tunneld(udid)
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
            provider = DvtProvider(rsd)
            await provider.__aenter__()
            loc_sim = LocationSimulation(provider)
            try:
                await loc_sim.__aenter__()
                await loc_sim.set(latitude, longitude)
            except Exception:
                try:
                    await loc_sim.__aexit__(None, None, None)
                except Exception:
                    pass
                try:
                    await provider.__aexit__(None, None, None)
                except Exception:
                    pass
                raise
            return {"rsd": rsd, "provider": provider, "sim": loc_sim, "ios_major": major}
        else:
            # iOS < 17
            lockdown = await _get_lockdown(serial=serial)
            from pymobiledevice3.services.simulate_location import DtSimulateLocation
            sim = DtSimulateLocation(lockdown)
            await sim.set(latitude, longitude)
            return {"lockdown": lockdown, "sim": sim, "ios_major": major}
    except Exception:
        try:
            await lockdown.close()
        except Exception:
            pass
        raise


async def clear_location(serial=None):
    """Clear simulated location (restore real GPS)."""
    lockdown = await _get_lockdown(serial=serial)
    try:
        version = lockdown.short_info.get("ProductVersion", "0")
        major = _ios_major(version)
        udid = lockdown.short_info.get("UniqueDeviceID")
        await lockdown.close()

        if major >= 17:
            rsd = await _get_lockdown_via_tunneld(udid)
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
            async with DvtProvider(rsd) as provider:
                async with LocationSimulation(provider) as loc_sim:
                    await loc_sim.clear()
        else:
            lockdown = await _get_lockdown(serial=serial)
            from pymobiledevice3.services.simulate_location import DtSimulateLocation
            sim = DtSimulateLocation(lockdown)
            await sim.clear()
            await lockdown.close()
    except Exception:
        raise


async def play_gpx_file(filepath, serial=None):
    """Play a GPX file trajectory on the device."""
    lockdown = await _get_lockdown(serial=serial)
    try:
        version = lockdown.short_info.get("ProductVersion", "0")
        major = _ios_major(version)
        udid = lockdown.short_info.get("UniqueDeviceID")
        await lockdown.close()

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
    except Exception:
        raise


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
