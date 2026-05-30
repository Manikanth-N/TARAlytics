# -*- mode: python ; coding: utf-8 -*-
#
# This spec works on:
#   - Windows (native PyInstaller)
#   - Linux (native PyInstaller — produces Linux binary)
#   - Wine/Docker (cross-compilation to Windows .exe)
#
# collect_data_files() only walks the filesystem — it never imports the package,
# so it is safe under Wine where Qt cannot initialise without a display.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Data files only — no imports triggered
pyqtgraph_datas = collect_data_files('pyqtgraph', includes=['**/*'])
opengl_datas    = collect_data_files('OpenGL',    includes=['**/*'])
pyqt6_datas     = collect_data_files('PyQt6',     includes=['**/*'])

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets/icon.ico', 'assets'),
        ('core',            'core'),
        ('ui',              'ui'),
    ] + pyqtgraph_datas + opengl_datas + pyqt6_datas,
    hiddenimports=[
        # Cryptography
        'cryptography',
        'cryptography.hazmat.primitives.asymmetric.ed25519',
        'cryptography.hazmat.backends',
        'cryptography.hazmat.backends.openssl',
        'cryptography.hazmat.bindings.openssl.binding',
        # Qt
        'PyQt6.QtOpenGL',
        'PyQt6.QtOpenGLWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        # Scientific
        'numpy',
        'numpy.core._multiarray_umath',
        'pandas',
        'pandas._libs.tslibs.timedeltas',
        'pandas._libs.tslibs.np_datetime',
        'pandas._libs.tslibs.nattype',
        'pandas._libs.tslibs.base',
        'pandas._libs.skiplist',
        # pyqtgraph submodules (explicit, no runtime import needed)
        'pyqtgraph',
        'pyqtgraph.graphicsItems',
        'pyqtgraph.widgets',
        'pyqtgraph.Qt',
        'pyqtgraph.opengl',
        'pyqtgraph.opengl.items',
        # OpenGL
        'OpenGL',
        'OpenGL.GL',
        'OpenGL.GLU',
        'OpenGL.arrays',
        'OpenGL.arrays.numpymodule',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'PIL', 'IPython', 'jupyter'],
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
    name='TARAlytics',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TARAlytics',
)
