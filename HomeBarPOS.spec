# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Home Bar POS
# Works for both Windows (build_exe.bat) and Linux (build_linux.sh)

import sys
from pathlib import Path

block_cipher = None

# Collect escpos data files (capabilities.json etc.) if the package is installed.
# This is optional — if escpos isn't installed the list is just empty and
# thermal receipt printing simply won't be available in the bundle.
try:
    from PyInstaller.utils.hooks import collect_data_files
    escpos_datas = collect_data_files('escpos')
except Exception:
    escpos_datas = []

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static',    'static'),
    ] + escpos_datas,
    hiddenimports=[
        'waitress',
        'waitress.runner',
        'flask',
        'flask_wtf',
        'stripe',
        'jinja2',
        'werkzeug',
        'sqlite3',
        'pkg_resources.py2_warn',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],   # escpos removed — it's now bundled properly with its data files
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HomeBarPOS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,       # keep console visible — server output is useful
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HomeBarPOS',
)
