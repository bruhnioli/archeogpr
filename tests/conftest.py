"""Shared test fixtures: a from-scratch OpenGPR (.ogpr) byte builder.

Building bytes here (rather than depending on the real sample file) lets
unit tests exercise every reader code path deterministically, without any
external file dependency. The layout mirrors the real format exactly
(magic/checksum/header-size preamble, JSON header, then binary blocks placed
at the byte offsets the header declares).
"""

from __future__ import annotations

import json
import struct
from typing import Any

import numpy as np
import pytest

from archaeogpr.model.dataset import GPRDataset

GEO_FIELDS_PER_CHANNEL = 8
CHECKSUM_PLACEHOLDER = "0" * 32
PREAMBLE_LEN = len("ogpr\n") + len(CHECKSUM_PLACEHOLDER) + 1 + 8 + 1  # magic + checksum + header-size lines


def _build_geo_bytes(slices_count: int, channels_count: int) -> bytes:
    chunks = []
    for s in range(slices_count):
        row = struct.pack("<q", s)
        for c in range(channels_count):
            x_top = 500000.0 + s * 1.0 + c * 0.5
            y_top = 4_000_000.0 + s * 0.1
            depth_top, elevation_top = 0.0, 10.0 - c * 0.01
            depth_bottom, elevation_bottom = -2.0, elevation_top - 2.0
            row += struct.pack(
                "<8d", x_top, y_top, depth_top, elevation_top, x_top, y_top, depth_bottom, elevation_bottom
            )
        chunks.append(row)
    return b"".join(chunks)


def build_synthetic_ogpr_bytes(
    *,
    slices_count: int = 3,
    channels_count: int = 2,
    samples_count: int = 4,
    sampling_time_ns: float = 0.5,
    value_type: str = "float",
    include_geolocation: bool = True,
    frequency_field: str = "frequency_MHz",
    frequency_value: float = 200.0,
    radar_byte_size_override: int | None = None,
    geo_byte_size_override: int | None = None,
    truncate_last_bytes: int = 0,
    corrupt_magic: bool = False,
    corrupt_json: bool = False,
    omit_radar_block: bool = False,
) -> bytes:
    """Build a complete .ogpr byte string; the corrupt_*/omit_* flags introduce one specific defect."""
    itemsize = 4  # float32; this builder only ever writes physically-real "float" data
    radar_count = slices_count * channels_count * samples_count
    real_radar_byte_size = radar_count * itemsize
    radar_bytes = (np.arange(radar_count, dtype="<f4") - radar_count / 2.0).tobytes()

    geo_record_size = 8 + channels_count * GEO_FIELDS_PER_CHANNEL * 8
    real_geo_byte_size = geo_record_size * slices_count
    geo_bytes = _build_geo_bytes(slices_count, channels_count) if include_geolocation else b""

    declared_radar_byte_size = (
        real_radar_byte_size if radar_byte_size_override is None else radar_byte_size_override
    )
    declared_geo_byte_size = real_geo_byte_size if geo_byte_size_override is None else geo_byte_size_override

    def assemble_header(radar_offset: int) -> dict[str, Any]:
        blocks: list[dict[str, Any]] = []
        if not omit_radar_block:
            blocks.append(
                {
                    "type": "Radar Volume",
                    "name": "Synthetic Radar Data Volume",
                    "byteOffset": radar_offset,
                    "byteSize": declared_radar_byte_size,
                    "radar": {
                        "samplingStep_m": 0.1,
                        "samplingTime_ns": sampling_time_ns,
                        "propagationVelocity_mPerSec": 1.0e8,
                        frequency_field: frequency_value,
                        "polarization": "horizontal",
                    },
                    "valueType": value_type,
                    "metadata": {"processing": None},
                }
            )
        if include_geolocation:
            blocks.append(
                {
                    "type": "Sample Geolocations",
                    "name": "Synthetic Sample Geographic Locations",
                    "byteOffset": radar_offset + real_radar_byte_size,
                    "byteSize": declared_geo_byte_size,
                    "srs": {"type": "EPSG", "value": 32632},
                }
            )
        return {
            "version": {"major": 2, "minor": 0},
            "mainDescriptor": {
                "samplesCount": samples_count,
                "channelsCount": channels_count,
                "slicesCount": slices_count,
                "metadata": {"swathName": "SynthSwath", "swathId": "synth-id", "arrayId": 1},
            },
            "dataBlockDescriptors": blocks,
        }

    radar_offset_guess = PREAMBLE_LEN
    header_json = b""
    for _ in range(6):
        header_json = json.dumps(assemble_header(radar_offset_guess)).encode("utf-8")
        new_offset = PREAMBLE_LEN + len(header_json)
        if new_offset == radar_offset_guess:
            break
        radar_offset_guess = new_offset
    else:
        raise RuntimeError("synthetic header offset did not converge; adjust test fixture sizes")

    if corrupt_json:
        header_json = b"{not-valid-json"

    header_size_field = f"{len(header_json):08d}".encode("ascii")
    assert len(header_size_field) == 8, "header size exceeds 8 digits; adjust test fixture sizes"

    magic = b"XXXX" if corrupt_magic else b"ogpr"
    preamble = magic + b"\n" + CHECKSUM_PLACEHOLDER.encode("ascii") + b"\n" + header_size_field + b"\n"
    assert len(preamble) == PREAMBLE_LEN

    full = preamble + header_json + radar_bytes + geo_bytes
    if truncate_last_bytes:
        full = full[:-truncate_last_bytes]
    return full


@pytest.fixture
def ogpr_builder():
    """Returns the builder function itself, so tests can pass their own overrides."""
    return build_synthetic_ogpr_bytes


@pytest.fixture
def valid_ogpr_path(tmp_path):
    """A ready-to-read synthetic .ogpr file at default size (3 slices, 2 channels, 4 samples)."""
    path = tmp_path / "synthetic.ogpr"
    path.write_bytes(build_synthetic_ogpr_bytes())
    return path


def make_gpr_dataset(
    *,
    slices_count: int = 6,
    channels_count: int = 4,
    samples_count: int = 200,
    sampling_time_ns: float = 0.5,
    amplitudes: np.ndarray | None = None,
    metadata: dict[str, Any] | None = None,
    time_ns: np.ndarray | None = None,
) -> GPRDataset:
    """A synthetic GPRDataset for archaeogpr.processing tests — no geolocation, no real file needed.

    ``time_ns``, if given, overrides the default ``arange(samples)*sampling_time_ns``
    axis — used to build datasets that already look time-zero-relative
    (e.g. starting negative) without going through ``correct_time_zero()``.
    """
    if amplitudes is None:
        amplitudes = np.zeros((slices_count, channels_count, samples_count), dtype=np.float32)
    else:
        slices_count, channels_count, samples_count = amplitudes.shape

    full_metadata: dict[str, Any] = {
        "sampling": {"sampling_time_ns": sampling_time_ns},
        "radar": {},
        "warnings": [],
    }
    if metadata:
        full_metadata.update(metadata)

    return GPRDataset(
        amplitudes=amplitudes,
        time_ns=(
            time_ns if time_ns is not None else np.arange(samples_count, dtype=np.float64) * sampling_time_ns
        ),
        x=None,
        y=None,
        depth_top_m=None,
        elevation_top_m=None,
        depth_bottom_m=None,
        elevation_bottom_m=None,
        metadata=full_metadata,
    )


@pytest.fixture
def dataset_factory():
    """Returns make_gpr_dataset itself, so tests can pass their own overrides."""
    return make_gpr_dataset
