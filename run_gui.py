"""Entry point for PyInstaller packaged GUI."""
import sys
from pathlib import Path

# Add package path for imports
sys.path.insert(0, str(Path(__file__).parent))

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
