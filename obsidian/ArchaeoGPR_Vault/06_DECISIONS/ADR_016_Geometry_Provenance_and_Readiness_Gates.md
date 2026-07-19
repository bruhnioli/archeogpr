---
type: adr
id: ADR-016
status: accepted
date: 2026-07-19
---

# ADR-016 — Geometry Provenance and Readiness Gates

## Context

Sprint GUI-1/GUI-2/GUI-1B/GUI-3A built a view-only + non-destructive-processing
native viewer with no concept of survey geometry beyond what
`MetadataPanel`'s "Geolocation" group already showed (a flat "present/not
present" flag and the raw, unvalidated `spatial_reference` passthrough --
see `src/archaeogpr/gui/views/metadata_panel.py`). Nothing in the GUI let a
user inspect *how confident* a spacing/origin/CRS value actually is, and
nothing prepared a coordinate grid a future C-scan/3D sprint could reuse
without re-deriving it.

Sprint 3D-0 implements exactly the scope its own brief set: audit-first
survey-geometry inspection, explicit per-field provenance, a 2D acquisition
plan view, and five readiness gates -- **not** a C-scan, not a volume, not
gain/migration/depth-conversion. See Alternatives Considered for what was
deliberately left to a future sprint.

## Decision

### 1. A new, Qt-free `archaeogpr.geometry` package -- never duplicates existing processing/QC math

