# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None
src_root = Path(SPECPATH)

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
    binaries=[],
    datas=[
        (str(src_root / 'fakegps' / 'ui.html'), 'fakegps'),
    ],
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
    ],
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
    strip=True,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
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
            'CFBundleShortVersionString': '6.2.0',
            'CFBundleName': 'FakeGPS',
            'NSHighResolutionCapable': True,
        },
    )
