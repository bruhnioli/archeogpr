# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the ArchaeoGPR native desktop viewer (Sprint GUI-1).

One-folder, windowed (no console) build. Only the GUI entry point
(``archaeogpr.gui.__main__``) is analyzed -- this bundles the viewer shell
and its own dependency graph (PySide6, pyqtgraph, numpy/pandas/matplotlib/
scipy transitively via ``archaeogpr.io``/``archaeogpr.model``/``archaeogpr.qc``),
not the whole repository. Never bundles user data: no raw ``.ogpr`` sample,
no ``outputs/``, no ``tests/`` fixtures -- see ``datas`` below (empty on
purpose) and ``scripts/build_windows.ps1``, which never copies those
directories into ``dist/``.

Build with ``scripts/build_windows.ps1`` (preferred) or directly:
    pyinstaller packaging/archaeogpr.spec --distpath dist --workpath build
"""

from __future__ import annotations

import os

from PyInstaller.utils.hooks import collect_submodules

# SPECPATH is injected by PyInstaller into the spec's exec namespace.
repo_root = os.path.abspath(os.path.join(SPECPATH, ".."))  # noqa: F821
src_dir = os.path.join(repo_root, "src")
entry_script = os.path.join(src_dir, "archaeogpr", "gui", "__main__.py")

# pyqtgraph resolves several exporter/colormap/graphicsItems submodules
# dynamically (not via static `import` PyInstaller's analyzer can see) --
# collect_submodules is the documented way to make sure those are bundled
# rather than failing at runtime with a hard-to-diagnose ModuleNotFoundError.
# Excludes `pyqtgraph.examples` (pyqtgraph's own demo scripts -- not used by
# this app) and `pyqtgraph.opengl` (this sprint has no 3D/OpenGL view, and
# PyOpenGL is not a project dependency) so only what this viewer actually
# needs is bundled.
hiddenimports = collect_submodules(
    "pyqtgraph",
    filter=lambda name: not name.startswith("pyqtgraph.examples")
    and not name.startswith("pyqtgraph.opengl"),
)

a = Analysis(
    [entry_script],
    pathex=[src_dir],
    binaries=[],
    # Deliberately empty: no raw .ogpr sample data, no outputs/, no test
    # fixtures, no icon (none exists this sprint -- see README/
    # Windows_Executable_Build.md). Nothing under data/, outputs/, or
    # tests/ is ever added here.
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ArchaeoGPR",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed: no black console window for the end user
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # no project .ico this sprint -- default executable icon is accepted
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ArchaeoGPR",
)