`src/archaeogpr/geometry/{__init__,models,resolve,validation,export,
summary}.py` (new, no PySide6/pyqtgraph import anywhere -- verified by the
core suite deselecting the GUI-marked tests without any import error,
matching ADR-012's isolation rule). It reuses, rather than reimplements:

- `archaeogpr.processing.background.compute_trace_spacing()` for trace
  spacing (geolocation-derived, falling back to the file's own
  `sampling.sampling_step_m`, exactly the same priority order the
  processing module itself already documents).
- `archaeogpr.qc.metadata.compute_cross_channel_spacing_m()` for channel
  spacing.

Neither of those two functions, nor `qc/geometry.py`'s
`CRS_WARNING_TEXT`/"as stored, not validated" convention, were touched or
copied -- the geometry resolver calls them directly.

### 2. `SurveyGeometry`: one immutable value object, with a provenance tag on every field

`GeometryProvenance` (`FILE_METADATA` / `DERIVED` / `USER_SUPPLIED` /
`INDEX_SPACE` / `MISSING`) is recorded per-field in
`SurveyGeometry.provenance`, not just inferred from `coordinate_mode`. This
is the audit's central finding made explicit: the real
`Swath003_Array02.ogpr` file has genuine per-(trace, channel) `x`/`y`
coordinates (`FILE_METADATA`) and a `spatial_reference` passthrough
(`FILE_METADATA`, but explicitly never validated -- ISSUE-001, see
`OpenGPR_File_Structure.md`), yet has **no** azimuth/heading, no
antenna/channel-offset, and no channel-identifier field anywhere in the
format (confirmed by an exhaustive keyword audit before any code was
written) -- so those three are only ever `DERIVED` (from real coordinates,
when available) or `MISSING`/`USER_SUPPLIED` (when not), **never**
silently assumed (e.g. azimuth is never defaulted to 0°; channel-zero
offset defaulting to `0.0` is the one exception, and is tagged
`INDEX_SPACE`, not `FILE_METADATA` or `DERIVED` -- see Decision 3, it is a
coordinate-origin *convention*, not a physical claim).

`along_track_coordinates`/`cross_track_offsets` are kept as separate 1-D
arrays (shape `(trace_count,)`/`(channel_count,)`), not one joint 2-D
grid -- nothing in this project supplies a per-channel along-track offset
or a per-trace cross-track offset, so a joint grid would only ever be
their outer sum. `x_coordinates`/`y_coordinates` (shape `(trace_count,
channel_count)`) are the one genuinely per-point 2-D field, because real
per-(trace, channel) coordinates *are* available in this project's data.
All arrays are frozen (read-only) on construction, exactly like
`GPRDataset` (ADR-001).

### 3. Priority order, identical for every field: user override > file metadata > derived > index fallback > missing

`resolve_survey_geometry(dataset, overrides=None)` never guesses. Channel
zero offset defaulting to `0.0` when not overridden is the sole,
deliberate exception to "never assume a value" -- explained in Decision 2:
choosing a coordinate system's own local origin is always an arbitrary,
legitimate choice, unlike inventing a physical measurement (azimuth,
spacing, a surveyed position) would be.

### 4. Two independent paths to `GLOBAL_PROJECTED`, not one

The audit surfaced a real design question: this project's actual file
already has genuine per-trace global coordinates, but the sprint's own
spec also describes an azimuth+origin+cross-track-direction reconstruction
formula (for a hypothetical dataset with *no* real coordinates, only local
spacing and a known start point/heading). Both are implemented, with an
explicit priority:

1. **`dataset.has_geolocation` is `True`** (real per-(trace, channel) `x`/
   `y` exist): those are used directly as `x_coordinates`/`y_coordinates`
   (`FILE_METADATA`) -- no azimuth/origin/cross-track-direction is needed
   or consulted to build the grid itself. `origin_x`/`origin_y` (mean
   first-trace position, matching `qc/geometry.py::plot_survey_geometry`'s
   own start-point convention), `azimuth_deg` (net first-to-last-trace
   direction), and `cross_track_direction` (sign of the cross-track vector
   projected onto the along-track-perpendicular "right" unit vector) are
   *additionally* derived from those same real coordinates, purely for
   display/plan-view-arrow purposes (`DERIVED`) -- overridable by the user
   like any other field.
2. **No real geolocation, but the user supplies `origin_x`, `origin_y`,
   `azimuth_deg`, a *known* `cross_track_direction` (not `UNKNOWN`), and a
   CRS identifier, and local-metric spacing is resolvable**: the
   azimuth-rotation formula projects local `(s, c)` to global `(E, N)`
   (`USER_SUPPLIED`). `CrossTrackDirection.UNKNOWN` always blocks this
   path -- there is no fallback guess for which physical side channels
   ascend on.

Azimuth convention: **degrees clockwise from grid north**. For
`CHANNEL_ASCENDING_RIGHT`: `E = E0 + s*sin(theta) + c*cos(theta)`,
`N = N0 + s*cos(theta) - c*sin(theta)`; for `CHANNEL_ASCENDING_LEFT` the
cross-track term's sign is flipped. Verified against the real file: the
derived azimuth (~131.3 deg) and derived direction
(`CHANNEL_ASCENDING_RIGHT`) are both self-consistent with the file's own
raw `x`/`y` arrays (cross-checked directly, not merely computed and
trusted).

### 5. Five readiness gates, each `(ready, blocking_issues, warnings)` -- not a single boolean

`index_view_ready` (valid shape only), `local_cscan_ready` (finite along/
cross-track coordinates, real spacing known -- monotonicity violations are
a *warning*, not a blocker), `global_cscan_ready` (`local_cscan_ready` +
finite global X/Y + a known CRS identifier), `time_volume_ready`
(`local_cscan_ready` + a finite, strictly-increasing `time_ns`),
`depth_volume_ready` (**always `False` this sprint** -- no propagation
velocity confirmation flow exists yet; see `3D_Volume_Data_Model.md`'s own
"depth requires an explicit user-confirmed velocity" rule, CLAUDE.md).

### 6. `GeometrySession`: a session object independent of `DatasetSession`, not a new field on it

`src/archaeogpr/gui/models/geometry_session.py` (new). Geometry is resolved
exactly once per successful file load
(`GeometrySession.resolve_for_new_dataset`, called from
`MainWindow._refresh_for_new_dataset`) and is **never** re-resolved on a
processing preview/apply/discard/reset-to-raw transition, because none of
the five registered processing operations change the trace or channel
count -- geometry is about the survey, not the amplitudes. A failed or
cancelled file load never calls `_refresh_for_new_dataset` at all, so the
previous file's geometry is left completely untouched "for free", with no
extra code needed. `geometry_revision` is bumped only by
`apply_overrides()`/`reset_to_file_metadata()` -- never by a processing
transition, and `DatasetSession.current_revision` and
`GeometrySession.geometry_revision` are two independent counters that
never read or write each other.

### 7. Override ambiguity: some fields' "unset" state is only reachable via Discard/Reset, not by re-typing zero

`trace_spacing_m`/`channel_spacing_m` use `QDoubleSpinBox.
setSpecialValueText("(not set)")` at the widget's minimum (`0.0`, which is
never a legal *positive* spacing) to unambiguously represent "no override"
-- typed `0.0` and "unset" are the same, correctly-invalid state for these
two fields. `channel_zero_offset_m`/`origin_x`/`origin_y`/`azimuth_deg` are
signed floats where `0.0` is a perfectly legitimate real value, so no such
sentinel is possible: once the user touches one of those spinboxes, it
becomes a real `USER_SUPPLIED` override (including an explicit `0.0`)
until `Discard Overrides`/`Reset Geometry to File Metadata` is clicked.
This is a known, accepted UX simplification, not an oversight -- a
per-field "clear to unset" affordance was considered and rejected as
unnecessary complexity for this sprint (the two session-level buttons
already cover every "go back to file-derived" need).

