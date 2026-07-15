"""Command-line interface for archaeogpr.

    python -m archaeogpr inspect data/raw/Swath003_Array02.ogpr --output-dir outputs/inspect
    python -m archaeogpr header data/raw/Swath003_Array02.ogpr
    python -m archaeogpr time-zero data/raw/Swath003_Array02.ogpr --output-dir outputs/sprint02/time_zero
    python -m archaeogpr dc-offset data/raw/Swath003_Array02.ogpr --output-dir outputs/sprint02/dc_offset
    python -m archaeogpr sprint2 data/raw/Swath003_Array02.ogpr --output-dir outputs/sprint02/combined
    python -m archaeogpr dewow outputs/sprint02/canonical_target16/sprint02_processed.npz \\
        --output-dir outputs/sprint03/dewow_manual --window-ns 8.0 --method running-mean
    python -m archaeogpr bandpass outputs/sprint03/dewow_manual/dewow_processed.npz \\
        --output-dir outputs/sprint03/bandpass_manual --method butterworth \\
        --lowcut-mhz 120 --highcut-mhz 800 --order 4
    python -m archaeogpr sprint3-candidates outputs/sprint02/canonical_target16/sprint02_processed.npz \\
        --output-dir outputs/sprint03
    python -m archaeogpr sprint3 outputs/sprint02/canonical_target16/sprint02_processed.npz \\
        --output-dir outputs/sprint03/canonical_D2_B1 \\
        --dewow-method running-mean --dewow-window-ns 8 --dewow-edge-mode reflect \\
        --bandpass-method butterworth --lowcut-mhz 100 --highcut-mhz 900 --order 4 --zero-phase

Tracebacks are hidden by default; pass --debug (before the subcommand) to see them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from archaeogpr.export.basic import (
    write_geolocation_csv,
    write_header_json,
    write_metadata_json,
    write_radar_volume_npz,
)
from archaeogpr.export.processed import (
    write_channel_picks_csv,
    write_combined_npz,
    write_corrected_npz,
    write_offsets_csv,
    write_processing_history_json,
    write_processing_metadata_json,
    write_relative_time_axis_csv,
    write_sprint2_summary_json,
    write_valid_sample_summary_json,
)
from archaeogpr.export.sprint3 import read_processed_npz, write_padding_verification_json
from archaeogpr.io.exceptions import OGPRError
from archaeogpr.io.ogpr_reader import read_ogpr, read_ogpr_header
from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing import ProcessingError, ProcessingResult, correct_dc_offset, correct_time_zero
from archaeogpr.processing.bandpass import correct_bandpass
from archaeogpr.processing.dewow import correct_dewow
from archaeogpr.qc.bandpass import save_bandpass_qc_suite
from archaeogpr.qc.bscan import (
    save_all_channels_bscan,
    save_bscan_comparison,
    save_channel_bscan,
    save_stage_differences,
)
from archaeogpr.qc.dc_offset import (
    save_channel_offset_statistics,
    save_offset_histogram,
    save_trace_means_before_after,
)
from archaeogpr.qc.dewow import save_dewow_qc_suite
from archaeogpr.qc.geometry import save_survey_geometry
from archaeogpr.qc.metadata import derive_metadata
from archaeogpr.qc.time_zero import save_channel_median_traces, save_padding_mask_plot, save_picks_and_shifts
from archaeogpr.sprint3_candidates import run_all_sprint3_candidates
from archaeogpr.sprint3_canonical import (
    SELECTION_AUTHORITY,
    run_sprint3_canonical,
    write_canonical_processing_note,
)

_TIME_ZERO_METHOD_CHOICES = ("manual", "channel-median-peak", "channel-median-cross-correlation")
_PEAK_POLARITY_CHOICES = ("max-abs", "positive-peak", "negative-peak")
_DC_METHOD_CHOICES = ("mean", "median")
_OVERFLOW_POLICY_CHOICES = ("error", "clip")
_WINDOW_REFERENCE_CHOICES = ("dataset-time", "sample-index")
_DEWOW_METHOD_CHOICES = ("running-mean", "running-median")
_EDGE_MODE_CHOICES = ("reflect", "nearest")
_BANDPASS_METHOD_CHOICES = ("butterworth", "ormsby")

#: Sprint 2.2 / ADR-004 canonical DC-offset window: far enough from the
#: direct-wave/time-zero event to give a target-sample-invariant DC bias
#: estimate. This is only the CLI's *default* for --dc-window-start-ns/
#: --dc-window-end-ns -- it is not embedded immutably in correct_dc_offset()
#: itself (whose own default remains "no window / full trace"), and it
#: remains fully overridable from the command line.
_CANONICAL_DC_WINDOW_START_NS = 20.0
_CANONICAL_DC_WINDOW_END_NS = 100.0


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _add_time_zero_arguments(parser: argparse.ArgumentParser, *, method_flag: str) -> None:
    parser.add_argument(
        method_flag,
        choices=_TIME_ZERO_METHOD_CHOICES,
        default="channel-median-peak",
        help="Time-zero detection method (default: channel-median-peak)",
    )
    parser.add_argument(
        "--picks-file",
        type=Path,
        default=None,
        help="JSON file of {channel: sample} picks, for method=manual",
    )
    parser.add_argument(
        "--search-start-ns", type=float, default=5.0, help="Search window start, ns (default: 5.0)"
    )
    parser.add_argument(
        "--search-end-ns", type=float, default=15.0, help="Search window end, ns (default: 15.0)"
    )
    parser.add_argument(
        "--target-sample", type=int, default=0, help="Sample index the picked event is moved to (default: 0)"
    )
    parser.add_argument(
        "--peak-polarity",
        choices=_PEAK_POLARITY_CHOICES,
        default="max-abs",
        help="Peak criterion for automatic methods (default: max-abs)",
    )
    parser.add_argument(
        "--reference-channel",
        type=int,
        default=0,
        help="Reference channel for cross-correlation (default: 0)",
    )
    parser.add_argument(
        "--max-shift-samples", type=int, default=64, help="Maximum allowed |shift| in samples (default: 64)"
    )
    parser.add_argument(
        "--fill-value",
        type=float,
        default=0.0,
        help="Fill value for the padded region after shifting (default: 0.0)",
    )
    parser.add_argument(
        "--overflow-policy",
        choices=_OVERFLOW_POLICY_CHOICES,
        default="error",
        help=(
            "'error' (default) aborts if a channel's shift exceeds --max-shift-samples; "
            "'clip' clips and marks the result valid_for_downstream_processing=false"
        ),
    )


def _resolve_time_zero_kwargs(
    *,
    method: str,
    picks_file: Path | None,
    search_start_ns: float,
    search_end_ns: float,
    target_sample: int,
    peak_polarity: str,
    reference_channel: int,
    max_shift_samples: int,
    fill_value: float,
    overflow_policy: str,
) -> dict[str, Any]:
    resolved_method = method.replace("-", "_")
    picks: dict[int, int] | None = None
    if resolved_method == "manual":
        if picks_file is None:
            raise ProcessingError("method=manual requires --picks-file")
        raw_picks = json.loads(Path(picks_file).read_text(encoding="utf-8"))
        picks = {int(channel): int(sample) for channel, sample in raw_picks.items()}
    return {
        "method": resolved_method,
        "picks": picks,
        "search_start_ns": search_start_ns,
        "search_end_ns": search_end_ns,
        "target_sample": target_sample,
        "peak_polarity": peak_polarity.replace("-", "_"),
        "reference_channel": reference_channel,
        "max_shift_samples": max_shift_samples,
        "fill_value": fill_value,
        "overflow_policy": overflow_policy,
    }


def _add_dc_offset_arguments(
    parser: argparse.ArgumentParser,
    *,
    method_flag: str,
    window_start_flag: str,
    window_end_flag: str,
    window_reference_flag: str,
) -> None:
    parser.add_argument(
        method_flag, choices=_DC_METHOD_CHOICES, default="mean", help="DC offset method (default: mean)"
    )
    parser.add_argument(
        window_start_flag,
        type=float,
        default=_CANONICAL_DC_WINDOW_START_NS,
        help=(
            f"Offset window start, ns (default: {_CANONICAL_DC_WINDOW_START_NS}, the canonical "
            "Sprint 2.2 policy -- see ADR-004). To use the full trace instead, pass explicit "
            "bounds wide enough to cover the whole time_ns range."
        ),
    )
    parser.add_argument(
        window_end_flag,
        type=float,
        default=_CANONICAL_DC_WINDOW_END_NS,
        help=(
            f"Offset window end, ns (default: {_CANONICAL_DC_WINDOW_END_NS}, the canonical Sprint 2.2 policy)"
        ),
    )
    parser.add_argument(
        window_reference_flag,
        choices=_WINDOW_REFERENCE_CHOICES,
        default="dataset-time",
        help=(
            "'dataset-time' (default) selects samples by dataset.time_ns itself, which makes "
            "the window target-sample-invariant after time-zero correction (see ADR-004); "
            "'sample-index' selects samples by literal round(ns/sampling_time_ns) from sample 0, "
            "ignoring dataset.time_ns (the pre-Sprint-2.2 behavior)"
        ),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archaeogpr", description="OpenGPR (.ogpr) reader and QC toolkit.")
    parser.add_argument("--debug", action="store_true", help="show full tracebacks on error")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Read an .ogpr file and generate QC outputs.")
    inspect_parser.add_argument("input", type=Path, help="Path to the .ogpr file")
    inspect_parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/inspect"), help="Directory for generated outputs"
    )
    inspect_parser.add_argument(
        "--channel", type=int, default=0, help="Channel index for the single-channel B-scan (default: 0)"
    )
    inspect_parser.add_argument(
        "--clip-percentile",
        type=float,
        default=99.0,
        help="Percentile for symmetric B-scan color clipping (default: 99)",
    )
    inspect_parser.add_argument(
        "--cmap",
        type=str,
        default="seismic",
        help="Matplotlib colormap for B-scan figures (default: seismic)",
    )

    header_parser = subparsers.add_parser(
        "header", help="Print a readable summary of an .ogpr file's header."
    )
    header_parser.add_argument("input", type=Path, help="Path to the .ogpr file")

    time_zero_parser = subparsers.add_parser(
        "time-zero", help="Run time-zero correction and generate QC outputs."
    )
    time_zero_parser.add_argument("input", type=Path, help="Path to the .ogpr file")
    time_zero_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/sprint02/time_zero"),
        help="Directory for generated outputs",
    )
    time_zero_parser.add_argument(
        "--channel", type=int, default=0, help="Channel for detailed B-scan QC (default: 0)"
    )
    time_zero_parser.add_argument(
        "--clip-percentile", type=float, default=99.0, help="B-scan color clip percentile"
    )
    time_zero_parser.add_argument(
        "--cmap", type=str, default="seismic", help="Matplotlib colormap for B-scan figures"
    )
    _add_time_zero_arguments(time_zero_parser, method_flag="--method")

    dc_offset_parser = subparsers.add_parser(
        "dc-offset", help="Run DC offset correction and generate QC outputs."
    )
    dc_offset_parser.add_argument("input", type=Path, help="Path to the .ogpr file")
    dc_offset_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/sprint02/dc_offset"),
        help="Directory for generated outputs",
    )
    dc_offset_parser.add_argument(
        "--channel", type=int, default=0, help="Channel for detailed B-scan QC (default: 0)"
    )
    dc_offset_parser.add_argument(
        "--clip-percentile", type=float, default=99.0, help="B-scan color clip percentile"
    )
    dc_offset_parser.add_argument(
        "--cmap", type=str, default="seismic", help="Matplotlib colormap for B-scan figures"
    )
    _add_dc_offset_arguments(
        dc_offset_parser,
        method_flag="--method",
        window_start_flag="--window-start-ns",
        window_end_flag="--window-end-ns",
        window_reference_flag="--window-reference",
    )

    sprint2_parser = subparsers.add_parser(
        "sprint2", help="Run time-zero then DC offset correction as one pipeline."
    )
    sprint2_parser.add_argument("input", type=Path, help="Path to the .ogpr file")
    sprint2_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/sprint02/combined"),
        help="Directory for generated outputs",
    )
    sprint2_parser.add_argument(
        "--channel", type=int, default=0, help="Channel for detailed B-scan QC (default: 0)"
    )
    sprint2_parser.add_argument(
        "--clip-percentile", type=float, default=99.0, help="B-scan color clip percentile"
    )
    sprint2_parser.add_argument(
        "--cmap", type=str, default="seismic", help="Matplotlib colormap for B-scan figures"
    )
    _add_time_zero_arguments(sprint2_parser, method_flag="--time-zero-method")
    _add_dc_offset_arguments(
        sprint2_parser,
        method_flag="--dc-method",
        window_start_flag="--dc-window-start-ns",
        window_end_flag="--dc-window-end-ns",
        window_reference_flag="--dc-window-reference",
    )

    dewow_parser = subparsers.add_parser(
        "dewow", help="Run dewow (moving-window baseline/wow removal) on a processed NPZ."
    )
    dewow_parser.add_argument("input", type=Path, help="Path to a Sprint 2/3-style processed NPZ")
    dewow_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/sprint03/dewow_manual"),
        help="Directory for generated outputs",
    )
    dewow_parser.add_argument("--channel", type=int, default=0, help="Channel for detailed QC (default: 0)")
    dewow_parser.add_argument(
        "--window-ns", type=float, default=8.0, help="Requested dewow window, ns (default: 8.0)"
    )
    dewow_parser.add_argument(
        "--method",
        choices=_DEWOW_METHOD_CHOICES,
        default="running-mean",
        help="Dewow method (default: running-mean). This CLI never marks a run canonical.",
    )
    dewow_parser.add_argument(
        "--edge-mode",
        choices=_EDGE_MODE_CHOICES,
        default="reflect",
        help="Edge handling at valid-segment boundaries (default: reflect)",
    )
    dewow_parser.add_argument(
        "--allow-repeat-processing",
        action="store_true",
        help="Allow re-applying dewow_correction if already present in the input's processing_history",
    )

    bandpass_parser = subparsers.add_parser(
        "bandpass", help="Run zero-phase band-pass filtering on a processed NPZ."
    )
    bandpass_parser.add_argument("input", type=Path, help="Path to a Sprint 2/3-style processed NPZ")
    bandpass_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/sprint03/bandpass_manual"),
        help="Directory for generated outputs",
    )
    bandpass_parser.add_argument(
        "--channel", type=int, default=0, help="Channel for detailed QC (default: 0)"
    )
    bandpass_parser.add_argument(
        "--method",
        choices=_BANDPASS_METHOD_CHOICES,
        default="butterworth",
        help="Band-pass method (default: butterworth). This CLI never marks a run canonical.",
    )
    bandpass_parser.add_argument("--lowcut-mhz", type=float, default=None, help="Butterworth low cutoff, MHz")
    bandpass_parser.add_argument(
        "--highcut-mhz", type=float, default=None, help="Butterworth high cutoff, MHz"
    )
    bandpass_parser.add_argument("--order", type=int, default=4, help="Butterworth filter order (default: 4)")
    bandpass_parser.add_argument(
        "--no-zero-phase",
        dest="zero_phase",
        action="store_false",
        help=(
            "Butterworth only: use a single causal sosfilt pass instead of zero-phase sosfiltfilt "
            "-- kept to demonstrate the phase-shift contrast, never for canonical use"
        ),
    )
    bandpass_parser.set_defaults(zero_phase=True)
    bandpass_parser.add_argument(
        "--ormsby-frequencies-mhz",
        type=float,
        nargs=4,
        default=None,
        metavar=("F1", "F2", "F3", "F4"),
        help="Ormsby corner frequencies f1<f2<f3<f4, MHz (method=ormsby only)",
    )
    bandpass_parser.add_argument(
        "--allow-repeat-processing",
        action="store_true",
        help="Allow re-applying bandpass_correction if already present in the input's processing_history",
    )

    sprint3_candidates_parser = subparsers.add_parser(
        "sprint3-candidates",
        help=(
            "Run all Sprint 3 dewow/band-pass/combined candidates and QC comparisons. "
            "Selects nothing canonical."
        ),
    )
    sprint3_candidates_parser.add_argument(
        "input", type=Path, help="Path to the Sprint 2 canonical processed NPZ"
    )
    sprint3_candidates_parser.add_argument(
        "--output-dir", type=Path, default=Path("outputs/sprint03"), help="Directory for generated outputs"
    )
    sprint3_candidates_parser.add_argument(
        "--dewow-config",
        type=Path,
        default=Path("configs/dewow_candidates.yaml"),
        help="Dewow candidates YAML config",
    )
    sprint3_candidates_parser.add_argument(
        "--bandpass-config",
        type=Path,
        default=Path("configs/bandpass_candidates.yaml"),
        help="Band-pass (and combined) candidates YAML config",
    )

    sprint3_parser = subparsers.add_parser(
        "sprint3",
        help=(
            "Run the CANONICAL Sprint 3 chain (D2 dewow + B1 band-pass, human/geophysical "
            "review selection). Defaults are the selected parameters; overriding them "
            "produces a non-canonical run."
        ),
    )
    sprint3_parser.add_argument("input", type=Path, help="Path to the Sprint 2 canonical processed NPZ")
    sprint3_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/sprint03/canonical_D2_B1"),
        help="Directory for generated outputs",
    )
    sprint3_parser.add_argument("--channel", type=int, default=0, help="Channel for B-scan QC (default: 0)")
    sprint3_parser.add_argument(
        "--clip-percentile", type=float, default=99.0, help="B-scan color clip percentile"
    )
    sprint3_parser.add_argument("--cmap", type=str, default="seismic", help="Matplotlib colormap for B-scans")
    sprint3_parser.add_argument(
        "--dewow-method",
        choices=_DEWOW_METHOD_CHOICES,
        default="running-mean",
        help="Dewow method (default: running-mean, the D2 selection)",
    )
    sprint3_parser.add_argument(
        "--dewow-window-ns", type=float, default=8.0, help="Requested dewow window, ns (default: 8.0, D2)"
    )
    sprint3_parser.add_argument(
        "--dewow-edge-mode",
        choices=_EDGE_MODE_CHOICES,
        default="reflect",
        help="Dewow edge mode (default: reflect, D2)",
    )
    sprint3_parser.add_argument(
        "--bandpass-method",
        choices=_BANDPASS_METHOD_CHOICES,
        default="butterworth",
        help="Band-pass method (default: butterworth, the B1 selection)",
    )
    sprint3_parser.add_argument(
        "--lowcut-mhz", type=float, default=100.0, help="Butterworth low cutoff, MHz (default: 100.0, B1)"
    )
    sprint3_parser.add_argument(
        "--highcut-mhz", type=float, default=900.0, help="Butterworth high cutoff, MHz (default: 900.0, B1)"
    )
    sprint3_parser.add_argument(
        "--order", type=int, default=4, help="Butterworth filter order (default: 4, B1)"
    )
    sprint3_parser.add_argument(
        "--zero-phase",
        dest="zero_phase",
        action="store_true",
        default=True,
        help="Use zero-phase sosfiltfilt (default: on, B1's own selection)",
    )
    sprint3_parser.add_argument(
        "--no-zero-phase",
        dest="zero_phase",
        action="store_false",
        help="Use a single causal pass instead -- NOT the canonical B1 selection",
    )

    return parser


def _cmd_inspect(args: argparse.Namespace) -> int:
    dataset = read_ogpr(args.input)
    header_info = read_ogpr_header(args.input)

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = args.input.stem

    generated: list[Path] = [
        write_metadata_json(dataset, output_dir / f"{stem}_metadata.json"),
        write_header_json(header_info, output_dir / f"{stem}_header.json"),
    ]

    warnings_list = list(dataset.metadata.get("warnings", []))

    if dataset.has_geolocation:
        generated.append(write_geolocation_csv(dataset, output_dir / f"{stem}_geolocation.csv"))
        generated.append(save_survey_geometry(dataset, output_dir / f"{stem}_survey_geometry.png"))
    else:
        warnings_list.append("Geolocation CSV and survey geometry plot skipped: no geolocation data.")

    generated.append(
        save_channel_bscan(
            dataset,
            args.channel,
            output_dir / f"{stem}_channel{args.channel:02d}_bscan.png",
            clip_percentile=args.clip_percentile,
            cmap=args.cmap,
        )
    )
    generated.append(
        save_all_channels_bscan(
            dataset,
            output_dir / f"{stem}_all_channels.png",
            clip_percentile=args.clip_percentile,
            cmap=args.cmap,
        )
    )
    generated.append(write_radar_volume_npz(dataset, output_dir / "radar_volume.npz"))

    derived = derive_metadata(dataset)
    radar_meta = dataset.metadata.get("radar", {}) or {}
    sampling_meta = dataset.metadata.get("sampling", {}) or {}
    geometry = derived.get("geometry", {}) or {}

    print(f"File: {dataset.metadata['source_file']['name']}")
    print(f"OpenGPR version: {dataset.metadata.get('opengpr_version')}")
    print(f"Radar shape (slice, channel, sample): {dataset.shape}")
    print(f"Dtype: {dataset.metadata.get('dtype')}")
    print(f"Sampling time: {sampling_meta.get('sampling_time_ns')} ns")
    print(f"Frequency: {radar_meta.get('nominal_frequency_MHz')} MHz")
    print(f"Polarization: {radar_meta.get('polarization')}")
    print(f"Geolocation present: {dataset.has_geolocation}")
    print(f"Spatial reference: {dataset.metadata.get('spatial_reference')}")
    print(f"Estimated profile length: {geometry.get('profile_length_m')} m")
    print(f"Estimated swath width: {geometry.get('swath_width_m')} m")
    print("Generated outputs:")
    for generated_path in generated:
        print(f"  - {generated_path}")
    if warnings_list:
        print("Warnings:")
        for warning in warnings_list:
            print(f"  - {warning}")
    return 0


def _cmd_header(args: argparse.Namespace) -> int:
    header_info = read_ogpr_header(args.input)
    header = header_info.header
    main_descriptor = header.get("mainDescriptor", {}) or {}
    version = header.get("version", {}) or {}
    main_metadata = main_descriptor.get("metadata", {}) or {}

    print(f"File: {args.input}")
    print(f"Magic: {header_info.magic}")
    print(f"Checksum: {header_info.checksum}")
    print(f"Header size: {header_info.header_size} bytes")
    print(f"OpenGPR version: {version.get('major')}.{version.get('minor')}")
    print(f"samplesCount: {main_descriptor.get('samplesCount')}")
    print(f"channelsCount: {main_descriptor.get('channelsCount')}")
    print(f"slicesCount: {main_descriptor.get('slicesCount')}")
    print(f"swathName: {main_metadata.get('swathName')}")
    print(f"arrayId: {main_metadata.get('arrayId')}")
    print("Data blocks:")
    for block in header.get("dataBlockDescriptors", []) or []:
        print(
            f"  - type={block.get('type')!r} name={block.get('name')!r} "
            f"byteOffset={block.get('byteOffset')} byteSize={block.get('byteSize')}"
        )
    return 0


def _print_common_header(args: argparse.Namespace, dataset: GPRDataset, before_hash: str) -> None:
    print(f"Input file: {args.input}")
    print(f"Input hash (sha256): {before_hash}")
    print(f"Input shape: {dataset.shape}")


def _print_common_footer(
    args: argparse.Namespace, before_hash: str, final_dataset: GPRDataset, generated: list[Path]
) -> None:
    after_hash = file_sha256(args.input)
    print("Generated outputs:")
    for path in generated:
        print(f"  - {path}")
    print(f"Output shape: {final_dataset.shape}, dtype: {final_dataset.amplitudes.dtype}")
    print(f"Processing history: {[record['operation'] for record in final_dataset.processing_history]}")
    print(f"Raw file hash unchanged: {before_hash == after_hash}")


def _cmd_time_zero(args: argparse.Namespace) -> int:
    dataset = read_ogpr(args.input)
    before_hash = file_sha256(args.input)
    _print_common_header(args, dataset, before_hash)

    tz_kwargs = _resolve_time_zero_kwargs(
        method=args.method,
        picks_file=args.picks_file,
        search_start_ns=args.search_start_ns,
        search_end_ns=args.search_end_ns,
        target_sample=args.target_sample,
        peak_polarity=args.peak_polarity,
        reference_channel=args.reference_channel,
        max_shift_samples=args.max_shift_samples,
        fill_value=args.fill_value,
        overflow_policy=args.overflow_policy,
    )
    result = correct_time_zero(dataset, **tz_kwargs)

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"channel{args.channel:02d}"

    generated: list[Path] = [write_channel_picks_csv(result, output_dir / "channel_picks.csv")]
    generated.extend(save_channel_median_traces(dataset, result.dataset, result, output_dir).values())
    generated.extend(
        save_bscan_comparison(
            dataset,
            result.dataset,
            args.channel,
            output_dir,
            stem,
            clip_percentile=args.clip_percentile,
            cmap=args.cmap,
        ).values()
    )
    generated.append(
        save_all_channels_bscan(
            dataset,
            output_dir / "all_channels_before.png",
            clip_percentile=args.clip_percentile,
            cmap=args.cmap,
        )
    )
    generated.append(
        save_all_channels_bscan(
            result.dataset,
            output_dir / "all_channels_after.png",
            clip_percentile=args.clip_percentile,
            cmap=args.cmap,
        )
    )
    generated.append(save_picks_and_shifts(result, output_dir / "picks_and_shifts.png"))
    generated.append(save_padding_mask_plot(result, args.channel, output_dir / f"padding_mask_{stem}.png"))
    generated.append(write_valid_sample_summary_json(result, output_dir / "valid_sample_summary.json"))
    generated.append(write_processing_metadata_json(result, output_dir / "processing_metadata.json"))
    generated.append(write_corrected_npz(result, output_dir / "time_zero_corrected.npz"))
    generated.append(write_relative_time_axis_csv(result.dataset, output_dir / "relative_time_axis.csv"))

    time_axis = result.diagnostics["time_axis"]
    print(f"Time-zero method: {result.diagnostics['method']}")
    print(f"Overflow policy: {result.diagnostics['overflow_policy']}")
    print(f"Has clipped shifts: {result.diagnostics['has_clipped_shifts']}")
    print(f"Valid for downstream processing: {result.diagnostics['valid_for_downstream_processing']}")
    print(
        f"Corrected time axis: [{time_axis['corrected_time_ns_start']}, "
        f"{time_axis['corrected_time_ns_end']}] ns"
    )
    print(
        f"Target sample (={time_axis['target_sample']}) time value: {time_axis['time_zero_reference_ns']} ns"
    )
    print(f"Negative-time sample count: {time_axis['negative_time_sample_count']}")
    print("Channel picks and shifts:")
    for channel in sorted(int(c) for c in result.diagnostics["channel_picks"]):
        picked = result.diagnostics["channel_picks"][str(channel)]
        shift = result.diagnostics["channel_shifts"][str(channel)]
        requested = result.diagnostics["requested_shifts"][str(channel)]
        print(f"  ch{channel:02d}: picked_sample={picked} requested_shift={requested} applied_shift={shift}")
    if not result.diagnostics["valid_for_downstream_processing"]:
        print(
            "WARNING: this result has clipped shifts and is NOT valid_for_downstream_processing. "
            "Do not treat it as a canonical output without explicit review."
        )
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    _print_common_footer(args, before_hash, result.dataset, generated)
    return 0


def _cmd_dc_offset(args: argparse.Namespace) -> int:
    dataset = read_ogpr(args.input)
    before_hash = file_sha256(args.input)
    _print_common_header(args, dataset, before_hash)

    result = correct_dc_offset(
        dataset,
        method=args.method,
        window_start_ns=args.window_start_ns,
        window_end_ns=args.window_end_ns,
        window_reference=args.window_reference.replace("-", "_"),
    )

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"channel{args.channel:02d}"

    generated: list[Path] = [write_offsets_csv(result, output_dir / "offsets.csv")]
    generated.extend(
        save_bscan_comparison(
            dataset,
            result.dataset,
            args.channel,
            output_dir,
            stem,
            clip_percentile=args.clip_percentile,
            cmap=args.cmap,
        ).values()
    )
    generated.append(save_offset_histogram(result, output_dir / "trace_offset_histogram.png"))
    generated.append(
        save_trace_means_before_after(dataset, result.dataset, output_dir / "trace_means_before_after.png")
    )
    generated.append(save_channel_offset_statistics(result, output_dir / "channel_offset_statistics.png"))
    generated.append(write_processing_metadata_json(result, output_dir / "processing_metadata.json"))
    generated.append(write_corrected_npz(result, output_dir / "dc_offset_corrected.npz"))

    print(f"DC offset method: {result.diagnostics['method']}")
    print(f"DC window: [{result.diagnostics['window_start_ns']}, {result.diagnostics['window_end_ns']}) ns")
    print(f"DC window reference: {result.diagnostics['window_reference']}")
    print(
        f"DC window sample indices: [{result.diagnostics['window_start_sample']}, "
        f"{result.diagnostics['window_end_sample']})"
    )
    print(f"Offset statistics: {result.diagnostics['offset_statistics']}")
    print(f"Padding value statistics: {result.diagnostics['padding_value_statistics']}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    _print_common_footer(args, before_hash, result.dataset, generated)
    return 0


def _cmd_sprint2(args: argparse.Namespace) -> int:
    dataset = read_ogpr(args.input)
    before_hash = file_sha256(args.input)
    _print_common_header(args, dataset, before_hash)

    tz_kwargs = _resolve_time_zero_kwargs(
        method=args.time_zero_method,
        picks_file=args.picks_file,
        search_start_ns=args.search_start_ns,
        search_end_ns=args.search_end_ns,
        target_sample=args.target_sample,
        peak_polarity=args.peak_polarity,
        reference_channel=args.reference_channel,
        max_shift_samples=args.max_shift_samples,
        fill_value=args.fill_value,
        overflow_policy=args.overflow_policy,
    )
    tz_result: ProcessingResult = correct_time_zero(dataset, **tz_kwargs)
    # DC offset must exclude time-zero's padding from both its own statistics
    # and its own subtraction — see processing/dc_offset.py. The window is
    # resolved against tz_result.dataset.time_ns (window_reference="dataset_time"
    # by default), which is time-zero-relative — see ADR-004 — so the same ns
    # window is target-sample-invariant.
    dc_result: ProcessingResult = correct_dc_offset(
        tz_result.dataset,
        method=args.dc_method,
        window_start_ns=args.dc_window_start_ns,
        window_end_ns=args.dc_window_end_ns,
        valid_mask=tz_result.valid_mask,
        window_reference=args.dc_window_reference.replace("-", "_"),
    )
    final_dataset = dc_result.dataset

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"channel{args.channel:02d}"

    generated: list[Path] = [
        write_combined_npz(tz_result, dc_result, output_dir / "sprint02_processed.npz"),
        write_processing_history_json(final_dataset, output_dir / "processing_history.json"),
        write_channel_picks_csv(tz_result, output_dir / "channel_picks.csv"),
        write_offsets_csv(dc_result, output_dir / "dc_offsets.csv"),
        write_processing_metadata_json(dc_result, output_dir / "processing_metadata.json"),
        write_valid_sample_summary_json(tz_result, output_dir / "valid_sample_summary.json"),
        write_relative_time_axis_csv(final_dataset, output_dir / "relative_time_axis.csv"),
        save_padding_mask_plot(tz_result, args.channel, output_dir / f"padding_mask_{stem}.png"),
    ]
    median_paths = save_channel_median_traces(
        dataset, tz_result.dataset, tz_result, output_dir, stem="channel_medians"
    )
    generated.extend(median_paths.values())
    before_after_path = output_dir / "channel_medians_before_after.png"
    shutil.copyfile(median_paths["overlay"], before_after_path)
    generated.append(before_after_path)
    generated.append(
        save_channel_bscan(
            dataset,
            args.channel,
            output_dir / "channel00_raw.png",
            clip_percentile=args.clip_percentile,
            cmap=args.cmap,
        )
    )
    generated.append(
        save_channel_bscan(
            tz_result.dataset,
            args.channel,
            output_dir / "channel00_timezero.png",
            clip_percentile=args.clip_percentile,
            cmap=args.cmap,
        )
    )
    generated.append(
        save_channel_bscan(
            final_dataset,
            args.channel,
            output_dir / "channel00_final.png",
            clip_percentile=args.clip_percentile,
            cmap=args.cmap,
        )
    )
    generated.append(
        save_stage_differences(
            [("raw", dataset), ("time-zero", tz_result.dataset), ("dc-offset", final_dataset)],
            args.channel,
            output_dir / "channel00_stage_differences.png",
            clip_percentile=args.clip_percentile,
            cmap=args.cmap,
        )
    )
    generated.append(
        write_sprint2_summary_json(
            dataset,
            tz_result,
            dc_result,
            output_dir / "sprint02_summary.json",
            source_file=args.input,
            raw_file_sha256=before_hash,
        )
    )

    time_axis = tz_result.diagnostics["time_axis"]
    print(f"Time-zero method: {tz_result.diagnostics['method']}")
    print(f"Time-zero overflow policy: {tz_result.diagnostics['overflow_policy']}")
    print(f"Time-zero has clipped shifts: {tz_result.diagnostics['has_clipped_shifts']}")
    print(f"Valid for downstream processing: {tz_result.diagnostics['valid_for_downstream_processing']}")
    print(
        f"Corrected time axis: [{time_axis['corrected_time_ns_start']}, "
        f"{time_axis['corrected_time_ns_end']}] ns"
    )
    print(
        f"Target sample (={time_axis['target_sample']}) time value: {time_axis['time_zero_reference_ns']} ns"
    )
    print(f"Negative-time sample count: {time_axis['negative_time_sample_count']}")
    print(f"DC offset method: {dc_result.diagnostics['method']}")
    print(
        f"DC window: [{dc_result.diagnostics['window_start_ns']}, "
        f"{dc_result.diagnostics['window_end_ns']}) ns "
        f"(reference={dc_result.diagnostics['window_reference']})"
    )
    print(
        f"DC window sample indices: [{dc_result.diagnostics['window_start_sample']}, "
        f"{dc_result.diagnostics['window_end_sample']})"
    )
    print(f"DC offset statistics: {dc_result.diagnostics['offset_statistics']}")
    print(f"DC offset valid_mask used: {dc_result.diagnostics['valid_mask_provided']}")
    print(f"Padding statistics: {dc_result.diagnostics['padding_value_statistics']}")
    print(f"Processing history order: {[record['operation'] for record in final_dataset.processing_history]}")
    all_warnings = [*tz_result.warnings, *dc_result.warnings]
    if not tz_result.diagnostics["valid_for_downstream_processing"]:
        print(
            "WARNING: time-zero clipped one or more channels; this combined result is NOT "
            "valid_for_downstream_processing. Do not treat it as canonical without explicit review."
        )
    if all_warnings:
        print("Warnings:")
        for warning in all_warnings:
            print(f"  - {warning}")
    _print_common_footer(args, before_hash, final_dataset, generated)
    return 0


def _cmd_dewow(args: argparse.Namespace) -> int:
    before_hash = file_sha256(args.input)
    dataset, valid_mask = read_processed_npz(args.input)

    print(f"Input file: {args.input}")
    print(f"Input hash (sha256): {before_hash}")
    print(f"Input shape: {dataset.shape}, dtype: {dataset.amplitudes.dtype}")
    print(f"Input processing history: {[record['operation'] for record in dataset.processing_history]}")
    sampling = dataset.metadata.get("sampling") or {}
    sampling_time_ns = sampling.get("sampling_time_ns")
    if sampling_time_ns:
        sampling_frequency_mhz = 1000.0 / sampling_time_ns
        print(f"Sampling interval: {sampling_time_ns} ns")
        print(
            f"Sampling frequency: {sampling_frequency_mhz:.4g} MHz, "
            f"Nyquist: {sampling_frequency_mhz / 2:.4g} MHz"
        )

    result = correct_dewow(
        dataset,
        window_ns=args.window_ns,
        method=args.method.replace("-", "_"),
        valid_mask=valid_mask,
        edge_mode=args.edge_mode,
        allow_repeat_processing=args.allow_repeat_processing,
    )

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = [
        write_corrected_npz(result, output_dir / "dewow_processed.npz"),
        write_processing_metadata_json(result, output_dir / "processing_metadata.json"),
        write_padding_verification_json(result, output_dir / "padding_verification.json"),
    ]
    generated.extend(save_dewow_qc_suite(dataset, result, output_dir, channel=args.channel).values())

    diag = result.diagnostics
    print(f"Dewow method: {diag['method']}")
    print(f"Dewow edge mode: {diag['edge_mode']}")
    print(f"Requested window: {diag['requested_window_ns']} ns ({diag['requested_window_samples']} samples)")
    print(f"Applied window: {diag['applied_window_ns']:.4g} ns ({diag['applied_window_samples']} samples)")
    print(
        f"Valid segment length range: [{diag['valid_segment_min_length']}, "
        f"{diag['valid_segment_max_length']}]"
    )
    print(
        f"Total valid samples: {diag['total_valid_samples']}, "
        f"total padded samples: {diag['total_padded_samples']}"
    )
    print(f"Removed-component statistics: {diag['removed_component_statistics']}")
    print(f"Output statistics: {diag['output_statistics']}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    print("Generated outputs:")
    for path in generated:
        print(f"  - {path}")
    print(f"Output shape: {result.dataset.shape}, dtype: {result.dataset.amplitudes.dtype}")
    print(
        f"Output processing history: {[record['operation'] for record in result.dataset.processing_history]}"
    )
    after_hash = file_sha256(args.input)
    print(f"Input file hash unchanged: {before_hash == after_hash}")
    print("Canonical selected: false")
    return 0


def _cmd_bandpass(args: argparse.Namespace) -> int:
    before_hash = file_sha256(args.input)
    dataset, valid_mask = read_processed_npz(args.input)

    print(f"Input file: {args.input}")
    print(f"Input hash (sha256): {before_hash}")
    print(f"Input shape: {dataset.shape}, dtype: {dataset.amplitudes.dtype}")
    print(f"Input processing history: {[record['operation'] for record in dataset.processing_history]}")

    kwargs: dict[str, Any] = {
        "method": args.method,
        "valid_mask": valid_mask,
        "allow_repeat_processing": args.allow_repeat_processing,
    }
    if args.method == "butterworth":
        if args.lowcut_mhz is None or args.highcut_mhz is None:
            raise ProcessingError("method=butterworth requires --lowcut-mhz and --highcut-mhz")
        kwargs.update(
            lowcut_mhz=args.lowcut_mhz,
            highcut_mhz=args.highcut_mhz,
            order=args.order,
            zero_phase=args.zero_phase,
        )
    else:
        if args.ormsby_frequencies_mhz is None:
            raise ProcessingError("method=ormsby requires --ormsby-frequencies-mhz F1 F2 F3 F4")
        kwargs["frequencies_mhz"] = tuple(args.ormsby_frequencies_mhz)

    result = correct_bandpass(dataset, **kwargs)

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = [
        write_corrected_npz(result, output_dir / "bandpass_processed.npz"),
        write_processing_metadata_json(result, output_dir / "processing_metadata.json"),
        write_padding_verification_json(result, output_dir / "padding_verification.json"),
    ]
    generated.extend(save_bandpass_qc_suite(dataset, result, output_dir, channel=args.channel).values())

    diag = result.diagnostics
    print(f"Band-pass method: {diag['method']}")
    print(
        f"Sampling frequency: {diag['sampling_frequency_mhz']:.4g} MHz, "
        f"Nyquist: {diag['nyquist_mhz']:.4g} MHz"
    )
    if diag["method"] == "butterworth":
        print(f"Cutoffs: [{diag['lowcut_mhz']}, {diag['highcut_mhz']}] MHz, order={diag['order']}")
        print(f"Zero phase: {diag['zero_phase']}")
    else:
        print(f"Ormsby corner frequencies: {diag['frequencies_mhz']} MHz")
    print(
        f"Valid segment length range: [{diag['valid_segment_min_length']}, "
        f"{diag['valid_segment_max_length']}]"
    )
    print(f"Internal padding per channel: {diag['internal_padding_samples_per_channel']}")
    all_lags = [
        s["median_trace_cross_correlation_lag"] for s in diag["peak_shift_and_lag_per_segment"].values()
    ]
    print(f"Max abs median-trace cross-correlation lag: {max((abs(lag) for lag in all_lags), default=None)}")
    print(f"Removed-component statistics: {diag['removed_component_statistics']}")
    print(f"Output statistics: {diag['output_statistics']}")
    if result.warnings:
        print("Warnings:")
        for warning in result.warnings:
            print(f"  - {warning}")
    print("Generated outputs:")
    for path in generated:
        print(f"  - {path}")
    print(f"Output shape: {result.dataset.shape}, dtype: {result.dataset.amplitudes.dtype}")
    print(
        f"Output processing history: {[record['operation'] for record in result.dataset.processing_history]}"
    )
    after_hash = file_sha256(args.input)
    print(f"Input file hash unchanged: {before_hash == after_hash}")
    print("Canonical selected: false")
    return 0


def _cmd_sprint3_candidates(args: argparse.Namespace) -> int:
    before_hash = file_sha256(args.input)
    print(f"Input file: {args.input}")
    print(f"Input hash (sha256): {before_hash}")

    result = run_all_sprint3_candidates(
        args.input,
        args.output_dir,
        dewow_config_path=args.dewow_config,
        bandpass_config_path=args.bandpass_config,
    )

    dataset = result["dataset"]
    print(f"Input shape: {dataset.shape}, dtype: {dataset.amplitudes.dtype}")
    print(f"Input processing history: {[record['operation'] for record in dataset.processing_history]}")
    print(f"Dewow candidates run: {[info['id'] for info in result['dewow_candidates']]}")
    print(f"Dewow base used for band-pass/combined comparison: {result['dewow_base_id']} (not canonical)")
    print(f"Band-pass candidates run: {[info['id'] for info in result['bandpass_candidates']]}")
    print(f"Combined candidates run: {[info['id'] for info in result['combined_candidates']]}")
    print(f"Output directory: {args.output_dir}")
    print(f"Sprint 3 review file: {result['review_path']}")
    after_hash = file_sha256(args.input)
    print(f"Input file hash unchanged: {before_hash == after_hash}")
    print("Canonical selected: false")
    return 0


def _cmd_sprint3(args: argparse.Namespace) -> int:
    before_hash = file_sha256(args.input)
    print(f"Input file: {args.input}")
    print(f"Input hash (sha256): {before_hash}")
    print(f"Selection authority: {SELECTION_AUTHORITY}")

    result = run_sprint3_canonical(
        args.input,
        args.output_dir,
        dewow_method=args.dewow_method.replace("-", "_"),
        dewow_window_ns=args.dewow_window_ns,
        dewow_edge_mode=args.dewow_edge_mode,
        bandpass_method=args.bandpass_method,
        lowcut_mhz=args.lowcut_mhz,
        highcut_mhz=args.highcut_mhz,
        order=args.order,
        zero_phase=args.zero_phase,
        channel=args.channel,
        clip_percentile=args.clip_percentile,
        cmap=args.cmap,
    )

    dataset = result["dataset"]
    dewow_result = result["dewow_result"]
    bandpass_result = result["bandpass_result"]
    phase_verification = result["phase_verification"]
    final_dataset = bandpass_result.dataset

    is_canonical_parameters = (
        args.dewow_method == "running-mean"
        and args.dewow_window_ns == 8.0
        and args.dewow_edge_mode == "reflect"
        and args.bandpass_method == "butterworth"
        and args.lowcut_mhz == 100.0
        and args.highcut_mhz == 900.0
        and args.order == 4
        and args.zero_phase
    )

    # The raw .ogpr's own path is derived from the loaded dataset's own metadata
    # (never hardcoded) so its hash can be reported alongside the canonical NPZ's.
    source_file_meta = dataset.metadata.get("source_file") or {}
    raw_file_path = source_file_meta.get("path")
    raw_file_hash_before = file_sha256(raw_file_path) if raw_file_path else None
    raw_file_hash_after = file_sha256(raw_file_path) if raw_file_path else None

    canonical_note_path = write_canonical_processing_note(
        result,
        raw_file_hash_before or "unknown (source_file path missing from metadata)",
        before_hash,
        args.output_dir / "CANONICAL_PROCESSING_NOTE.md",
    )

    print(f"Raw source file: {raw_file_path or 'unknown (source_file path missing from metadata)'}")
    print(f"Raw source file hash (sha256): {raw_file_hash_before}")
    print(f"Sprint 2 canonical NPZ hash (sha256): {before_hash}")
    print(f"Input shape: {dataset.shape}, dtype: {dataset.amplitudes.dtype}")
    print(f"Input processing history: {[record['operation'] for record in dataset.processing_history]}")
    print(
        f"Applied dewow window: requested={dewow_result.diagnostics['requested_window_ns']}ns "
        f"applied={dewow_result.diagnostics['applied_window_ns']:.4g}ns "
        f"({dewow_result.diagnostics['applied_window_samples']} samples), "
        f"edge_mode={dewow_result.diagnostics['edge_mode']}"
    )
    print(
        f"Applied band-pass parameters: {bandpass_result.diagnostics['method']} "
        f"[{bandpass_result.diagnostics['lowcut_mhz']}, {bandpass_result.diagnostics['highcut_mhz']}] MHz "
        f"order={bandpass_result.diagnostics['order']} zero_phase={bandpass_result.diagnostics['zero_phase']}"
    )
    print(
        f"Output processing history: {[record['operation'] for record in final_dataset.processing_history]}"
    )
    print(f"Padding verification: {result['generated']['padding_verification_json']}")
    print(
        f"Phase lag: max_abs_median_trace_cross_correlation_lag="
        f"{phase_verification['max_abs_median_trace_cross_correlation_lag']}, "
        f"confirmed_zero_phase={phase_verification['confirmed_zero_phase']}"
    )
    print("Generated outputs:")
    for path in (*result["generated"].values(), canonical_note_path):
        print(f"  - {path}")
    after_hash = file_sha256(args.input)
    print(f"Sprint 2 canonical NPZ hash unchanged: {before_hash == after_hash}")
    print(f"Raw source file hash unchanged: {raw_file_hash_before == raw_file_hash_after}")
    print(f"canonical selected: {'true' if is_canonical_parameters else 'false'}")
    if not is_canonical_parameters:
        print(
            "WARNING: one or more parameters were overridden from the human/geophysical "
            "selection (D2 + B1) -- this run is NOT the canonical Sprint 3 chain."
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            return _cmd_inspect(args)
        if args.command == "header":
            return _cmd_header(args)
        if args.command == "time-zero":
            return _cmd_time_zero(args)
        if args.command == "dc-offset":
            return _cmd_dc_offset(args)
        if args.command == "sprint2":
            return _cmd_sprint2(args)
        if args.command == "dewow":
            return _cmd_dewow(args)
        if args.command == "bandpass":
            return _cmd_bandpass(args)
        if args.command == "sprint3-candidates":
            return _cmd_sprint3_candidates(args)
        if args.command == "sprint3":
            return _cmd_sprint3(args)
        parser.error(f"unknown command {args.command!r}")
        return 2
    except (OGPRError, ProcessingError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if args.debug:
            raise
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        if args.debug:
            raise
        return 1
    except Exception as exc:  # top-level CLI safety net; re-raised under --debug
        print(f"Unexpected error: {exc}", file=sys.stderr)
        if args.debug:
            raise
        return 1


if __name__ == "__main__":
    sys.exit(main())
