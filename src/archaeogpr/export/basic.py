"""Basic (non-processing) exports: metadata JSON, full header JSON, geolocation CSV, and NPZ.

Nothing here performs signal processing — these functions only serialize
what :func:`archaeogpr.io.ogpr_reader.read_ogpr` /
:func:`archaeogpr.io.ogpr_reader.read_ogpr_header` already extracted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from archaeogpr.io.ogpr_reader import OgprHeaderInfo
from archaeogpr.model.dataset import GPRDataset
from archaeogpr.qc.metadata import derive_metadata


def build_metadata_export(dataset: GPRDataset) -> dict[str, Any]:
    """Combine the dataset's source-derived metadata with computed QC metadata.

    Does not modify ``dataset``. Warnings from both sources are merged
    without duplicates, preserving first-seen order.
    """
    derived = derive_metadata(dataset)

    merged_warnings = list(dataset.metadata.get("warnings", []))
    for warning in derived.get("warnings", []):
        if warning not in merged_warnings:
            merged_warnings.append(warning)

    export = dict(dataset.metadata)
    export["derived"] = {key: value for key, value in derived.items() if key != "warnings"}
    export["warnings"] = merged_warnings
    return export


def write_metadata_json(dataset: GPRDataset, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(build_metadata_export(dataset), indent=2), encoding="utf-8")
    return output_path


def write_header_json(header_info: OgprHeaderInfo, output_path: str | Path) -> Path:
    """Save the full parsed header (plus preamble fields) as readable JSON."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "magic": header_info.magic,
        "checksum": header_info.checksum,
        "header_size": header_info.header_size,
        "header": header_info.header,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def build_geolocation_dataframe(dataset: GPRDataset) -> pd.DataFrame:
    """One row per (slice, channel) with the full raw geolocation record.

    Raises ``ValueError`` if ``dataset`` has no geolocation data.
    """
    if not dataset.has_geolocation:
        raise ValueError("Dataset has no geolocation data; cannot build a geolocation table.")

    slices_count, channels_count, _ = dataset.shape
    slice_index, channel_index = np.meshgrid(
        np.arange(slices_count), np.arange(channels_count), indexing="ij"
    )

    def flat(array: np.ndarray | None) -> np.ndarray:
        if array is None:
            return np.full(slices_count * channels_count, np.nan)
        return array.reshape(-1)

    return pd.DataFrame(
        {
            "slice": slice_index.reshape(-1),
            "channel": channel_index.reshape(-1),
            "x_top": flat(dataset.x),
            "y_top": flat(dataset.y),
            "depth_top_m": flat(dataset.depth_top_m),
            "elevation_top_m": flat(dataset.elevation_top_m),
            "x_bottom": flat(dataset.x_bottom),
            "y_bottom": flat(dataset.y_bottom),
            "depth_bottom_m": flat(dataset.depth_bottom_m),
            "elevation_bottom_m": flat(dataset.elevation_bottom_m),
        }
    )


def write_geolocation_csv(dataset: GPRDataset, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_geolocation_dataframe(dataset).to_csv(output_path, index=False)
    return output_path


def write_radar_volume_npz(dataset: GPRDataset, output_path: str | Path) -> Path:
    """Save amplitudes/time_ns/metadata (+ coordinates if present) as a compressed NPZ.

    When the dataset has no geolocation, coordinate keys are omitted entirely
    rather than storing ``None`` as an object array; ``has_geolocation`` is
    stored explicitly so callers can tell the two cases apart.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "amplitudes": dataset.amplitudes,
        "time_ns": dataset.time_ns,
        "has_geolocation": dataset.has_geolocation,
        "metadata_json": json.dumps(build_metadata_export(dataset)),
    }
    if dataset.has_geolocation:
        payload["x"] = dataset.x
        payload["y"] = dataset.y
        payload["elevation_top_m"] = dataset.elevation_top_m

    np.savez_compressed(output_path, **payload)
    return output_path