### 8. Plan View: one vectorized scatter item, never one widget per point

`src/archaeogpr/gui/views/plan_view.py` mirrors
`BScanView`'s conventions (`pg.PlotWidget`, `sigMouseClicked`/
`sigMouseMoved`, a `fit_to_data`/`reset_view`-equivalent). All ~1925 of the
real file's acquisition points (and any future, larger multi-swath survey)
render through one `pg.ScatterPlotItem`, never per-point `QWidget`s. Along-
track direction is shown as a start(green)/end(red) marker pair + line
(mirroring `qc/geometry.py::plot_survey_geometry`'s own convention);
channel-ascending direction is shown separately as a first-trace,
channel-0-to-last-channel line, since the two are physically independent
axes and conflating them into one arrow would hide whichever one a given
survey's geometry happens to make visually small.

### 9. Geometry Inspector: a read-only `QTreeWidget`, mirroring `MetadataPanel` exactly

`src/archaeogpr/gui/views/geometry_panel.py` reuses `MetadataPanel`'s
grouped (field, value) tree + copy-to-clipboard context menu convention
verbatim, rather than inventing a new display widget class. Six groups (A.
Status, B. Dataset axes, C. Spacing/orientation, D. Georeferencing, E.
Provenance, F. Validation) match the sprint's own spec section numbering
exactly.

### 10. Busy-state: functional guards, not a third deferred-close state machine

`resolve_survey_geometry()` is a fast, synchronous, pure-Python computation
on already-in-memory arrays -- unlike file loading/processing, it never
needs its own `QThread`/cancel-token/deferred-close plumbing. Every
geometry-mutating handler (`_on_apply_geometry_clicked`,
`_on_reset_geometry_clicked`, `_on_export_geometry_report_triggered`)
checks `self._close_pending or self.is_loading or self.is_processing`
before doing anything, exactly like `_on_reset_to_raw_clicked` already
does -- this project's established pattern (confirmed by re-reading
`test_file_load_rejected_during_processing`/
`test_processing_rejected_during_file_load`) is that the *functional*
guard in the handler is authoritative; a widget's visual `.isEnabled()`
state is refreshed at that subsystem's own transition points (new file
load, Apply/Discard/Reset), not reactively on every other subsystem's
state change. The read-only info tree and the Plan View (including its
trace/channel selection sync) stay fully usable while a processing preview
is running -- only the override form/Apply/Discard/Reset/Export are
gated.

## Alternatives Considered

- **Deriving `cross_track_direction`/`azimuth_deg` only via the
  reconstruction formula, never from real coordinates**: rejected --
  the real file already has genuine coordinates, and it would be
  scientifically dishonest to require a user to re-enter values the data
  already answers. Both derivations are cross-checked against the raw
  `x`/`y` arrays before being trusted (see Decision 4).
- **A per-channel along-track offset / per-trace cross-track offset
  field**: rejected -- no source (file, derived, or user-realistic) exists
  for either in this project; adding the field would only ever hold a
  degenerate broadcast of the two 1-D arrays this sprint already has.
- **Reprojecting/validating the header's CRS (EPSG:32632)**: explicitly
  out of scope (ISSUE-001 remains open) -- `crs_identifier` is carried "as
  stored", exactly like `qc/geometry.py`'s existing policy.
- **A `GLOBAL_GEOGRAPHIC` (lat/lon) resolver path**: not implemented this
  sprint (no reprojection dependency was added) -- the enum value exists
  for forward-compatibility, but `resolve_survey_geometry` never produces
  it.
- **A per-field "clear to unset" control** for signed-float overrides:
  considered, rejected as unnecessary UI complexity given the existing
  Discard/Reset buttons already cover it (see Decision 7).
