"""Survey geometry inspection and readiness gates (Sprint 3D-0).

Qt-free (importable with no PySide6 installed, matching ADR-012's isolation
rule) -- resolves index/local-metric/global-projected survey geometry for
one dataset, with an explicit provenance tag on every field (real file
metadata vs. derived vs. user-supplied vs. index fallback vs. missing), and
reports whether the dataset is ready for an index-space view, a local
C-scan, a global C-scan, or a time-domain volume. Does not build a C-scan or
any volume itself -- see
``obsidian/ArchaeoGPR_Vault/06_DECISIONS/
ADR_016_Geometry_Provenance_and_Readiness_Gates.md`` and
``03_ARCHITECTURE/3D_Volume_Data_Model.md`` for what a future sprint builds
on top of this.
"""

from __future__ import annotations

from archaeogpr.geometry.models import (
    CoordinateMode,
    CrossTrackDirection,
    CrsValidationStatus,
    GeometryProvenance,
    ReadinessGates,
    ReadinessStatus,
    SurveyGeometry,
)
from archaeogpr.geometry.regularity import GridRegularity, assess_grid_regularity
from archaeogpr.geometry.resolve import GeometryOverrides, GeometryResolution, resolve_survey_geometry
from archaeogpr.geometry.summary import GeometrySummary, compute_geometry_summary

__all__ = [
    "GeometryProvenance",
    "CoordinateMode",
    "CrossTrackDirection",
    "CrsValidationStatus",
    "ReadinessStatus",
    "ReadinessGates",
    "SurveyGeometry",
    "GeometryOverrides",
    "GeometryResolution",
    "resolve_survey_geometry",
    "GeometrySummary",
    "compute_geometry_summary",
    "GridRegularity",
    "assess_grid_regularity",
]
