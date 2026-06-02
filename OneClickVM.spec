# OneClickVM.spec
# PyInstaller build spec for OneClickVM Windows release.
# Usage:  pyinstaller OneClickVM.spec
# Output: dist/OneClickVM/OneClickVM.exe  (onedir mode)

import os
block_cipher = None

# ── Resolve asset paths relative to this spec file ───────────────────────────
ROOT = os.path.abspath(os.path.dirname(SPEC))

a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # ── Branding / logo assets ────────────────────────────────────────────
        (os.path.join(ROOT, 'frontend', 'logo.png'),            'frontend'),
        (os.path.join(ROOT, 'frontend', 'favicon'),             'frontend/favicon'),
        # OS templates (JSON / YAML config)
        (os.path.join(ROOT, 'templates'),                       'templates'),
        # Widget package resources
        (os.path.join(ROOT, 'frontend', 'widgets'),             'frontend/widgets'),
        # Marketplace data (JSON catalog + banner images)
        (os.path.join(ROOT, 'frontend', 'data'),                'frontend/data'),
        (os.path.join(ROOT, 'frontend', 'assets'),              'frontend/assets'),
    ],
    hiddenimports=[
        # PyQt5 plugins that PyInstaller misses under onedir
        'PyQt5.sip',
        'PyQt5.QtSvg',
        'PyQt5.QtXml',
        # QFluentWidgets internal registries
        'qfluentwidgets',
        'qfluentwidgets.common',
        'qfluentwidgets.components',
        # pywin32 extensions used for HWND embedding
        'win32api',
        'win32con',
        'win32gui',
        'pywintypes',
        # system
        'psutil',
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'email',
        'html',
        'http',
        'xml',
        'pydoc',
        'doctest',
    ],
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
    name='OneClickVM',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,                              # no black console window
    icon=os.path.join(ROOT, 'frontend', 'favicon', 'favicon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OneClickVM',
)