- **Reusing/extending `DatasetSession` directly** instead of a new
  `GeometrySession`: rejected -- geometry state is orthogonal to
  raw/current/preview processing state; a separate session object means
  zero changes to `DatasetSession`'s already-tested behavior.
- **A `GeometryDiagnostics`/gridding class** (the design doc's own planned
  next stage): explicitly deferred to a future 3D/C-scan sprint -- this
  sprint's `SurveyGeometry`/readiness gates are the foundation that stage
  will consume, not duplicate (see `3D_Volume_Data_Model.md`).

## Consequences

- `src/archaeogpr/geometry/{__init__,models,resolve,validation,export,
  summary}.py` (new) is Qt-free and the one place geometry resolution,
  readiness, validation, and JSON export logic lives.
- `src/archaeogpr/gui/models/geometry_session.py` (new) is the one place
  `GeometrySession` lives -- independent of `DatasetSession`.
- `src/archaeogpr/gui/views/{geometry_panel,plan_view}.py` (new) are the
  read-only info tree and the 2D acquisition plan view.
- `main_window.py` gained a Survey Geometry dock (info tree + override
  form + Apply/Discard/Reset), a Plan View dock, trace/channel selection
  sync in both directions, and a File > Export Geometry Report... action.
  Every GUI-1/GUI-2/GUI-1B/GUI-3A feature (display controls, file loading,
  processing preview/apply, deferred close) is unchanged by this sprint.
- No amplitude C-scan, no time-slice aggregation, no gridding/resampling,
  no PyVista/VTK, no volume rendering, no depth conversion, no velocity
  input, no gain, no undo/redo, no recipe system, no processed-dataset
  save, no installer -- all remain exactly as scoped out in this sprint's
  own brief.
- Version `0.3.0` -> `0.4.0` (minor -- new user-visible Geometry Inspector
  capability).

## Validation

- `tests/test_geometry.py` (new, 25 tests, Qt-free): index/local/global
  coordinate construction, spacing rejection (negative/zero/non-finite),
  provenance recording, override-over-file-metadata priority, missing-
  metadata index fallback, raw-dataset/input-array immutability,
  read-only output arrays, the azimuth-0/azimuth-90/right/left transform
  conventions, unknown-cross-track-direction rejection, missing-CRS
  blocking global readiness, local/time-volume/depth-volume readiness,
  duplicate/non-finite coordinate detection, finite-and-serializable JSON
  export, and raw-file hash/mtime invariance through export.
- `tests/test_gui_geometry.py` (new, 30 tests, `@pytest.mark.gui`): dock
  construction, summary population on load, disabled-with-no-dataset,
  index/local/global-mode axis labels and CRS display, provenance/
  readiness/validation display correctness, Apply/Discard/Reset override
  behavior (including invalid-override rejection), busy-state rejection
  during processing and file loading, geometry preservation across a
  failed/cancelled load and across every processing transition (including
  time-zero, which changes `time_ns` but never `x`/`y`), bidirectional
  plan-point/trace-channel selection sync, equal-aspect plan view,
  fit-to-data, a non-finite-coordinate geometry rendering without
  crashing, hover readout correctness, geometry report export (success,
  user-cancelled, shutdown-pending-rejected), and raw-file invariance
  through a full override/apply/export cycle.
- All of Sprint GUI-1/GUI-2/GUI-1B/GUI-3A's existing 152 GUI tests pass
  unchanged. Combined GUI suite: 152 passed, 369 deselected.
- Core suite (`pytest -m "not gui"`, no Qt installed): 343 passed, 26
  skipped, 152 deselected -- confirms `gui/geometry/*` and
  `gui/models/geometry_session.py`/`gui/views/{geometry_panel,plan_view}.py`
  never import Qt at module scope where it isn't supposed to (the
  `archaeogpr.geometry` package proper has zero Qt import anywhere) and
  never break headless collection.
