---
type: adr
id: ADR-017
status: accepted
date: 2026-07-20
---

# ADR-017 — Actual X/Y C-scan and No-Interpolation Policy

## Context

Sprint 3D-0 produced a validated survey-geometry model and seven readiness
gates but deliberately built no C-scan, no time-slice, and no volume (see
[[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]]). Sprint
3D-1 implements the first real amplitude C-scan/time-slice viewer, scoped
tightly: a time-sample-or-window-derived `(trace_count, channel_count)`
value grid, rendered either on the real acquisition's actual X/Y point grid
(default, no interpolation) or on the idealized derived s/c parameter grid
(clearly labeled, never conflated with the first) — **not** a volume, not
PyVista/VTK, no spatial interpolation/gridding/resampling of any kind, no
depth conversion. See Alternatives Considered for what was deliberately
left to a future sprint.

## Decision

### 1. A new, Qt-free `archaeogpr.cscan` package — genuinely new math, not a reuse of existing functions

`src/archaeogpr/cscan/{__init__,models,compute,validation,export}.py` (new,
no PySide6/pyqtgraph import anywhere). Unlike Sprint 3D-0's
`archaeogpr.geometry` package, this one does **not** reuse an existing
processing/QC function for its core computation — no prior module in this
project selects a time sample/window and aggregates amplitudes across it.
`compute_cscan()` is new, scoped math operating purely on
`GPRDataset.amplitudes`/`time_ns` and an optional
`ProcessingResult`-shaped `valid_mask`; it imports neither
`archaeogpr.geometry` nor any GUI module, and vice versa — a C-scan *value*
grid is a function of amplitudes/time only, never of coordinates. Rendering
that grid on a coordinate grid is entirely a GUI-layer concern (see
Decision 5).

### 2. `CScanAggregation`: one signed selection, three non-negative windows — deliberately no signed window mean

`CScanAggregation` (`SINGLE_SAMPLE` / `RMS` / `MEAN_ABSOLUTE` /
`MAXIMUM_ABSOLUTE`), `aggregation_is_signed()`, `aggregation_uses_window()`.
`SINGLE_SAMPLE` reports the real signed amplitude of the nearest sample —
it is the only aggregation that can be negative. A signed *window* mean was
considered and rejected: averaging a GPR wavelet's positive and negative
half-cycles over a window can cancel toward zero directly on top of a
strong reflection, which would be scientifically misleading (a
"no-reflection" reading exactly where a reflection is strongest). `RMS`
(`sqrt(mean(x^2))`), `MEAN_ABSOLUTE` (`mean(|x|)`), and `MAXIMUM_ABSOLUTE`
(`max(|x|)`) are non-negative by construction instead, each computed only
over samples that are both `valid_mask`-true and finite
(`np.errstate(invalid="ignore", divide="ignore")` around the division, with
an explicit `usable_count > 0` check producing `NaN` rather than a spurious
`0/0`-derived value).

### 3. Half-open time window `[start, stop)`, clamp-with-warning vs reject-as-error, independent of any geometry readiness gate

`CScanRequest` (`aggregation, center_time_ns, window_width_ns, source_kind,
source_revision, geometry_revision, token`) validates in
`__post_init__` that `window_width_ns` is `None` if-and-only-if the
aggregation is `SINGLE_SAMPLE`. `compute_cscan()`:

- **`SINGLE_SAMPLE`**: nearest-sample selection via
  `np.argmin(np.abs(time_ns - center_time_ns))` — always well-defined, even
  for a center time outside the dataset's range (reported via a warning,
  never an error; the one-element window collapses to
  `(selected_index, selected_index + 1)`).
- **Window aggregations**: `[center - width/2, center + width/2)` intersected
  with `time_ns`'s actual range via direct boolean masking on the
  (possibly negative, time-zero-relative) `time_ns` array. Raises
  `CScanError` **only** if the requested window falls *entirely* outside
  the dataset's time range; a *partial* overlap is silently clamped to what
  actually exists and reported via a warning naming the exact clamped range
  used — it is never treated as an error, and never pretends the full
  requested width was honored.
- **`time_ns` monotonicity is validated independently inside
  `compute_cscan()` itself** (`_validate_time_axis`), not via
  `archaeogpr.geometry`'s readiness gates — a C-scan on the actual X/Y
  point grid must work even when `rectilinear_cscan_ready=False` (as it
  does for the bundled real file, see ADR-016 Addendum 2), so this module
  never imports or checks geometry readiness at all.

