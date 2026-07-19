"""Immutable data model for one dataset's resolved survey geometry.

Every field here is either read straight from the file, derived by pure
arithmetic from other file-sourced values, explicitly supplied by the user,
or a plain index fallback -- never guessed. :class:`GeometryProvenance`
records which of those four (or "missing") applies to each individual
field, so the GUI and the exported report can always show the user exactly
how confident a number is, instead of presenting an index or a derived
estimate as if it were a surveyed fact. See ``ADR_016_Geometry_Provenance_
and_Readiness_Gates.md`` for the full rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from archaeogpr.model._frozen import freeze_array

__all__ = [
    "GeometryProvenance",
    "CoordinateMode",
    "CrossTrackDirection",
    "CrsValidationStatus",
    "ReadinessStatus",
    "ReadinessGates",
    "SurveyGeometry",
]


class GeometryProvenance(Enum):
    """Where one resolved geometry field's value actually came from."""

    #: Read directly from the ``.ogpr`` file's header or geolocation block.
    FILE_METADATA = "file_metadata"
    #: Computed by pure arithmetic from other ``FILE_METADATA`` values (e.g.
    #: a spacing statistic derived from real per-trace coordinates).
    DERIVED = "derived"
    #: Entered by the user as a session-level override; never written back
    #: to the raw dataset or the ``.ogpr`` file.
    USER_SUPPLIED = "user_supplied"
    #: A plain array-index fallback (0, 1, 2, ...) used only because no
    #: file, derived, or user value exists -- never in physical units.
    INDEX_SPACE = "index_space"
    #: No value exists anywhere; the field is genuinely unknown.
    MISSING = "missing"


class CoordinateMode(Enum):
    """Which coordinate system :class:`SurveyGeometry` currently represents."""

    #: Trace/channel array indices only -- no physical spacing is known.
    INDEX = "index"
    #: Along-track/cross-track offsets in meters, relative to an arbitrary
    #: local origin -- no georeferencing.
    LOCAL_METRIC = "local_metric"
    #: Projected easting/northing (or equivalent), with a CRS identifier
    #: carried alongside "as stored, not validated".
    GLOBAL_PROJECTED = "global_projected"
    #: Geographic latitude/longitude. Not produced by this sprint's
    #: resolver (no reprojection dependency was added) -- reserved for a
    #: future sprint; see ``ADR_016``.
    GLOBAL_GEOGRAPHIC = "global_geographic"


class CrossTrackDirection(Enum):
    """Which physical direction increasing channel index points, relative to travel direction."""

    #: Channel index increases to the right of (clockwise from) the
    #: along-track travel direction -- i.e. the starboard side.
    CHANNEL_ASCENDING_RIGHT = "channel_ascending_right"
    #: Channel index increases to the left (port side).
    CHANNEL_ASCENDING_LEFT = "channel_ascending_left"
    #: Not known and not supplied -- global-coordinate reconstruction from
    #: local geometry must be refused while this holds (see ``resolve.py``).
    UNKNOWN = "unknown"


class CrsValidationStatus(Enum):
    """How much a :attr:`SurveyGeometry.crs_identifier` has actually been checked.

    A CRS identifier being present (``FILE_METADATA`` or ``USER_SUPPLIED``
    provenance) only means it was *declared* somewhere -- never that anyone
    confirmed it is the correct authority code for this survey's real-world
    location (see ISSUE-001 / ``ADR_016``). This project adds no GIS
    authority database and performs no network lookup, so ``VALIDATED`` is
    never produced by this sprint's resolver -- it exists only so a future
    sprint that *does* add real authority validation has somewhere to record
    a positive result, without repurposing this enum's other members.
    """

    #: No CRS identifier is known at all.
    MISSING = "missing"
    #: Read from the file's own metadata, but never checked against a CRS
    #: authority or the survey's real-world location.
    DECLARED_UNVERIFIED = "declared_unverified"
    #: Entered by the user as an override, but equally unchecked.
    USER_SUPPLIED_UNVERIFIED = "user_supplied_unverified"
    #: Reserved for a future sprint that adds real authority/network
    #: validation. Never produced by ``resolve_survey_geometry`` today.
    VALIDATED = "validated"


