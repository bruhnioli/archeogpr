"""Sprint 3 pipeline/integration tests: the shared contiguous_true_runs helper,
the read_processed_npz loader, load_candidates_config, write_padding_verification_json,
and a synthetic end-to-end time-zero -> dc-offset -> dewow -> band-pass chain.

Real-.ogpr-file-dependent integration lives in test_sprint3_real_integration.py;
everything here is synthetic and runs unconditionally.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from archaeogpr.export.processed import write_combined_npz, write_corrected_npz
from archaeogpr.export.sprint3 import (
    load_candidates_config,
    read_processed_npz,
    write_padding_verification_json,
)
from archaeogpr.processing.bandpass import correct_bandpass
from archaeogpr.processing.common import ProcessingError, contiguous_true_runs
from archaeogpr.processing.dc_offset import correct_dc_offset
from archaeogpr.processing.dewow import correct_dewow
from archaeogpr.processing.time_zero import correct_time_zero

SAMPLING_TIME_NS = 0.5


# --- contiguous_true_runs (shared helper used by both dewow and bandpass) ----------


def test_contiguous_true_runs_all_false_returns_empty():
    assert contiguous_true_runs(np.zeros(10, dtype=bool)) == []


def test_contiguous_true_runs_all_true_returns_one_full_run():
    assert contiguous_true_runs(np.ones(10, dtype=bool)) == [(0, 10)]


def test_contiguous_true_runs_single_interior_run():
    mask = np.zeros(20, dtype=bool)
    mask[5:12] = True
    assert contiguous_true_runs(mask) == [(5, 12)]


def test_contiguous_true_runs_multiple_runs_including_boundaries():
    mask = np.zeros(20, dtype=bool)
    mask[0:3] = True  # touches the start
    mask[8:11] = True  # interior
    mask[17:20] = True  # touches the end
    assert contiguous_true_runs(mask) == [(0, 3), (8, 11), (17, 20)]


def test_contiguous_true_runs_single_sample_run():
    mask = np.zeros(5, dtype=bool)
    mask[2] = True
    assert contiguous_true_runs(mask) == [(2, 3)]


# --- read_processed_npz -------------------------------------------------------------


def _dataset_with_pulse(dataset_factory):
    amplitudes = np.zeros((5, 2, 100), dtype=np.float32)
    amplitudes[:, 0, 40] = 100.0
    amplitudes[:, 1, 45] = 100.0
    return dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)


def test_read_processed_npz_round_trips_a_full_sprint2_style_pipeline(dataset_factory, tmp_path):
    ds = _dataset_with_pulse(dataset_factory)
    tz_result = correct_time_zero(ds, method="manual", picks={0: 40, 1: 45}, target_sample=16)
    dc_result = correct_dc_offset(tz_result.dataset, method="mean", valid_mask=tz_result.valid_mask)

    npz_path = write_combined_npz(tz_result, dc_result, tmp_path / "sprint02_processed.npz")
    reloaded_dataset, reloaded_mask = read_processed_npz(npz_path)

    np.testing.assert_array_equal(reloaded_dataset.amplitudes, dc_result.dataset.amplitudes)
    np.testing.assert_array_equal(reloaded_dataset.time_ns, dc_result.dataset.time_ns)
    assert reloaded_mask is not None
    np.testing.assert_array_equal(reloaded_mask, dc_result.valid_mask)
    assert [r["operation"] for r in reloaded_dataset.processing_history] == [
        "time_zero_correction",
        "dc_offset_correction",
    ]
    assert (
        reloaded_dataset.x is None and reloaded_dataset.y is None
    )  # no geolocation in this synthetic dataset


def test_read_processed_npz_returned_arrays_are_immutable(dataset_factory, tmp_path):
    ds = _dataset_with_pulse(dataset_factory)
    result = correct_dc_offset(ds, method="mean")
    npz_path = write_corrected_npz(result, tmp_path / "dc.npz")
    reloaded_dataset, reloaded_mask = read_processed_npz(npz_path)
    assert reloaded_dataset.amplitudes.flags.writeable is False
    assert reloaded_dataset.time_ns.flags.writeable is False
    assert reloaded_mask is None  # this result had no valid_mask


def test_read_processed_npz_valid_mask_is_immutable(dataset_factory, tmp_path):
    ds = _dataset_with_pulse(dataset_factory)
    tz_result = correct_time_zero(ds, method="manual", picks={0: 40, 1: 45}, target_sample=0)
    npz_path = write_corrected_npz(tz_result, tmp_path / "tz.npz")
    _, reloaded_mask = read_processed_npz(npz_path)
    assert reloaded_mask is not None
    assert reloaded_mask.flags.writeable is False


def test_read_processed_npz_raises_on_missing_required_key(tmp_path):
    path = tmp_path / "broken.npz"
    np.savez_compressed(path, amplitudes=np.zeros((2, 1, 10), dtype=np.float32))  # missing everything else
    with pytest.raises(ProcessingError, match="missing required NPZ key"):
        read_processed_npz(path)


def test_read_processed_npz_raises_on_invalid_metadata_json(tmp_path):
    path = tmp_path / "bad_metadata.npz"
    np.savez_compressed(
        path,
        amplitudes=np.zeros((1, 1, 10), dtype=np.float32),
        time_ns=np.arange(10, dtype=np.float64),
        metadata_json="{not valid json",
        processing_history_json=json.dumps([]),
        has_valid_mask=False,
    )
    with pytest.raises(ProcessingError, match="not valid JSON"):
        read_processed_npz(path)


def test_read_processed_npz_raises_on_processing_history_not_a_list_of_records(tmp_path):
    path = tmp_path / "bad_history.npz"
    np.savez_compressed(
        path,
        amplitudes=np.zeros((1, 1, 10), dtype=np.float32),
        time_ns=np.arange(10, dtype=np.float64),
        metadata_json=json.dumps({"sampling": {"sampling_time_ns": 1.0}}),
        processing_history_json=json.dumps([{"no_operation_key": True}]),
        has_valid_mask=False,
    )
    with pytest.raises(ProcessingError, match="must be a list of records"):
        read_processed_npz(path)


def test_read_processed_npz_raises_on_out_of_order_processing_history(tmp_path):
    path = tmp_path / "out_of_order.npz"
    # dc_offset_correction before time_zero_correction violates the documented stage order.
    history = [{"operation": "dc_offset_correction"}, {"operation": "time_zero_correction"}]
    np.savez_compressed(
        path,
        amplitudes=np.zeros((1, 1, 10), dtype=np.float32),
        time_ns=np.arange(10, dtype=np.float64),
        metadata_json=json.dumps({"sampling": {"sampling_time_ns": 1.0}}),
        processing_history_json=json.dumps(history),
        has_valid_mask=False,
    )
    with pytest.raises(ProcessingError, match="violates the documented stage order"):
        read_processed_npz(path)


def test_read_processed_npz_raises_when_has_valid_mask_true_but_key_missing(tmp_path):
    path = tmp_path / "missing_mask.npz"
    np.savez_compressed(
        path,
        amplitudes=np.zeros((1, 1, 10), dtype=np.float32),
        time_ns=np.arange(10, dtype=np.float64),
        metadata_json=json.dumps({"sampling": {"sampling_time_ns": 1.0}}),
        processing_history_json=json.dumps([]),
        has_valid_mask=True,
    )
    with pytest.raises(ProcessingError, match="valid_mask' key is missing"):
        read_processed_npz(path)


def test_read_processed_npz_raises_on_valid_mask_shape_mismatch(tmp_path):
    path = tmp_path / "mismatched_mask.npz"
    np.savez_compressed(
        path,
        amplitudes=np.zeros((3, 2, 10), dtype=np.float32),  # 2 channels, 10 samples
        time_ns=np.arange(10, dtype=np.float64),
        metadata_json=json.dumps({"sampling": {"sampling_time_ns": 1.0}}),
        processing_history_json=json.dumps([]),
        has_valid_mask=True,
        valid_mask=np.ones((5, 10), dtype=bool),  # wrong channel count
    )
    with pytest.raises(ProcessingError, match="valid_mask shape"):
        read_processed_npz(path)


def test_read_processed_npz_is_allow_pickle_false_safe(dataset_factory, tmp_path):
    # Every array this project writes is numeric or a plain unicode JSON string --
    # confirm the loader never needs allow_pickle=True by directly re-checking the file.
    ds = _dataset_with_pulse(dataset_factory)
    result = correct_dc_offset(ds, method="mean")
    npz_path = write_corrected_npz(result, tmp_path / "safe.npz")
    with np.load(npz_path, allow_pickle=False) as npz:
        assert set(npz.files) >= {"amplitudes", "time_ns", "metadata_json", "processing_history_json"}
    read_processed_npz(npz_path)  # must not raise


# --- load_candidates_config -----------------------------------------------------------


def test_load_candidates_config_reads_real_dewow_config():
    config = load_candidates_config("configs/dewow_candidates.yaml")
    ids = [c["id"] for c in config["candidates"]]
    assert ids == ["D1", "D2", "D3", "D4"]
    assert config["edge_mode"] == "reflect"


def test_load_candidates_config_reads_real_bandpass_config():
    config = load_candidates_config("configs/bandpass_candidates.yaml")
    ids = [c["id"] for c in config["candidates"]]
    assert ids == ["B1", "B2", "B3", "B4"]
    assert config["dewow_base_candidate"] == "D2"
    combined_ids = [c["id"] for c in config["combined_candidates"]]
    assert combined_ids == ["C1", "C2", "C3", "C4", "C5", "C6"]


def test_load_candidates_config_raises_on_non_mapping_yaml(tmp_path):
    path = tmp_path / "list.yaml"
    path.write_text("- 1\n- 2\n- 3\n", encoding="utf-8")
    with pytest.raises(ProcessingError, match="expected a YAML mapping"):
        load_candidates_config(path)


# --- write_padding_verification_json ---------------------------------------------------


def test_write_padding_verification_json_reports_clean_padding(dataset_factory, tmp_path):
    ds = _dataset_with_pulse(dataset_factory)
    tz_result = correct_time_zero(ds, method="manual", picks={0: 40, 1: 45}, target_sample=0)
    path = write_padding_verification_json(tz_result, tmp_path / "padding.json")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["all_channels_padding_untouched"] is True
    assert report["all_channels_removed_component_zero_at_padding"] is True
    assert "0" in report["per_channel"] and "1" in report["per_channel"]


def test_write_padding_verification_json_raises_without_valid_mask(dataset_factory, tmp_path):
    ds = _dataset_with_pulse(dataset_factory)
    result = correct_dc_offset(ds, method="mean")  # no valid_mask
    with pytest.raises(ProcessingError, match="requires result.valid_mask"):
        write_padding_verification_json(result, tmp_path / "padding.json")


# --- synthetic end-to-end pipeline: time-zero -> dc-offset -> dewow -> band-pass -----


def test_full_synthetic_pipeline_preserves_shape_and_accumulates_history(dataset_factory, tmp_path):
    amplitudes = np.zeros((6, 2, 200), dtype=np.float32)
    amplitudes[:, 0, 20] = 500.0
    amplitudes[:, 1, 22] = 500.0
    ds = dataset_factory(amplitudes=amplitudes, sampling_time_ns=SAMPLING_TIME_NS)

    tz_result = correct_time_zero(ds, method="manual", picks={0: 20, 1: 22}, target_sample=16)
    dc_result = correct_dc_offset(tz_result.dataset, method="mean", valid_mask=tz_result.valid_mask)
    npz_path = write_combined_npz(tz_result, dc_result, tmp_path / "sprint02_processed.npz")

    reloaded_dataset, reloaded_mask = read_processed_npz(npz_path)
    dewow_result = correct_dewow(
        reloaded_dataset, window_ns=9.0, method="running_mean", valid_mask=reloaded_mask
    )
    bandpass_result = correct_bandpass(
        dewow_result.dataset,
        method="butterworth",
        lowcut_mhz=50.0,
        highcut_mhz=800.0,
        order=4,
        valid_mask=reloaded_mask,
    )

    final = bandpass_result.dataset
    assert final.shape == ds.shape
    assert final.amplitudes.dtype == np.float32
    assert [r["operation"] for r in final.processing_history] == [
        "time_zero_correction",
        "dc_offset_correction",
        "dewow_correction",
        "bandpass_correction",
    ]
    assert np.isfinite(final.amplitudes).all()

    # Reloading a dewow-processed NPZ and calling correct_dewow again must hit the
    # same repeat-processing guard as the in-memory case -- proves the loader
    # round-trips processing_history in a form the guard actually recognizes.
    dewow_npz_path = write_corrected_npz(dewow_result, tmp_path / "dewow_only.npz")
    reloaded_dewow_dataset, reloaded_dewow_mask = read_processed_npz(dewow_npz_path)
    with pytest.raises(ProcessingError, match="already contains"):
        correct_dewow(
            reloaded_dewow_dataset, window_ns=9.0, method="running_mean", valid_mask=reloaded_dewow_mask
        )
