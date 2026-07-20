---
type: reference
---

# Windows Executable Build

How to build, run, and smoke-test the ArchaeoGPR native Windows desktop
viewer (Sprint GUI-1, display controls added in Sprint GUI-2, background
file loading added in Sprint GUI-1B, non-destructive processing preview &
apply added in Sprint GUI-3A, survey geometry inspector and C-scan
readiness added in Sprint 3D-0, actual X/Y point-grid C-scan/time-slice
viewer added in Sprint 3D-1 — current version `0.5.0`). See
[[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]] /
[[02_SPRINTS/Sprint_GUI_2_Display_Controls]] /
[[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]] /
[[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]] /
[[02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector]] /
[[02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan]] for the sprint
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

One-folder build, ~285 MB total (2026-07-19 measurement, v0.4.0 /
Sprint 3D-0: 298,597,708 bytes on disk, of which `ArchaeoGPR.exe` itself
is 21,113,104 bytes; v0.3.0 / Sprint GUI-3A measured 298,551,600 bytes) —
dominated by PySide6's Qt binaries and numpy/scipy's OpenBLAS DLLs, not by
this project's own code. The ~46 KB delta between 0.3.0 and 0.4.0 reflects
the new pure-Python `archaeogpr.geometry` package and GUI modules only —
no new binary dependency was added for Sprint 3D-0. v0.5.0 / Sprint 3D-1
adds only the new pure-Python `archaeogpr.cscan` package and GUI modules
(no new binary dependency either — see the sprint's own final report for
the exact measured size/hash once built). `packaging/archaeogpr.spec` explicitly excludes
`pyqtgraph.examples`/`pyqtgraph.opengl` from the bundle (not used by this
viewer) but does not attempt deeper Qt-submodule trimming yet — see
[[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]] Issues Discovered.

## Smoke Test