- Two genuine test-authoring bugs found and fixed while writing the GUI
  suite (neither a production-code bug): (1) an early draft asserted
  `geometry_apply_button.isEnabled()` was `False` immediately after
  `MainWindow()` construction, which failed -- `__init__` was missing the
  equivalent of `_set_processing_state(ProcessingState.IDLE)`'s implicit
  panel refresh for the new Survey Geometry dock; fixed by adding an
  explicit `self._refresh_geometry_panel()` call at the end of `__init__`
  (a genuine, small production-code gap this test caught, not a test bug).
  (2) the geometry-report export test used a placeholder
  `Path("x.ogpr")` that did not exist on disk; `export_geometry_report`
  correctly needs to hash the real source file and raised
  `FileNotFoundError`, which `main_window.py` correctly surfaced via
  `QMessageBox.critical` -- which then hung offscreen because that
  specific test lacked the `no_blocking_dialogs` fixture (the same,
  already-documented pitfall from ADR-015). Fixed by writing real bytes to
  an actual on-disk path before exercising the export handler. (3) a
  third, pure test-setup mistake: the time-zero preview test's synthetic
  dataset was too small (4 samples * 0.5 ns) for `correct_time_zero`'s
  default `[5, 15)` ns search window, which correctly raised
  `ProcessingError` -- fixed by using a larger sample count/sampling
  interval, matching the dimensions already used elsewhere in this test
  suite for the same operation.

## Addendum: Pre-Commit Audit Fixes (2026-07-19)

Before the first commit, the user requested a commit-pre-audit rather than a
rewrite. Four findings, all fixed without touching the architecture above:

1. **File-scope accounting was wrong in the first two draft reports.**
   `git status --short` shows 11 modified + 8 untracked *lines*, but one of
   those untracked lines (`?? src/archaeogpr/geometry/`) is a directory
   collapsing 6 real files -- so the real count is 11 modified + 13 added =
   24 files, not "10 modified + 8 untracked = 18" as first reported. No
   unexpected file was present; this was purely a reporting error, corrected
   before staging anything.
2. **A real `RuntimeWarning` in `PlanView.set_geometry()`**: when an entire
   trace's `along_track_coordinates` value is non-finite, it broadcasts to
   an all-NaN X value across every channel in that row; feeding that
   straight into `invalid_scatter.setData()` made pyqtgraph's own internal
   `np.nanmin`/`np.nanmax` bounds computation warn "All-NaN slice
   encountered" (harmless -- no crash -- but noisy). Fixed by checking, per
   axis, whether the invalid subset has *any* finite value before passing it
   to pyqtgraph; if not, render nothing for that update instead (there is no
   sensible 2D location for a point missing a coordinate anyway). 4 new
   tests (3 domain, 1 strengthened GUI test using `warnings.catch_warnings`
   + a direct, deterministic `dataBounds()` call rather than relying on
   `-W error`/timing).
3. **`CrsValidationStatus`** (`MISSING`/`DECLARED_UNVERIFIED`/
   `USER_SUPPLIED_UNVERIFIED`/`VALIDATED`) added as a `SurveyGeometry`
   *computed property* (derived from `crs_identifier` + its provenance,
   never a separately-stored field, so the two can never disagree) --
   `VALIDATED` is never produced this sprint (no authority/network check
   exists). The GUI's "Coordinate mode" row no longer shows a bare "Global
   projected"; it reads e.g. "Global projected — declared CRS, unverified".
   A new "CRS validation status" row was added to section D; `global_
   cscan_ready.warnings` now always carries an unverified-CRS note when a
   CRS is present (readiness itself is unaffected -- it was always about
   computational readiness, never a correctness guarantee). **ISSUE-001
   remains open** -- this makes the existing ambiguity visible, it does not
   resolve it.
