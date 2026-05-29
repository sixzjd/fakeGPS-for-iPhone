"""Entry point for PyInstaller packaged GUI."""
import sys
from pathlib import Path

# Add package path for imports
sys.path.insert(0, str(Path(__file__).parent))

from fakegps.gui import main

main()
