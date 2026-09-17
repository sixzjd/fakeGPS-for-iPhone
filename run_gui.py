"""Entry point for PyInstaller packaged GUI."""
import sys
import os
import subprocess
from pathlib import Path

# Add package path for imports
sys.path.insert(0, str(Path(__file__).parent))


def _unblock_frozen_bundle():
    """Remove the browser download zone mark from extracted bundle files."""
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return
    bundle = getattr(sys, "_MEIPASS", None)
    if not bundle:
        return
    command = (
        "Get-ChildItem -LiteralPath $env:FAKEGPS_BUNDLE -Recurse -Force "
        "-File | Unblock-File -ErrorAction SilentlyContinue"
    )
    env = os.environ.copy()
    env["FAKEGPS_BUNDLE"] = bundle
    kwargs = {"env": env, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            timeout=30,
            check=False,
            **kwargs,
        )
    except (OSError, subprocess.SubprocessError):
        pass


_unblock_frozen_bundle()

if len(sys.argv) > 1 and sys.argv[1] == "--tunneld":
    # Helper mode: run the pymobiledevice3 tunneld server in the foreground
    # instead of the GUI.  core.ensure_tunneld() re-executes the frozen
    # binary with this flag (elevated) so the daemon starts without opening
    # a second GUI window.
    from fakegps.core import run_tunneld_forever

    run_tunneld_forever()
    raise SystemExit(0)

if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
    # Import-only smoke test for the device path.  Launching the GUI does not
    # import pymobiledevice3 at all, so a missing transitive dependency stays
    # invisible until a user plugs in an iPhone -- which is exactly how v6.2.3
    # shipped with prompt_toolkit excluded and every connect/location call
    # failing.  CI runs this on the frozen bundle and fails the build on error.
    #
    # The list has to cover every path a user can actually reach, including the
    # tunneld helper: core.run_tunneld_forever() pins TunnelProtocol.TCP, and
    # the TCP tunnel lives in pymobiledevice3.remote.tunnel_service.
    import importlib

    _SELFTEST_MODULES = (
        "pymobiledevice3.usbmux",
        "pymobiledevice3.lockdown",
        "pymobiledevice3.services.simulate_location",
        "pymobiledevice3.services.dvt.instruments.dvt_provider",
        "pymobiledevice3.services.dvt.instruments.location_simulation",
        "pymobiledevice3.tunneld.api",
        "pymobiledevice3.tunneld.server",
        "pymobiledevice3.remote.common",
        "pymobiledevice3.remote.tunnel_service",
    )

    # Value-level checks.  tunnel_service imports sslpsk_pmd3 inside a
    # ``try/except ImportError`` that silently degrades SSLPSKContext to None,
    # so a bundle missing it imports perfectly and only fails later with an
    # AssertionError while the user waits for a location update.  Importing the
    # module is therefore not enough -- the value has to be asserted.
    _SELFTEST_ASSERTIONS = 3

    _failed = []
    for _name in _SELFTEST_MODULES:
        try:
            importlib.import_module(_name)
        except Exception as _exc:
            _failed.append(f"{_name}: {type(_exc).__name__}: {_exc}")

    try:
        from pymobiledevice3.remote.common import TunnelProtocol
        from pymobiledevice3.remote import tunnel_service

        if TunnelProtocol.TCP.value != "tcp":
            _failed.append(
                f"TunnelProtocol.TCP: unexpected value {TunnelProtocol.TCP.value!r}")
        # Python >=3.13 builds the PSK context from the stdlib ssl module, so
        # sslpsk_pmd3 is only load-bearing below that.
        if sys.version_info < (3, 13) and tunnel_service.SSLPSKContext is None:
            _failed.append(
                "sslpsk_pmd3.sslpsk: SSLPSKContext is None, but the TCP tunnel "
                "pinned by core.run_tunneld_forever() requires it on python<3.13")
    except Exception as _exc:
        _failed.append(f"tcp tunnel probe: {type(_exc).__name__}: {_exc}")

    _total = len(_SELFTEST_MODULES) + _SELFTEST_ASSERTIONS
    for _line in _failed:
        print(f"FAIL {_line}")
    print(f"selftest: {_total - len(_failed)}/{_total} checks passed")
    raise SystemExit(1 if _failed else 0)

from fakegps.gui import main

main()
