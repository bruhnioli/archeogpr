"""Sprint 3 exports: safe loading of a Sprint 2-style processed NPZ, plus
dewow/band-pass-specific QC exports.

``write_corrected_npz``/``write_combined_npz`` (``export/processed.py``) remain
the writers for a single ``ProcessingResult`` -- dewow and band-pass results
reuse them unchanged. This module adds only what's new for Sprint 3: reading
a processed NPZ back into a ``GPRDataset`` (+ its ``valid_mask``, since that
isn't a ``GPRDataset`` field), and a padding-verification report.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from archaeogpr.model._frozen import freeze_array
from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing.common import ProcessingError
from archaeogpr.processing.result import ProcessingResult

#: Documented stage order (see Processing_Order in the vault) -- later stages
#: must not precede earlier ones if both are present in a loaded history.
_KNOWN_STAGE_ORDER = (
    "time_zero_correction",
    "dc_offset_correction",
    "dewow_correction",
    "bandpass_correction",
)

_REQUIRED_NPZ_KEYS = ("amplitudes", "time_ns", "metadata_json", "processing_history_json", "has_valid_mask")

_OPTIONAL_COORDINATE_KEYS = (
    "x",
    "y",
    "x_bottom",
    "y_bottom",
    "depth_top_m",
    "elevation_top_m",
    "depth_bottom_m",
    "elevation_bottom_m",
)


def _validate_processing_order(operations: list[str], source: Path) -> None:
    """Raise ``ProcessingError`` if two known stages appear out of their documented order."""
    positions = {op: i for i, op in enumerate(_KNOWN_STAGE_ORDER)}
    seen: list[tuple[int, str]] = []
    for operation in operations:
        if operation not in positions:
            continue  # an unrecognized/future operation -- not ours to order-check
        seen.append((positions[operation], operation))
    for (pos_a, op_a), (pos_b, op_b) in zip(seen, seen[1:], strict=False):
        if pos_b < pos_a:
            raise ProcessingError(
                f"{source}: processing_history has {op_b!r} appearing after {op_a!r}, "
                f"which violates the documented stage order {_KNOWN_STAGE_ORDER}"
            )


def read_processed_npz(path: str | Path) -> tuple[GPRDataset, np.ndarray | None]:
    """Load a Sprint 2/3-style processed NPZ back into a ``(GPRDataset, valid_mask)`` pair.

    ``valid_mask`` is returned alongside rather than as a ``GPRDataset`` field
    (it never is one -- see ``ProcessingResult.valid_mask``) so callers can
    feed it straight into ``correct_dewow``/``correct_bandpass``.

    Reads with ``allow_pickle=False`` -- every array this project ever writes
    is numeric or a plain unicode string (JSON text), never a pickled Python
    object, so this is a real safety property, not a formality. Raises
    ``ProcessingError`` for any missing required key, invalid JSON, or a
    processing_history whose known stages are out of documented order.
    Coordinate/elevation arrays (``x``, ``y``, ...) are optional -- absent in
    e.g. the Sprint 2 canonical NPZ (an export gap predating this loader, not
    something this function silently invents data for) and restored as
    ``None`` when missing, exactly like a ``GPRDataset`` with no geolocation.
    """
    path = Path(path)
    with np.load(path, allow_pickle=False) as npz:
        missing = [key for key in _REQUIRED_NPZ_KEYS if key not in npz.files]
        if missing:
            raise ProcessingError(f"{path}: missing required NPZ key(s): {missing}")

        try:
            metadata = json.loads(npz["metadata_json"].item())
        except (ValueError, TypeError) as exc:
            raise ProcessingError(f"{path}: metadata_json is not valid JSON: {exc}") from exc
        if not isinstance(metadata, dict):
            raise ProcessingError(
                f"{path}: metadata_json must decode to a JSON object, got {type(metadata).__name__}"
            )

        try:
            history_list = json.loads(npz["processing_history_json"].item())
        except (ValueError, TypeError) as exc:
            raise ProcessingError(f"{path}: processing_history_json is not valid JSON: {exc}") from exc
        if not isinstance(history_list, list) or not all(
            isinstance(record, dict) and "operation" in record for record in history_list
        ):
            raise ProcessingError(
                f"{path}: processing_history_json must be a list of records, each with an 'operation' key"
            )
        _validate_processing_order([record["operation"] for record in history_list], path)

        amplitudes = np.array(npz["amplitudes"])
        time_ns = np.array(npz["time_ns"])

        channels_count, samples_count = amplitudes.shape[1], amplitudes.shape[2]
        has_valid_mask = bool(npz["has_valid_mask"])
        valid_mask: np.ndarray | None = None
        if has_valid_mask:
            if "valid_mask" not in npz.files:
                raise ProcessingError(f"{path}: has_valid_mask=True but 'valid_mask' key is missing")
            valid_mask = freeze_array("valid_mask", np.array(npz["valid_mask"]), ndim=2)
            if valid_mask is not None and valid_mask.shape != (channels_count, samples_count):
                raise ProcessingError(
                    f"{path}: valid_mask shape {valid_mask.shape} does not match "
                    f"(channels, samples)={(channels_count, samples_count)} from amplitudes"
                )

        coordinates: dict[str, np.ndarray | None] = {
            key: (np.array(npz[key]) if key in npz.files else None) for key in _OPTIONAL_COORDINATE_KEYS
        }

    dataset = GPRDataset(
        amplitudes=amplitudes,
        time_ns=time_ns,
        metadata=metadata,
        processing_history=tuple(history_list),
        **coordinates,
    )
    return dataset, valid_mask


def load_candidates_config(path: str | Path) -> dict[str, Any]:
    """Load a ``configs/*_candidates.yaml`` file with ``yaml.safe_load``.

    Raises ``ProcessingError`` if the file doesn't decode to a mapping.
    """
    path = Path(path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ProcessingError(
            f"{path}: expected a YAML mapping at the top level, got {type(loaded).__name__}"
        )
    return loaded


def write_padding_verification_json(
    result: ProcessingResult,
    output_path: str | Path,
    *,
    fill_value: float = 0.0,
) -> Path:
    """Save a compact report proving padding was excluded from and unaffected by this stage.

    Compares ``result.dataset.amplitudes`` at padding positions (``~valid_mask``)
    against ``fill_value`` and confirms ``removed_component`` is exactly zero
    there. Raises ``ProcessingError`` if ``result.valid_mask`` is ``None``
    (nothing to verify).
    """
    if result.valid_mask is None:
        raise ProcessingError("write_padding_verification_json requires result.valid_mask, got None")

    valid_mask = result.valid_mask
    amplitudes = result.dataset.amplitudes
    removed = result.removed_component
    channels_count = valid_mask.shape[0]

    per_channel: dict[str, Any] = {}
    all_padding_untouched = True
    all_removed_zero_at_padding = True
    for channel in range(channels_count):
        padding_positions = ~valid_mask[channel]
        padding_count = int(padding_positions.sum())
        if padding_count == 0:
            per_channel[str(channel)] = {"padding_count": 0}
            continue
        padding_values = amplitudes[:, channel, padding_positions].astype(np.float64)
        removed_at_padding = removed[:, channel, padding_positions].astype(np.float64)
        untouched = bool(np.all(padding_values == fill_value))
        removed_zero = bool(np.all(removed_at_padding == 0.0))
        all_padding_untouched = all_padding_untouched and untouched
        all_removed_zero_at_padding = all_removed_zero_at_padding and removed_zero
        per_channel[str(channel)] = {
            "padding_count": padding_count,
            "unique_padding_values": [float(v) for v in np.unique(padding_values)],
            "padding_min": float(padding_values.min()),
            "padding_max": float(padding_values.max()),
            "padding_untouched": untouched,
            "removed_component_zero_at_padding": removed_zero,
        }

    report: dict[str, Any] = {
        "fill_value": fill_value,
        "all_channels_padding_untouched": all_padding_untouched,
        "all_channels_removed_component_zero_at_padding": all_removed_zero_at_padding,
        "per_channel": per_channel,
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return output_path