```powershell
dist\ArchaeoGPR\ArchaeoGPR.exe --smoke-test   # exit 0, no visible window stays open
dist\ArchaeoGPR\ArchaeoGPR.exe --version      # prints "archaeogpr 0.5.0"
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
22. In the **Survey Geometry** dock, review sections A-G (coordinate
    mode, geometry revision, and all 7 readiness flags; dataset axes;
    spacing/orientation; georeferencing; per-field provenance;
    validation/warnings; grid regularity — sampling/direction/rectilinear
    fit and the three footprint-area figures) for the loaded real file —
    confirm the coordinate mode reads **Global projected** (real
    geolocation present) and azimuth/cross-track direction are shown as
    *Derived*, not *File metadata* (Sprint 3D-0, see
    [[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]]).
    Confirm section G reports `rectilinear_cscan_ready` as blocked for
    this real file (the real acquisition grid does not fit a single-
    origin/single-azimuth reconstruction within tolerance) even though
    sampling regularity and direction consistency both read as regular —
    see "Commit-Öncesi Audit Turu 2" in
    [[02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector]].
23. In the **Plan View** dock, confirm the acquisition points render as a
    single scatter with equal-aspect axes, a start (green) / end (red)
    along-track marker and line, and a separate cross-track
    (channel-ascending direction) line.
24. Click a point in the Plan View — the B-scan trace/channel selection
    updates to match; conversely, change the trace spin box or channel
    selector — the Plan View's highlighted point updates to match.
25. Hover over the Plan View — the coordinate readout updates
    continuously without changing the persistent selection.
26. Change an override field (e.g., Azimuth degrees) in the geometry
    override form — the Survey Geometry panel must **not** update until
    you click **Apply Geometry**; then click **Discard Overrides** instead
    and confirm the form reverts to the last-applied/file values.
27. Click **Apply Geometry** with a valid override set — the panel
    updates, `Geometry revision` increments, and section E shows the
    overridden fields as *User supplied*; then click **Reset Geometry to
    File Metadata** and confirm every override clears.
28. Start a Preview (Processing dock) or a new file load, and confirm
    **Apply Geometry** / **File → Export Geometry Report...** are
    disabled while it is in flight, but the Survey Geometry / Plan View
    panels remain readable and trace/channel selection sync keeps
    working.
29. **File → Export Geometry Report...**, save the `.geometry.json` file,
    and confirm it opens as valid JSON with no `NaN`/`Infinity` tokens.
30. In the **C-scan / Time Slice** dock, leave Source at its default
    (**Current**), Geometry view at its default (**Actual X/Y point
    map**), Aggregation at its default (**Single sample**), set a Center
    time within the loaded file's time range, and click **Compute** — the
    rendered view shows one colored point per valid (trace, channel), and
    the mode label reads "Actual X/Y point map — no interpolation"
    (Sprint 3D-1, see
    [[06_DECISIONS/ADR_017_Actual_XY_CScan_and_No_Interpolation_Policy]]).
31. Switch **Geometry view** to **Derived s/c parameter grid** — the view
    switches to a continuous image (along-track on the X axis,
    cross-track on the Y axis) and the mode label reads "Derived s/c
    parameter grid"; switch back and confirm the two views never show the
    same rendering.
32. Switch **Aggregation** to **RMS**, **Mean absolute**, or **Maximum
    absolute** — the "Window width, ns" field becomes enabled; set a
    width and click **Compute** again — confirm the displayed values are
    never negative for these three, unlike **Single sample**. Confirm
    **Symmetric around zero** (Display section) becomes disabled for a
    window aggregation and re-enables for **Single sample**.
33. Click a point in the C-scan view — the B-scan/A-scan trace and
    channel selection updates to match; conversely, change the trace spin
    box or channel selector — the C-scan view's highlighted point updates
    to match, and the Plan View's own selection stays in sync with both.
34. Confirm a successful Compute positions the B-scan's draggable time
    cursor at the requested center time; drag the cursor to a new
    position on the B-scan and confirm the C-scan dock's "Center time, ns"
    field updates to match.
35. Change **Source** to **Preview** (only enabled once a Processing
    preview exists), Compute again, then click **Discard Preview** in the
    Processing dock — confirm the C-scan status changes to "Stale" rather
    than silently showing a now-invalid result.
36. Start a Preview (Processing dock) or a new file load, and confirm
    **Compute**/**Export C-scan PNG + JSON...** are disabled while it is
    in flight, but the C-scan view remains visible (showing the last
    valid result) and trace/channel selection sync keeps working;
    conversely, starting a C-scan Compute must disable **File → Open**
    and the Processing dock's **Preview** button until it finishes.
37. Start a C-scan Compute on a sufficiently large file, then click
    **Cancel Compute** — the dock returns to its previous state without
    crashing, and any *previous* valid result (if one existed) remains
    displayed.
38. While a C-scan compute is running, close the window — it must
    disappear immediately (same deferred-close policy as file loading/
    processing preview), with no crash and no "QThread: Destroyed while
    thread is still running" warning.
39. **File → Export C-scan PNG + JSON...** (or the dock's own Export
    button), save the file, and confirm both the `.png` and its
    `.cscan.json` sidecar exist, the JSON opens as valid JSON with no
    `NaN`/`Infinity` tokens, and it includes `"no_interpolation": true`.
40. Close the window.

The raw `.ogpr` file's SHA-256 must be identical before and after this
entire flow, including every processing preview/apply, every geometry
override/apply/export, and every C-scan compute/view-switch/export — the
reader only ever opens it `"rb"`, and no processing, geometry, or C-scan
operation ever writes to it (see `archaeogpr.io.ogpr_reader`, unchanged by
every GUI sprint).

## Known Limitations (Sprint GUI-1/GUI-2/GUI-1B/GUI-3A/3D-0/3D-1)

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
- The Survey Geometry Inspector and Plan View (Sprint 3D-0) audit and
  display geometry — they never build or render a C-scan or 3D volume.
  No PyVista, no VTK, no gridding/resampling, no depth conversion; all
  seven readiness gates (`index_view_ready`, `local_parameter_grid_ready`,
  `rectilinear_cscan_ready`, `actual_xy_point_grid_ready`,
  `global_cscan_ready`, `time_volume_ready`, `depth_volume_ready`) report
  *whether* a downstream volume could be built, never build one — see
  [[02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector]] /
  [[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]].
  `depth_volume_ready` is unconditionally `False` this sprint (no
  velocity-confirmation flow exists yet).
- "Regular sampling" (are step lengths and cross-channel spacing close to
  constant?) and "rectilinear fit" (does the real acquisition grid
  coincide with a single-origin, single-azimuth reconstruction within
  tolerance?) are independent findings, not one combined flag — a survey
  can be excellently sampled and still fail rectilinear fit (confirmed on
  the bundled real file: step-length and cross-channel spacing
  coefficients of variation are both under 1%, yet the point-by-point
  residual against the idealized reconstruction is several times the
  channel spacing). `rectilinear_cscan_ready` and
  `actual_xy_point_grid_ready` expose this distinction as separate gates;
  see the "Grid Regularity" section of the Survey Geometry dock and
  ADR-016 Addendum 2.
- The geometry override form validates the CRS/EPSG field's format and
  sign only (e.g. `"EPSG:32632"` or a bare positive integer) — there is
  no network lookup or authority validation. Overriding
  `channel_zero_offset_m`/origin/azimuth fields marks them
  *User supplied* as soon as the field is touched (these are legitimately
  signed, so `0.0` is a real value, not an "unset" sentinel); reverting to
  "not set" for those specific fields requires **Discard Overrides** or
  **Reset Geometry to File Metadata**, not clearing the field itself.
- Geometry is resolved once per successful file load and is never
  recomputed by processing preview/apply/discard/reset-to-raw — this is
  correct for all five current processing operations (none change
  trace/channel count) but would need revisiting if a future
  shape-changing operation were added.
- The "Coordinate mode" row and a dedicated "CRS validation status" row
  always make explicit that a present CRS/EPSG code (declared in the file
  or entered by the user) is *unverified* — this project performs no
  authority/network CRS validation (`CrsValidationStatus.VALIDATED` is
  never produced this sprint; see ISSUE-001, still open, and
  [[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]]).
  `global_cscan_ready` stays computationally ready with a CRS present —
  that readiness is never a correctness guarantee about the CRS itself.
- `GeometrySummary.footprint_area_m2` is withheld (with an explanatory
  warning) whenever the real acquisition grid's own shape — step-length
  and cross-channel spacing consistency, heading consistency — is not
  close enough to a straight, evenly-spaced line; a genuinely curving or
  unevenly-spaced real survey is never presented with a naive rectangular
  area figure.
- No project/session save, no `.ogpr` file association, no Start Menu/
  desktop shortcut, no installer, no auto-update — all deferred to a
  future packaging sprint.
- The **C-scan / Time Slice** dock (Sprint 3D-1) computes a value grid
  from one time sample or time window and renders it on the actual X/Y
  point grid or the derived s/c parameter grid — it never performs
  spatial interpolation, IDW, kriging, Delaunay gridding, or raster
  resampling of any kind, and never builds a 3D volume. No PyVista, no
  VTK, no isosurfaces, no depth conversion. See
  [[02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan]] /
  [[06_DECISIONS/ADR_017_Actual_XY_CScan_and_No_Interpolation_Policy]].
- `CScanAggregation.SINGLE_SAMPLE` is the only signed C-scan aggregation;
  `RMS`/`Mean absolute`/`Maximum absolute` are non-negative by
  construction — there is deliberately no signed *window* mean, since
  averaging a wavelet's positive/negative half-cycles over a window can
  cancel toward a falsely small value directly over a strong reflection.
- A partially out-of-range C-scan time window is silently clamped to the
  dataset's actual time range (with a warning naming the clamped range
  used); a window entirely outside the dataset's time range is rejected.
  This clamp/reject decision is independent of the Survey Geometry dock's
  own readiness gates — a C-scan on the actual X/Y point grid works even
  when `rectilinear_cscan_ready` is blocked (as it is for the bundled real
  file).
- A C-scan result computed against a since-superseded Processing preview,
  applied processing chain, or geometry override is labeled "Stale" rather
  than silently discarded or left unlabeled — recompute to clear the
  label; export is rejected while a result is data/geometry-stale. Changing
  a request-form value (center time, window width, aggregation, source)
  after a compute relabels the displayed result "Stale (parameters
  changed — recompute)" — a label only; the result shown is still the
  validly-computed one, a recompute is never auto-started, and the
  center-time spin moves the B-scan time cursor immediately as you change
  it.
- **Dock layout (post-acceptance-failure fix, see ADR-018)**: the default
  window layout is three tabified dock pairs — Dataset + Processing
  (left), Metadata + Survey Geometry (right), Plan View + C-scan / Time
  Slice (bottom, full width) — with only the B-scan/A-scan view in the
  center. Window geometry and dock layout persist across sessions in
  `%LOCALAPPDATA%\ArchaeoGPR\window_state.ini` (schema-versioned; a layout
  saved by a different schema version, a corrupt file, a saved geometry
  that no longer fits the current screen, or a saved layout from a larger
  window than the current one all fall back to the default layout instead
  of restoring). **View → Reset Window Layout** clears the saved state and
  rebuilds the default arrangement without restarting. Long panels
  (Processing, Survey Geometry, C-scan) scroll inside their docks rather
  than forcing the window larger. Docks cannot float (explicit UX
  decision — ADR-018 Decision 5); they can still be moved between areas
  and re-tabbed, and closable docks reopen via Reset Window Layout. The
  default layout is verified overlap-free at 1280×800 and 1366×768.
- **Settings isolation (ADR-018 Addendum)**: the real
  `%LOCALAPPDATA%\ArchaeoGPR\window_state.ini` above is persistent **only**
  for normal interactive use. `ArchaeoGPR.exe --smoke-test` (and
  `--open <file> --smoke-test`) never reads or writes it — it runs with an
  ephemeral, non-persisted settings backend instead, so running the smoke
  test can never overwrite a real saved layout. Every automated GUI test
  in this repository is isolated the same way (a per-test temp file, via
  `tests/conftest.py`'s autouse fixture). `scripts\build_windows.ps1`
  proves this: it records the real file's SHA-256/size (or its absence)
  before its own smoke-test run and fails the build if that is not
  byte-for-byte identical (or still absent) afterward. **Reset Window
  Layout** only ever clears the settings backend the running window
  instance actually uses — in normal interactive use that is the real
  file; it can never reach a different one.

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

**Close any running `ArchaeoGPR.exe` first.** The script refuses to
proceed (a clear error, not a wall of `Remove-Item` permission failures)
if a previous build's executable is still running — its open
`_internal\*.pyd`/`.dll` handles would otherwise block the cleanup step.
The script never force-closes a running instance for you.

## İlgili Notlar

- [[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]]
- [[02_SPRINTS/Sprint_GUI_2_Display_Controls]]
- [[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]]
- [[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]]
- [[02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector]]
- [[02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan]]
- [[06_DECISIONS/ADR_011_GUI_Technology_Decision]]
- [[06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime]]
- [[06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization]]
- [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]]
- [[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]]
- [[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]]
- [[06_DECISIONS/ADR_017_Actual_XY_CScan_and_No_Interpolation_Policy]]
- [[03_ARCHITECTURE/GUI_Architecture]]
- `packaging/archaeogpr.spec`
- `scripts/build_windows.ps1`