### 4. Two-layer validity: a channel-wide structural mask, plus a genuinely per-cell mask

`compute_cscan()` accepts an optional `valid_mask` (shape `(channel_count,
sample_count)`, e.g. from `DatasetSession.current_valid_mask`/
`preview_valid_mask` — the same shape `ProcessingResult.valid_mask` already
uses). `CScanResult.valid_mask`, by contrast, is `(trace_count,
channel_count)` — genuinely per-*cell*, not per-channel — because a cell
can be individually invalid (e.g. one trace's non-finite amplitude at an
otherwise-valid channel/sample) even though the structural mask itself
cannot vary per-trace. `NaN` in `values` always means `valid_mask` is
`False` at that cell and vice versa (checked by a defensive
internal-consistency assertion in `compute_cscan()` itself, not just by
tests).

### 5. Two geometry views, rendered from `SurveyGeometry`, never resampled into each other

`CScanGeometryView` (`ACTUAL_XY_POINT_MAP` / `DERIVED_PARAMETER_GRID`) is a
GUI-layer concept (`archaeogpr.gui.views.cscan_view`), not a domain one —
`archaeogpr.cscan` has no notion of it.

- **`ACTUAL_XY_POINT_MAP`** (default): the real per-(trace, channel)
  `SurveyGeometry.x_coordinates`/`y_coordinates`, rendered as one vectorized
  `pg.ScatterPlotItem` with per-point colors (never one `QWidget` per point,
  mirroring `PlanView`'s established convention for the same ~1925-point
  real file) — labeled **"Actual X/Y point map — no interpolation"**
  on-screen. A cell whose coordinate or value is non-finite is excluded from
  the colored scatter and optionally drawn as a red "x" invalid marker
  (`show_invalid_points`), never silently dropped without a visual trace.
- **`DERIVED_PARAMETER_GRID`**: a new `_derived_parameter_grid()` helper
  broadcasts `SurveyGeometry.along_track_coordinates`/
  `cross_track_offsets` (1-D) into a `(trace_count, channel_count)` grid —
  **unlike** `plan_view._acquisition_point_grid()`, this helper never
  substitutes the real `x_coordinates`/`y_coordinates` even when they
  exist, because the entire point of this second view is to stay
  structurally distinct from the first (see Decision 6). Rendered via
  `pg.ImageItem`, labeled **"Derived s/c parameter grid"**. The one
  transpose point (`values.T`) is documented directly in
  `CScanView._render_derived_grid()`'s docstring and pinned by a synthetic
  index-coded test: `result.values` is `(trace_count, channel_count)`, and
  with `pg.setConfigOptions(imageAxisOrder="row-major")` (set once in
  `app.py`, same as `BScanView`), `ImageItem` reads axis 0 as the row (Y)
  and axis 1 as the column (X) — so trace must land on X and channel on Y,
  requiring the transpose.
- **Availability falls out of what data exists, not a named gate check**:
  neither view checks `actual_xy_point_grid_ready`/`rectilinear_cscan_ready`
  directly — `_render_actual_xy()` simply requires
  `x_coordinates`/`y_coordinates` to be non-`None` on the resolved
  `SurveyGeometry`, and `_derived_parameter_grid()` requires
  `along_track_coordinates`/`cross_track_offsets`. This is simpler than
  duplicating ADR-016's readiness-gate logic in the GUI layer and cannot
  drift out of sync with it, since both ultimately come from the same
  `GeometryResolution`.

### 6. No-interpolation policy: this sprint performs no spatial interpolation/gridding/resampling of any kind

Every cell's value in both views is the same raw aggregation at its own
`(trace, channel)` — plotted at its actual position or at an idealized
position, never blended with a neighbor's value, never estimated at a
position no trace/channel actually occupies. `export_cscan_report()`
records `"no_interpolation": true` **unconditionally** (regardless of which
geometry view was active) precisely so a downstream consumer of the JSON
report never has to guess. This is the same "two representations, never
silently substituted for each other" principle ADR-016 Decision 6
established for the geometry package, now realized as actual pixels/points
on screen.

### 7. `CScanSession`: mirrors `GeometrySession`'s independence, but tracks staleness against two other sessions instead of none

