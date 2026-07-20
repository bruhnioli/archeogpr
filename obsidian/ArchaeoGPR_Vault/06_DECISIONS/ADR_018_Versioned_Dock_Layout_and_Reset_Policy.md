---
type: adr
id: ADR-018
status: accepted
date: 2026-07-20
---

# ADR-018 — Versioned Dock Layout and Reset Policy

## Context

Sprint 3D-1's manual acceptance FAILED on a dock-layout regression: with six
docks (Dataset, Metadata, Processing, Survey Geometry, Plan View, C-scan /
Time Slice), the window opened with the Processing dock spilling over the
left/center area, the C-scan dock overlapping Processing, the center
graphics, and the right dock, and dock titles crushed together.

The root-cause audit (performed before any code change) found this was a
**construction-time default-layout defect, not a stale-persisted-state
defect** — `MainWindow` had **no** `saveState`/`restoreState`/`QSettings`
usage anywhere, so every launch rebuilt the same broken hardcoded
arrangement:

1. **`splitDockWidget(..., Qt.Orientation.Vertical)` was used to stack
   Dataset above Processing (left) and Metadata above Survey Geometry
   (right).** Four vertically-stacked, form-heavy panels must share each
   side column's height; each panel's natural minimum height (many stacked
   `QFormLayout` rows, no scroll areas anywhere) exceeds half a 800px-tall
   window, so Qt's dock layout was over-constrained the moment the C-scan
   dock (min height 240, sharing the bottom area) joined in Sprint 3D-1 —
   producing exactly the overlapping/spilled arrangement in the screenshot.
2. **No dock had an `objectName`**, so even if persistence had existed, no
   layout could ever have been saved/restored.
3. **No `setDockNestingEnabled`/`setCorner` configuration** — bottom-area
   width behavior was Qt's unconfigured default.
4. **No scroll areas** — every long form panel propagated its full natural
   minimum size up to its dock.

## Decision

### 1. Deterministic default layout: three tabified pairs, center untouched

`_build_docks()` constructs each dock exactly once;
`_arrange_docks_default()` — re-runnable, purely arrangement, never
constructing widgets or connecting signals — establishes the default:

- **Left**: Dataset + Processing, `tabifyDockWidget`, **Dataset** frontmost.
- **Right**: Metadata + Survey Geometry, `tabifyDockWidget`, **Metadata**
  frontmost.
- **Bottom** (full window width, via explicit
  `setCorner(BottomLeft/BottomRight, BottomDockWidgetArea)`): Plan View +
  C-scan / Time Slice, `tabifyDockWidget`, **Plan View** frontmost — chosen
  because Plan View is immediately meaningful right after a file loads,
  whereas C-scan shows nothing until the user configures and runs a
  Compute.
- **Center**: only the B-scan/A-scan splitter.
- `setDockNestingEnabled(True)`; no dock floats by default; sizes seeded
  with `resizeDocks` (left 240, right 360, bottom 220) — hints, not
  constraints.

