# -*- mode: python ; coding: utf-8 -*-
import sys
import glob
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

block_cipher = None
src_root = Path(SPECPATH)

# Keep Windows builds compatible with enterprise code-integrity policies.
# UPX-compressed binaries and stripped PE files are more likely to be treated
# as untrusted, and can prevent Python's runtime DLL from loading.
is_windows = sys.platform == 'win32'
windows_version_file = str(src_root / 'windows_version_info.txt') if is_windows else None

# pywebview's Windows backend uses pythonnet.  Collect the package as a whole
# so PyInstaller cannot silently mix a loader from one release with a runtime
# DLL from another release.
PYTHONNET_HIDDENIMPORTS = collect_submodules('pythonnet') + collect_submodules('clr_loader')
PYTHONNET_DATAS = collect_data_files('pythonnet') + collect_data_files('clr_loader')
PYTHONNET_BINARIES = collect_dynamic_libs('pythonnet') + collect_dynamic_libs('clr_loader')
for runtime_dll in glob.glob(str(Path(sys.prefix) / 'Lib' / 'site-packages' / 'pythonnet' / 'runtime' / '*.dll')):
    PYTHONNET_BINARIES.append((runtime_dll, 'pythonnet/runtime'))

# ── Modules to exclude (saves space by removing transitive deps) ──
EXCLUDED_MODULES = [
    # IPython & friends
    'IPython', 'ipython', 'ipykernel', 'ipywidgets',
    'jedi', 'parso', 'prompt_toolkit', 'pygments',
    'traitlets', 'nbformat', 'nbclient', 'notebook',
    # Image processing (not used)
    'PIL', 'Pillow', 'pillow',
    # Packaging (not needed at runtime)
    'setuptools', 'pkg_resources',
    # Testing
    'pytest', 'unittest2',
    # Unused async frameworks
    'trio', 'twisted', 'gevent',
    # Heavy scientific packages
    'matplotlib', 'numpy', 'pandas', 'scipy',
    'tkinter', '_tkinter', 'turtle',
    # Cross-platform webview backends we don't need
    # (macOS uses cocoa, Windows uses edgechromium — exclude qt/gtk backends)
    'webview.platforms.qt',
    'webview.platforms.gtk',
    # PyQt6 is no longer used (switched to pywebview)
    'PyQt6', 'PyQt5', 'PySide6', 'PySide2',
]

a = Analysis(
    [str(src_root / 'run_gui.py')],
    pathex=[str(src_root)],
    datas=[
        (str(src_root / 'fakegps' / 'ui.html'), 'fakegps'),
    ] + PYTHONNET_DATAS,
    hiddenimports=[
        'pymobiledevice3',
        'pymobiledevice3.usbmux',
        'pymobiledevice3.lockdown',
        'pymobiledevice3.services.simulate_location',
        'pymobiledevice3.services.dvt.instruments.dvt_provider',
        'pymobiledevice3.services.dvt.instruments.location_simulation',
        'pymobiledevice3.tunneld.api',
        'pymobiledevice3.tunneld.server',
        'pymobiledevice3.remote.remote_service_discovery',
        'webview',
        'webview.platforms',
        'webview.platforms.cocoa',
        'webview.platforms.edgechromium',
        'webview.platforms.winforms',
        'webview.util',
    ] + PYTHONNET_HIDDENIMPORTS,
    binaries=PYTHONNET_BINARIES,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(src_root / 'hook_stub_modules.py')],
    excludes=EXCLUDED_MODULES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Platform-specific icon
if sys.platform == 'darwin':
    app_icon = str(src_root / 'icon.icns')
else:
    app_icon = str(src_root / 'icon.ico')

# GUI executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FakeGPS',
    icon=app_icon,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    version=windows_version_file,
    # tunneld needs administrator rights on Windows.  Elevate FakeGPS once
    # at launch so Set Location does not invoke UAC on every retry.
    uac_admin=is_windows,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='FakeGPS',
)

# macOS .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='FakeGPS.app',
        icon=str(src_root / 'icon.icns'),
        bundle_identifier='com.sixzjd.fakegps',
        info_plist={
            'CFBundleShortVersionString': '6.2.6',
            'CFBundleName': 'FakeGPS',
            'NSHighResolutionCapable': True,
        },
    )
