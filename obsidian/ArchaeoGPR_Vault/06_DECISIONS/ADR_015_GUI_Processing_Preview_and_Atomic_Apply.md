---
type: adr
id: ADR-015
status: accepted
date: 2026-07-19
---

# ADR-015 — GUI Processing Preview and Atomic Apply

## Context

Sprint GUI-1/GUI-2/GUI-1B built a view-only native viewer: B-scan/A-scan
display, non-destructive display controls (ADR-013), responsive background
file loading (ADR-014). None of them connected the GUI to
`src/archaeogpr/processing/*.py` -- the five already-stable, already-tested
functions (`correct_time_zero`, `correct_dc_offset`, `correct_dewow`,
`correct_bandpass`, `remove_background`) remained CLI-only.
`obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/Processing_Preview_and_Commit_Model.md`
(written during Sprint GUI-0) sketched a design for exactly this -- an
`OperationSpec` registry, a preview/apply/cancel flow, and a full
`SessionState`/`DatasetState` undo-redo + recipe system -- but marked
"tasarım, henüz implemente edilmedi" throughout.

Sprint GUI-3A implements the registry + preview/apply portion of that
design -- deliberately **not** the undo/redo stack or the recipe system
(see Alternatives Considered). Scope: exactly the five stable operations,
non-destructive (preview never commits until the user clicks Apply),
cancellable, mutually exclusive with file loading. No gain, no 3D, no
processed-file save.

## Decision

### 1. Three-way dataset split: raw / current / preview, not a full undo/redo stack

`DatasetSession` (`src/archaeogpr/gui/models/dataset_session.py`) gained
`raw_dataset`, `current_dataset`, `preview_dataset` (plus
`current_valid_mask`/`preview_valid_mask`, `current_revision`,
`preview_base_revision`) instead of the single `dataset` field GUI-1/GUI-2/
GUI-1B used. `dataset` is kept as a **property** aliasing `current_dataset`
(with a setter for pre-GUI-3A call sites that assign it directly) so none
of GUI-1/GUI-2/GUI-1B's own code, or `tests/test_gui.py`, had to change.

- `raw_dataset` is set once, on file load (`commit_dataset`), and never
  reassigned by any processing operation.
- `current_dataset` is the committed chain's current head -- what every
  other view (B-scan/A-scan/metadata/export) treats as "the" dataset.
  Only `apply_preview()`/`reset_to_raw()` ever replace it, both atomic,
  both bump `current_revision`.
- `preview_dataset` is a processing result computed against
  `current_dataset` but not yet committed; cleared by
  `apply_preview()`/`discard_preview()`/a new file load/`reset_to_raw()`.