4. **Real vs. idealized grid, and footprint-area gating**
   (`src/archaeogpr/geometry/regularity.py`, new): `along_track_coordinates`/
   `cross_track_offsets` are *always* a perfectly rectilinear idealization
   built from one spacing statistic -- independent of whether the real
   per-(trace, channel) acquisition actually followed a straight line at
   constant spacing. `assess_grid_regularity()` compares the real
   (`x_coordinates`/`y_coordinates`) grid against that idealization via
   three *shape* statistics -- along-track step-length CV, cross-channel
   spacing CV (both warn above 15%), and circular standard deviation of
   trace-to-trace heading (warns above 10 deg) -- and gates
   `GeometrySummary.footprint_area_m2` on all three being within tolerance
   for `GLOBAL_PROJECTED` geometries (`LOCAL_METRIC` is exact by
   construction, so it is never gated). **Important finding, discovered
   empirically against the real file, not assumed**: a fourth candidate
   metric -- point-by-point residual between the real grid and the
   idealized reconstruction -- was tried first and rejected as a gating
   criterion. On `Swath003_Array02.ogpr`, that residual reaches 38 cm (a
   10% per-step tolerance would be ~0.4 cm) *despite* the shape statistics
   being excellent (2.3% step-length CV, 1.7 deg direction std) -- because
   real GPS-triggered trace positions naturally drift from a two-point
   (first/last-trace) straight-line reconstruction by an amount that grows
   with profile length, even along a genuinely straight, evenly-paced line.
   Gating on it would have rejected essentially all real survey data, not
   just genuinely curved/irregular ones. It is still computed and reported
   (informational only, `GridRegularity.residual_max_m`/
   `residual_tolerance_m`), since the sprint spec asked for it to be
   evaluated. C-scan grid contract, now explicit and covered by a
   dedicated test: `x_coordinates`/`y_coordinates` share `amplitudes`'
   first two axes' shape and order exactly (`(trace_count, channel_count)`),
   and C-order flattening (`.flatten(order="C")`, numpy's default) maps
   flat index `i = trace * channel_count + channel` back to cell
   `[trace, channel]` identically for both -- the same convention a future
   `amplitudes.reshape(trace_count * channel_count, samples_count)` would
   use. 6 new domain tests (synthetic straight/curved/variable-spacing
   grids, an explicit "real coordinates are never replaced" test, footprint
   withheld for an irregular grid, and the C-order contract test).
5. **`MainWindow`'s +305 lines audited, no refactor made**: every
   geometry-related addition is either pure widget construction (matching
   every pre-existing `_build_*` dock method) or a thin busy-state-guarded
   delegation to `GeometrySession`/`GeometryPanel`/`PlanView`/
   `archaeogpr.geometry.export` -- structurally identical to the
   established Processing-dock pattern from Sprint GUI-3A. No business
   logic was found living in `MainWindow` that belonged elsewhere.
6. **A separate, real production bug found while fixing item 5's
   `geometry_panel.py` code**: the "F. Validation" section's warning list
   only ever collected `local_cscan_ready.warnings`, silently dropping
   `index_view_ready`/`global_cscan_ready`/`time_volume_ready`/
   `depth_volume_ready`'s warnings (and, before this addendum, there was
   nowhere for `GeometrySummary.warnings` to appear at all) -- meaning the
   new CRS-unverified and grid-regularity warnings from items 3-4 would
   have been silently invisible in the GUI. Fixed to collect all five
   gates' warnings plus `GeometrySummary.warnings`.

New/changed files this addendum: `src/archaeogpr/geometry/regularity.py`
(new); `src/archaeogpr/geometry/{models,resolve,summary,export}.py`,
`src/archaeogpr/gui/views/{plan_view,geometry_panel}.py` (edited);
`tests/test_geometry.py` (+14 tests: 3 all-NaN-summary + 6 grid-regularity
+ 5 CRS-validation-status, 25 -> 39);
`tests/test_gui_geometry.py` (+1 test, 1 strengthened, 30 -> 31).

## Addendum 2: Regularity Model Refinement (2026-07-19, same day)

The user reviewed Addendum 1 and identified a real scientific conflation
still present: **regular sampling and rectilinear geometry are not the
same claim**, and Addendum 1's single `is_regular` boolean answered both
at once. A survey can be sampled very evenly (constant step length,
constant channel spacing, constant heading) while still not coinciding
with a single-origin, single-azimuth rectilinear reconstruction -- which
is exactly what the real file turned out to demonstrate.

### 1. Four separated concepts, not one `is_regular`

`GridRegularity` (`regularity.py`) now reports, independently:

- **`actual_point_grid_available`** (plain `bool`, never `None`): does a
  real `x_coordinates`/`y_coordinates` grid exist at all.
- **`sampling_regular`** (`bool | None`): along-track step-length CV and
  cross-channel spacing CV both within 15% -- computed directly from real
  point-to-point distances, needs no origin/azimuth.
- **`direction_consistent`** (`bool | None`): trace-to-trace heading's
  circular standard deviation within 10 deg -- likewise needs no
  origin/azimuth, only the real points themselves.
- **`rectilinear_fit_acceptable`** (`bool | None`): does the real grid
  actually coincide with the idealized single-origin/azimuth
  reconstruction within a physically-scaled tolerance (Decision 2 below).
  This is the *only* one of the four that needs origin/azimuth/direction/
  spacing to even be checkable.

