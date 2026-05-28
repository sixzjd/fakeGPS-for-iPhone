"""Core device management and location simulation via pymobiledevice3.

Handles iOS version detection and delegates to the appropriate API:
- iOS < 17: DtSimulateLocation (lockdown-based)
- iOS 17+: LocationSimulation via DvtProvider (DVT/instruments-based)

Also manages tunneld status checking.
"""

import asyncio
import subprocess
import platform
from dataclasses import dataclass


@dataclass
class DeviceInfo:
    udid: str
    name: str
    ios_version: str


async def _get_lockdown(serial=None):
    """Create a lockdown client. Auto-selects first USB device if serial is None."""
    from pymobiledevice3.lockdown import create_using_usbmux
    return await create_using_usbmux(serial=serial)


async def list_connected_devices():
    """List all connected iOS devices. Returns list of DeviceInfo."""
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
    """Extract major iOS version number."""
    try:
        return int(version_str.split(".")[0])
    except (ValueError, IndexError):
        return 0


async def set_location(latitude, longitude, serial=None):
    """Set simulated GPS location on connected iPhone.

    Automatically selects the correct API based on iOS version.
    """
    lockdown = await _get_lockdown(serial=serial)
    try:
        version = lockdown.short_info.get("ProductVersion", "0")
        major = _ios_major(version)

        if major >= 17:
            # iOS 17+ uses DVT instruments
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
            # Note: DvtProvider is a context manager that keeps the connection open.
            # For set-and-hold, we need to return the connection objects.
            # We'll use the lower-level approach.
            provider = DvtProvider(lockdown)
            await provider.__aenter__()
            loc_sim = LocationSimulation(provider)
            await loc_sim.__aenter__()
            await loc_sim.set(latitude, longitude)
            # Return objects so caller can close them later
            return {"lockdown": lockdown, "provider": provider, "sim": loc_sim, "ios_major": major}
        else:
            # iOS < 17
            from pymobiledevice3.services.simulate_location import DtSimulateLocation
            sim = DtSimulateLocation(lockdown)
            await sim.set(latitude, longitude)
            return {"lockdown": lockdown, "sim": sim, "ios_major": major}
    except Exception:
        await lockdown.close()
        raise


async def clear_location(serial=None):
    """Clear simulated location (restore real GPS)."""
    lockdown = await _get_lockdown(serial=serial)
    try:
        version = lockdown.short_info.get("ProductVersion", "0")
        major = _ios_major(version)

        if major >= 17:
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
            async with DvtProvider(lockdown) as provider:
                async with LocationSimulation(provider) as loc_sim:
                    await loc_sim.clear()
        else:
            from pymobiledevice3.services.simulate_location import DtSimulateLocation
            sim = DtSimulateLocation(lockdown)
            await sim.clear()
    finally:
        await lockdown.close()


async def play_gpx_file(filepath, serial=None):
    """Play a GPX file trajectory on the device."""
    lockdown = await _get_lockdown(serial=serial)
    try:
        version = lockdown.short_info.get("ProductVersion", "0")
        major = _ios_major(version)

        if major >= 17:
            from pymobiledevice3.services.dvt.instruments.dvt_provider import DvtProvider
            from pymobiledevice3.services.dvt.instruments.location_simulation import LocationSimulation
            async with DvtProvider(lockdown) as provider:
                async with LocationSimulation(provider) as loc_sim:
                    await loc_sim.play_gpx_file(filepath)
        else:
            from pymobiledevice3.services.simulate_location import DtSimulateLocation
            sim = DtSimulateLocation(lockdown)
            await sim.play_gpx_file(filepath)
    finally:
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
        # On Windows, pgrep doesn't exist
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV"],
                capture_output=True, text=True, timeout=5
            )
            return "tunneld" in result.stdout.lower()
        except Exception:
            return False


def run_async(coro):
    """Run an async function synchronously. Safe for nested event loops (e.g. GUI)."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already in an event loop (e.g. Qt), use a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        return asyncio.run(coro)
