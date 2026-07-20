"""Read-only, schema-versioned JSON export of one C-scan result.

Mirrors ``archaeogpr.geometry.export``'s atomic-write, schema-versioned,
SHA-256-of-source pattern (rather than ``gui/export.py``'s older
non-atomic PNG-sidecar pattern) — see ADR-017 for why. Never touches the
source ``.ogpr`` file, never re-imported.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from archaeogpr import __version__ as ARCHAEOGPR_VERSION
from archaeogpr.cscan.models import CScanGeometryView, CScanResult

__all__ = ["CSCAN_REPORT_SCHEMA_VERSION", "build_cscan_report", "export_cscan_report"]

CSCAN_REPORT_SCHEMA_VERSION = 1
_READ_CHUNK_BYTES = 1024 * 1024


def _sha256_of_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any) -> Any:
    """Recursively replace non-finite floats with ``None`` so the result is always valid JSON."""
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


def build_cscan_report(
    result: CScanResult,
    *,
    source_path: Path,
    geometry_view: CScanGeometryView,
    colormap: str,
    display_min: float,
    display_max: float,
    crs_identifier: str | None,
    crs_validation_status: str,
) -> dict[str, Any]:
    """Build the JSON-serializable C-scan report payload. Does not write anything."""
    payload: dict[str, Any] = {
        "schema_version": CSCAN_REPORT_SCHEMA_VERSION,
        "software_version": ARCHAEOGPR_VERSION,
        "export_timestamp": datetime.now(UTC).isoformat(),
        "source_path": str(source_path),
        "source_sha256": _sha256_of_file(source_path),
        "source_kind": result.source_kind.value,
        "source_revision": result.source_revision,
        "geometry_revision": result.geometry_revision,
        "aggregation": result.aggregation.value,
        "requested_center_time_ns": result.requested_center_time_ns,
        "requested_window_width_ns": result.requested_window_width_ns,
        "selected_sample_index": result.selected_sample_index,
        "sample_start_index": result.sample_start_index,
        "sample_stop_index": result.sample_stop_index,
        "actual_start_time_ns": result.actual_start_time_ns,
        "actual_stop_time_ns": result.actual_stop_time_ns,
        "result_shape": list(result.values.shape),
        "valid_count": result.statistics.valid_count,
        "invalid_count": result.statistics.invalid_count,
        "min_value": result.statistics.min_value,
        "max_value": result.statistics.max_value,
        "mean_value": result.statistics.mean_value,
        "display_colormap": colormap,
        "display_min": display_min,
        "display_max": display_max,
        "geometry_view_mode": geometry_view.value,
        "crs_identifier": crs_identifier,
        "crs_validation_status": crs_validation_status,
        # True regardless of geometry_view_mode: this sprint performs no spatial
        # interpolation/resampling/gridding of any kind (see ADR-017 Scope) — a
        # cell's value is always the raw aggregation at its own (trace, channel),
        # whether plotted at its actual X/Y position or at an idealized s/c
        # position. This flag documents that guarantee for downstream consumers.
        "no_interpolation": True,
        "warnings": list(result.warnings),
    }
    return _json_safe(payload)


def export_cscan_report(
    result: CScanResult,
    output_path: str | Path,
    *,
    source_path: Path,
    geometry_view: CScanGeometryView,
    colormap: str,
    display_min: float,
    display_max: float,
    crs_identifier: str | None,
    crs_validation_status: str,
) -> Path:
    """Write the C-scan report to ``output_path`` atomically (temp file + ``os.replace``)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_cscan_report(
        result,
        source_path=source_path,
        geometry_view=geometry_view,
        colormap=colormap,
        display_min=display_min,
        display_max=display_max,
        crs_identifier=crs_identifier,
        crs_validation_status=crs_validation_status,
    )
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
