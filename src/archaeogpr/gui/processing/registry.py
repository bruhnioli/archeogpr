"""The Processing panel's operation registry (Sprint GUI-3A, see ADR-015).

Exactly the five stable, already-tested processing functions this sprint is
scoped to -- time-zero correction, DC offset correction, dewow, band-pass
filtering, background removal. No gain/AGC entry exists here, and none
should be added without a separate, explicitly-requested sprint (see
ADR-015 / ``01_PROJECT_STATE/02_Next_Development_Sprint.md``).

Every default below is copied from the real function's own default keyword
value (see the processing API audit cited in ADR-015) -- never invented --
except where a function has no default at all (``remove_background``'s
``method`` is a required keyword; a default had to be chosen for the GUI's
initial form state, and ``"global_mean"`` was picked only because it is the
one variant that needs no window parameter to be immediately runnable, not
because it is scientifically preferred -- background removal has no
canonical choice at all, see ADR-009).
"""

from __future__ import annotations

from archaeogpr.gui.processing.adapters import (
    apply_background,
    apply_bandpass,
    apply_dc_offset,
    apply_dewow,
    apply_time_zero,
    validate_background,
    validate_bandpass,
    validate_dc_offset,
    validate_dewow,
    validate_time_zero,
)
from archaeogpr.gui.processing.models import ParameterSpec, ProcessingOperationSpec

TIME_ZERO = ProcessingOperationSpec(
    operation_id="time_zero",
    display_name="Time-Zero Correction",
    description=(
        "Shifts each channel to align a signal-processing time-zero reference "
        "sample -- rewrites the time axis (time_ns[target_sample] == 0). Not an "
        "independently calibrated physical surface time."
    ),
    changes_time_axis=True,
    parameters=(
        ParameterSpec(
            name="method",
            label="Method",
            kind="choice",
            default="channel_median_peak",
            choices=("channel_median_peak", "channel_median_cross_correlation"),
            description=(
                "Automatic time-zero pick methods only -- manual per-channel picks "
                "are not exposed in this panel (see ADR-015)."
            ),
        ),
        ParameterSpec(
            name="search_start_ns",
            label="Search window start",
            kind="float",
            default=5.0,
            unit="ns",
            minimum=0.0,
        ),
        ParameterSpec(
            name="search_end_ns",
            label="Search window end",
            kind="float",
            default=15.0,
            unit="ns",
            minimum=0.0,
        ),
        ParameterSpec(
            name="target_sample",
            label="Target sample",
            kind="int",
            default=0,
            minimum=0,
            description="The sample index the picked time becomes -- time_ns is 0 there.",
        ),
        ParameterSpec(
            name="peak_polarity",
            label="Peak polarity",
            kind="choice",
            default="max_abs",
            choices=("max_abs", "positive_peak", "negative_peak"),
        ),
        ParameterSpec(
            name="reference_channel",
            label="Reference channel",
            kind="int",
            default=0,
            minimum=0,
            description="Used only by channel_median_cross_correlation.",
        ),
        ParameterSpec(
            name="max_shift_samples",
            label="Max shift",
            kind="int",
            default=64,
            unit="samples",
            minimum=0,
        ),
        ParameterSpec(
            name="fill_value",
            label="Fill value",
            kind="float",
            default=0.0,
            description="Raw amplitude value written into samples shifted in as padding.",
        ),
        ParameterSpec(
            name="overflow_policy",
            label="Overflow policy",
            kind="choice",
            default="error",
            choices=("error", "clip"),
            description="'error' aborts before touching any data if a shift exceeds max_shift_samples.",
        ),
    ),
    apply=apply_time_zero,
    validate=validate_time_zero,
)

DC_OFFSET = ProcessingOperationSpec(
    operation_id="dc_offset",
    display_name="DC Offset Correction",
    description="Removes a per-trace constant offset (mean or median), independent per slice/channel.",
    changes_time_axis=False,
    parameters=(
        ParameterSpec(
            name="method",
            label="Method",
            kind="choice",
            default="mean",
            choices=("mean", "median"),
        ),
        ParameterSpec(
            name="use_window",
            label="Use a time window",
            kind="bool",
            default=False,
            description="Off = compute the offset from the whole trace.",
        ),
        ParameterSpec(
            name="window_start_ns",
            label="Window start",
            kind="float",
            default=0.0,
            unit="ns",
        ),
        ParameterSpec(
            name="window_end_ns",
            label="Window end",
            kind="float",
            default=5.0,
            unit="ns",
        ),
        ParameterSpec(
            name="window_reference",
            label="Window reference",
            kind="choice",
            default="dataset_time",
            choices=("dataset_time", "sample_index"),
            description="dataset_time resolves against time_ns itself (recommended after time-zero)",
        ),
    ),
    apply=apply_dc_offset,
    validate=validate_dc_offset,
)