`src/archaeogpr/gui/models/cscan_session.py` (new). `CScanSession` (`result,
request, state: CScanState, error`) holds no reference to `DatasetSession`
or `GeometrySession` — only a snapshot of the revisions a past compute used
(`CScanRequest.source_revision`/`geometry_revision`), compared against the
*live* revisions by `MainWindow._cscan_source_revision_for()`/
`is_stale()`, exactly the pattern `ProcessingWorker`'s `base_revision` vs
`DatasetSession.current_revision` already established.

**Design choice on failure/cancel, consistent with the project's established
"make the user aware, don't hide" philosophy** (e.g. unverified-CRS labels
in ADR-016): `fail()`/`cancel()` only update `state`/`error` — `result`/
`request` are written **only** by `complete()`/`clear()`. A failed,
cancelled, or now-stale compute keeps the last valid result on screen,
relabeled "Stale"/"Cancelled"/"Failed" by `_cscan_status_text()`, rather
than blanking the view. `clear()` (full reset) is called in exactly one
place: a new successful file load always discards the old C-scan result,
regardless of what source it was computed from (Sprint 3D-1 spec section
21).

**A genuine staleness-detection gap found and fixed while implementing
this**: source-revision tracking for `CScanSourceKind.PREVIEW` initially
used `DatasetSession.preview_base_revision`, which fails to detect
re-previewing with *different parameters* at the *same* base revision — a
genuinely different `preview_dataset` array object that
`preview_base_revision` alone cannot distinguish. Fixed by using
`id(session.preview_dataset)` instead: a plain Python `int`, so it fits
`CScanRequest.source_revision`'s existing type with zero schema change, and
it changes exactly when `DatasetSession.set_preview()`/`discard_preview()`
replace the object — precisely the staleness this needs to catch.
`CScanSourceKind.RAW` always reports revision `0`, since `raw_dataset`
never mutates within one file's lifetime and a new file load
unconditionally clears `cscan_session` outright, so no finer-grained check
is needed for that source.

### 8. `CScanWorker`: exact structural mirror of `FileLoadWorker`/`ProcessingWorker`

`src/archaeogpr/gui/workers/cscan_worker.py` (new). `QObject` +
`moveToThread` (never a `QThread` subclass), signals `progress(int, str)`,
`result_ready(int, object)`, `failed(int, str, str)`, `cancelled(int)`,
`finished(int)`. Token-based stale-result rejection (the outcome handler
compares the signal's token against `MainWindow._current_cscan_token`, not
`sender()` — documented-unreliable across a queued connection, see
ADR-014). Cooperative `threading.Event` cancellation. Cleanup happens
**only** in `_on_cscan_thread_finished` (connected to `thread.finished`),
never in an outcome handler — the same lifecycle discipline ADR-014/
ADR-015 established, reused without modification to either of those
workers.

### 9. `ActiveTaskKind`: a new convenience enum, not a replacement for the existing gates

A third background task (C-scan compute) joins file loading and processing
preview. Rather than rewriting the established
`is_loading`/`is_processing` properties (each independently keyed on its
own thread-object-is-not-None check, per ADR-014/ADR-015) into a shared
state machine, `ActiveTaskKind` (`NONE` / `FILE_LOAD` / `PROCESSING` /
`CSCAN` / `SHUTDOWN_PENDING`) is a **purely derived** property
(`MainWindow.active_task_kind`) layered on top of the three independent,
still-authoritative booleans (`is_loading`, `is_processing`, and the new
`is_computing_cscan`). Every busy-state guard in this sprint (file load,
processing start, geometry apply, C-scan compute, close/shutdown) checks
the same explicit `self._close_pending or self.is_loading or
self.is_processing or self.is_computing_cscan`-style condition already
established by ADR-014/ADR-015, extended with the one new term — never a
switch on `active_task_kind` itself, which exists only for call sites that
want one value to describe/log/display "what's busy" (e.g. a unified
status message), not for gating logic.

**3-way mutual exclusion**: file load, processing preview, and C-scan
compute cannot run concurrently; dataset/geometry-mutating controls (Apply
Preview, Discard Preview, Reset-to-Raw, Apply Geometry, Discard Overrides,
Reset Geometry) are also disabled while a C-scan compute is running. The
read-only C-scan view itself (like the Survey Geometry info tree and Plan
View before it) stays visible and its trace/channel selection sync keeps
working during a processing preview — only the request form/Compute/
Export are gated.

