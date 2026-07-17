---
type: adr
tags: [decision]
id: ADR-013
status: accepted
date: 2026-07-17
---

# ADR-013 — Display Policy and Non-Destructive Visualization

## Context

Sprint GUI-1 ([[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]]) shipped a view-only
B-scan/A-scan viewer with a fixed 99th-percentile symmetric grayscale
display. The user's own manual demo of that build surfaced a real,
expected consequence of `Swath003_Array02.ogpr`'s wide dynamic range: the
strong direct-arrival/antenna-coupling energy around 8-12 ns dominates a
fixed display range, making most of the B-scan render as flat gray and
weaker deeper reflections invisible. The user explicitly framed this as
"a display-scaling problem, not a parser error" and asked for Sprint
GUI-2: interactive contrast controls, colormap choice, A-scan display
modes, a more legible metadata panel, and PNG export -- **display features
only, no processing**.

This ADR records the one governing principle behind every GUI-2 control,
so future sprints (and future contributors) have a single place that
states it explicitly rather than re-deriving it from scattered docstrings.

## Decision

**Contrast, clipping, colormap, A-scan normalization, and visible-range
autoscale are display policy, not processing.** Concretely:

1. None of `DisplaySettings`'s fields, or any function that consumes it
   (`compute_display_levels`, `colormap_lookup_table`,
   `BScanView.set_display_settings`, `AScanView.set_mode`,
   `export_bscan_png`), is ever permitted to call
   `GPRDataset.with_processing_step`, append to
   `dataset.processing_history`, or write to `dataset.amplitudes`. This is
   enforced structurally, not just by convention: `GPRDataset.amplitudes`
   is still read-only per ADR-001 (`ndarray.flags.writeable == False`),
   so an attempt to write raises `ValueError` rather than silently
   succeeding -- tests assert this directly (see
   [[02_SPRINTS/Sprint_GUI_2_Display_Controls]] Validation Results).
2. `DisplaySettings` is an immutable dataclass (`dataclasses.replace`, the
   same discipline ADR-001 applies to `GPRDataset` itself, applied to
   display state instead of radar data) -- there is no in-place "set
   contrast" mutation anywhere in the GUI.
3. **A-scan "Normalize for display"** produces a *new*,
   independently-allocated array (`trace / max(|trace|)`); the source
   trace, `dataset.processing_history`, and all metadata are untouched.
   The mode is labeled "display only" in the UI and the X axis is
   relabeled "Normalized amplitude (display only)" so a user cannot
   mistake it for a processed/gained amplitude.
4. **PNG export is a display export, not a processing export.** It lives
   in `archaeogpr/gui/export.py`, entirely separate from
   `archaeogpr.export` (the existing headless CLI export package for
   processed NPZ/CSV/JSON). Every exported PNG's accompanying
   `.display.json` sidecar records the display policy used (colormap,
   percentile, level mode, actual min/max) and explicitly states
   `"note": "Display-only export; source amplitudes unchanged."`.
5. **Manual levels vs. symmetric mode**: enabling "Manual levels"
   disables "Symmetric around zero" (rather than trying to reconcile
   both as a combined state). Rationale: manual levels are an explicit,
   complete override of *both* bounds chosen by the user -- treating
   "symmetric + manual" as "user enters only ±Max Abs" (the alternative
   considered below) still leaves an ambiguous question for asymmetric
   auto-levels' relationship to manual mode, whereas "manual replaces
   auto entirely, full stop" has exactly one meaning regardless of which
   auto-mode was active before. The manual fields are seeded with the
   current auto-computed levels when first enabled, so the user edits a
   real, currently-displayed starting point rather than `0.0`/`0.0`.
6. **Invalid manual levels (`min >= max` or non-finite) are never applied
   to the render pipeline.** `compute_display_levels` silently falls back
   to the automatic (symmetric/asymmetric) computation for that one
   render; the GUI separately shows the invalid state via a red field
   background -- the two are independent safeguards (a UI bug in the
   validation styling could never itself cause a broken/NaN color range,
   because the pipeline-level fallback doesn't depend on the UI noticing
   first).