This is **not** the design doc's `SessionState{states: list[DatasetState],
cursor: int}` -- there is no append-only history list, no cursor, no
undo/redo. `reset_to_raw()` collapses straight back to the raw dataset in
one step; it does not step back one operation at a time. A future sprint
could build the full undo/redo stack on top of this (each `apply_preview()`
call is already a natural "checkpoint"), but this sprint does not.

### 2. `current_valid_mask` threads a `ProcessingResult.valid_mask` across chained operations

Verified from the processing API audit and `cli.py`'s own `sprint2`
pipeline handler: `_cmd_sprint2` explicitly passes
`valid_mask=tz_result.valid_mask` into `correct_dc_offset(...)`, and the
later CLI subcommands read a `valid_mask` back out of the processed NPZ and
thread it into `correct_dewow`/`correct_bandpass`/`remove_background`. The
GUI mirrors this: after any `apply_preview()`, `current_valid_mask` becomes
whatever `ProcessingResult.valid_mask` that operation returned (for
`correct_time_zero` this is a freshly-computed padding mask; for the other
four it is an independent copy of whatever mask was passed in, or `None`).
The next preview's adapter call always receives `current_valid_mask` as its
`valid_mask` argument. Time-zero's own padding is therefore correctly
excluded from a subsequent DC-offset/dewow/band-pass/background-removal
preview, exactly as the CLI's own canonical pipeline does it.

### 3. Registry + adapters, never a direct `processing/*.py` call from the GUI

`src/archaeogpr/gui/processing/{models,registry,adapters}.py` (new, Qt-free
-- importable with no PySide6 installed, matching ADR-012's isolation
rule). `ParameterSpec` describes one form field (name/label/kind/unit/
range/default/choices); `ProcessingOperationSpec` bundles a `display_name`,
`description`, a `parameters` tuple, `changes_time_axis`, and two
callables: `apply(dataset, params, valid_mask) -> ProcessingResult` and
`validate(params, dataset) -> tuple[str, ...]`. Every `apply`/`validate` in
`adapters.py` is a thin translation layer -- it pulls values out of the
GUI's `params` dict and calls the one real function with its real,
audited keyword arguments; it never reimplements or wraps the underlying
math. `validate()` is a fast, synchronous, GUI-thread pre-check (used to
keep an obviously invalid parameter from ever starting a worker); the real
function's own validation (`ProcessingError`) still runs afterward
regardless and remains the actual source of truth.

**Registered operations (`registry.py`, exactly five, see Consequences for
the gain-absence check)**: `time_zero`, `dc_offset`, `dewow`, `bandpass`,
`background`. Every default parameter value is copied from the real
function's own default keyword value (audited, never invented) except
`remove_background`'s `method`, which has no default in the real function
(it is a required keyword) -- `"global_mean"` was picked for the GUI's
initial form state only because it needs no window parameter to be
immediately runnable, not because it is scientifically preferred
(background removal has no canonical choice at all -- see ADR-009).

**Two scope-narrowing decisions, both to avoid a fundamentally different
per-operation UI shape than every other one here:**

- Time-zero's `"manual"` method (per-channel pick entry, a
  `{channel: sample}` dict) is not exposed -- only the two automatic
  methods (`channel_median_peak`, `channel_median_cross_correlation`).
- Band-pass's `"ormsby"` method (a 4-corner-frequency design,
  `frequencies_mhz=(f1,f2,f3,f4)`) is not exposed -- only `"butterworth"`
  (low cutoff, high cutoff, order, zero-phase), matching this sprint's own
  scope description verbatim.

Band-pass's client-side Nyquist check (`adapters.py::_nyquist_mhz`) is a
byte-for-byte copy of `processing/bandpass.py`'s own private
`_nyquist_mhz` expression -- duplicated, not imported (it is a private
helper of that module), specifically so the GUI's pre-flight check can
never accept a value the real function would then reject, or vice versa.

### 4. Processing worker reuses ADR-014's pattern, with two additions

`src/archaeogpr/gui/workers/processing_worker.py`: `ProcessingWorker`
(`QObject` + `moveToThread`, never a `QThread` subclass), every signal
connected only to bound methods of `MainWindow` (never a lambda -- see
ADR-014's crash post-mortem), cooperative-only cancellation via a
caller-owned `threading.Event` checked before and after the one opaque,
uninterruptible `apply()` call, a `finished` signal that always fires last
exactly once. This is not a new design -- it is ADR-014's `FileLoadWorker`
pattern, reused, with exactly two differences:

1. **Every terminal signal also carries `base_revision`** -- the
   `DatasetSession.current_revision` the input dataset was captured at.
   GUI-1B's token alone only detects "a newer request superseded this
   one"; it cannot detect "the committed dataset itself changed underneath
   this preview" (the user applied a different operation, or reset to raw,
   while this one was still computing). `MainWindow` checks both `token`
   and `base_revision` before ever calling `DatasetSession.set_preview()`.
   Structurally, this should be unreachable in this sprint's own code (the
   Processing panel is locked -- Preview/Apply/Discard/Reset all disabled
   -- for the entire time a run is in flight, so nothing can change
   `current_revision` while it runs), but the check is kept as a defensive
   guard regardless, exactly the same posture ADR-014 took for stale-token
   rejection.
2. **A successful run produces a preview, never a commit.** The success
   signal is `preview_ready`, not `loaded`; nothing in `processing_worker.py`
   ever touches `DatasetSession.current_dataset`. Only `MainWindow`'s Apply
   Preview action (`DatasetSession.apply_preview()`) does that, and only
   for a still-fresh preview (`DatasetSession.has_fresh_preview`).

No `ADR-016` was created for this: these are additive refinements to
ADR-014's already-documented decisions, not a new architectural decision in
their own right.

### 5. File loading and processing preview are mutually exclusive; two parallel state machines, not one merged enum

`MainWindow.is_processing` (`self._processing_thread is not None`) is the
exact structural analogue of `is_loading` (ADR-014): a new load cannot
start while `is_processing` is `True`, and a new processing run cannot
start while `is_loading` is `True` (`open_path()` and
`_on_preview_clicked()`/`_start_processing_preview()` each check both,
plus `_close_pending`). `ProcessingState` (`IDLE`/`RUNNING`/`CANCELLING`/
`SUCCESS`/`ERROR`/`CANCELLED`) is a second enum, deliberately mirroring
`FileLoadState`'s shape rather than merging both subsystems into one
`BusyState` -- the existing, already-tested `FileLoadState` machine and its
widgets (`load_status_label`, `_load_progress_widget`, etc.) did not need
to be touched at all; the Processing panel gets its own, symmetric set. The
single shared gate is `self._close_pending`, extended to block both
subsystems identically (see Decision 7).

The Processing panel's persistent "No preview / Computing / Ready /
Failed" status text is deliberately **not** driven by `ProcessingState`
directly -- that enum's `SUCCESS`/`ERROR`/`CANCELLED` are momentary
(settle back to `IDLE` in the same slot call, exactly like
`FileLoadState`'s). The label is computed from
`DatasetSession.has_fresh_preview` and `MainWindow._last_preview_outcome`
instead, so "Ready" keeps showing long after the transient `SUCCESS` state
has already moved on.

### 6. A parameter edit or operation change discards any existing preview outright

Considered: track a third "outdated" visual state alongside "No preview /
Computing / Ready / Failed". Rejected as unnecessary complexity for this
sprint -- editing a parameter or switching the operation combo while a
preview exists calls `DatasetSession.discard_preview()` immediately; the
user re-runs Preview to see the new result. Simpler to reason about and
test than a fourth state that still requires the user to notice it before
Apply would (incorrectly) commit a preview that no longer matches the
form's current values.

### 7. Deferred close extends to cover whichever background task is active

`closeEvent()` no longer checks only `is_loading` -- it checks
`not self.is_loading and not self.is_processing` for the immediate-accept
path, and separately cancels+defers for whichever of the two is actually
running (both branches are unconditional, not `elif`, so this stays
correct even if the mutual-exclusion invariant above is ever relaxed
later). `_on_processing_thread_finished` is the exact structural analogue
of `_on_load_thread_finished`: the one place
`_processing_thread`/`_processing_worker`/`_processing_cancel_event` are
cleared, never in the outcome handlers, and where a deferred close is
retried via `QTimer.singleShot(0, self.close)` if `_close_pending` is set.

### 8. Raw/Current/Preview display source is a MainWindow-level view concern, not `DatasetSession`'s

`MainWindow._display_source` (`"raw"`/`"current"`/`"preview"`) and
`_dataset_for_display()` decide which of the three datasets the B-scan/
A-scan/metadata panel actually render; `DatasetSession` itself has no
opinion about what is "currently shown" beyond tracking the three
datasets. The "Preview" combo item is disabled whenever no preview exists,
and the display source is snapped back to `"current"` automatically the
moment a preview is applied, discarded, or superseded by a new file load --
never leaving the user looking at a display source that no longer refers
to anything real.

### 9. History panel renders `dataset.processing_history` directly -- no parallel data structure

The History list is built straight from whichever dataset
`_dataset_for_display()` currently returns -- `operation`/`applied_at`/
`parameters` read directly out of each real `processing_history` entry.
While viewing a preview, entries beyond the committed dataset's own history
length are suffixed `"-- PREVIEW, NOT APPLIED"`, so a not-yet-committed
step is never presented as though it already were.

## Alternatives Considered

- **Building the design doc's full `SessionState`/`DatasetState` undo-redo
  stack in this sprint**: rejected as out of scope -- this sprint's own
  brief is explicitly "yalnızca ... preview → apply", not undo/redo. The
  raw/current/preview + `current_revision` split is forward-compatible
  with adding a full history stack later (each `apply_preview()` is
  already a natural append point) but does not build it now.
- **A recipe system** (`history_to_recipe`/`apply_recipe`, per the design
  doc): explicitly out of scope for this sprint (no processed-result save
  either) -- deferred to a future sprint.
- **One merged `BusyState` enum** instead of two parallel ones: considered
  (the user's own instructions offered both as options) -- rejected in
  favor of two mirrored enums (`FileLoadState`, `ProcessingState`) sharing
  only the `_close_pending` gate, so GUI-1B's already-tested state machine
  and widgets needed zero changes.
- **Exposing all of time-zero's/band-pass's real method variants**
  (`"manual"` picks, `"ormsby"`): rejected for this sprint -- both require
  a fundamentally different per-operation UI (a per-channel picks table; a
  4-corner-frequency form) that no other operation here needs; deferred,
  not silently dropped (see Decision 3).
- **Exposing `valid_mask` as a user-editable parameter**: rejected --
  it is derived, session-tracked state (`current_valid_mask`), never
  something a user types in; threading it automatically mirrors the CLI's
  own established pipeline behavior (see Decision 2).

## Consequences

- `src/archaeogpr/gui/processing/{__init__,models,registry,adapters}.py`
  (new) is the one place the registry and its five adapters live -- no Qt
  import anywhere in this package.
- `src/archaeogpr/gui/workers/processing_worker.py` (new) is the one place
  `ProcessingWorker`/`ProcessingState` live.
- `src/archaeogpr/gui/models/dataset_session.py` gained the raw/current/
  preview split, `current_valid_mask`/`preview_valid_mask`,
  `current_revision`/`preview_base_revision`, `has_fresh_preview`,
  `set_preview`/`discard_preview`/`apply_preview`/`reset_to_raw`. `dataset`
  remains a working alias (property + setter) for every pre-GUI-3A caller.
- `main_window.py` gained a Processing dock (operation combo, generic
  parameter form, Preview/Apply/Discard/Cancel/Reset-to-Raw buttons,
  display-source combo, history list) and the full worker-lifecycle wiring
  described above; every GUI-1/GUI-2/GUI-1B feature (display controls,
  file loading, deferred close) is unchanged by this sprint.
- No gain, no 3D, no depth conversion, no migration, no undo/redo, no
  recipe system, no processed-file save, no installer -- all remain
  exactly as scoped out in this sprint's own brief and in
  `01_PROJECT_STATE/02_Next_Development_Sprint.md`.
- Version `0.2.1` -> `0.3.0` (minor -- new user-visible processing
  capability).

## Validation

- `tests/test_gui_processing.py` (new, 48 tests, `@pytest.mark.gui`):
  session/model invariants (raw/current/preview identity, atomic apply,
  revision increment, discard, reset-to-raw, stale-preview rejection),
  registry/form correctness (exactly five operations, no gain, per-
  operation parameter widgets, invalid-parameter pre-flight rejection,
  Nyquist validation, operation-switch form rebuild, parameter-edit preview
  discard), processing-worker lifecycle (runs off the main thread, result
  handler runs on the Qt main thread, success produces a preview never a
  commit, runtime error and cancellation both preserve the current
  session, late-after-cancel/stale-token/stale-revision results are all
  discarded, concurrent processing is rejected, file-load/processing mutual
  exclusion in both directions, a new run starts cleanly once the previous
  one's thread has finished, deferred close during processing, no
  "QThread: Destroyed while thread is still running" warning, shutdown-
  pending rejects new work), view correctness (display-source selection,
  the "not applied" history label, the Preview combo item's enabled state,
  time-zero's time-axis change is visible through the preview, applying
  updates history/metadata, selected channel/trace and `DisplaySettings`
  both survive an apply), per-operation integration (all five leave their
  input dataset untouched, shape/dtype preserved, `valid_mask` threads
  correctly across a chained time-zero -> DC-offset run, real
  `processing_history` operation-name strings), and frozen-executable
  smoke (`--open`/`--smoke-test` still work with the Processing panel
  present, a real-file processing preview never touches the raw `.ogpr` on
  disk).
- All of Sprint GUI-1/GUI-2/GUI-1B's existing 74 GUI tests
  (`tests/test_gui.py`) pass unchanged -- the `dataset`
  property/setter alias means none of them needed to know raw/current/
  preview exist. Combined GUI suite: 122 passed.
- Core suite (`pytest -m "not gui"`, no Qt installed): 318 passed, 26
  skipped, 122 deselected -- confirms the new `gui/processing/` package and
  `gui/workers/processing_worker.py` never import Qt at module scope and
  never break headless collection (ADR-012's isolation rule).
- One genuine test bug found and fixed while writing this suite (not a
  bug in the production code): an early draft of
  `test_new_processing_can_start_after_previous_finishes` ran `dewow`
  twice in a row on the same dataset without `allow_repeat_processing` --
  the real function's reprocessing guard correctly raised, the worker
  correctly emitted `failed`, and `MainWindow._on_processing_failed`
  correctly opened a `QMessageBox.critical` -- which then hung forever
  offscreen with nothing to click it (the exact, already-documented
  `test_gui.py` pitfall). Fixed by using `dc_offset` (no reprocessing
  guard) for the test's second run, which is what "a new, independent run
  starts after the previous one finishes" actually means.

## Related Files

- `src/archaeogpr/gui/processing/models.py`
- `src/archaeogpr/gui/processing/registry.py`
- `src/archaeogpr/gui/processing/adapters.py`
- `src/archaeogpr/gui/workers/processing_worker.py`
- `src/archaeogpr/gui/models/dataset_session.py`
- `src/archaeogpr/gui/main_window.py`
- [[02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply]]
- [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]] (the design this
  sprint partially implements)
- [[06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy]]
  (the worker/cancellation pattern this sprint reuses)
- [[06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization]]
- [[06_DECISIONS/ADR_009_Canonical_No_Background_Removal_Policy]] (why
  background removal has no canonical default)
- [[03_ARCHITECTURE/GUI_Architecture]]
