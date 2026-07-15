"""Reader for OpenGPR (``.ogpr``) files produced by IDS GeoRadar systems.

File layout (validated against a real ``Swath003_Array02.ogpr`` sample; see
``obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/OpenGPR_File_Structure.md``)::

    b"ogpr"                     magic line
    <32-char checksum>          text line
    <8-digit header byte size>  text line, zero-padded ASCII decimal
    <JSON header>                exactly headerSize bytes, no trailing newline
    <data blocks...>             raw binary, positioned by absolute byteOffset

Every byte offset, byte size, value type, and dimension used to decode the
binary blocks is read from the JSON header's ``mainDescriptor`` and
``dataBlockDescriptors`` — nothing is hardcoded from the sample file. The one
exception is the internal record layout of the ``Sample Geolocations`` block,
which has no per-field descriptor in the header at all; that layout is
documented and validated in :func:`_read_geolocations` below, and a byte-size
consistency check guards against silently misreading a differently-shaped
block.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from archaeogpr.io.exceptions import (
    InconsistentDimensionsError,
    InvalidGeolocationBlockError,
    InvalidHeaderError,
    InvalidMagicError,
    MissingRadarBlockError,
    OGPRError,
    TruncatedBlockError,
    UnsupportedValueTypeError,
)
from archaeogpr.model.dataset import GPRDataset

EXPECTED_MAGIC = "ogpr"

# Maps the header's "valueType" string to a numpy dtype. The header has no
# explicit byte-order field for this OpenGPR version; little-endian is the
# validated default (see _resolve_dtype), overridable if a future variant
# adds an explicit byteOrder/endianness field.
_VALUE_TYPE_DTYPES: dict[str, np.dtype] = {
    "float": np.dtype("<f4"),
}

# OpenGPR v2 "Sample Geolocations" per-channel field order, validated against
# a real sample file (Section 3 of the Sprint 1 task). Not documented
# per-field in the JSON header.
GEOLOCATION_FIELD_ORDER = (
    "x_top",
    "y_top",
    "depth_top_m",
    "elevation_top_m",
    "x_bottom",
    "y_bottom",
    "depth_bottom_m",
    "elevation_bottom_m",
)


@dataclass(frozen=True)
class OgprHeaderInfo:
    """Raw preamble + parsed JSON header of an ``.ogpr`` file."""

    magic: str
    checksum: str
    header_size: int
    header: Mapping[str, Any]
    header_byte_range: tuple[int, int]


def read_ogpr_header(path: str | Path) -> OgprHeaderInfo:
    """Read and parse only the text preamble + JSON header of an ``.ogpr`` file.

    Does not touch any binary data block. Raises ``InvalidMagicError`` or
    ``InvalidHeaderError`` if the preamble/header is malformed.
    """
    path = Path(path)
    try:
        with open(path, "rb") as f:
            magic_line = f.readline()
            checksum_line = f.readline()
            header_size_line = f.readline()
            preamble_end = f.tell()

            magic = magic_line.rstrip(b"\r\n").decode("ascii", errors="replace")
            if magic != EXPECTED_MAGIC:
                raise InvalidMagicError(
                    f"{path}: expected magic {EXPECTED_MAGIC!r} on line 1, found {magic!r}"
                )

            checksum = checksum_line.rstrip(b"\r\n").decode("ascii", errors="replace")
            if not checksum:
                raise InvalidHeaderError(f"{path}: checksum line (line 2) is empty or missing")

            header_size_text = header_size_line.rstrip(b"\r\n").decode("ascii", errors="replace")
            try:
                header_size = int(header_size_text)
            except ValueError as exc:
                raise InvalidHeaderError(
                    f"{path}: header size line (line 3) is not an integer: {header_size_text!r}"
                ) from exc
            if header_size <= 0:
                raise InvalidHeaderError(f"{path}: header size must be a positive integer, got {header_size}")

            header_bytes = f.read(header_size)
            if len(header_bytes) != header_size:
                raise InvalidHeaderError(
                    f"{path}: header declares {header_size} bytes but only "
                    f"{len(header_bytes)} were available in the file"
                )
            header_end = f.tell()
    except OSError as exc:
        raise OGPRError(f"Could not read {path}: {exc}") from exc

    try:
        header = json.loads(header_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidHeaderError(f"{path}: header is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(header, dict):
        raise InvalidHeaderError(f"{path}: header JSON must be an object, got {type(header).__name__}")

    return OgprHeaderInfo(
        magic=magic,
        checksum=checksum,
        header_size=header_size,
        header=header,
        header_byte_range=(preamble_end, header_end),
    )


def read_ogpr(path: str | Path) -> GPRDataset:
    """Read a full OpenGPR file into an immutable :class:`GPRDataset`.

    Always reads the ``Radar Volume`` block (required — raises
    ``MissingRadarBlockError`` if absent). Reads the ``Sample Geolocations``
    block if present; if it is absent, coordinate/depth/elevation fields are
    ``None`` and a warning is recorded in ``dataset.metadata["warnings"]``.
    """
    path = Path(path)
    header_info = read_ogpr_header(path)
    header = header_info.header
    warnings_list: list[str] = []

    version_info = header.get("version")
    if isinstance(version_info, dict) and "major" in version_info and "minor" in version_info:
        version_str: str | None = f"{version_info['major']}.{version_info['minor']}"
    else:
        version_str = None
        warnings_list.append("Header has no valid 'version' object; OpenGPR version is unknown.")

    main_descriptor = header.get("mainDescriptor")
    if not isinstance(main_descriptor, dict):
        raise InvalidHeaderError(f"{path}: header has no 'mainDescriptor' object")
    samples_count = _require_int(main_descriptor, "samplesCount", path, context="mainDescriptor")
    channels_count = _require_int(main_descriptor, "channelsCount", path, context="mainDescriptor")
    slices_count = _require_int(main_descriptor, "slicesCount", path, context="mainDescriptor")
    main_metadata = main_descriptor.get("metadata")
    if not isinstance(main_metadata, dict):
        main_metadata = {}

    block_descriptors = header.get("dataBlockDescriptors")
    if not isinstance(block_descriptors, list):
        raise InvalidHeaderError(f"{path}: header has no 'dataBlockDescriptors' list")

    file_size = path.stat().st_size

    radar_descriptor = _find_data_block(block_descriptors, "Radar Volume")
    if radar_descriptor is None:
        raise MissingRadarBlockError(f"{path}: no data block with type 'Radar Volume' found")

    amplitudes = _read_radar_volume(
        path, radar_descriptor, slices_count, channels_count, samples_count, file_size
    )

    radar_params = radar_descriptor.get("radar")
    if not isinstance(radar_params, dict):
        raise InvalidHeaderError(f"{path}: 'Radar Volume' block has no 'radar' parameter object")
    sampling_time_ns = _require_float(radar_params, "samplingTime_ns", path, context="Radar Volume.radar")
    time_ns = np.arange(samples_count, dtype=np.float64) * sampling_time_ns

    sampling_step_m = _optional_float(radar_params, "samplingStep_m")
    propagation_velocity_m_per_sec = _optional_float(radar_params, "propagationVelocity_mPerSec")
    # "fequency_MHz" is a typo present in real files alongside/instead of the correct spelling.
    frequency_mhz = _optional_float(radar_params, "frequency_MHz", "fequency_MHz")
    polarization = radar_params.get("polarization")
    if not isinstance(polarization, str):
        polarization = None

    if sampling_step_m is None:
        warnings_list.append("radar.samplingStep_m not found; along-track sampling step is unknown.")
    if propagation_velocity_m_per_sec is None:
        warnings_list.append(
            "radar.propagationVelocity_mPerSec not found; depth estimates are not available."
        )
    if frequency_mhz is None:
        warnings_list.append("Nominal frequency not found under 'frequency_MHz' or 'fequency_MHz'.")
    if polarization is None:
        warnings_list.append("radar.polarization not found.")

    geo_descriptor = _find_data_block(block_descriptors, "Sample Geolocations")
    srs: Any = None
    if geo_descriptor is None:
        warnings_list.append(
            "Sample Geolocations block not found; x, y, depth_*_m and elevation_*_m are None."
        )
        x = y = depth_top_m = elevation_top_m = depth_bottom_m = elevation_bottom_m = None
        x_bottom = y_bottom = None
    else:
        geo = _read_geolocations(path, geo_descriptor, slices_count, channels_count, file_size)
        warnings_list.extend(geo["warnings"])
        x, y = geo["x_top"], geo["y_top"]
        x_bottom, y_bottom = geo["x_bottom"], geo["y_bottom"]
        depth_top_m, elevation_top_m = geo["depth_top_m"], geo["elevation_top_m"]
        depth_bottom_m, elevation_bottom_m = geo["depth_bottom_m"], geo["elevation_bottom_m"]
        srs = geo_descriptor.get("srs")
        warnings_list.append(
            "Spatial reference (srs) metadata is read as stored in the file header and has not "
            "been independently validated; coordinates are shown as stored and are not reprojected."
        )
        if geo["max_top_bottom_horizontal_offset_m"] > 1e-6:
            warnings_list.append(
                "Top and bottom horizontal positions differ for at least one trace by up to "
                f"{geo['max_top_bottom_horizontal_offset_m']:.4g} m; 'x'/'y' store the top position only."
            )

    metadata: dict[str, Any] = {
        "source_file": {"name": path.name, "path": str(path), "size_bytes": file_size},
        "opengpr_version": version_str,
        "checksum": header_info.checksum,
        "swath_name": main_metadata.get("swathName"),
        "swath_id": main_metadata.get("swathId"),
        "array_id": main_metadata.get("arrayId"),
        "dimensions": {
            "slices_count": slices_count,
            "channels_count": channels_count,
            "samples_count": samples_count,
            "axis_order": ["slice", "channel", "sample"],
        },
        "dtype": str(amplitudes.dtype),
        "sampling": {
            "sampling_time_ns": sampling_time_ns,
            "sampling_step_m": sampling_step_m,
        },
        "radar": {
            "nominal_frequency_MHz": frequency_mhz,
            "polarization": polarization,
            "propagation_velocity_m_per_sec": propagation_velocity_m_per_sec,
            "propagation_velocity_m_per_ns": (
                propagation_velocity_m_per_sec / 1e9 if propagation_velocity_m_per_sec is not None else None
            ),
        },
        "geolocation_present": geo_descriptor is not None,
        "spatial_reference": srs,
        "warnings": warnings_list,
    }

    return GPRDataset(
        amplitudes=amplitudes,
        time_ns=time_ns,
        x=x,
        y=y,
        depth_top_m=depth_top_m,
        elevation_top_m=elevation_top_m,
        depth_bottom_m=depth_bottom_m,
        elevation_bottom_m=elevation_bottom_m,
        metadata=metadata,
        processing_history=(),
        x_bottom=x_bottom,
        y_bottom=y_bottom,
    )


def _read_radar_volume(
    path: Path,
    descriptor: Mapping[str, Any],
    slices_count: int,
    channels_count: int,
    samples_count: int,
    file_size: int,
) -> np.ndarray:
    byte_offset = _require_int(descriptor, "byteOffset", path, context="Radar Volume")
    byte_size = _require_int(descriptor, "byteSize", path, context="Radar Volume")
    dtype = _resolve_dtype(descriptor, path)

    expected_count = slices_count * channels_count * samples_count
    expected_bytes = expected_count * dtype.itemsize
    if byte_size != expected_bytes:
        raise InconsistentDimensionsError(
            f"{path}: Radar Volume byteSize={byte_size} does not match "
            f"slicesCount*channelsCount*samplesCount*itemsize="
            f"{slices_count}*{channels_count}*{samples_count}*{dtype.itemsize}={expected_bytes}"
        )
    _check_range(path, "Radar Volume", byte_offset, byte_size, file_size)

    raw = _read_bytes(path, byte_offset, byte_size, "Radar Volume")
    flat = np.frombuffer(raw, dtype=dtype, count=expected_count)
    return flat.reshape(slices_count, channels_count, samples_count)


def _read_geolocations(
    path: Path,
    descriptor: Mapping[str, Any],
    slices_count: int,
    channels_count: int,
    file_size: int,
) -> dict[str, Any]:
    byte_offset = _require_int(descriptor, "byteOffset", path, context="Sample Geolocations")
    byte_size = _require_int(descriptor, "byteSize", path, context="Sample Geolocations")

    record_dtype = np.dtype(
        [
            ("slice_index", "<i8"),
            ("fields", "<f8", (channels_count, len(GEOLOCATION_FIELD_ORDER))),
        ]
    )
    expected_bytes = record_dtype.itemsize * slices_count
    if byte_size != expected_bytes:
        raise InvalidGeolocationBlockError(
            f"{path}: Sample Geolocations byteSize={byte_size} does not match the expected "
            f"record layout ({record_dtype.itemsize} bytes/slice * {slices_count} slices = "
            f"{expected_bytes}); this file's geolocation block may use a different record schema "
            "than the one this reader knows how to decode"
        )
    _check_range(path, "Sample Geolocations", byte_offset, byte_size, file_size)

    raw = _read_bytes(path, byte_offset, byte_size, "Sample Geolocations")
    records = np.frombuffer(raw, dtype=record_dtype, count=slices_count)

    geo_warnings: list[str] = []
    if not np.array_equal(records["slice_index"], np.arange(slices_count)):
        geo_warnings.append(
            "Sample Geolocations leading index field is not a plain 0..N-1 sequence; its meaning "
            "is not documented in the OpenGPR header and was not used further."
        )

    fields = records["fields"]  # view: (slices, channels, len(GEOLOCATION_FIELD_ORDER))
    result: dict[str, Any] = {name: fields[:, :, i] for i, name in enumerate(GEOLOCATION_FIELD_ORDER)}
    horizontal_offset = np.hypot(result["x_top"] - result["x_bottom"], result["y_top"] - result["y_bottom"])
    result["max_top_bottom_horizontal_offset_m"] = float(np.max(horizontal_offset))
    result["warnings"] = geo_warnings
    return result


def _read_bytes(path: Path, byte_offset: int, byte_size: int, block_label: str) -> bytes:
    with open(path, "rb") as f:
        f.seek(byte_offset)
        raw = f.read(byte_size)
    if len(raw) != byte_size:
        raise TruncatedBlockError(
            f"{path}: expected to read {byte_size} bytes for {block_label} at offset {byte_offset}, "
            f"got only {len(raw)}"
        )
    return raw


def _check_range(path: Path, block_label: str, byte_offset: int, byte_size: int, file_size: int) -> None:
    if byte_offset < 0 or byte_size < 0 or byte_offset + byte_size > file_size:
        raise TruncatedBlockError(
            f"{path}: {block_label} block needs bytes [{byte_offset}, {byte_offset + byte_size}) "
            f"but the file is only {file_size} bytes"
        )


def _resolve_dtype(descriptor: Mapping[str, Any], path: Path) -> np.dtype:
    value_type = descriptor.get("valueType")
    if not isinstance(value_type, str):
        raise InvalidHeaderError(f"{path}: Radar Volume block has no 'valueType' string field")
    key = value_type.strip().lower()
    base_dtype = _VALUE_TYPE_DTYPES.get(key)
    if base_dtype is None:
        raise UnsupportedValueTypeError(
            f"{path}: unsupported radar valueType {value_type!r}; supported types: "
            f"{sorted(_VALUE_TYPE_DTYPES)}"
        )

    byte_order = _first_present(descriptor, "byteOrder", "endianness", "endian")
    if byte_order is None:
        # OpenGPR v2 header has no explicit byte-order field; little-endian is
        # the validated default for this format.
        return base_dtype
    normalized = str(byte_order).strip().lower()
    if normalized in ("little", "<", "little-endian", "le"):
        return base_dtype.newbyteorder("<")
    if normalized in ("big", ">", "big-endian", "be"):
        return base_dtype.newbyteorder(">")
    raise UnsupportedValueTypeError(f"{path}: unrecognized byte order {byte_order!r}")


def _find_data_block(descriptors: list[Any], block_type: str) -> dict[str, Any] | None:
    normalized = block_type.lower()
    for entry in descriptors:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("type"), str)
            and entry["type"].strip().lower() == normalized
        ):
            return entry
    # Controlled fallback for files where 'type' is missing/renamed but the
    # block is still identifiable from its descriptive 'name'.
    for entry in descriptors:
        if (
            isinstance(entry, dict)
            and isinstance(entry.get("name"), str)
            and normalized in entry["name"].lower()
        ):
            return entry
    return None


def _first_present(d: Mapping[str, Any], *keys: str) -> Any | None:
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return None


def _optional_float(d: Mapping[str, Any], *keys: str) -> float | None:
    value = _first_present(d, *keys)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _require_int(d: Mapping[str, Any], key: str, path: Path, *, context: str) -> int:
    if key not in d:
        raise InvalidHeaderError(f"{path}: '{context}.{key}' is required but missing")
    value = d[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidHeaderError(f"{path}: '{context}.{key}' must be an integer, got {value!r}")
    return value


def _require_float(d: Mapping[str, Any], key: str, path: Path, *, context: str) -> float:
    if key not in d:
        raise InvalidHeaderError(f"{path}: '{context}.{key}' is required but missing")
    value = d[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidHeaderError(f"{path}: '{context}.{key}' must be a number, got {value!r}")
    return float(value)
