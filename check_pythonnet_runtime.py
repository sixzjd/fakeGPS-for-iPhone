"""Fail CI if the packaged Python.NET runtime lacks its public loader symbol."""
from pathlib import Path
import sys
from importlib.metadata import version

try:
    import clr_loader
    import pythonnet
    from pythonnet import load
except Exception as exc:
    raise SystemExit(f'Python.NET import failed: {exc}')

runtime = Path(pythonnet.__file__).with_name('runtime') / 'Python.Runtime.dll'
if not runtime.is_file():
    raise SystemExit(f'Python.Runtime.dll not found: {runtime}')

try:
    load()
    from System.Reflection import Assembly
    assembly = Assembly.LoadFile(str(runtime.resolve()))
    loader_type = assembly.GetType('Python.Runtime.Loader')
    initialize = loader_type.GetMethod('Initialize') if loader_type else None
except Exception as exc:
    raise SystemExit(f'Python.Runtime.dll could not be loaded: {exc}')

if loader_type is None or initialize is None:
    raise SystemExit(f'{runtime} lacks Python.Runtime.Loader.Initialize; installed Python.NET is incompatible')
print(f"pywebview {version('pywebview')}; Python.NET {version('pythonnet')}; clr-loader {version('clr-loader')}; verified {runtime}")