**A real production gap found and fixed via a failing test**: `open_path()`
uses a sequence of separate `if` blocks (one per guard), not one combined
`if A or B or C:` line — the new C-scan guard was initially added to every
*other* call site via a blanket edit but skipped this one, since it didn't
match the same textual pattern. `test_file_load_rejected_during_cscan_compute`
caught the omission; fixed by adding the missing `if self.is_computing_cscan:
... return` block directly.

### 10. Export: PNG + JSON sidecar, atomic, mirrors `archaeogpr.geometry.export`'s pattern rather than the older `gui/export.py` one

`src/archaeogpr/cscan/export.py` (new): `CSCAN_REPORT_SCHEMA_VERSION = 1`,
`build_cscan_report()`/`export_cscan_report()`. Follows
`archaeogpr.geometry.export`'s schema-versioned, `source_sha256`-recording,
atomic-write (`tempfile.mkstemp` + `os.replace`) convention, not
`gui/export.py`'s older, non-atomic `.display.json` sidecar pattern — a
C-scan export is explicitly required to never leave a half-written file
behind. `export_cscan_png()` (added to the existing `gui/export.py`,
alongside `export_bscan_png`) renders from data (never a live screen grab)
on the same matplotlib `Agg` backend, also atomically, for the same reason.

**A real bug found and fixed while writing the GUI test suite**:
`export_cscan_png()`'s atomic temp file is created via
`tempfile.mkstemp(..., suffix=".tmp")`, and the first implementation
called `fig.savefig(tmp_name, dpi=150)` without an explicit format — since
matplotlib's `savefig` infers the output format from the filename
extension by default, and `.tmp` is not a recognized image format, every
export raised `ValueError: Format 'tmp' is not supported` the moment it
tried to write the temp file (caught by
`test_export_produces_png_and_json`/
`test_real_ogpr_hash_and_mtime_unchanged_by_cscan_operations`, both of
which assert the PNG actually exists on disk afterward). `export_bscan_png`
never hit this, because it writes directly to the final `.png`-suffixed
path with no atomic temp-file step. Fixed by passing `format="png"`
explicitly to `fig.savefig()`, independent of whatever suffix the temp file
happens to have.

## Alternatives Considered

- **A signed window-mean aggregation**: rejected — positive/negative
  half-cycle cancellation would produce a falsely-small value directly over
  a strong reflection (see Decision 2).
- **Blending or interpolating between the actual X/Y point map and the
  derived parameter grid** (e.g. to show one continuous surface): rejected
  outright by this sprint's own scope — no spatial interpolation/gridding/
  resampling of any kind was implemented (see Decision 6); a future
  gridding sprint may add this, but must never make it the default or
  silently substitute for either existing view.
- **Gating `CScanGeometryView` availability on `archaeogpr.geometry`'s named
  readiness gates directly** (`actual_xy_point_grid_ready`/
  `rectilinear_cscan_ready`): considered, rejected in favor of checking for
  the presence of the underlying coordinate arrays themselves (see Decision
  5) — simpler, and structurally cannot drift out of sync with the gates
  since both derive from the same `GeometryResolution`.
- **A single shared `BusyState` enum across file load/processing/C-scan**:
  rejected — mirrors ADR-014/ADR-015's established precedent of one
  parallel state enum per subsystem (`FileLoadState`/`ProcessingState`/now
  `CScanState`), each independently owned by its own worker/session pair.
  `ActiveTaskKind` (Decision 9) provides the convenience a shared enum would
  have, without disturbing either existing gate.
- **Using `DatasetSession.preview_base_revision` for `PREVIEW`-source
  staleness tracking**: superseded during implementation by an
  `id(preview_dataset)`-based check (see Decision 7) — the revision-int
  alone cannot distinguish two different previews computed at the same base
  revision.
- **Blanking the C-scan view on any failure/cancel/staleness**: rejected —
  consistent with this project's established preference (unverified-CRS
  labels, geometry-preservation-on-failed-load) for keeping the last valid
  result visible with an honest label over hiding it (see Decision 7).