`sampling_regular`/`direction_consistent` are computed from the real grid
alone (two real points compared to each other); `rectilinear_fit_
acceptable` compares the real grid to a synthetic reconstruction. This is
why they can (and, for the real file, do) disagree.

### 2. Rectilinear-fit tolerance: `max(50% x channel spacing, 1% x along-track span)`

Fixed, documented, dimensionless-ratio-based (never a bare `0.1 m`-style
constant): `RECTILINEAR_FIT_CHANNEL_SPACING_FRACTION = 0.5`,
`RECTILINEAR_FIT_ALONG_TRACK_SPAN_FRACTION = 0.01`. Rationale: half a
channel width is the point past which a real position could plausibly be
mistaken for an *adjacent* channel's position -- "still basically the same
rectangle" stops being reasonable beyond that. 1% of the along-track span
is a conventional order-of-magnitude bound for accumulated dead-reckoning/
GPS-relative drift over a traverse of that length (a fixed per-step bound
does not scale for a long profile). `rectilinear_fit_acceptable` also
requires `direction_consistent` (the accepted policy's explicit `AND`) --
a curving path is never "acceptable" regardless of residual size. Reported
alongside three dimensionless ratios for transparency: `residual_max_m /
channel_spacing_m`, `residual_rmse_m / channel_spacing_m`, `residual_max_m
/ along_track_span`.

**The addendum-1 residual check (10% of channel spacing, informational
only) is superseded by this real gate** -- it remains available as
diagnostic-only numbers (`residual_max_m`, `residual_rmse_m`) but the
50%/1% combination above is what actually decides
`rectilinear_fit_acceptable` now.

### 3. Real file's honest result: `sampling_regular=True`, `direction_consistent=True`, `rectilinear_fit_acceptable=False`

Exactly the outcome the user predicted before any code was run. Verified
numbers: along-track step-length CV 2.34%, cross-channel spacing CV
0.008%, direction std 1.74 deg -- all excellent -- yet
`residual_max_m=0.3817 m`, which is 5.09x the channel spacing (0.075 m)
and comfortably exceeds the 0.0700 m tolerance (`max(0.5*0.075, 0.01*6.97)
= 0.0697` rounds to the reported 0.0700). This is a real, well-behaved,
regularly-sampled survey that is nonetheless not geometrically equivalent
to a rectilinear grid -- precisely the distinction Addendum 1 blurred.

### 4. Seven readiness gates, not five

`ReadinessGates` gained two fields and renamed one:

- `local_cscan_ready` -> **`local_parameter_grid_ready`** (same
  computation as before -- finite along/cross-track coordinates, known
  spacing -- but the name no longer implies the real acquisition itself is
  rectilinear; its `warnings` now say so explicitly).
- **`rectilinear_cscan_ready`** (new): `local_parameter_grid_ready.ready`
  AND (no real grid to check, OR `sampling_regular` AND
  `rectilinear_fit_acceptable`). `False` for the real file.
- **`actual_xy_point_grid_ready`** (new): real, finite X/Y coordinates
  exist -- independent of rectilinearity. `True` for the real file.
- `global_cscan_ready`'s semantics clarified in text (not behavior): it
  means a computationally usable actual X/Y point grid plus a declared
  CRS, never a rectilinearity or CRS-correctness claim; it now derives its
  blocking issues from `actual_xy_point_grid_ready` directly (previously
  duplicated the same finite-X/Y check inline).
- `time_volume_ready` now depends on `rectilinear_cscan_ready` (a
  time-domain *volume*, i.e. a regular `(nu, nv, nsamples)` array, needs a
  regular spatial grid) and its `warnings` say so explicitly, distinguishing
  it from a possible future time representation on the actual/curvilinear
  point grid (which would depend on `actual_xy_point_grid_ready` instead --
  not implemented this sprint).
- `depth_volume_ready`: unchanged, still unconditionally `False`.

### 5. Footprint area: three names, three meanings, never conflated

`GeometrySummary.footprint_area_m2` (Addendum 1) is replaced by three
explicitly-named fields:

- **`rectilinear_parameter_grid_area_m2`**: `along_span * cross_span` of
  the *derived* grid. Always reported for `LOCAL_METRIC` (no real grid to
  disagree with it). For `GLOBAL_PROJECTED`, reported **only** when
  `rectilinear_fit_acceptable is True` -- exactly Addendum 1's gating
  intent, now keyed on the correctly separated concept (an
  implementation bug where this had briefly become unconditional was
  caught and fixed before this addendum, via the very tests written to
  verify it).
- **`approximate_ribbon_area_m2`**: real along-track path length (summed
  trace-center-to-trace-center distances, not just the span) times nominal
  swath width. Always reported for `GLOBAL_PROJECTED` with a real grid,
  always with a warning stating it is an approximation.
- **`actual_polygon_area_m2`**: shoelace-formula area of the real
  acquisition footprint's own outer boundary (perimeter of the
  `(trace, channel)` grid, traced once around). Withheld -- with a warning
  -- if any boundary point is non-finite, or if the shoelace result
  disagrees with the ribbon estimate by more than 3x (a cheap, documented
  heuristic sanity check for a self-intersecting or degenerate boundary,
  not a formal simple-polygon proof). For the real file, all three
  agree closely (~5.22-5.24 m^2) except `rectilinear_parameter_grid_area_m2`,
  which is correctly withheld.