Tabifying (one panel's height per side, selectable by tab) instead of
vertically splitting (both panels' heights summed per side) is what removes
the over-constraint that caused the overlap.

### 2. Unique, stable `objectName` on every dock

`datasetDock`, `metadataDock`, `processingDock`, `surveyGeometryDock`,
`planViewDock`, `cscanDock` — assigned at construction, before any
`addDockWidget`/`restoreState`, verified unique and non-empty by a test.
Renaming/adding/removing a dock requires bumping the schema version
(Decision 3).

### 3. Versioned window-state persistence, isolated from all other state

New module `src/archaeogpr/gui/window_state.py`:
`WINDOW_STATE_SCHEMA_VERSION` (currently **1** — this is the first version
that persists anything; bump on any dock-set change) and
`open_window_settings()` — a dedicated INI file
(`%LOCALAPPDATA%\ArchaeoGPR\window_state.ini`, same root as the existing
log directory, never the Windows registry, never shared with any other
setting) so window/dock placement can be reset or corrupted in complete
isolation from dataset/processing state.

`MainWindow._save_window_state()` (called from `closeEvent`'s clean-close
branch and from Reset Window Layout, never mid-deferred-shutdown) stores:
schema version, `saveGeometry()` blob, `saveState(SCHEMA)` blob, and the
window's plain-int width/height (the blobs are opaque; the ints let restore
reason about size *before* applying anything).

`MainWindow._restore_window_state()` (called at the end of `__init__`,
after every dock exists — the default layout is always fully built first
and stands as the fallback) applies a saved layout only when **all** of the
following hold, otherwise it returns `False` and the default layout stays:

- schema key present, parseable, and equal to
  `WINDOW_STATE_SCHEMA_VERSION` (Qt's own `restoreState(state, version)`
  version check is used in addition, not instead);
- geometry/dock-state/size keys all present;
- geometry restore is attempted **only if the saved window size fits the
  current screen's `availableGeometry()`** — `restoreGeometry()` clamps an
  oversized window (correct for placement), but the dock state below was
  laid out for the original size, and applying it into a clamped-smaller
  window is over-constrained (empirically bled the dock a few pixels over
  the central widget — the same defect class this ADR exists to prevent;
  caught by `test_layout_stable_after_two_open_close_cycles` on the
  offscreen platform, whose small virtual screen forces the clamp);
- dock state is applied **only into a window at least as large as the one
  it was saved from** (a larger window is safe — extra space goes to the
  center view); and
- `restoreState()`'s return value is `True` — on `False`,
  `_arrange_docks_default()` is re-run explicitly rather than trusting a
  failed restore left the construction-time layout untouched.

A stale/mismatched/corrupt entry is **never silently re-saved**: only a
clean close or an explicit Reset writes the keys (at which point the
then-current, valid layout legitimately replaces the bad one). Restore
order is Qt's canonical geometry-first, dock-state-second.

### 4. Long dock panels are scroll-wrapped

`_wrap_in_scroll_area()` (module-level helper): `QScrollArea` with
`widgetResizable=True`, both scrollbars as-needed, wrapping the
Processing, Survey Geometry, and C-scan panel widgets. A long form's
natural minimum height no longer propagates to its dock — the dock can
shrink to whatever space the layout actually has, scrolling the remainder,
instead of forcing an over-constrained layout. Dataset (short form),
Metadata, and Plan View (both already viewport-style widgets) are not
wrapped. No `setFixedHeight`/`QSizePolicy.Fixed`/manual `setGeometry`
existed in the panels (audited); the pre-existing per-dock
`setMinimumWidth`/`setMinimumHeight` values (220–320 / 180–240) are modest
and kept.

### 5. Floating docks are not supported (this turn's explicit UX decision)

None of the six docks' `setFeatures()` calls include
`DockWidgetFloatable` — which was already the pre-existing (if implicit)
behavior of every dock before this fix; this ADR makes it an explicit,
documented decision rather than an accident. Rationale: supporting
floating *well* requires off-screen-geometry clamping and
stale-floating-state overlap handling that are orthogonal to the docked
overlap defect this turn fixes; a floating dock also cannot overlap the
docked layout by definition of the bug being fixed. Docks remain Movable
(re-arrangeable between areas/tabs) and — except Dataset — Closable
(re-openable via Reset Window Layout). Revisiting this means adding the
feature flag back per-dock *plus* the clamping logic, plus a schema bump
if the persisted-state semantics change.

### 6. View → Reset Window Layout

A new `View` menu with one action: clears the window-state settings file
(`QSettings.clear()`), un-floats and shows every dock, re-runs
`_arrange_docks_default()`, and saves the fresh default as the new
baseline — all without restarting. This is the user-facing escape hatch
for any layout state this policy's guards don't anticipate.

### 7. Minimum supported window size for the default layout

The default layout is verified non-overlapping (real rectangle-intersection
assertions, not `isVisible()`) at **1280×800** and **1366×768**;
`MainWindow`'s own minimum stays 900×600, where scroll areas absorb the
deficit. Larger sizes (1600×900, 1920×1080) simply give the center view
more space — no dock ever gains overlap from extra room.

## Alternatives Considered

- **Keeping `splitDockWidget` stacks with smaller minimum heights**:
  rejected — shrinking minimums below usable form heights just trades
  overlap for unusable clipped panels; tabifying removes the height
  competition entirely.
- **Persisting window state in the Windows registry (default `QSettings`)
  or in one shared app-settings file**: rejected — a dedicated INI file can
  be deleted/reset in isolation, is visible/debuggable, and structurally
  cannot corrupt (or be corrupted by) any other stored state.
- **Restoring dock state into a smaller-than-saved window and trusting Qt
  to squeeze**: rejected empirically — Qt resolves the over-constraint with
  a several-pixel dock-over-center bleed (measured 3px on the offscreen
  platform), which is precisely the defect class reported.
- **Supporting floating docks with clamped restore geometry**: deferred,
  not rejected forever — see Decision 5.
- **A confirmation dialog on Reset Window Layout**: omitted — the action is
  non-destructive to data (it only touches window placement) and
  immediately reversible by re-arranging.

## Consequences

- `src/archaeogpr/gui/window_state.py` (new) — schema constant + settings
  factory, the one place window-state storage policy lives.
- `main_window.py`: `_build_docks()` rewritten (objectNames, tabified
  default via `_arrange_docks_default()`, corners/nesting, scroll
  wrapping, no-float features), `_save_window_state()`/
  `_restore_window_state()`/`_on_reset_window_layout_triggered()` added,
  `closeEvent` clean-close branch saves state, `__init__` restores after
  all docks exist, new View menu.
- `tests/test_gui_dock_layout.py` (new, 27 tests): objectName uniqueness,
  restore-after-construction, tabified pairs, no-floating default,
  center-widget positive area, geometry-intersection no-overlap at
  1280×800/1366×768 (with explicit event settling — `isVisible()` alone is
  insufficient for tabified docks, whose backgrounded tabs stay "visible"
  at degenerate coordinates), scroll wrapping, stale-schema/corrupt-state/
  too-small-window fallbacks, valid-state restore, Reset behavior
  (arrangement/visibility/un-float/preserves dataset+processing state),
  two-cycle stability, deferred-close safety, no-dataset and post-load
  validity, center-view non-collapse, viewport containment, and a
  no-Qt-layout-warnings sweep.
- The Sprint 3D-1 dock set is schema version 1's dock set; the next dock
  addition/removal/rename must bump `WINDOW_STATE_SCHEMA_VERSION`.
- **Manual acceptance for Sprint 3D-1 remains NOT completed** — it failed
  on this regression and must be re-run against the fixed build.

## Addendum: Settings Isolation for Automated Verification (2026-07-20, same day)

Manual acceptance review of the dock-layout fix flagged a second,
release-blocking risk before this ADR's own fix could be accepted: the
report itself admitted that `test_gui.py`'s existing `--open --smoke-test`
GUI tests, the executable's `--smoke-test` mode, and `build_windows.ps1`'s
frozen-executable verification could all read, write, or clear the real
`%LOCALAPPDATA%\ArchaeoGPR\window_state.ini` -- automated verification
overwriting a developer's actual saved layout is unacceptable regardless of
whether the dock arrangement itself is now correct.

### 1. Dependency injection at both ends: `open_window_settings()` and `MainWindow`

`window_state.py` gained two new `open_window_settings()` keyword
parameters, `path_override` (an exact, absolute path -- used by test/DI
callers) and `ephemeral` (a unique per-process temp file, never the real
path -- used by `--smoke-test`), mutually exclusive with each other.
`MainWindow.__init__` gained two new keyword-only parameters:
`persist_window_state: bool = True` (when `False`, `_save_window_state()`
and `_restore_window_state()` are unconditional no-ops -- the real file is
never even opened, not merely "opened but not written") and
`window_settings_factory: Callable[[], QSettings] | None = None` (defaults
to the real `open_window_settings`; overriding it redirects every save/
restore/Reset call this window makes). Production callers (`app.py`'s
normal launch path) pass neither and get exactly the pre-existing behavior.

### 2. Smoke-test mode: both guards applied together

`app.py`'s `--smoke-test` branch constructs
`MainWindow(persist_window_state=False, window_settings_factory=lambda:
open_window_settings(ephemeral=True))` -- belt-and-suspenders: even if one
guard were ever accidentally removed, the other still prevents the real
file from being touched. A smoke run's construction, `--open` (if given),
event pumping, and close all use this window; `--version` returns before
any `QApplication`/`MainWindow` exists at all and therefore needs no
settings guard.

### 3. Explicit environment override for external processes

`WINDOW_STATE_PATH_ENV_VAR = "ARCHAEOGPR_WINDOW_STATE_PATH"` -- read by
`default_window_state_path()` with precedence over the real
`%LOCALAPPDATA%` resolution, rejected safely (logged, ignored, falls
through to the real default) if set to an empty or non-absolute value.
Used by two external callers that cannot pass Python keyword arguments:
`scripts/build_windows.ps1` (sets it to a per-run temp file for its
subprocess `--smoke-test` invocation) and `tests/conftest.py`'s autouse
`_isolate_gui_window_state` fixture (sets it to a per-test `tmp_path` file
for every `@pytest.mark.gui` test in the entire suite -- not just
`test_gui_dock_layout.py`). `conftest.py` hardcodes the env var's literal
string value rather than importing it from `window_state.py`, since that
module imports `PySide6.QtCore` and importing it from `conftest.py` would
break headless core-suite collection (the same Qt-free-core-import rule
ADR-012 established).

### 4. Build script: preflight + before/after invariance proof

`build_windows.ps1` gained two things: (a) a preflight check that fails
fast with a clear message if an `ArchaeoGPR.exe` from a previous build is
still running (its open `_internal\*.pyd`/`.dll` handles otherwise turn the
subsequent cleanup step into a wall of `Remove-Item` permission errors) --
the script never force-closes it; the user must close it themselves; and
(b) the script now records the real `window_state.ini`'s SHA-256/size (or
its absence) immediately before the smoke test and verifies it is
byte-for-byte identical (or still absent) immediately after, failing the
build with an explicit "settings-isolation violation" message if not --
this is the build script proving its own isolation guarantee, not merely
asserting it in a comment.

