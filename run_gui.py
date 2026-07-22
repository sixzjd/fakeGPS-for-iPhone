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

from fakegps.gui import main

main()