- **Reusing `CScanDisplaySettings` = `DisplaySettings`**: rejected — a
  C-scan has no A-scan mode or visible-region autoscale, and needs two
  fields (`point_size`, `geometry_view`) `DisplaySettings` has no use for;
  kept as a separate, smaller type mirroring the same manual/symmetric/
  asymmetric percentile resolution order instead.

## Consequences

- `src/archaeogpr/cscan/{__init__,models,compute,validation,export}.py`
  (new) is Qt-free and the one place C-scan value-grid computation,
  request/result validation, and JSON export logic lives.
- `src/archaeogpr/gui/models/{cscan_session,cscan_display_settings}.py`,
  `src/archaeogpr/gui/workers/cscan_worker.py`,
  `src/archaeogpr/gui/views/cscan_view.py` (all new).
- `main_window.py` gained `ActiveTaskKind`, a C-scan/Time Slice dock
  (Request form, Compute/Cancel, Display settings, Export button, rendered
  `CScanView`), trace/channel/time selection sync across B-scan/A-scan/Plan
  View/C-scan, and a File-menu-adjacent Export C-scan PNG + JSON action.
  Every prior sprint's feature (display controls, file loading, processing
  preview/apply, survey geometry inspection, deferred close) is unchanged.
- `bscan_view.py` gained a draggable `pg.InfiniteLine` time cursor
  (`timeCursorDragged` signal, `set_time_cursor()` for non-emitting
  programmatic placement) so a successful C-scan compute can visually mark
  its center time on the B-scan.
- No spatial interpolation, IDW, kriging, Delaunay gridding, or raster
  resampling; no PyVista/VTK/volume rendering/isosurfaces; no depth
  conversion/velocity workflow/migration; no gain; no undo/redo; no recipe
  system; no processed-dataset saving — all remain exactly as scoped out in
  this sprint's own brief, same as ADR-016's Consequences for Sprint 3D-0.
- Version `0.4.0` -> `0.5.0` (minor — new user-visible C-scan/time-slice
  capability).

## Validation

- `tests/test_cscan.py` (new, 26 tests, Qt-free): aggregation math (RMS/
  mean-absolute/maximum-absolute against hand-computed values, SINGLE_SAMPLE
  sign preservation), half-open window selection (in-range, partially
  clamped with warning, entirely-out-of-range rejection, a negative
  time-zero-relative axis), independent time-axis monotonicity rejection,
  mask/NaN/overflow safety under `-W error`, request validation
  (`window_width_ns` None-iff-SINGLE_SAMPLE), result immutability, and JSON
  export (schema version, `no_interpolation: true`, source hash, NaN-safe
  serialization).
- `tests/test_gui_cscan.py` (new, 39 tests, `@pytest.mark.gui`): dock
  construction and default state, both geometry views' labels/rendering
  (including the real file's rectilinear/CRS-unverified warnings), compute
  on/off the GUI thread, 3-way mutual exclusion in every direction, cancel/
  stale/failed-result preservation, trace/channel/time-cursor selection sync
  in both directions, display settings (symmetric-disabled-for-non-negative
  aggregations), Raw/Current/Preview source behavior, PNG+JSON export
  (success, stale-rejected, shutdown-pending-rejected), deferred close, and
  raw-file hash/mtime invariance through a full compute/export cycle.
- Two genuine test-authoring bugs found and fixed while writing the GUI
  suite (neither a production-code bug): an off-by-one trace index
  (`_select_trace(3)` against a 3-trace synthetic fixture, where valid
  indices are only 0-2 — the sibling test right below it already used the
  correct index 2 for the same fixture) and two tests missing the
  established `no_blocking_dialogs` fixture, which caused an unpatched,
  real `QMessageBox.critical`/`.warning` call to block the Qt event loop
  forever with no user present to dismiss it in an offscreen run — the
  same, already-documented pitfall from ADR-015/ADR-016.
- One real production bug found this way (Decision 10): `export_cscan_png`'s
  atomic temp file's `.tmp` suffix defeated matplotlib's format inference;
  fixed by passing `format="png"` explicitly.
- One real production bug found via a failing test (Decision 9):
  `open_path()` was missing the `is_computing_cscan` busy-state guard.

## Addendum: Dock-Layout Regression and Section-11 Hardening (2026-07-20, same day)

Manual acceptance of this sprint **failed** on a dock-layout regression
(overlapping/spilled docks with the new C-scan dock present). The layout
fix itself is a separate architectural decision — see
[[ADR_018_Versioned_Dock_Layout_and_Reset_Policy]]. The same turn also
hardened several of this ADR's own decisions (none of the C-scan
scientific/aggregation math changed):