@dataclass(frozen=True)
class ReadinessStatus:
    """One readiness gate's outcome: not just a bool, but why."""

    ready: bool
    blocking_issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadinessGates:
    """The seven readiness gates this sprint defines. See ``ADR_016`` for each gate's exact rule.

    Renamed/added in the pre-commit audit's regularity refinement:
    ``local_cscan_ready`` (Sprint 3D-0's original name) is now
    ``local_parameter_grid_ready`` -- being ready for a *derived*, always-
    rectilinear-by-construction ``s``/``c`` parameter grid never implied the
    real acquisition was itself rectilinear, and the old name invited that
    conflation. ``rectilinear_cscan_ready`` and ``actual_xy_point_grid_ready``
    are new: a future C-scan sprint has two genuinely different paths (a
    rectilinear parameter-grid render vs. an actual/curvilinear point-grid
    render), and this sprint reports readiness for each separately rather
    than picking one silently.
    """

    index_view_ready: ReadinessStatus
    local_parameter_grid_ready: ReadinessStatus
    rectilinear_cscan_ready: ReadinessStatus
    actual_xy_point_grid_ready: ReadinessStatus
    global_cscan_ready: ReadinessStatus
    time_volume_ready: ReadinessStatus
    depth_volume_ready: ReadinessStatus


def _freeze_1d(name: str, array: np.ndarray | None) -> np.ndarray | None:
    if array is None:
        return None
    frozen = freeze_array(name, array, ndim=1)
    return frozen


def _freeze_2d(name: str, array: np.ndarray | None) -> np.ndarray | None:
    if array is None:
        return None
    frozen = freeze_array(name, array, ndim=2)
    return frozen


@dataclass(frozen=True)
class SurveyGeometry:
    """One dataset's resolved survey geometry, at a specific :attr:`geometry_revision`.

    ``along_track_coordinates`` (shape ``(trace_count,)``) and
    ``cross_track_offsets`` (shape ``(channel_count,)``) are kept as
    separate 1-D arrays rather than one ``(trace_count, channel_count)``
    grid: nothing in this project supplies a per-channel along-track offset
    or a per-trace cross-track offset (see the Sprint 3D-0 audit), so a
    joint 2-D array would only ever be their outer sum -- callers that need
    the full acquisition-point grid (e.g. the plan view) broadcast the two
    themselves. ``x_coordinates``/``y_coordinates`` (shape ``(trace_count,
    channel_count)``) are the one genuinely per-point 2-D field, because
    real per-(trace, channel) coordinates *are* available in this project's
    data (the ``Sample Geolocations`` block).

    All arrays are frozen (read-only) on construction, exactly like
    ``GPRDataset`` (ADR-001) -- this is a value object, never mutated after
    :func:`archaeogpr.geometry.resolve.resolve_survey_geometry` returns it.
    """

    trace_count: int
    channel_count: int
    coordinate_mode: CoordinateMode
    along_track_coordinates: np.ndarray | None
    cross_track_offsets: np.ndarray | None
    trace_spacing_m: float | None
    channel_spacing_m: float | None
    channel_zero_offset_m: float | None
    origin_x: float | None
    origin_y: float | None
    azimuth_deg: float | None
    cross_track_direction: CrossTrackDirection
    crs_identifier: str | None
    x_coordinates: np.ndarray | None
    y_coordinates: np.ndarray | None
    provenance: dict[str, GeometryProvenance]
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    geometry_revision: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "along_track_coordinates",
            _freeze_1d("along_track_coordinates", self.along_track_coordinates),
        )
        object.__setattr__(
            self, "cross_track_offsets", _freeze_1d("cross_track_offsets", self.cross_track_offsets)
        )
        object.__setattr__(self, "x_coordinates", _freeze_2d("x_coordinates", self.x_coordinates))
        object.__setattr__(self, "y_coordinates", _freeze_2d("y_coordinates", self.y_coordinates))
        object.__setattr__(self, "provenance", dict(self.provenance))

    def provenance_for(self, field_name: str) -> GeometryProvenance:
        """The provenance recorded for ``field_name``, or ``MISSING`` if it was never set."""
        return self.provenance.get(field_name, GeometryProvenance.MISSING)

    @property
    def crs_validation_status(self) -> CrsValidationStatus:
        """Derived from ``crs_identifier``/its provenance -- never a separately-set field.

        Keeping this a computed property (instead of a stored field set
        alongside ``crs_identifier``) guarantees the two can never disagree.
        """
        if self.crs_identifier is None:
            return CrsValidationStatus.MISSING
        provenance = self.provenance_for("crs_identifier")
        if provenance is GeometryProvenance.USER_SUPPLIED:
            return CrsValidationStatus.USER_SUPPLIED_UNVERIFIED
        return CrsValidationStatus.DECLARED_UNVERIFIED
