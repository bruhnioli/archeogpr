---
type: reference
---

# Windows Executable Build

How to build, run, and smoke-test the ArchaeoGPR native Windows desktop
viewer (Sprint GUI-1). See [[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]] for the
sprint record and [[06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]]
for why the interpreter choice below is not optional.

## Prerequisites

- **A python.org CPython 3.12 or 3.13 x64 interpreter** — never Anaconda,
  Miniconda, or the Microsoft Store Python. `scripts/build_windows.ps1`
  refuses to build if it detects one of those in `sys.executable`.
- The project's own `.venv`, built from that interpreter:
  ```powershell
  py -3.13 -m venv .venv
  .\.venv\Scripts\python.exe -m pip install --upgrade pip
  .\.venv\Scripts\python.exe -m pip install -e ".[dev,gui-test,packaging]"
  ```
- Windows 10/11 x64 (the executable is not cross-platform).

## Build Command

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

The script (see its own docstring for full detail):

1. Finds the repository root from its own location (not the caller's cwd).
2. Uses `.venv\Scripts\python.exe` only — refuses a conda/Microsoft Store
   interpreter.
3. Verifies `PySide6`/`PySide6_Essentials`/`PySide6_Addons`/`shiboken6`
   report the *same* version.
4. Runs a `PySide6.QtCore`/`QtWidgets`/`pyqtgraph` import smoke test —
   hard-fails before ever invoking PyInstaller if this doesn't pass.
5. Removes only its own previous `build\ArchaeoGPR\` and
   `dist\ArchaeoGPR\` output (never a general `git clean`).
6. Runs `python -m PyInstaller packaging\archaeogpr.spec`.
7. Runs `dist\ArchaeoGPR\ArchaeoGPR.exe --smoke-test` and fails the script
   (non-zero exit) if that fails.

Or directly:

```powershell
.\.venv\Scripts\python.exe -m PyInstaller packaging\archaeogpr.spec --distpath dist --workpath build --noconfirm
```

## Output Structure

```
dist\
└── ArchaeoGPR\
    ├── ArchaeoGPR.exe          <- the file the end user double-clicks
    └── _internal\              <- Python runtime, Qt, numpy/scipy/pandas/
                                    matplotlib/pyqtgraph -- everything
                                    needed, no separate Python install
```

One-folder build, ~288 MB total (2026-07-17 measurement) — dominated by
PySide6's Qt binaries and numpy/scipy's OpenBLAS DLLs, not by this
project's own code. `packaging/archaeogpr.spec` explicitly excludes
`pyqtgraph.examples`/`pyqtgraph.opengl` from the bundle (not used by this
viewer) but does not attempt deeper Qt-submodule trimming yet — see
[[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]] Issues Discovered.

## Smoke Test

```powershell
dist\ArchaeoGPR\ArchaeoGPR.exe --smoke-test   # exit 0, no visible window stays open
dist\ArchaeoGPR\ArchaeoGPR.exe --version      # prints "archaeogpr 0.1.0"
dist\ArchaeoGPR\ArchaeoGPR.exe --open data\raw\Swath003_Array02.ogpr --smoke-test
```

All three are logged to `%LOCALAPPDATA%\ArchaeoGPR\logs\archaeogpr.log`
(`frozen: True` confirms it's the bundled executable, not a dev run).

## Manual Demo (interactive)

1. Double-click `dist\ArchaeoGPR\ArchaeoGPR.exe`.
2. **File → Open OGPR...**, pick a `.ogpr` file.
3. B-scan renders for channel 0; the channel spin box becomes enabled.
4. Change the channel — the B-scan updates.
5. Click anywhere on the B-scan — the yellow trace marker moves there and
   the A-scan panel updates to that trace.
6. Move the mouse over the B-scan — the status bar shows trace/channel/
   time/amplitude.
7. Scroll to zoom, drag to pan (pyqtgraph's built-in `ViewBox` behavior —
   no custom code).
8. Close the window.

The raw `.ogpr` file's SHA-256 must be identical before and after this
entire flow — the reader only ever opens it `"rb"` (see
`archaeogpr.io.ogpr_reader`, unchanged by this sprint).

## Known Limitations (Sprint GUI-1)

- View-only: no processing (time-zero/DC/dewow/band-pass/background/gain),
  no undo/redo, no recipe, no 3D/depth — see
  [[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]] Out of Scope.
- File loading is synchronous (no background worker yet — `GUI-1B` TODO in
  `models/dataset_session.py`). Acceptable for the ~8 MB reference sample;
  a much larger file would visibly freeze the UI while it loads.
- No project/session save, no `.ogpr` file association, no Start Menu/
  desktop shortcut, no installer, no auto-update — all deferred to a
  future packaging sprint.

## SmartScreen / Code Signing

**This build is unsigned.** Windows SmartScreen may show an "unrecognized
publisher" warning the first time a user runs `ArchaeoGPR.exe` — this is
expected, not a bug, and no code in this project attempts to suppress,
bypass, or auto-dismiss that warning. Before any wider distribution, a
code-signing certificate should be evaluated (out of scope for this
sprint).

## One-Folder vs. One-File

**The one-folder build (`dist\ArchaeoGPR\ArchaeoGPR.exe` +
`_internal\`) is this sprint's accepted primary deliverable.** A one-file
build (a single self-extracting `.exe`) was not required and has not been
attempted in this sprint; if tried later, evaluate startup time (one-file
self-extracts to a temp directory on every launch), antivirus
false-positive risk (single-file PyInstaller executables are flagged more
often than one-folder ones), and re-run the same raw-hash and Turkish/
space-path checks above before treating it as a second accepted output —
see [[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]] for the acceptance bar a
one-file build would also need to clear.

## Clean Rebuild Procedure

```powershell
Remove-Item -Recurse -Force build\ArchaeoGPR, dist\ArchaeoGPR -ErrorAction SilentlyContinue
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

(`build_windows.ps1` already does this removal itself — the above is only
for a manual rebuild without the script.) Never use a general `git clean`
or delete `data\raw\` / `outputs\` — those are user data, not build
output.

## İlgili Notlar

- [[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]]
- [[06_DECISIONS/ADR_011_GUI_Technology_Decision]]
- [[06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]]
- [[03_ARCHITECTURE/GUI_Architecture]]
- `packaging/archaeogpr.spec`
- `scripts/build_windows.ps1`
