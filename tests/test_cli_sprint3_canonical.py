"""Tests for the ``sprint3`` CLI subcommand (canonical D2 + B1 chain).

Skips cleanly (not a failure) if the real Sprint 2 canonical NPZ or the raw
sample file are not present. Runs ``archaeogpr.cli.main`` in-process
(no subprocess) and asserts on captured stdout plus the written outputs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from archaeogpr.cli import main
from archaeogpr.export.sprint3 import read_processed_npz

_CANONICAL_NPZ = (
    Path(__file__).resolve().parents[1]
    / "outputs"
    / "sprint02"
    / "canonical_target16"
    / "sprint02_processed.npz"
)
_RAW_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "Swath003_Array02.ogpr"

pytestmark = pytest.mark.skipif(
    not (_CANONICAL_NPZ.is_file() and _RAW_FILE.is_file()),
    reason="Real Sprint 2 canonical NPZ or raw file not found; skipping sprint3 CLI tests.",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_sprint3_cli_defaults_report_canonical_true(tmp_path, capsys):
    exit_code = main(["sprint3", str(_CANONICAL_NPZ), "--output-dir", str(tmp_path / "canonical")])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "canonical selected: true" in out
    assert "selection authority: human/geophysical review".lower() in out.lower()
    assert "WARNING" not in out


def test_sprint3_cli_override_reports_canonical_false_with_warning(tmp_path, capsys):
    exit_code = main(
        ["sprint3", str(_CANONICAL_NPZ), "--output-dir", str(tmp_path / "canonical"), "--order", "6"]
    )
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "canonical selected: false" in out
    assert "WARNING" in out
    assert "NOT the canonical Sprint 3 chain" in out


def test_sprint3_cli_reports_distinct_raw_and_npz_hashes(tmp_path, capsys):
    expected_raw_hash = _sha256(_RAW_FILE)
    expected_npz_hash = _sha256(_CANONICAL_NPZ)

    main(["sprint3", str(_CANONICAL_NPZ), "--output-dir", str(tmp_path / "canonical")])
    out = capsys.readouterr().out

    assert expected_raw_hash in out
    assert expected_npz_hash in out
    assert expected_raw_hash != expected_npz_hash
    assert "Raw source file hash unchanged: True" in out
    assert "Sprint 2 canonical NPZ hash unchanged: True" in out


def test_sprint3_cli_prints_required_diagnostics(tmp_path, capsys):
    main(["sprint3", str(_CANONICAL_NPZ), "--output-dir", str(tmp_path / "canonical")])
    out = capsys.readouterr().out

    for expected_substring in (
        "Applied dewow window:",
        "Applied band-pass parameters:",
        "Output processing history:",
        "Padding verification:",
        "Phase lag:",
        "Generated outputs:",
    ):
        assert expected_substring in out


def test_sprint3_cli_writes_all_fifteen_required_files(tmp_path):
    output_dir = tmp_path / "canonical"
    main(["sprint3", str(_CANONICAL_NPZ), "--output-dir", str(output_dir)])

    required_files = [
        "sprint03_processed.npz",
        "processing_history.json",
        "processing_metadata.json",
        "canonical_parameters.json",
        "channel00_raw.png",
        "channel00_after_dewow.png",
        "channel00_final.png",
        "channel00_removed_dewow.png",
        "channel00_removed_bandpass.png",
        "all_channels_final.png",
        "spectrum_before_after.png",
        "transfer_function.png",
        "padding_verification.json",
        "phase_verification.json",
        "CANONICAL_PROCESSING_NOTE.md",
    ]
    for filename in required_files:
        path = output_dir / filename
        assert path.is_file(), f"missing required canonical output: {filename}"
        assert path.stat().st_size > 0


def test_sprint3_cli_deterministic_across_two_runs(tmp_path):
    main(["sprint3", str(_CANONICAL_NPZ), "--output-dir", str(tmp_path / "run_a")])
    main(["sprint3", str(_CANONICAL_NPZ), "--output-dir", str(tmp_path / "run_b")])

    dataset_a, mask_a = read_processed_npz(tmp_path / "run_a" / "sprint03_processed.npz")
    dataset_b, mask_b = read_processed_npz(tmp_path / "run_b" / "sprint03_processed.npz")
    np.testing.assert_array_equal(dataset_a.amplitudes, dataset_b.amplitudes)
    np.testing.assert_array_equal(mask_a, mask_b)


def test_sprint3_cli_does_not_touch_raw_or_canonical_npz(tmp_path):
    raw_hash_before = _sha256(_RAW_FILE)
    npz_hash_before = _sha256(_CANONICAL_NPZ)

    main(["sprint3", str(_CANONICAL_NPZ), "--output-dir", str(tmp_path / "canonical")])

    assert _sha256(_RAW_FILE) == raw_hash_before
    assert _sha256(_CANONICAL_NPZ) == npz_hash_before
