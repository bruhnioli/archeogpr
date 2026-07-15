"""Unit tests for archaeogpr.io.ogpr_reader, using synthetic .ogpr fixtures.

See conftest.py for the ogpr_builder/valid_ogpr_path fixtures.
"""

from __future__ import annotations

import numpy as np
import pytest

from archaeogpr.io.exceptions import (
    InconsistentDimensionsError,
    InvalidGeolocationBlockError,
    InvalidHeaderError,
    InvalidMagicError,
    MissingRadarBlockError,
    TruncatedBlockError,
    UnsupportedValueTypeError,
)
from archaeogpr.io.ogpr_reader import read_ogpr, read_ogpr_header


def test_invalid_magic_is_rejected(tmp_path, ogpr_builder):
    path = tmp_path / "bad_magic.ogpr"
    path.write_bytes(ogpr_builder(corrupt_magic=True))
    with pytest.raises(InvalidMagicError):
        read_ogpr_header(path)


def test_invalid_json_header_is_rejected(tmp_path, ogpr_builder):
    path = tmp_path / "bad_json.ogpr"
    path.write_bytes(ogpr_builder(corrupt_json=True))
    with pytest.raises(InvalidHeaderError):
        read_ogpr_header(path)


def test_missing_radar_block_raises(tmp_path, ogpr_builder):
    path = tmp_path / "no_radar.ogpr"
    path.write_bytes(ogpr_builder(omit_radar_block=True, include_geolocation=False))
    with pytest.raises(MissingRadarBlockError):
        read_ogpr(path)


def test_unsupported_value_type_raises(tmp_path, ogpr_builder):
    path = tmp_path / "bad_type.ogpr"
    path.write_bytes(ogpr_builder(value_type="int16"))
    with pytest.raises(UnsupportedValueTypeError):
        read_ogpr(path)


def test_truncated_radar_block_raises(tmp_path, ogpr_builder):
    path = tmp_path / "short.ogpr"
    path.write_bytes(ogpr_builder(include_geolocation=False, truncate_last_bytes=5))
    with pytest.raises(TruncatedBlockError):
        read_ogpr(path)


def test_inconsistent_radar_dimensions_raises(tmp_path, ogpr_builder):
    path = tmp_path / "inconsistent.ogpr"
    path.write_bytes(ogpr_builder(radar_byte_size_override=999_999))
    with pytest.raises(InconsistentDimensionsError):
        read_ogpr(path)


def test_invalid_geolocation_block_raises(tmp_path, ogpr_builder):
    path = tmp_path / "bad_geo.ogpr"
    path.write_bytes(ogpr_builder(geo_byte_size_override=123))
    with pytest.raises(InvalidGeolocationBlockError):
        read_ogpr(path)


def test_radar_dimensions_are_reshaped_correctly(valid_ogpr_path):
    dataset = read_ogpr(valid_ogpr_path)
    assert dataset.shape == (3, 2, 4)
    assert dataset.amplitudes.dtype == np.dtype("<f4")
    count = 3 * 2 * 4
    expected = (np.arange(count, dtype="<f4") - count / 2.0).reshape(3, 2, 4)
    np.testing.assert_array_equal(dataset.amplitudes, expected)


def test_time_ns_axis_is_correct(valid_ogpr_path):
    dataset = read_ogpr(valid_ogpr_path)
    np.testing.assert_allclose(dataset.time_ns, np.arange(4) * 0.5)


def test_file_without_geolocation_opens_with_radar_data(tmp_path, ogpr_builder):
    path = tmp_path / "no_geo.ogpr"
    path.write_bytes(ogpr_builder(include_geolocation=False))
    dataset = read_ogpr(path)
    assert dataset.has_geolocation is False
    assert dataset.x is None
    assert dataset.y is None
    assert dataset.shape == (3, 2, 4)
    assert any("Sample Geolocations block not found" in w for w in dataset.metadata["warnings"])


def test_frequency_typo_fallback_is_supported(tmp_path, ogpr_builder):
    path = tmp_path / "typo_freq.ogpr"
    path.write_bytes(ogpr_builder(frequency_field="fequency_MHz", frequency_value=600.0))
    dataset = read_ogpr(path)
    assert dataset.metadata["radar"]["nominal_frequency_MHz"] == 600.0


def test_read_ogpr_header_exposes_raw_header(valid_ogpr_path):
    header_info = read_ogpr_header(valid_ogpr_path)
    assert header_info.header["mainDescriptor"]["slicesCount"] == 3
    assert header_info.checksum == "0" * 32
    assert header_info.magic == "ogpr"


def test_geolocation_fields_round_trip(valid_ogpr_path):
    dataset = read_ogpr(valid_ogpr_path)
    # Fixture writes x_top == x_bottom, y_top == y_bottom (vertical traces).
    np.testing.assert_array_equal(dataset.x, dataset.x_bottom)
    np.testing.assert_array_equal(dataset.y, dataset.y_bottom)
    np.testing.assert_allclose(dataset.elevation_top_m - dataset.elevation_bottom_m, 2.0)