7. **Visible-region autoscale** (optional, `visible_region_autoscale`)
   recomputes levels only from the samples within the B-scan's currently
   visible time range, debounced 200 ms after a zoom/pan settles
   (`ViewBox.sigRangeChanged` -> a single-shot `QTimer`) -- never on every
   intermediate drag frame. This was judged straightforward enough to
   implement in full this sprint (not deferred to a `GUI-2B` TODO, the
   `Sprint_GUI_2_Display_Controls.md` task list's own "out" clause) since
   the actual computation (`np.searchsorted` + a percentile over the
   sliced region) is cheap at this dataset's size (see Validation).

### Addendum (fix round, same date): A-scan axis policy + level-source exclusivity

A second manual visual test on the same build (before commit/push) found
two display bugs and one UX conflict, all fixed on the same
`sprint-gui-2-display-controls` branch -- see
[[02_SPRINTS/Sprint_GUI_2_Display_Controls]] Issues Discovered → Fix Round
for the full narrative. This addendum records the two additional policy
points that fall under this ADR's scope (display policy, not processing):

8. **A-scan "Normalize for display" always sets an explicit X view range**
   (`(-1.05, 1.05)`), unconditionally, every redraw while that mode is
   active. Previously the X-range branch only handled `"robust"`/`"full"`;
   switching into `"normalize"` left whichever raw-amplitude range a prior
   mode had set, and the ~[-1, 1] normalized curve became visually
   indistinguishable from a flat line at that scale. This is display
   policy, not a data change -- the curve data itself was always correct;
   only the *view range* was wrong.
9. **The A-scan's time (Y) axis is always derived from the current
   dataset's own `time_ns` array, never hardcoded and never assumed to
   start at 0.** `AScanView._apply_time_axis_bounds()` computes
   `float(np.min(time_ns))`/`float(np.max(time_ns))` and applies them via
   `ViewBox.setLimits(yMin=, yMax=)` -- a hard pan/zoom constraint that
   persists across channel/trace/mode changes -- plus a full view reset
   (`setYRange`) only on first load and `reset_view()`. This is the same
   "always derive from the dataset, never hardcode" principle already
   applied to `time_ns` construction elsewhere in the pipeline (see
   [[06_DECISIONS/ADR_004_TimeZero_Relative_Axis_and_DC_Window]]), now
   also applied to this GUI's own axis rendering -- a future time-zero-
   corrected dataset with a negative-starting `time_ns` is handled
   correctly without any GUI code change.
10. **Manual levels and visible-region autoscale are mutually exclusive
    level *sources*, enforced twice.** UI level (`main_window.py`):
    enabling one unchecks and disables the other's checkbox, in both
    directions. Render-pipeline level (`BScanView._visible_region_autoscale_active()`):
    even if a `DisplaySettings` instance somehow has both flags `True`
    (e.g. constructed directly, bypassing the UI), the visible-region
    percentile recompute is skipped entirely -- not just overridden after
    running -- because `compute_display_levels` already resolves manual
    first (see Decision item 6 and `compute_display_levels`'s docstring).
    The display-summary label was extended to show exactly one of four
    mutually exclusive words (`symmetric`/`asymmetric`/`manual`/
    `visible-range auto`) rather than only ever showing
    symmetric/asymmetric and silently ignoring an active visible-range
    autoscale.

## Alternatives Considered

- **Symmetric + Manual as a combined "±Max Abs only" mode** (the task's
  alternative (A)): rejected in favor of "manual disables symmetric"
  (alternative (B), see Decision item 5) -- simpler invariant, no
  partial-state UI to design/test, and the seeded-starting-value UX
  mitigates the main downside (typing two numbers instead of one).
- **Reusing `qc/bscan.py::plot_bscan` directly for PNG export**: rejected.
  `plot_bscan`'s `vlimit` parameter is symmetric-only
  (`vmin=-limit, vmax=limit`); GUI-2 must export whatever the user is
  actually looking at, including an asymmetric or manual (possibly
  non-zero-centered) range, so a small dedicated
  `archaeogpr/gui/export.py::export_bscan_png` was written instead,
  accepting an explicit `(vmin, vmax)` tuple. It still uses the same
  matplotlib `imshow`/`origin="upper"` convention as `plot_bscan` for
  visual consistency with the existing QC exports.
- **A dedicated colormap module**: considered, rejected as an unnecessary
  extra file for a single consumer; `colormap_lookup_table()` lives in
  `bscan_view.py` (the only place that needs a LUT) as the one
  centralized function the task asked for, without a new file.
- **Caching percentile computations by (dataset id, channel, settings)**:
  considered per the task's own performance section, rejected as
  premature. Benchmarked directly (see Validation): ~2.2 ms per
  `compute_display_levels` call on the real 175x1024 sample dataset --
  far under any perceptible-lag threshold for a slider/spinbox
  interaction. No cache was added; this decision is revisitable if a
  future, much larger dataset makes it necessary.

## Consequences

- `src/archaeogpr/gui/models/display_settings.py` (new) is the single
  place `DisplaySettings` and `compute_display_levels` live; every view
  (`BScanView`, `AScanView`) and `main_window.py` import from it rather
  than each re-implementing percentile/level logic.
- `src/archaeogpr/gui/export.py` (new) is the one place a PNG + sidecar is
  produced; it duplicates none of `archaeogpr.export`'s (CLI) logic and
  is not imported by it either -- the two export paths stay independent,
  matching CLAUDE.md's "processing/export separation" spirit applied to
  the GUI's own display exports.
- `BScanView`/`AScanView` were refactored around an explicit pipeline
  (source view -> finite subset -> levels from policy -> `ImageItem`/LUT
  update -> never write back) -- see
  [[02_SPRINTS/Sprint_GUI_2_Display_Controls]] Implementation Notes for
  the exact stage list.
- No processing GUI (time-zero/DC/dewow/band-pass/background/gain), no
  undo/redo, no recipe, no 3D/depth conversion was added -- all remain
  exactly as scoped out in
  [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]] and
  [[03_ARCHITECTURE/3D_Volume_Data_Model]].

## Validation

- `tests/test_gui.py` (Sprint GUI-2 additions): percentile/symmetric/
  asymmetric/manual level tests, colormap-switch test, three A-scan-mode
  tests (including a zero-trace-safe normalize test), trace-selection
  boundary tests (0, last index, out-of-range, and a zoomed view), PNG
  export + sidecar tests -- all assert `dataset.amplitudes.tobytes()`
  and/or `.flags.writeable` are unchanged after the display operation
  under test. See [[02_SPRINTS/Sprint_GUI_2_Display_Controls]] Validation
  Results for the exact pass count.
- Percentile computation benchmark on the real sample dataset (175 trace
  x 1024 sample, one channel): ~2.2 ms/call, 200 calls in ~443 ms --
  confirms no caching is needed at this scale (see Alternatives
  Considered).
- Manual invalid-range fallback verified directly: `manual_min=500.0,
  manual_max=100.0` (invalid) never reaches the render pipeline; the
  function returns the automatic symmetric/asymmetric levels instead.
- **Fix-round addendum**: 10 further tests cover normalize-mode visibility
  and range, all three A-scan mode transitions' X-range behavior, the
  A-scan time axis matching real `dataset.time_ns` bounds (including a
  negative-starting time-zero fixture) and blocking an out-of-bounds pan,
  manual/visible-autoscale two-way mutual exclusion (UI and render
  pipeline), the display-summary label's single-active-mode invariant, and
  a stale-cursor regression lock -- see
  [[02_SPRINTS/Sprint_GUI_2_Display_Controls]] Validation Results for the
  full list and pass count (45 total GUI tests).

## Related Files

- `src/archaeogpr/gui/models/display_settings.py`
- `src/archaeogpr/gui/export.py`
- `src/archaeogpr/gui/views/bscan_view.py`
- `src/archaeogpr/gui/views/ascan_view.py`
- `src/archaeogpr/gui/main_window.py`
- [[02_SPRINTS/Sprint_GUI_2_Display_Controls]]
- [[06_DECISIONS/ADR_001_OpenGPR_Internal_Data_Model]] (the immutability
  guarantee this ADR extends to display state)
- [[06_DECISIONS/ADR_011_GUI_Technology_Decision]]
- [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]]
