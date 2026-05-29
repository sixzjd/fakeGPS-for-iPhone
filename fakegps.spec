# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

block_cipher = None
src_root = Path(SPECPATH)

a = Analysis(
    [str(src_root / 'run_gui.py')],
    pathex=[str(src_root)],
    binaries=[],
    datas=[
        (str(src_root / 'fakegps' / 'map.html'), 'fakegps'),
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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    strip=False,
    upx=True,
    console=False,  # No terminal window for GUI
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
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