### 6. C-scan contract: two paths, now named

A future gridding sprint has exactly two representations to choose
between, and must pick explicitly rather than silently defaulting:
**(1)** a rectilinear parameter-grid render, built from
`along_track_coordinates`/`cross_track_offsets` (gated on
`rectilinear_cscan_ready`), or **(2)** an actual/curvilinear point-grid
render, built from `x_coordinates`/`y_coordinates` directly (gated on
`actual_xy_point_grid_ready`). `amplitudes[trace, channel, sample]`,
`x_coordinates[trace, channel]`/`y_coordinates[trace, channel]`, and
`along_track_coordinates[trace]`/`cross_track_offsets[channel]` all share
the same C-order flatten convention
(`flat_index = trace_index * channel_count + channel_index`). Neither
path may silently substitute for the other -- a non-rectilinear real grid
must never be quietly rendered as if it were rectilinear. No
interpolation/resampling was added this sprint for either path.

### 7. Tests

6 new domain tests: irregular along-track spacing (a different failure
mode than irregular cross-channel spacing), a precisely-known lateral
residual verifying both the exact ratio values and that it blocks
`rectilinear_cscan_ready`, ribbon area reported with its warning,
derived-grid provenance mirroring its source spacing's own provenance
(not blindly `DERIVED`), JSON export structure for all the new fields, and
a real-file consistency test (skips cleanly if the file is absent) pinning
down the exact `sampling_regular=True, direction_consistent=True,
rectilinear_fit_acceptable=False` result. 1 new GUI test confirms the
Geometry Inspector shows sampling/direction/rectilinear-fit as separate
rows, never one flag -- and, in fixing it, uncovered that this project's
`ogpr_builder` synthetic fixture's default 3-trace/2-channel geolocation
is itself a near-degenerate sliver (cross-track vector nearly parallel to
along-track, not perpendicular), for which `actual_polygon_area_m2` is
correctly withheld by the same safety check for a different underlying
reason than the real file's case -- a test-fixture quirk documented in
the test itself, not a production defect.
`tests/test_geometry.py`: 39 -> 45 (+6). `tests/test_gui_geometry.py`:
31 -> 32 (+1, plus one existing test's hardcoded top-level-group count
updated from 6 to 7 for the new "G. Grid Regularity" section).

## Related Files

- `src/archaeogpr/geometry/models.py`
- `src/archaeogpr/geometry/resolve.py`
- `src/archaeogpr/geometry/regularity.py`
- `src/archaeogpr/geometry/transform.py`
- `src/archaeogpr/geometry/validation.py`
- `src/archaeogpr/geometry/export.py`
- `src/archaeogpr/geometry/summary.py`
- `src/archaeogpr/gui/models/geometry_session.py`
- `src/archaeogpr/gui/views/geometry_panel.py`
- `src/archaeogpr/gui/views/plan_view.py`
- `src/archaeogpr/gui/main_window.py`
- [[02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector]]
- [[03_ARCHITECTURE/3D_Volume_Data_Model]] (the future sprint this one prepares for)
- [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]
- [[06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply]] (the busy-state pattern this sprint reuses)
- [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]]
- [[06_DECISIONS/ADR_001_OpenGPR_Internal_Data_Model]]
- [[03_ARCHITECTURE/OpenGPR_File_Structure]] (ISSUE-001, the unresolved EPSG:32632 discrepancy)
- [[03_ARCHITECTURE/GUI_Architecture]]