DEWOW = ProcessingOperationSpec(
    operation_id="dewow",
    display_name="Dewow",
    description="Moving-window baseline (low-frequency 'wow') removal, independent per valid segment.",
    changes_time_axis=False,
    parameters=(
        ParameterSpec(
            name="window_ns",
            label="Window",
            kind="float",
            default=8.0,
            unit="ns",
            minimum=0.0,
        ),
        ParameterSpec(
            name="method",
            label="Method",
            kind="choice",
            default="running_mean",
            choices=("running_mean", "running_median"),
        ),
        ParameterSpec(
            name="edge_mode",
            label="Edge mode",
            kind="choice",
            default="reflect",
            choices=("reflect", "nearest"),
        ),
        ParameterSpec(
            name="allow_repeat_processing",
            label="Allow reprocessing",
            kind="bool",
            default=False,
            description="Off = refuse if dewow already appears in this dataset's processing history.",
        ),
    ),
    apply=apply_dewow,
    validate=validate_dewow,
)

BANDPASS = ProcessingOperationSpec(
    operation_id="bandpass",
    display_name="Band-Pass Filter",
    description=(
        "Zero-phase Butterworth band-pass filter, independent per valid segment. "
        "Ormsby corner-frequency filtering is not exposed in this panel (see ADR-015)."
    ),
    changes_time_axis=False,
    parameters=(
        ParameterSpec(
            name="lowcut_mhz",
            label="Low cutoff",
            kind="float",
            default=100.0,
            unit="MHz",
            minimum=0.0,
        ),
        ParameterSpec(
            name="highcut_mhz",
            label="High cutoff",
            kind="float",
            default=900.0,
            unit="MHz",
            minimum=0.0,
        ),
        ParameterSpec(
            name="order",
            label="Filter order",
            kind="int",
            default=4,
            minimum=1,
        ),
        ParameterSpec(
            name="zero_phase",
            label="Zero-phase",
            kind="bool",
            default=True,
            description="Off = a single causal pass (introduces real phase delay).",
        ),
        ParameterSpec(
            name="allow_repeat_processing",
            label="Allow reprocessing",
            kind="bool",
            default=False,
            description="Off = refuse if band-pass already appears in this dataset's processing history.",
        ),
    ),
    apply=apply_bandpass,
    validate=validate_bandpass,
)

BACKGROUND_REMOVAL = ProcessingOperationSpec(
    operation_id="background",
    display_name="Background Removal",
    description=(
        "Removes a per-channel common-mode estimate (mean/median, global or sliding-window along "
        "the trace axis). No candidate is canonical for this project (see ADR-009) -- this is the "
        "most scientifically risky filter available here: it cannot, on its own, distinguish "
        "unwanted common-mode noise from a genuinely long, laterally continuous reflection."
    ),
    changes_time_axis=False,
    parameters=(
        ParameterSpec(
            name="method",
            label="Method",
            kind="choice",
            default="global_mean",
            choices=("global_mean", "global_median", "sliding_mean", "sliding_median"),
        ),
        ParameterSpec(
            name="window_m",
            label="Window",
            kind="float",
            default=1.0,
            unit="m",
            minimum=0.0,
            description="Used only by sliding_mean/sliding_median; converted to an odd trace count",
        ),
        ParameterSpec(
            name="edge_mode",
            label="Edge mode",
            kind="choice",
            default="reflect",
            choices=("reflect", "nearest"),
        ),
        ParameterSpec(
            name="allow_reprocessing",
            label="Allow reprocessing",
            kind="bool",
            default=False,
            description="Off = refuse if background removal is already in this dataset's processing history",
        ),
    ),
    apply=apply_background,
    validate=validate_background,
)

#: Registration order is display order in the Processing panel's operation combo box.
REGISTRY: tuple[ProcessingOperationSpec, ...] = (
    TIME_ZERO,
    DC_OFFSET,
    DEWOW,
    BANDPASS,
    BACKGROUND_REMOVAL,
)


def get_operation(operation_id: str) -> ProcessingOperationSpec:
    """The registered spec with this ``operation_id``. Raises ``KeyError`` if unregistered."""
    for spec in REGISTRY:
        if spec.operation_id == operation_id:
            return spec
    raise KeyError(f"No registered processing operation {operation_id!r}")
