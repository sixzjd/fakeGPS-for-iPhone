# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None
src_root = Path(SPECPATH)

# ── Modules to exclude ──
EXCLUDED_MODULES = [
    'IPython', 'ipython', 'ipykernel', 'ipywidgets',
    'jedi', 'parso', 'prompt_toolkit', 'pygments',
    'traitlets', 'nbformat', 'nbclient', 'notebook',
    'PIL', 'Pillow', 'pillow',
    'setuptools', 'distutils', 'pkg_resources',
    'pytest', 'unittest2',
    'trio', 'twisted', 'gevent',
    'matplotlib', 'numpy', 'pandas', 'scipy',
    'tkinter', '_tkinter', 'turtle',
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
        'webview.platforms.gtk',
        'webview.platforms.qt',
        'webview.platforms.winforms',
        'webview.util',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED_MODULES,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# GUI executable
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FakeGPS',
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
        icon=None,
        bundle_identifier='com.sixzjd.fakegps',
        info_plist={
            'CFBundleShortVersionString': '6.0.0',
            'CFBundleName': 'FakeGPS',
            'NSHighResolutionCapable': True,
        },
    )
