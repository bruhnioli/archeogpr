"""Adapters: translate GUI parameter dicts into real ``archaeogpr.processing`` calls.

**No processing algorithm is duplicated here.** Every ``apply_*`` function
below does exactly three things: pull values out of the GUI's ``params``
dict, call the one real ``processing/*.py`` function with its real keyword
arguments (verified against the actual source, not guessed -- see ADR-015),
and return its ``ProcessingResult`` unchanged. Every ``validate_*`` function
is a fast, synchronous, GUI-thread pre-check (used to keep an obviously
invalid parameter from ever starting a background worker -- see
:mod:`archaeogpr.gui.workers.processing_worker`); the real function's own
validation (``ProcessingError``) still runs afterwards regardless and is
still the source of truth -- these pre-checks exist for responsiveness, not
because the worker's own error handling is untrusted.

**Scope decisions (see ADR-015 for the full rationale):**

- Time-zero's ``"manual"`` method (per-channel pick entry) is not exposed --
  only the two automatic methods (``channel_median_peak``,
  ``channel_median_cross_correlation``) are. A per-channel picks table is a
  different UI shape than every other operation here and is deferred.
- Band-pass's ``"ormsby"`` method (a 4-corner-frequency design) is not
  exposed -- only ``"butterworth"`` (matching the exact parameters named in
  this sprint's own scope: low/high cutoff, order, zero-phase).
- None of the five expose ``valid_mask`` as a user-facing parameter -- it is
  threaded automatically by :class:`~archaeogpr.gui.models.dataset_session.DatasetSession`
  (see its module docstring) from whichever operation most recently ran,
  exactly like ``cli.py``'s ``sprint2`` pipeline threads
  ``tz_result.valid_mask`` into ``correct_dc_offset``.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing import ProcessingResult, correct_dc_offset, correct_time_zero
from archaeogpr.processing.background import remove_background
from archaeogpr.processing.bandpass import correct_bandpass
from archaeogpr.processing.dewow import correct_dewow

# -- time-zero correction -----------------------------------------------------


def apply_time_zero(
    dataset: GPRDataset, params: dict[str, Any], valid_mask: np.ndarray | None
) -> ProcessingResult:
    # `correct_time_zero` has no `valid_mask` parameter at all (it *produces*
    # one; it doesn't accept one) -- see the processing API audit in ADR-015.
    del valid_mask
    return correct_time_zero(
        dataset,
        method=params["method"],
        search_start_ns=params["search_start_ns"],
        search_end_ns=params["search_end_ns"],
        target_sample=int(params["target_sample"]),
        peak_polarity=params["peak_polarity"],
        reference_channel=int(params["reference_channel"]),
        max_shift_samples=int(params["max_shift_samples"]),
        fill_value=params["fill_value"],
        overflow_policy=params["overflow_policy"],
    )


def validate_time_zero(params: dict[str, Any], dataset: GPRDataset | None) -> tuple[str, ...]:
    del dataset
    errors: list[str] = []
    if params["search_end_ns"] <= params["search_start_ns"]:
        errors.append("search_end_ns must be greater than search_start_ns")
    if params["target_sample"] < 0:
        errors.append("target_sample must be >= 0")
    if params["max_shift_samples"] < 0:
        errors.append("max_shift_samples must be >= 0")
    if params["reference_channel"] < 0:
        errors.append("reference_channel must be >= 0")
    return tuple(errors)


# -- DC offset correction ------------------------------------------------------


def apply_dc_offset(
    dataset: GPRDataset, params: dict[str, Any], valid_mask: np.ndarray | None
) -> ProcessingResult:
    use_window = bool(params["use_window"])
    return correct_dc_offset(
        dataset,
        method=params["method"],
        window_start_ns=params["window_start_ns"] if use_window else None,
        window_end_ns=params["window_end_ns"] if use_window else None,
        valid_mask=valid_mask,
        window_reference=params["window_reference"],
    )


def validate_dc_offset(params: dict[str, Any], dataset: GPRDataset | None) -> tuple[str, ...]:
    del dataset
    errors: list[str] = []
    if params["use_window"] and params["window_end_ns"] <= params["window_start_ns"]:
        errors.append("window_end_ns must be greater than window_start_ns")
    return tuple(errors)


# -- dewow ----------------------------------------------------------------------


def apply_dewow(
    dataset: GPRDataset, params: dict[str, Any], valid_mask: np.ndarray | None
) -> ProcessingResult:
    return correct_dewow(
        dataset,
        window_ns=params["window_ns"],
        method=params["method"],
        valid_mask=valid_mask,
        edge_mode=params["edge_mode"],
        allow_repeat_processing=bool(params["allow_repeat_processing"]),
    )


def validate_dewow(params: dict[str, Any], dataset: GPRDataset | None) -> tuple[str, ...]:
    del dataset
    errors: list[str] = []
    if params["window_ns"] <= 0:
        errors.append("window_ns must be > 0")
    return tuple(errors)


# -- band-pass filtering (Butterworth only -- see module docstring) -----------


def _nyquist_mhz(sampling_time_ns: float) -> float:
    """Identical expression to ``processing/bandpass.py::_nyquist_mhz`` -- see ADR-015.

    Duplicated (not imported) because it is a private helper of that module;
    kept byte-for-byte identical so this GUI-side pre-check can never accept
    a value the real function would then reject, or vice versa.
    """
    sampling_frequency_hz = 1.0 / (sampling_time_ns * 1e-9)
    return sampling_frequency_hz / 2.0 / 1e6


def apply_bandpass(
    dataset: GPRDataset, params: dict[str, Any], valid_mask: np.ndarray | None
) -> ProcessingResult:
    return correct_bandpass(
        dataset,
        method="butterworth",
        lowcut_mhz=params["lowcut_mhz"],
        highcut_mhz=params["highcut_mhz"],
        order=int(params["order"]),
        zero_phase=bool(params["zero_phase"]),
        valid_mask=valid_mask,
        allow_repeat_processing=bool(params["allow_repeat_processing"]),
    )


def validate_bandpass(params: dict[str, Any], dataset: GPRDataset | None) -> tuple[str, ...]:
    errors: list[str] = []
    if params["lowcut_mhz"] <= 0:
        errors.append("lowcut_mhz must be > 0")
    if params["highcut_mhz"] <= params["lowcut_mhz"]:
        errors.append("highcut_mhz must be greater than lowcut_mhz")
    if params["order"] < 1:
        errors.append("order must be >= 1")
    if dataset is not None:
        sampling = dataset.metadata.get("sampling") or {}
        sampling_time_ns = sampling.get("sampling_time_ns")
        if sampling_time_ns:
            nyquist_mhz = _nyquist_mhz(sampling_time_ns)
            if params["highcut_mhz"] >= nyquist_mhz:
                errors.append(f"highcut_mhz must be below the Nyquist frequency ({nyquist_mhz:g} MHz)")
    return tuple(errors)


# -- background removal --------------------------------------------------------

_SLIDING_METHODS = ("sliding_mean", "sliding_median")


def apply_background(
    dataset: GPRDataset, params: dict[str, Any], valid_mask: np.ndarray | None
) -> ProcessingResult:
    kwargs: dict[str, Any] = {
        "method": params["method"],
        "valid_mask": valid_mask,
        "edge_mode": params["edge_mode"],
        "allow_reprocessing": bool(params["allow_reprocessing"]),
    }
    if params["method"] in _SLIDING_METHODS:
        kwargs["window_m"] = params["window_m"]
    return remove_background(dataset, **kwargs)


def validate_background(params: dict[str, Any], dataset: GPRDataset | None) -> tuple[str, ...]:
    del dataset
    errors: list[str] = []
    if params["method"] in _SLIDING_METHODS and params["window_m"] <= 0:
        errors.append("window_m must be > 0 for sliding_mean/sliding_median")
    return tuple(errors)
