"""Qt-free C-scan / time-slice domain package (Sprint 3D-1).

See ``archaeogpr.cscan.models`` for the scientific scope, and ADR-017 for
the actual-X/Y-vs-derived-parameter-grid rendering policy this package
supports but does not itself implement (rendering is a GUI-layer concern).
"""

from archaeogpr.cscan.compute import compute_cscan
from archaeogpr.cscan.export import CSCAN_REPORT_SCHEMA_VERSION, build_cscan_report, export_cscan_report
from archaeogpr.cscan.models import (
    CScanAggregation,
    CScanError,
    CScanGeometryView,
    CScanRequest,
    CScanResult,
    CScanSourceKind,
    CScanStatistics,
    aggregation_is_signed,
    aggregation_uses_window,
)
from archaeogpr.cscan.validation import validate_center_time_ns, validate_window_width_ns

__all__ = [
    "CScanAggregation",
    "CScanError",
    "CScanGeometryView",
    "CScanRequest",
    "CScanResult",
    "CScanSourceKind",
    "CScanStatistics",
    "CSCAN_REPORT_SCHEMA_VERSION",
    "aggregation_is_signed",
    "aggregation_uses_window",
    "build_cscan_report",
    "compute_cscan",
    "export_cscan_report",
    "validate_center_time_ns",
    "validate_window_width_ns",
]
