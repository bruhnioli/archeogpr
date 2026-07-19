---
type: reference
---

# Windows Executable Build

How to build, run, and smoke-test the ArchaeoGPR native Windows desktop
viewer (Sprint GUI-1, display controls added in Sprint GUI-2, background
file loading added in Sprint GUI-1B, non-destructive processing preview &
apply added in Sprint GUI-3A — current version `0.3.0`). See
[[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]] /
[[02_SPRINTS/Sprint_GUI_2_Display_Controls]] /
[[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]] /
[[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]] for the sprint
records and
[[06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]] for why
the interpreter choice below is not optional. The package version is a
single source of truth (`archaeogpr.__version__` in
`src/archaeogpr/__init__.py`, read by `pyproject.toml` via
`dynamic = ["version"]`) -- `python -m archaeogpr.gui --version`,
`ArchaeoGPR.exe --version`, `pip show archaeogpr`, the startup log entry,
and every PNG export's `.display.json` sidecar all report the same value.

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

One-folder build, ~285 MB total (2026-07-19 measurement, v0.3.0 /
Sprint GUI-3A: 298,551,600 bytes on disk) — dominated by PySide6's Qt
binaries and numpy/scipy's OpenBLAS DLLs, not by this project's own
code. `packaging/archaeogpr.spec` explicitly excludes
`pyqtgraph.examples`/`pyqtgraph.opengl` from the bundle (not used by this
viewer) but does not attempt deeper Qt-submodule trimming yet — see
[[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]] Issues Discovered.

## Smoke Test

```powershell
dist\ArchaeoGPR\ArchaeoGPR.exe --smoke-test   # exit 0, no visible window stays open
dist\ArchaeoGPR\ArchaeoGPR.exe --version      # prints "archaeogpr 0.3.0"
dist\ArchaeoGPR\ArchaeoGPR.exe --open data\raw\Swath003_Array02.ogpr --smoke-test
```

`--open --smoke-test` now waits for the background load (Sprint GUI-1B,
see [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]])
to reach a terminal state (bounded, 15s) before deciding the exit code:
success -> 0, error/cancelled/timeout -> non-zero.

Without `--smoke-test`, the executable stays open (a normal, interactive
window) until the user closes it -- `--smoke-test` exists specifically to
make CI/automated verification possible without a blocking event loop.

All three are logged to `%LOCALAPPDATA%\ArchaeoGPR\logs\archaeogpr.log`
(`frozen: True` confirms it's the bundled executable, not a dev run).

## Manual Demo (interactive)

1. Double-click `dist\ArchaeoGPR\ArchaeoGPR.exe`.
2. **File → Open OGPR...**, pick a `.ogpr` file. A progress indicator with
   a **Cancel** button appears in the status bar; **File → Open** is
   disabled while a load is in progress (Sprint GUI-1B).
3. B-scan renders for channel 0; the channel/trace controls become enabled.
4. Change the channel — the B-scan updates.
5. Open a second file, then click **Cancel** before it finishes — the
   previously-displayed dataset (if any) must remain completely
   unchanged; the status bar shows "Load cancelled".
6. Move the "Clip percentile" slider (90-100%) — the contrast changes;
   weaker reflections become more visible at a lower percentile.
7. Switch Gray ↔ Seismic — the colormap changes.
8. Toggle "Symmetric around zero" off, then try "Manual levels" with a
   valid and then an invalid (min ≥ max) range — the invalid range is
   rejected (shown in red) and never applied.
9. Click anywhere on the B-scan — the yellow trace marker moves there, the
   trace spin box updates, and the A-scan panel updates to that trace.
10. Switch the A-scan mode (Full / Robust / Normalize) and observe the
    difference — the underlying data never changes.
11. Move the mouse over the B-scan — the status bar's "Cursor" label shows
    trace/channel/time/amplitude, separate from the "Selected trace" label.
12. Scroll to zoom, drag to pan (pyqtgraph's built-in `ViewBox` behavior —
    no custom code), then click **Reset View**.
13. Right-click a metadata row — copy its field/value/row/source path.
14. **File → Export Current B-scan PNG...** and check the exported PNG +
    its `.display.json` sidecar.
15. While a file is loading, close the window — it must disappear
    immediately (deferred close: cancellation is requested and the window
    is hidden right away), with no crash and no "QThread: Destroyed while
    thread is still running" warning; the application fully exits once the
    in-flight read actually returns, which is not instant for a large file
    (Sprint GUI-1B, see
    [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]]).
16. In the **Processing** dock, pick an operation (e.g. Dewow), adjust a
    parameter, click **Preview** — the B-scan/A-scan update to show the
    preview, the History list marks it "-- PREVIEW, NOT APPLIED", and
    switching **Display source** to Raw/Current still shows the untouched
    original/committed dataset (Sprint GUI-3A, see
    [[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]]).
17. Click **Apply Preview** — the History list now shows the operation as
    applied (no longer "not applied"), and the channel/trace selection and
    display settings are unchanged.
18. Preview a different operation, then click **Discard Preview** instead
    of Apply — the previously-applied chain is untouched.
19. Click **Reset Current to Raw** (confirm the dialog) — the dataset
    returns to exactly what was read from the file, discarding the entire
    applied processing chain in one step (not step-by-step undo).
20. Start a Preview on a sufficiently large file, then try **File → Open**
    — it must be rejected (disabled) while processing is in flight, and
    vice versa (starting a file load disables the Processing panel).
21. While a preview is computing, close the window — it must disappear
    immediately (same deferred-close policy as file loading), with no
    crash and no "QThread: Destroyed while thread is still running"
    warning.
22. Close the window.

The raw `.ogpr` file's SHA-256 must be identical before and after this
entire flow, including every processing preview/apply — the reader only
ever opens it `"rb"`, and no processing operation ever writes to it (see
`archaeogpr.io.ogpr_reader`, unchanged by every GUI sprint).

## Known Limitations (Sprint GUI-1/GUI-2/GUI-1B/GUI-3A)

- Processing preview/apply is implemented for exactly five stable
  operations (time-zero correction, DC offset correction, dewow,
  band-pass filtering, background removal) — see
  [[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]] /
  [[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]]. No
  gain, no undo/redo stack (only a one-step "Reset Current to Raw"), no
  recipe system, no saving a processed dataset to a file, no 3D/depth —
  see [[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]] /
  [[02_SPRINTS/Sprint_GUI_2_Display_Controls]] /
  [[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]] /
  [[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]] Out of Scope.
- Time-zero's `"manual"` (per-channel pick) method and band-pass's
  `"ormsby"` method are not exposed in the Processing panel — only the
  automatic time-zero methods and Butterworth band-pass (see ADR-015).
- File loading now runs on a background thread (Sprint GUI-1B) and shows
  progress + a Cancel button, but cancellation is cooperative only: a
  cancel request cannot interrupt the read already in flight (it only
  guarantees the result is never committed) — see
  [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]].
  Processing preview's cancellation is cooperative in exactly the same
  way (see ADR-015).
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
- [[02_SPRINTS/Sprint_GUI_2_Display_Controls]]
- [[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]]
- [[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]]
- [[06_DECISIONS/ADR_011_GUI_Technology_Decision]]
- [[06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]]
- [[06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization]]
- [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]]
- [[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]]
- [[03_ARCHITECTURE/GUI_Architecture]]
- `packaging/archaeogpr.spec`
- `scripts/build_windows.ps1`
