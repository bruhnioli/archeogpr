"""Integration test for Sprint 2 (time-zero + DC offset) against the real sample file.

Skips cleanly (not a failure) if the file is not present under data/raw/.
Only structural/statistical properties are asserted here (shape, dtype,
finiteness, hash, alignment, history order, export round-trips) — never a
scientific/archaeological interpretation of the data.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from archaeogpr.export.processed import (
    write_channel_picks_csv,
    write_combined_npz,
    write_corrected_npz,
    write_offsets_csv,
)
from archaeogpr.io.ogpr_reader import read_ogpr
from archaeogpr.processing.dc_offset import correct_dc_offset
from archaeogpr.processing.time_zero import correct_time_zero
from archaeogpr.qc.bscan import save_bscan_comparison

_REAL_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "Swath003_Array02.ogpr"

pytestmark = pytest.mark.skipif(
    not _REAL_FILE.is_file(),
    reason=f"Real sample file not found at {_REAL_FILE}; skipping Sprint 2 integration test.",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_time_zero_and_dc_offset_on_real_file(tmp_path):
    hash_before = _sha256(_REAL_FILE)
    raw = read_ogpr(_REAL_FILE)
    assert raw.shape == (175, 11, 1024)
    assert raw.amplitudes.dtype == np.dtype("<f4")

    tz_result = correct_time_zero(
        raw,
        method="channel_median_peak",
        search_start_ns=5.0,
        search_end_ns=15.0,
        target_sample=0,
        peak_polarity="max_abs",
        max_shift_samples=128,  # generous enough that no channel's shift is clipped on this file
    )

    search_start_sample, search_end_sample = tz_result.diagnostics["search_window_samples"]
    for channel_str, picked_sample in tz_result.diagnostics["channel_picks"].items():
        assert search_start_sample <= picked_sample < search_end_sample, (
            f"channel {channel_str}: pick {picked_sample} outside search window "
            f"[{search_start_sample}, {search_end_sample})"
        )
    for shift in tz_result.diagnostics["channel_shifts"].values():
        assert abs(shift) <= 128

    assert np.isfinite(tz_result.dataset.amplitudes).all()
    assert tz_result.dataset.shape == raw.shape
    assert tz_result.dataset.amplitudes.dtype == raw.amplitudes.dtype

    # Re-pick on the corrected dataset: every unclipped channel must now sit at target_sample=0.
    verification = correct_time_zero(
        tz_result.dataset,
        method="channel_median_peak",
        search_start_ns=0.0,
        search_end_ns=30.0,
        target_sample=0,
    )
    for channel_str, shift in tz_result.diagnostics["channel_shifts"].items():
        if (
            abs(shift) < 128
        ):  # only channels whose shift wasn't clipped are guaranteed to land exactly on target
            assert verification.diagnostics["channel_picks"][channel_str] == 0

    dc_result = correct_dc_offset(tz_result.dataset, method="mean")
    assert np.isfinite(dc_result.dataset.amplitudes).all()
    assert dc_result.dataset.shape == raw.shape

    trace_mean_before = tz_result.dataset.amplitudes.astype(np.float64).mean(axis=2)
    trace_mean_after = dc_result.dataset.amplitudes.astype(np.float64).mean(axis=2)
    assert np.abs(trace_mean_after).mean() < np.abs(trace_mean_before).mean()

    operations = [record["operation"] for record in dc_result.dataset.processing_history]
    assert operations == ["time_zero_correction", "dc_offset_correction"]

    hash_after = _sha256(_REAL_FILE)
    assert hash_after == hash_before
    np.testing.assert_array_equal(raw.amplitudes, read_ogpr(_REAL_FILE).amplitudes)

    # --- exports round-trip -----------------------------------------------------

    picks_csv = write_channel_picks_csv(tz_result, tmp_path / "channel_picks.csv")
    picks_df = pd.read_csv(picks_csv)
    assert len(picks_df) == raw.shape[1]  # one row per channel

    offsets_csv = write_offsets_csv(dc_result, tmp_path / "offsets.csv")
    offsets_df = pd.read_csv(offsets_csv)
    assert len(offsets_df) == raw.shape[0] * raw.shape[1]  # one row per (slice, channel)

    tz_npz_path = write_corrected_npz(tz_result, tmp_path / "time_zero_corrected.npz")
    with np.load(tz_npz_path) as npz:
        assert npz["amplitudes"].shape == raw.shape
        assert str(npz["amplitudes"].dtype) == "float32"

    combined_npz_path = write_combined_npz(tz_result, dc_result, tmp_path / "sprint02_processed.npz")
    with np.load(combined_npz_path) as npz:
        assert npz["amplitudes"].shape == raw.shape
        assert np.isfinite(npz["amplitudes"]).all()

    # --- QC PNGs are non-empty and openable -------------------------------------

    bscan_paths = save_bscan_comparison(raw, dc_result.dataset, 0, tmp_path, "channel00")
    for path in bscan_paths.values():
        assert path.stat().st_size > 0


def test_max_shift_samples_96_gives_zero_clipping_on_the_real_file():
    # The Sprint 2.1 review's chosen validation setting: generous enough that
    # every channel's true requested shift is accommodated exactly, so
    # overflow_policy="error" never triggers and nothing is clipped.
    raw = read_ogpr(_REAL_FILE)

    result = correct_time_zero(
        raw,
        method="channel_median_peak",
        search_start_ns=5.0,
        search_end_ns=15.0,
        target_sample=0,
        peak_polarity="max_abs",
        max_shift_samples=96,
        overflow_policy="error",
    )

    assert result.diagnostics["has_clipped_shifts"] is False
    assert result.diagnostics["valid_for_downstream_processing"] is True
    for channel_str in result.diagnostics["channel_shifts"]:
        assert (
            result.diagnostics["channel_shifts"][channel_str]
            == result.diagnostics["requested_shifts"][channel_str]
        )
    assert result.valid_mask.shape == (raw.shape[1], raw.shape[2])