1. **Decision 7 superseded in one detail — `id(preview_dataset)` replaced
   by a monotonic `DatasetSession.preview_generation` counter.** CPython
   legally reuses `id()` values after garbage collection, so two different
   previews could in principle have compared equal. The new counter is
   bumped by every transition that sets, replaces, or clears the preview
   (`set_preview`/`discard_preview`/`apply_preview`/`reset_to_raw`/
   `commit_dataset`) and cannot collide. Same `int` type, same
   `CScanRequest.source_revision` slot, same staleness semantics.
2. **Decision 5 extended — the two geometry-view combo items are now also
   gated on their *named* ADR-016 readiness gates** (`actual_xy_point_grid_
   ready` for the point map, `local_parameter_grid_ready` for the derived
   grid), item-level with blocking-issue tooltips — in addition to (not
   instead of) the view widgets' own degrade-safely-on-missing-arrays
   behavior. The current selection is never force-switched.
3. **Immediate cursor sync**: changing the C-scan center-time spin now moves
   the B-scan time cursor at once (via the non-emitting
   `set_time_cursor()`), not only after a successful compute.
4. **Parameter-staleness labeling**: changing any request-form value
   (center time, window width, aggregation, source) after a compute
   relabels the displayed result "Stale (parameters changed — recompute)";
   a recompute is never auto-started. Data/geometry-revision staleness
   (Decision 7) is unchanged and still blocks export; parameter staleness
   is label-only, since the displayed result is still internally valid and
   its JSON records the request actually used.
5. **Decision 9 extended — `can_start_background_task`**: the three
   background-task start sites (`open_path`, Preview, C-scan Compute) now
   share one centralized start-permission property
   (`active_task_kind is NONE`) instead of each re-spelling the four-term
   guard. The per-subsystem `is_loading`/`is_processing`/
   `is_computing_cscan` properties remain authoritative and untouched.
6. **Decision 10 extended — export partial-failure semantics**: the PNG and
   its JSON sidecar are one deliverable. If the sidecar write fails after
   the PNG was already written, the PNG is removed (rolled back) and the
   error dialog says exactly that — a provenance-less image never remains
   on disk.
7. **Degenerate shapes pinned by tests**: 1×N, N×1, and 1×1
   trace/channel grids are now explicitly covered by domain tests (they
   already worked; the tests make it a contract).
8. **Package metadata**: the editable install's stale dist-info (reporting
   0.2.1 to `pip show`) was refreshed to 0.5.0 (`pip install -e . --no-deps`)
   — an environment fix; `archaeogpr.__version__` was always correct.

New tests: 3 domain (degenerate shapes) + 5 GUI (preview-generation
monotonicity, immediate cursor sync, parameter-staleness-without-
auto-compute, JSON-failure PNG rollback, named-gate combo gating) + the 27
dock-layout tests documented in ADR-018.

## Related Files

- `src/archaeogpr/cscan/models.py`
- `src/archaeogpr/cscan/compute.py`
- `src/archaeogpr/cscan/validation.py`
- `src/archaeogpr/cscan/export.py`
- `src/archaeogpr/gui/models/cscan_session.py`
- `src/archaeogpr/gui/models/cscan_display_settings.py`
- `src/archaeogpr/gui/workers/cscan_worker.py`
- `src/archaeogpr/gui/views/cscan_view.py`
- `src/archaeogpr/gui/views/bscan_view.py` (time cursor addition)
- `src/archaeogpr/gui/export.py` (`export_cscan_png` addition)
- `src/archaeogpr/gui/main_window.py`
- `src/archaeogpr/gui/window_state.py` (ADR-018)
- [[06_DECISIONS/ADR_018_Versioned_Dock_Layout_and_Reset_Policy]]
- [[02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan]]
- [[02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector]] (the geometry/readiness foundation this sprint consumes, never recomputes)
- [[06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates]]
- [[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]] (the busy-state and worker pattern this sprint reuses)
- [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]]
- [[03_ARCHITECTURE/3D_Volume_Data_Model]] (the future gridding/volume sprint this one prepares for, without implementing it)
- [[03_ARCHITECTURE/GUI_Architecture]]
- [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]
