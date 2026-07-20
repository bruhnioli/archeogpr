# archaeogpr

[![CI](https://github.com/bruhnioli/archeogpr/actions/workflows/ci.yml/badge.svg)](https://github.com/bruhnioli/archeogpr/actions/workflows/ci.yml)

Read, validate, and quality-control OpenGPR (`.ogpr`) ground-penetrating radar
files produced by IDS GeoRadar systems, as a foundation for future
archaeological GPR visualization.

**Parser scope:** validated against the observed IDS GeoRadar/IQMaps OpenGPR
2.0 variant represented by `Swath003_Array02.ogpr`. This is *not* a claim
that every OpenGPR file is supported — see
[Parser scope and limitations](#parser-scope-and-limitations).

**Implemented so far (Sprint 1 – Sprint 4A):** file reading,
data modeling, header/metadata validation, basic QC outputs (plots, CSV,
JSON, NPZ), time-zero correction, DC offset correction, dewow,
zero-phase band-pass filtering, and background removal. For the validated
sample dataset (`Swath003_Array02.ogpr`), a **canonical processing chain
has been selected by human/geophysical review**: Sprint 2 canonical
(`target_sample=16`) → **D2** dewow → **B1** band-pass — see
[Canonical Sprint 3 selection (D2 + B1)](#canonical-sprint-3-selection-d2--b1)
below. **Background-removal algorithms are implemented as Sprint 4A
candidates, but no candidate has been selected as canonical** — see
[Sprint 4A background-removal candidates](#sprint-4a-background-removal-candidates)
below. No archaeological interpretation, gain, F-K filtering, velocity
analysis, or migration is implemented yet — see
[Not yet implemented](#not-yet-implemented).

## Installation

Requires Python 3.11+.

```bash
cd archaeogpr
python -m venv .venv
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Core runtime dependencies: `numpy`, `pandas`, `matplotlib`, `scipy`, `pyyaml`.
Optional dev dependencies (`.[dev]`): `ruff`, `mypy`, `pytest` — **no Qt
dependency**, so a broken/absent GUI environment can never take down
headless `pytest` (see
[ADR-012](obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime.md)).

**GUI/packaging extras** (see
[GUI (native Windows desktop viewer)](#gui-native-windows-desktop-viewer)
below):

| Use case | Command | Pulls in |
|---|---|---|
| Headless processing (no GUI) | `pip install -e .` | numpy/pandas/matplotlib/scipy/pyyaml only |
| 2D GUI runtime | `pip install -e ".[gui]"` | + PySide6, pyqtgraph |
| GUI development + tests | `pip install -e ".[dev,gui-test]"` | + `dev` + PySide6, pyqtgraph, pytest-qt |
| Full 2D + 3D GUI runtime | `pip install -e ".[gui3d]"` | + pyvista, pyvistaqt (self-contained — does not require `.[gui]` separately) |
| Windows executable build | `pip install -e ".[dev,gui-test,packaging]"` | + PyInstaller |

**Important:** on Windows, use a **python.org CPython 3.12/3.13 x64**
interpreter for any `gui`/`gui-test`/`gui3d`/`packaging` install — not
Anaconda, Miniconda, or the Microsoft Store Python. This project hit a
`PySide6.QtCore` DLL-loading failure specifically under an Anaconda-based
interpreter; a python.org CPython venv with the identical PySide6 wheel
worked on the first try. See
[ADR-012](obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime.md)
for the full investigation. Core (`dev`-only) work is unaffected by this —
any interpreter satisfying `requires-python = ">=3.11"` works fine.

Core testing splits by marker: `pytest -m "not gui"` (no Qt needed) vs.
`pytest -m gui` (needs `gui-test`, run with
`QT_QPA_PLATFORM=offscreen` for a headless machine/CI).

## Sample data

Place a real `.ogpr` file (e.g. `Swath003_Array02.ogpr`) under `data/raw/`.
This directory is **read-only input** — see [Raw data safety](#raw-data-safety) below,
and is excluded from version control (`.gitignore`) since raw radar data is
user-supplied and may be large or proprietary. If no real file is present,
unit tests still run in full using synthetic in-memory fixtures; only the
real-file integration tests skip cleanly.

## CLI usage

```bash
# Read a file and generate every QC output into --output-dir
python -m archaeogpr inspect data/raw/Swath003_Array02.ogpr --output-dir outputs/inspect

# Optional flags
python -m archaeogpr inspect data/raw/Swath003_Array02.ogpr \
  --output-dir outputs/inspect \
  --channel 0 \
  --clip-percentile 99 \
  --cmap seismic

# Print a readable header summary without generating any output files
python -m archaeogpr header data/raw/Swath003_Array02.ogpr

# Time-zero correction (channel-wide, constant shift per channel)
python -m archaeogpr time-zero data/raw/Swath003_Array02.ogpr \
  --output-dir outputs/sprint02/time_zero \
  --method channel-median-peak --search-start-ns 5 --search-end-ns 15 \
  --peak-polarity max-abs --target-sample 0

# Time-zero correction from a verified manual pick file (one sample index per channel)
python -m archaeogpr time-zero data/raw/Swath003_Array02.ogpr \
  --output-dir outputs/sprint02/time_zero_manual \
  --method manual --picks-file configs/time_zero_picks.json --target-sample 0

# DC offset correction (per-trace, independent per slice/channel)
python -m archaeogpr dc-offset data/raw/Swath003_Array02.ogpr \
  --output-dir outputs/sprint02/dc_offset --method mean

# Combined pipeline: time-zero, then DC offset, in that fixed order
python -m archaeogpr sprint2 data/raw/Swath003_Array02.ogpr \
  --output-dir outputs/sprint02/combined \
  --time-zero-method channel-median-peak --search-start-ns 5 --search-end-ns 15 \
  --peak-polarity max-abs --target-sample 0 --dc-method mean

# Dewow (moving-window baseline removal) on a Sprint 2/3-style processed NPZ.
# Never marks a run canonical -- for experimentation/comparison only.
python -m archaeogpr dewow outputs/sprint02/canonical_target16/sprint02_processed.npz \
  --output-dir outputs/sprint03/dewow_manual --window-ns 8.0 --method running-mean

# Zero-phase band-pass filtering. Never marks a run canonical.
python -m archaeogpr bandpass outputs/sprint03/dewow_manual/dewow_processed.npz \
  --output-dir outputs/sprint03/bandpass_manual --method butterworth \
  --lowcut-mhz 100 --highcut-mhz 900 --order 4

# Run every dewow/band-pass/combined candidate + QC comparisons (configs/*.yaml).
# Selects nothing canonical -- produces comparison evidence only.
python -m archaeogpr sprint3-candidates outputs/sprint02/canonical_target16/sprint02_processed.npz \
  --output-dir outputs/sprint03

# The CANONICAL Sprint 3 chain: D2 dewow + B1 band-pass, selected by
# human/geophysical review (see "Canonical Sprint 3 selection" below).
# The flags shown here ARE the canonical defaults -- omitting them applies
# the same D2+B1 parameters. Overriding any of them prints
# "canonical selected: false" plus an explicit warning.
python -m archaeogpr sprint3 outputs/sprint02/canonical_target16/sprint02_processed.npz \
  --output-dir outputs/sprint03/canonical_D2_B1 \
  --dewow-method running-mean --dewow-window-ns 8 --dewow-edge-mode reflect \
  --bandpass-method butterworth --lowcut-mhz 100 --highcut-mhz 900 --order 4 --zero-phase

# Background removal on the canonical Sprint 3 (D2+B1) output. Never marks
# a run canonical -- for experimentation/comparison only.
python -m archaeogpr background outputs/sprint03/canonical_D2_B1/sprint03_processed.npz \
  --output-dir outputs/sprint04a/manual_background \
  --method sliding-median --window-m 1.0 --edge-mode reflect

# Run all 8 background-removal candidates (A1-A8, configs/background_candidates.yaml)
# + QC comparisons + decision panel. Selects nothing canonical -- see
# "Sprint 4A background-removal candidates" below.
python -m archaeogpr sprint4a-candidates outputs/sprint03/canonical_D2_B1/sprint03_processed.npz \
  --output-dir outputs/sprint04a
```

Tracebacks are hidden by default on error; pass `--debug` (before the
subcommand) to see the full traceback.

**Important:** `--max-shift-samples` (default 64) does **not** clip by
default. The default `--overflow-policy error` **aborts before touching
any data** if a channel's shift exceeds `--max-shift-samples` — no output
is written. Clipping only happens with the explicit opt-in
`--overflow-policy clip`, and a clipped result is marked
`valid_for_downstream_processing=false` in its diagnostics; it must never
be treated as canonical without explicit human review. On the real sample
file, the combination of `--target-sample 0` and `--max-shift-samples 64`
exceeds the limit on most channels (their true shift is ~61–74 samples) —
raise `--max-shift-samples` (e.g. to 96) if you need every channel to land
exactly on `--target-sample` without hitting the error/clip decision at
all. See [`ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset`](obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_003_Overflow_Policy_and_Padding_Aware_DC_Offset.md)
for the full policy.

## Generated outputs

`inspect` writes the following into `--output-dir` (default `outputs/inspect/`),
using the input file's stem as a prefix:

| File | Contents |
|---|---|
| `<stem>_metadata.json` | Source facts (dimensions, dtype, sampling, frequency, polarization, velocity, spatial reference) + derived QC figures (time window, depth estimate, geometry stats, amplitude stats) + warnings |
| `<stem>_header.json` | The full raw JSON header, plus magic/checksum/header size |
| `<stem>_geolocation.csv` | One row per (slice, channel): `x_top, y_top, depth_top_m, elevation_top_m, x_bottom, y_bottom, depth_bottom_m, elevation_bottom_m` — omitted if the file has no geolocation block |
| `<stem>_channel00_bscan.png` | Single-channel B-scan, symmetric zero-centered color scale, percentile-clipped for display only |
| `<stem>_all_channels.png` | All channels as small QC panels (not for quantitative use) |
| `<stem>_survey_geometry.png` | Plan-view (x, y) line per channel, equal-aspect axes, start/end markers — omitted if no geolocation |
| `radar_volume.npz` | Compressed `amplitudes`, `time_ns`, `metadata_json`, `has_geolocation`, and (if present) `x`/`y`/`elevation_top_m` |

`time-zero`/`dc-offset`/`sprint2` write into their own `--output-dir`
(default `outputs/sprint02/...`), never into `outputs/inspect/` or
`data/raw/`:

| File | Contents |
|---|---|
| `channel_picks.csv` | One row per channel: picked/target sample, shift (samples & ns), method, clip warning |
| `offsets.csv` | One row per (slice, channel): removed DC offset, method, window |
| `channel_median_traces_{before,after,overlay}.png` | Per-channel median trace with pick/target markers (time-zero only) |
| `channel00_{before,after,difference}.png` | Same-scale before/after B-scan + a separately-scaled difference |
| `all_channels_{before,after}.png` | Per-channel-clipped grid, before vs. after (time-zero only) |
| `picks_and_shifts.png` | Bar chart of picked sample and applied shift per channel (time-zero only) |
| `trace_offset_histogram.png`, `trace_means_before_after.png`, `channel_offset_statistics.png` | DC offset distribution QC |
| `processing_metadata.json` | That stage's own `processing_history` entry (operation, parameters, diagnostics, warnings) |
| `time_zero_corrected.npz` / `dc_offset_corrected.npz` | That stage's corrected `amplitudes` + `removed_component` + full history |
| `sprint02_processed.npz`, `processing_history.json`, `sprint02_summary.json` | Combined-pipeline final dataset, full history, and a compact summary (`sprint2` only) |

`dewow`/`bandpass`/`sprint3-candidates`/`sprint3` write into their own
`--output-dir` (default `outputs/sprint03/...`):

| File | Contents |
|---|---|
| `{dewow,bandpass,sprint03}_processed.npz` | That stage's corrected `amplitudes` + `removed_component` + full `processing_history` |
| `channel00_{raw,after,before,removed,difference}.png`, `all_channels_final.png` | Before/after/removed-component B-scans |
| `spectrum_before_after.png`, `transfer_function.png` | Amplitude-spectrum QC and (band-pass) the filter's own transfer function |
| `padding_verification.json` | Machine-readable proof padding was never touched and `removed_component` is exactly zero there |
| `phase_verification.json` | Zero-phase proof (median-trace cross-correlation lag; canonical `sprint3` output only) |
| `processing_metadata.json`, `processing_history.json` | That stage's diagnostics and the dataset's full processing history |
| `canonical_parameters.json`, `CANONICAL_PROCESSING_NOTE.md` | Selection authority, D2/B1 rationale, dataset scope (canonical `sprint3` output only) |

`sprint3-candidates` additionally writes one such set per D1–D4/B1–B4/C1–C6
candidate under its own subfolder, plus a `comparison/*_REVIEW_REQUIRED.md`
per family and a top-level `SPRINT3_REVIEW_REQUIRED.md` — see
[Canonical Sprint 3 selection](#canonical-sprint-3-selection-d2--b1).

`background`/`sprint4a-candidates` write into their own `--output-dir`
(default `outputs/sprint04a/...`):

| File | Contents |
|---|---|
| `background_processed.npz` | Background-removed `amplitudes` + `removed_component` + full `processing_history` |
| `channel00_{before,after,removed,difference}.png`, `channel{05,10}_before_after_removed.png`, `all_channels_after.png` | Before/after/removed-component B-scans |
| `median_trace_before_after.png`, `removed_component_median_trace.png`, `removed_component_spectrum.png` | Median-trace and spectral QC of the removed component |
| `signal_preservation_metrics.json`, `removed_component_metrics.json` | Per-time-window waveform/RMS/spectral retention and removed-component energy/coherence/localized-event-risk metrics |
| `trace_spacing_and_window.json` | Requested vs. applied window (traces/metres), trace-spacing source (`geolocation`/`metadata_sampling_step`/`unavailable`) — never a hardcoded constant |
| `padding_verification.json`, `processing_metadata.json`, `processing_history.json` | Same contract as the Sprint 3 files above |
| `candidate_validation.json` | Machine-readable acceptance checklist (shape/dtype/padding/hash/canonical=false/gain_applied=false) |

`sprint4a-candidates` additionally writes one such set per A1–A8 candidate
under its own subfolder, plus `comparison/` (cross-candidate PNGs/CSVs +
synthetic risk-experiment outputs + `BACKGROUND_REVIEW_REQUIRED.md`) and
two top-level files, `BACKGROUND_DECISION_PANEL.png` (+ `_DETAIL.png`) and
`BACKGROUND_FINAL_DECISION_REQUIRED.md` — see
[Sprint 4A background-removal candidates](#sprint-4a-background-removal-candidates).

## Canonical Sprint 3 selection (D2 + B1)

Sprint 3 produced four dewow candidates (D1–D4) and four band-pass
candidates (B1–B4); nothing in that comparison code path is ever marked
canonical automatically. For the validated sample dataset
(`Swath003_Array02.ogpr`), the human/geophysical reviewer selected:

- **D2** dewow — `running_mean`, requested `8.0 ns` → applied `8.125 ns`
  (65 samples), `edge_mode=reflect`.
- **B1** band-pass — Butterworth, `100–900 MHz`, `order=4`, zero-phase.

This selection is encoded as fixed, named parameters in
`src/archaeogpr/sprint3_canonical.py` (`run_sprint3_canonical()`), which
calls the same `correct_dewow()`/`correct_bandpass()` used everywhere
else — **no new filtering algorithm was introduced to make this
canonical**. Run it with `python -m archaeogpr sprint3` (see
[CLI usage](#cli-usage)); the canonical output lives in
`outputs/sprint03/canonical_D2_B1/` and includes
`CANONICAL_PROCESSING_NOTE.md`, documenting the rationale, that B1 is the
preservation-favoring choice over B2, and that the energy B1 retains in
the 800–900 MHz band has **no confirmed archaeological interpretation**.

**This selection is scoped to `Swath003_Array02.ogpr` only.** A different
dataset or acquisition setting requires its own Sprint-3-style candidate
comparison and its own human/geophysical review before any parameters may
be treated as canonical for it — see
`obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_007_Canonical_D2_B1_Selection.md`.

## Sprint 4A background-removal candidates

**Sprint 4A status: `review_required`.** Background removal (`processing/background.py`, `remove_background()`) is
implemented as four methods — `global_mean`, `global_median`,
`sliding_mean`, `sliding_median` — computed independently per channel
(channels are never merged into one background). Sprint 4A ran eight
candidates (A1–A8: 2 global + 6 sliding at 0.5/1.0/1.5 m windows) on the
canonical Sprint 3 (D2+B1) output and produced full signal-preservation
and removed-component QC for each. **This is, by a wide margin, the most
scientifically risky filter this project has implemented**: a
moving-average/median estimate along the trace axis cannot, on its own,
distinguish an unwanted common-mode component from a genuinely long,
laterally continuous archaeological reflection.

**Background-removal algorithms are implemented as Sprint 4A candidates,
but no candidate has been selected as canonical.** Run
`python -m archaeogpr sprint4a-candidates` (see [CLI usage](#cli-usage))
to reproduce all 8 candidates; the output lives in `outputs/sprint04a/`
and includes `BACKGROUND_DECISION_PANEL.png` and
`BACKGROUND_FINAL_DECISION_REQUIRED.md`, both explicitly requiring
human/geophysical review before any candidate is used for anything beyond
QC comparison. On this dataset, every candidate's removed component shows
high spatial coherence (adjacent-trace correlation 0.83–1.0) — a risk
signal reported transparently, not a basis for automatic selection.

**Gain has not been started** — see [Not yet implemented](#not-yet-implemented).
Full rationale: `obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_008_Background_Removal_Channelwise_and_Window_Policy.md`.

## Radar array axis order

`GPRDataset.amplitudes` is always `(slice, channel, sample)`. This is fixed
and documented in `metadata["dimensions"]["axis_order"]` on every dataset.

## Raw data safety

- Files under `data/raw/` (or any path you pass to the CLI) are treated as
  **read-only**. The reader only ever opens files in `"rb"` mode.
- Every byte offset, byte size, and value type used to decode a binary block
  is read from the file's own JSON header descriptors — never hardcoded.
- `GPRDataset` arrays are copied and marked non-writable on construction;
  in-place mutation (e.g. `dataset.amplitudes[0] = 0`) raises `ValueError`.
- All outputs are written under the directory you pass to `--output-dir`
  (default `outputs/`) — never next to the source file, and never under
  `data/raw/`.
- Processing functions (`correct_time_zero`, `correct_dc_offset`) never
  mutate their input `GPRDataset`; they return a new one via
  `ProcessingResult.dataset`. Raw exports (`outputs/inspect/`) and processed
  exports (`outputs/sprint02/`) live in separate directories.
- `data/raw/*.ogpr` is excluded from version control via `.gitignore`.

## Automatic time-zero picks are not calibrated physical times

`time-zero`'s automatic methods (`channel-median-peak`,
`channel-median-cross-correlation`) select a **signal-processing
reference** — the extremum of a median trace, or its alignment to another
channel. This is not the same as an independently, field-calibrated
physical surface time. Every result carries this warning verbatim:

> Automatic time-zero picks are signal-processing references and are not
> independently calibrated physical surface times.

Use `--method manual --picks-file <picks.json>` to apply picks a
geophysicist has actually verified.

## Spatial reference warning

If present, the source file's spatial reference (e.g. an EPSG code) is
carried into `metadata["spatial_reference"]` **as-is**. It is never validated
against ground truth and no reprojection is ever performed. Every QC output
that shows coordinates says so explicitly ("coordinate values shown as
stored; CRS not validated").

## Depth is a metadata-velocity estimate, not a measurement

Any depth or max-depth figure (`derive_metadata()["depth_estimate"]`) is
computed from the file's own metadata propagation velocity assumption
(`velocity_m_per_ns * sampling_time_ns / 2`), not from a validated subsurface
velocity model. Treat it as an approximation only — see
`depth_estimate["basis"]` in the metadata JSON.

## Parser scope and limitations

The `.ogpr` binary/header format is **not independently documented**. This
reader was built and validated directly against one real file,
`Swath003_Array02.ogpr` (an IDS GeoRadar/IQMaps OpenGPR **2.0** export), by
reading its bytes and cross-checking every field. It is *validated against
the observed IDS GeoRadar/IQMaps OpenGPR 2.0 variant represented by
`Swath003_Array02.ogpr`* — it does **not** claim to support every OpenGPR
file. In particular:

- Every byte offset/size/value type is read from that file's own header
  descriptors at runtime (never hardcoded), so a differently-sized file of
  the *same* format should still parse correctly.
- The `Sample Geolocations` block's internal record layout has **no
  per-field description anywhere in the header** — it was reverse-engineered
  from the observed IDS variant and is only cross-checked by total byte
  size. A file whose geolocation block uses a different layout will raise
  `InvalidGeolocationBlockError` rather than being silently misread.

## Running tests

```bash
pytest
```

Unit tests (`test_ogpr_reader.py`, `test_data_model.py`, `test_time_zero.py`,
`test_dc_offset.py`, `test_dewow.py`, `test_bandpass.py`, `test_spectrum.py`,
`test_sprint3_pipeline.py`, `test_sprint3_1_decision_qc.py`,
`test_sprint3_canonical.py`, `test_cli_sprint3_canonical.py`,
`test_background.py`, `test_background_qc.py`, `test_sprint4a_pipeline.py`,
`test_processing_history.py`, `test_target_invariance.py`,
`test_export_processed.py`) use synthetic in-memory fixtures and always
run. `test_real_ogpr_integration.py`, `test_sprint2_real_integration.py`,
`test_sprint3_real_integration.py`, `test_sprint3_canonical.py`,
`test_cli_sprint3_canonical.py`, and `test_sprint4a_real_integration.py`
also include real-file checks that run only if
`data/raw/Swath003_Array02.ogpr` is present, and otherwise skip cleanly
(not a failure) — this is why CI (see badge above) is expected to show
these real-file cases as **skipped**, since the raw sample file is
intentionally excluded from version control.

Also run as part of CI:

```bash
ruff format --check .
ruff check .
mypy src/archaeogpr
python scripts/validate_obsidian_vault.py obsidian/ArchaeoGPR_Vault
```

## Implementation status

**Implemented (Sprint 1 – Sprint 4A):** file reading
(`io/`), the immutable data model (`model/`), metadata/QC derivation and
plots (`qc/`), basic exports (`export/basic.py`), time-zero correction and
DC offset correction (`processing/time_zero.py`, `processing/dc_offset.py`),
dewow (`processing/dewow.py`), zero-phase band-pass filtering
(`processing/bandpass.py`), amplitude-spectrum QC (`qc/spectrum.py`),
candidate-comparison orchestration (`sprint3_candidates.py` — never marks
anything canonical), the canonical D2+B1 Sprint 3 chain
(`sprint3_canonical.py`, human/geophysical selection — see
[Canonical Sprint 3 selection](#canonical-sprint-3-selection-d2--b1)),
background removal (`processing/background.py`, four methods, 8 Sprint 4A
candidates — see
[Sprint 4A background-removal candidates](#sprint-4a-background-removal-candidates),
**no candidate canonical**), and the CLI. See
`obsidian/ArchaeoGPR_Vault/02_SPRINTS/` for the full sprint records and
`06_DECISIONS/ADR_001..008` for the architectural decisions behind each
of them.

## GUI (native Windows desktop viewer)

**ArchaeoGPR now has a native PySide6 Windows desktop viewer** (Sprint
GUI-1, 2026-07-17; display controls added in Sprint GUI-2; background file
loading added in Sprint GUI-1B; non-destructive processing preview & apply
added in Sprint GUI-3A; survey geometry inspector and C-scan readiness
added in Sprint 3D-0; actual X/Y point-grid C-scan/time-slice viewer added
in Sprint 3D-1; current version `0.5.0`) alongside the CLI — a
real Windows application, not a webpage: it never opens a browser tab,
never listens on `localhost`, and never uses
Flask/FastAPI/Streamlit/Dash/Electron. **Processing is preview-only, never
destructive** — see [Not yet implemented](#not-yet-implemented) and
[obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply.md](obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply.md)
for exactly what this does and does not include: no gain, no undo/redo
stack, no recipe system, no processed-dataset save, no 3D. Those remain
planned for later, separately-requested sprints (see
[obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/Processing_Preview_and_Commit_Model.md](obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/Processing_Preview_and_Commit_Model.md)).

**Sprint 3D-0 (`0.4.0`) survey geometry inspector and C-scan readiness** —
a new Qt-free `archaeogpr.geometry` package
(`models.py`/`resolve.py`/`validation.py`/`export.py`/`summary.py`/
`regularity.py`) scientifically audits trace/channel geometry and
classifies every resolved field's provenance (`FILE_METADATA`/`DERIVED`/
`USER_SUPPLIED`/`INDEX_SPACE`/`MISSING`) instead of guessing spacing,
origin, azimuth, or CRS. A new "Survey Geometry" dock shows this
provenance plus seven structured readiness gates (`index_view_ready`,
`local_parameter_grid_ready`, `rectilinear_cscan_ready`,
`actual_xy_point_grid_ready`, `global_cscan_ready`, `time_volume_ready`,
and `depth_volume_ready` — always `False` this sprint, since no
velocity-confirmation flow exists yet), an override form (spacing,
origin, azimuth, channel direction, CRS) that only takes effect on
explicit **Apply Geometry**, and a new **Plan View** dock (2D acquisition
footprint, one vectorized PyQtGraph scatter item, bidirectionally synced
with the B-scan/A-scan trace/channel selection). **This sprint does not
render a volume or an amplitude C-scan** — no PyVista, no VTK, no
gridding/resampling, no depth conversion. See
[ADR-016](obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates.md)
and
[obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector.md](obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector.md).

**Sprint 3D-1 (`0.5.0`) actual X/Y point-grid C-scan and time-slice
viewer** — a new Qt-free `archaeogpr.cscan` package
(`models.py`/`compute.py`/`validation.py`/`export.py`) computes a single
`(trace_count, channel_count)` C-scan value grid from one time sample or
a half-open time window, using one of four aggregations (`Single sample`
— the only signed one; `RMS`/`Mean absolute`/`Maximum absolute` — all
non-negative by construction, since a signed window mean could cancel
positive/negative half-cycles toward a falsely small value directly over
a real reflection). A new "C-scan / Time Slice" dock renders that grid on
either the survey's **actual X/Y point grid** (default, explicitly
labeled "no interpolation") or an idealized **derived s/c parameter
grid** (clearly labeled, never conflated with the first) — the two are
never resampled into or substituted for each other. Raw/Current/Preview
sources are all supported, trace/channel/time selection stays
synchronized across the B-scan/A-scan/Plan View/C-scan, and a stale C-scan
result (from a since-applied processing or geometry change) is labeled
rather than silently discarded. **This sprint performs no spatial
interpolation, IDW, kriging, Delaunay gridding, or raster resampling of
any kind, and renders no volume** — no PyVista, no VTK, no isosurfaces, no
depth conversion. See
[ADR-017](obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_017_Actual_XY_CScan_and_No_Interpolation_Policy.md)
and
[obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan.md](obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan.md).

**Sprint GUI-3A (`0.3.0`) non-destructive processing preview & apply** —
five already-stable, already-tested `processing/*.py` functions
(time-zero correction, DC offset correction, dewow, band-pass filtering,
background removal) can now be run from a Processing dock: **Preview**
computes a result on a background thread without touching the displayed
dataset; **Apply Preview** atomically commits it only when the user
explicitly asks; **Discard Preview** and **Reset Current to Raw** are
always available. A raw/current/preview split
(`archaeogpr.gui.models.dataset_session.DatasetSession`) keeps the
original file's data untouched no matter how many operations are
previewed or applied. See
[ADR-015](obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply.md).

**Sprint GUI-1B (`0.2.1`) responsive file loading** — opening a `.ogpr`
file no longer freezes the window: the read happens on a background
`QThread` (see
[ADR-014](obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy.md)),
with a progress indicator, a Cancel button, and a strict guarantee that a
cancelled or failed load never touches the currently-displayed dataset.
File loading and processing preview are mutually exclusive (neither can
start while the other is running).

**Sprint GUI-2 (`0.2.0`) display features** — every one of these only
changes how the same, unmodified `dataset.amplitudes` is *rendered*; none
of them can write to the dataset (see
[ADR-013](obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization.md)):

- **Contrast controls**: percentile clipping (90.0-100.0%, default 99.0%,
  spinbox + slider), symmetric-around-zero or asymmetric (robust two-sided)
  auto levels, manual min/max override (an invalid range is never applied
  to the display — it falls back to the automatic levels and is flagged in
  the UI), and an optional "auto-scale from visible time range" mode.
- **Colormap**: Gray or Seismic (sampled directly from matplotlib's own
  colormaps, so it matches the existing QC PNG exports pixel-for-pixel).
- **A-scan display modes**: Full amplitude (raw), Robust autoscale (the
  curve is identical to Full — only the axis range changes), Normalize for
  display (a separate, display-only copy — the source trace is never
  modified; the axis is explicitly labeled "display only").
- **Selected trace**: a spin box synced with clicking the B-scan (0 to
  `trace_count - 1`), a brighter/thicker marker line, and a status bar that
  clearly separates the persistently *selected* trace from the transient
  *cursor-hover* readout.
- **Metadata panel**: the Value column now stretches with the window,
  every cell has a full-text tooltip, and a right-click menu copies a
  field/value/row/source path.
- **PNG export**: File → Export Current B-scan PNG... renders exactly
  what's on screen (current channel/colormap/levels) plus a
  `<name>.display.json` sidecar recording the display settings used —
  explicitly marked as a display export, never a processing export.

**Run in development** (after `pip install -e ".[dev,gui-test]"`, from a
python.org CPython venv — see [Installation](#installation)):

```bash
python -m archaeogpr.gui
python -m archaeogpr.gui --open data/raw/Swath003_Array02.ogpr
```

**Build the Windows executable** (see
[obsidian/ArchaeoGPR_Vault/09_REFERENCES/Windows_Executable_Build.md](obsidian/ArchaeoGPR_Vault/09_REFERENCES/Windows_Executable_Build.md)
for full detail):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

This produces a one-folder, windowed (no console) build at:

```
dist\ArchaeoGPR\ArchaeoGPR.exe
```

**This is the file an end user double-clicks.** No Python install, no
terminal, and no virtual environment are needed on their machine — the
`_internal\` folder next to it bundles the Python runtime, Qt, and every
other dependency. **This build is unsigned** (a development build); Windows
SmartScreen may show an "unrecognized publisher" warning the first time it
runs — that is expected, not a bug, and this project does not attempt to
suppress or bypass it. A code-signing certificate should be evaluated
before any wider distribution.

Raw `.ogpr` files are opened read-only exactly as they are by the CLI (see
[Raw data safety](#raw-data-safety)) — the viewer never writes to the file
you open, verified by SHA-256 before/after in
[obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_1_Viewer_Shell.md](obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_1_Viewer_Shell.md),
[obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_2_Display_Controls.md](obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_2_Display_Controls.md),
[obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_1B_Background_Tasks.md](obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_1B_Background_Tasks.md),
[obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply.md](obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply.md),
and
[obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector.md](obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector.md),
and
[obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan.md](obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan.md) —
this holds regardless of how many processing operations are previewed or
applied in-memory, regardless of any geometry override staged or applied,
and regardless of how many C-scans are computed, viewed, or exported.

Architecture and design records:
`obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_011_GUI_Technology_Decision.md`,
`obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_012_GUI_Extras_Isolation_and_PythonOrg_Runtime.md`,
`obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization.md`,
`obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_014_GUI_Background_Worker_and_Cancellation_Policy.md`,
`obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_015_GUI_Processing_Preview_and_Atomic_Apply.md`,
`obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_016_Geometry_Provenance_and_Readiness_Gates.md`,
`obsidian/ArchaeoGPR_Vault/06_DECISIONS/ADR_017_Actual_XY_CScan_and_No_Interpolation_Policy.md`,
`obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/GUI_Architecture.md`,
`obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/3D_Volume_Data_Model.md`,
`obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/Processing_Preview_and_Commit_Model.md`,
`obsidian/ArchaeoGPR_Vault/09_REFERENCES/GPRPy_Reference_and_License_Notes.md`,
`obsidian/ArchaeoGPR_Vault/09_REFERENCES/Windows_Executable_Build.md`,
`obsidian/ArchaeoGPR_Vault/01_PROJECT_STATE/06_GUI_3D_Risk_Register.md`,
`obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_0_Foundation.md`,
`obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_1_Viewer_Shell.md`,
`obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_2_Display_Controls.md`,
`obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_1B_Background_Tasks.md`,
`obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_3A_Processing_Preview_Apply.md`,
`obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_3D_0_Survey_Geometry_Inspector.md`,
`obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_3D_1_Actual_XY_Point_Grid_CScan.md`.

The `io`, `model`, `processing`, `qc`, `export` packages and the CLI
documented above are **unchanged** by the GUI — it is a new consumer of
those existing, unmodified functions (via a thin adapter layer, see
ADR-015), not a rewrite of them.

## Not yet implemented

None of the following are implemented. No placeholder, partial, or
fake-working code exists for them:

gain, AGC, F-K filtering, velocity analysis, migration, Hilbert envelope,
depth slices, anomaly detection, archaeological classification, Blender
export, GIS export, trace-by-trace (per-trace-independent) automatic
time-zero warping, sub-sample shifting. **GUI**: a native Windows viewer
(B-scan/A-scan/metadata) with non-destructive processing preview & apply
(time-zero/DC offset/dewow/band-pass/background removal), a survey
geometry inspector with C-scan/3D readiness reporting (index/local/global
coordinate resolution, per-field provenance, a 2D acquisition footprint
plan view, a geometry report JSON export), and an actual amplitude C-scan/
time-slice viewer (time sample or half-open time window, four
aggregations, actual X/Y point-map or derived s/c parameter-grid
rendering, PNG+JSON export — see
[GUI (native Windows desktop viewer)](#gui-native-windows-desktop-viewer))
is implemented — but gain, an undo/redo stack, a recipe system, saving a
processed dataset to a file, and any spatial interpolation/gridding/
resampling or 3D volume rendering (PyVista/VTK, isosurfaces, depth
conversion) are not, and remain planned for later, separately-requested
sprints. Sprint 3D-1's C-scan is a per-(trace, channel) value grid on the
survey's own point positions, never a resampled/interpolated grid or a
volume — see
[obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/3D_Volume_Data_Model.md](obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/3D_Volume_Data_Model.md).

**Background-removal algorithms are implemented as Sprint 4A candidates,
but no candidate has been selected as canonical** — see
[Sprint 4A background-removal candidates](#sprint-4a-background-removal-candidates).

See `05_PROCESSING/` in the Obsidian vault for the planned (not
implemented) API shape of the modules above, and
`obsidian/ArchaeoGPR_Vault/01_PROJECT_STATE/02_Next_Development_Sprint.md`
for how a future sprint (e.g. Gain, or a canonical background-removal
selection) would be scoped — it is not started, and neither the D2+B1
canonical selection nor the Sprint 4A candidates above, by themselves,
start it.

## Obsidian Knowledge Base

Project documentation and development context are maintained in:

`obsidian/ArchaeoGPR_Vault/`

Open this directory as an Obsidian vault.

Start with:

- `00_HOME.md`
- `01_PROJECT_STATE/00_Claude_Context.md`
- `01_PROJECT_STATE/01_Current_Project_State.md`
- `01_PROJECT_STATE/02_Next_Development_Sprint.md`

The vault contains project status, sprint notes, architecture records,
dataset metadata, validation results and session logs.

The source code and automated tests remain the primary source of truth.