### 5. Reset Window Layout operates only on the active backend

`_on_reset_window_layout_triggered()` already called
`self._window_settings_factory()` (Decision 1) rather than the bare
production function -- this addendum makes explicit and tests directly
that Reset therefore can never clear a settings store other than the one
this specific window instance would itself save to. In production (no
override), that is the real file, exactly as intended; in test/ephemeral
mode, it is the injected/ephemeral one, and the real file is provably
untouched.

### 6. Tests

18 new tests, `tests/test_gui_window_state.py`: production-path
resolution, `path_override`/`ephemeral` behavior, env-override
honored/rejected (relative, empty), smoke-mode restore/save no-ops
(including "file absent before -> absent after" and "file present before
-> byte-for-byte and mtime-identical after"), deferred-close-in-ephemeral-
mode writes nothing, `app.main(["--smoke-test"])` and
`app.main(["--open", ..., "--smoke-test"])` end-to-end never touch a faked
real `LOCALAPPDATA`, Reset clears only the active backend while a separate
"real" store is untouched, a persistent (non-ephemeral) clean close *does*
write (proving the guard is mode-specific, not a global kill switch),
corrupt injected state falls back to default via the DI seam directly, and
two independent injected settings paths / two simultaneous `MainWindow`
instances never cross-contaminate. Combined with `test_gui_dock_layout.py`'s
existing 27 (now isolated via the same autouse mechanism instead of their
own local `LOCALAPPDATA` monkeypatch) and the rest of the GUI suite's now
also-autouse-isolated tests, no automated test in this repository can reach
the real settings file.

New/changed files this addendum: `src/archaeogpr/gui/window_state.py`
(`path_override`/`ephemeral`/env-override additions),
`src/archaeogpr/gui/main_window.py` (`persist_window_state`/
`window_settings_factory` constructor parameters and guards),
`src/archaeogpr/gui/app.py` (`--smoke-test` uses both), `tests/conftest.py`
(new autouse fixture), `tests/test_gui_dock_layout.py` (local fixture
simplified to rely on the autouse one), `tests/test_gui_window_state.py`
(new, 18 tests), `scripts/build_windows.ps1` (preflight + isolation +
invariance proof).

## Related Files

- `src/archaeogpr/gui/window_state.py`
- `src/archaeogpr/gui/main_window.py`
- `src/archaeogpr/gui/app.py`
- `tests/conftest.py`
- `tests/test_gui_dock_layout.py`
- `tests/test_gui_window_state.py`
- `scripts/build_windows.ps1`
- [[02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan]]
- [[06_DECISIONS/ADR_017_Actual_XY_CScan_and_No_Interpolation_Policy]]
- [[03_ARCHITECTURE/GUI_Architecture]]
- [[09_REFERENCES/Windows_Executable_Build]]
