"""Integration test against the real Swath003_Array02.ogpr sample file.

Skips cleanly (not a failure) if the file is not present under data/raw/ —
this repository does not ship the proprietary sample file itself.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from archaeogpr.io.ogpr_reader import read_ogpr

_REAL_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "Swath003_Array02.ogpr"

pytestmark = pytest.mark.skipif(
    not _REAL_FILE.is_file(),
    reason=f"Real sample file not found at {_REAL_FILE}; skipping integration test.",
)


def test_real_file_matches_documented_metadata():
    dataset = read_ogpr(_REAL_FILE)

    assert dataset.shape == (175, 11, 1024)
    assert dataset.amplitudes.dtype == np.dtype("<f4")

    dims = dataset.metadata["dimensions"]
    assert dims["samples_count"] == 1024
    assert dims["channels_count"] == 11
    assert dims["slices_count"] == 175

    assert dataset.metadata["sampling"]["sampling_time_ns"] == pytest.approx(0.125)
    assert dataset.metadata["radar"]["nominal_frequency_MHz"] == pytest.approx(600.0)
    assert dataset.metadata["radar"]["polarization"].lower() == "horizontal"
    assert dataset.has_geolocation is True


def test_real_file_derived_metadata_is_physically_sane():
    dataset = read_ogpr(_REAL_FILE)
    from archaeogpr.qc.metadata import derive_metadata

    derived = derive_metadata(dataset)
    assert derived["time_window_ns"] == pytest.approx(128.0)
    assert derived["depth_estimate"]["max_depth_m"] == pytest.approx(6.4)
    assert derived["geometry"]["profile_length_m"] > 0
