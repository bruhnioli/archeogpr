# archaeogpr

Read, validate, and quality-control OpenGPR (`.ogpr`) ground-penetrating radar
files produced by IDS GeoRadar systems, as a foundation for future
archaeological GPR visualization.

**Parser scope:** validated against the observed IDS GeoRadar/IQMaps OpenGPR
2.0 variant represented by `Swath003_Array02.ogpr`. This is *not* a claim
that every OpenGPR file is supported — see
[Parser scope and limitations](#parser-scope-and-limitations).

**Implemented so far (Sprint 1 + Sprint 2):** file reading, data modeling,
header/metadata validation, basic QC outputs (plots, CSV, JSON, NPZ),
time-zero correction, and DC offset correction. No other signal processing
is implemented yet — see [Not yet implemented](#not-yet-implemented).

## Installation

Requires Python 3.11+.

```bash
cd archaeogpr
python -m venv .venv
source .venv/Scripts/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Core runtime dependencies: `numpy`, `pandas`, `matplotlib`, `pytest`.
Optional dev dependencies (`.[dev]`): `ruff`, `mypy`.

## Sample data

Place a real `.ogpr` file (e.g. `Swath003_Array02.ogpr`) under `data/raw/`.
This directory is **read-only input** — see [Raw data safety](#raw-data-safety) below.
If no real file is present, unit tests still run in full using a synthetic
in-memory fixture; only the real-file integration test is skipped.

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
```

Tracebacks are hidden by default on error; pass `--debug` (before the
subcommand) to see the full traceback.

**Important:** `--max-shift-samples` (default 64) clips — and warns about —
any channel shift that exceeds it; it is never applied silently. On the real
sample file, the default combination of `--target-sample 0` and
`--max-shift-samples 64` clips most channels (their true shift is ~61–74
samples). Raise `--max-shift-samples` if you need every channel to land
exactly on `--target-sample`.

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
`test_dc_offset.py`, `test_processing_history.py`) use synthetic in-memory
fixtures and always run. `test_real_ogpr_integration.py` and
`test_sprint2_real_integration.py` run only if
`data/raw/Swath003_Array02.ogpr` is present, and otherwise skip cleanly
(not a failure).

## Implementation status

**Implemented (Sprint 1 + Sprint 2):** file reading (`io/`), the immutable
data model (`model/`), metadata/QC derivation and plots (`qc/`), basic
exports (`export/basic.py`), time-zero correction and DC offset correction
(`processing/`, `export/processed.py`), and the CLI. See
`obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_01_OpenGPR_Infrastructure.md`
and `.../Sprint_02_TimeZero_DCOffset.md` for the full sprint records.

## Not yet implemented

None of the following are implemented. No placeholder, partial, or
fake-working code exists for them:

dewow, band-pass filtering, background removal, gain, AGC, F-K filtering,
velocity analysis, migration, Hilbert envelope, depth slices, anomaly
detection, archaeological classification, Blender export, GIS export, GUI,
trace-by-trace (per-trace-independent) automatic time-zero warping,
sub-sample shifting.

See `05_PROCESSING/` in the Obsidian vault for their planned (not
implemented) API shape.

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
