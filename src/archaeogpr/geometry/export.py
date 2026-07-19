"""Read-only JSON export of a resolved :class:`~archaeogpr.geometry.resolve.GeometryResolution`.

This is a report of what the resolver concluded, not a processing result --
it is never re-imported (Sprint 3D-0 scope) and never touches the source
``.ogpr`` file or ``dataset.processing_history``. Written atomically
(temp file + replace) so a crash or concurrent read never observes a
half-written report.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from archaeogpr import __version__ as ARCHAEOGPR_VERSION
from archaeogpr.geometry.resolve import GeometryResolution
from archaeogpr.geometry.summary import compute_geometry_summary
from archaeogpr.model.dataset import GPRDataset

__all__ = ["GEOMETRY_REPORT_SCHEMA_VERSION", "build_geometry_report", "export_geometry_report"]

GEOMETRY_REPORT_SCHEMA_VERSION = 1
GEOMETRY_REPORT_SUFFIX = ".geometry.json"

_READ_CHUNK_BYTES = 1024 * 1024


def _sha256_of_file(path: Path) -> str:
    """SHA-256 of ``path``'s bytes, read strictly read-only (``"rb"``), streamed in chunks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    """Recursively replace non-finite floats with ``None`` so the result is always valid JSON.

    Python's own ``json.dumps`` would otherwise silently emit the
    non-standard ``NaN``/``Infinity``/``-Infinity`` tokens (``allow_nan``
    defaults to ``True``) -- this project's exports never do that (see
    Sprint 3D-0 spec).
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _array_summary(array: np.ndarray | None) -> dict[str, Any] | None:
    """A JSON-safe ``{shape, values}`` view of a 1-D array, or ``None``."""
    if array is None:
        return None
    return {"shape": list(array.shape), "values": _json_safe(array)}


def build_geometry_report(
    resolution: GeometryResolution,
    dataset: GPRDataset,
    source_path: Path,
) -> dict[str, Any]:
    """Build the JSON-serializable geometry report payload. Does not write anything."""
    geometry = resolution.geometry
    readiness = resolution.readiness

    def gate(name: str, status: Any) -> dict[str, Any]:
        return {
            "name": name,
            "ready": status.ready,
            "blocking_issues": list(status.blocking_issues),
            "warnings": list(status.warnings),
        }

    provenance = {key: value.value for key, value in geometry.provenance.items()}

    time_ns = dataset.time_ns
    time_range = [float(time_ns[0]), float(time_ns[-1])] if time_ns.size else None

    payload: dict[str, Any] = {
        "schema_version": GEOMETRY_REPORT_SCHEMA_VERSION,
        "software_version": ARCHAEOGPR_VERSION,
        "export_timestamp": datetime.now(UTC).isoformat(),
        "source_path": str(source_path),
        "source_sha256": _sha256_of_file(source_path),
        "dataset_shape": {
            "trace_count": geometry.trace_count,
            "channel_count": geometry.channel_count,
            "sample_count": int(dataset.shape[2]),
        },
        "sampling_time_ns": (dataset.metadata.get("sampling") or {}).get("sampling_time_ns"),
        "time_range_ns": time_range,
        "coordinate_mode": geometry.coordinate_mode.value,
        "geometry_revision": geometry.geometry_revision,
        "resolved_fields": {
            "trace_spacing_m": geometry.trace_spacing_m,
            "channel_spacing_m": geometry.channel_spacing_m,
            "channel_zero_offset_m": geometry.channel_zero_offset_m,
            "origin_x": geometry.origin_x,
            "origin_y": geometry.origin_y,
            "azimuth_deg": geometry.azimuth_deg,
            "cross_track_direction": geometry.cross_track_direction.value,
            "crs_identifier": geometry.crs_identifier,
            "crs_validation_status": geometry.crs_validation_status.value,
        },
        "field_provenance": provenance,
        "along_track_coordinates": _array_summary(geometry.along_track_coordinates),
        "cross_track_offsets": _array_summary(geometry.cross_track_offsets),
        "x_coordinates": _array_summary(geometry.x_coordinates),
        "y_coordinates": _array_summary(geometry.y_coordinates),
        "summary": asdict(compute_geometry_summary(geometry)),
        "readiness": {
            "index_view_ready": gate("index_view_ready", readiness.index_view_ready),
            "local_parameter_grid_ready": gate(
                "local_parameter_grid_ready", readiness.local_parameter_grid_ready
            ),
            "rectilinear_cscan_ready": gate("rectilinear_cscan_ready", readiness.rectilinear_cscan_ready),
            "actual_xy_point_grid_ready": gate(
                "actual_xy_point_grid_ready", readiness.actual_xy_point_grid_ready
            ),
            "global_cscan_ready": gate("global_cscan_ready", readiness.global_cscan_ready),
            "time_volume_ready": gate("time_volume_ready", readiness.time_volume_ready),
            "depth_volume_ready": gate("depth_volume_ready", readiness.depth_volume_ready),
        },
        "warnings": list(geometry.warnings),
        "errors": list(geometry.errors),
        "source_summary": resolution.source_summary,
    }
    return _json_safe(payload)


def export_geometry_report(
    resolution: GeometryResolution,
    dataset: GPRDataset,
    source_path: Path,
    output_path: str | Path,
) -> Path:
    """Write the geometry report to ``output_path`` atomically (temp file + ``os.replace``).

    Never touches ``source_path`` (the raw ``.ogpr`` file) -- only reads it,
    read-only, to compute :func:`_sha256_of_file`.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_geometry_report(resolution, dataset, source_path)
    text = json.dumps(payload, indent=2)

    fd, tmp_name = tempfile.mkstemp(
        dir=str(output_path.parent), prefix=f".{output_path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, output_path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp_name)
        raise
    return output_path
