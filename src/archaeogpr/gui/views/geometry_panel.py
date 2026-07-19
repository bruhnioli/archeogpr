"""Read-only Survey Geometry info tree (Sprint 3D-0): status, axes, spacing/
orientation, georeferencing, per-field provenance, and validation.

Mirrors :mod:`archaeogpr.gui.views.metadata_panel`'s grouped
(field, value) ``QTreeWidget`` convention exactly (including its
copy-to-clipboard context menu) -- this is a display of a
:class:`~archaeogpr.geometry.resolve.GeometryResolution`, never of
``dataset.amplitudes``, and never mutates anything.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QHeaderView,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from archaeogpr.geometry.models import (
    CoordinateMode,
    CrsValidationStatus,
    GeometryProvenance,
    ReadinessStatus,
)
from archaeogpr.geometry.resolve import GeometryResolution
from archaeogpr.geometry.summary import compute_geometry_summary

_MISSING = "—"

_PROVENANCE_LABELS: dict[GeometryProvenance, str] = {
    GeometryProvenance.FILE_METADATA: "File metadata",
    GeometryProvenance.DERIVED: "Derived",
    GeometryProvenance.USER_SUPPLIED: "User supplied",
    GeometryProvenance.INDEX_SPACE: "Index fallback",
    GeometryProvenance.MISSING: "Missing",
}

_COORDINATE_MODE_LABELS: dict[CoordinateMode, str] = {
    CoordinateMode.INDEX: "Index",
    CoordinateMode.LOCAL_METRIC: "Local metric",
    CoordinateMode.GLOBAL_PROJECTED: "Global projected",
    CoordinateMode.GLOBAL_GEOGRAPHIC: "Global geographic",
}

#: Suffix appended to the "Global projected" label so the CRS's verification
#: status is never silently implied to be a surveyed fact (see ADR-016 /
#: Sprint 3D-0 pre-commit audit section 3, ISSUE-001). VALIDATED is never
#: produced this sprint but is handled here for completeness.
_CRS_VALIDATION_SUFFIXES: dict[CrsValidationStatus, str] = {
    CrsValidationStatus.MISSING: " — no CRS known",
    CrsValidationStatus.DECLARED_UNVERIFIED: " — declared CRS, unverified",
    CrsValidationStatus.USER_SUPPLIED_UNVERIFIED: " — user-supplied CRS, unverified",
    CrsValidationStatus.VALIDATED: "",
}


def _coordinate_mode_label(mode: CoordinateMode, crs_validation_status: CrsValidationStatus) -> str:
    label = _COORDINATE_MODE_LABELS[mode]
    if mode is CoordinateMode.GLOBAL_PROJECTED:
        label += _CRS_VALIDATION_SUFFIXES[crs_validation_status]
    return label


_TRACKED_FIELDS: tuple[tuple[str, str], ...] = (
    ("trace_spacing_m", "Trace spacing"),
    ("channel_spacing_m", "Channel spacing"),
    ("channel_zero_offset_m", "Channel zero offset"),
    ("origin_x", "Origin Easting/X"),
    ("origin_y", "Origin Northing/Y"),
    ("azimuth_deg", "Azimuth"),
    ("cross_track_direction", "Cross-track direction"),
    ("crs_identifier", "CRS/EPSG"),
    ("x_coordinates", "Global X coordinates"),
    ("y_coordinates", "Global Y coordinates"),
)


def _fmt(value: Any) -> str:
    if value is None:
        return _MISSING
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _fmt_with_provenance(value: Any, provenance: GeometryProvenance) -> str:
    if value is None:
        return _MISSING
    return f"{_fmt(value)} ({_PROVENANCE_LABELS[provenance]})"


def _fmt_ready(status: ReadinessStatus) -> str:
    return "Ready" if status.ready else "Not ready"


def _fmt_tri_state(value: bool | None, true_label: str, false_label: str) -> str:
    if value is None:
        return "N/A"
    return true_label if value else false_label


def _fmt_ratio(value: float | None) -> str:
    return _MISSING if value is None else f"{value:.2f}x"


class GeometryPanel(QWidget):
    """Read-only survey-geometry info tree: status / axes / spacing / georeferencing / provenance."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Field", "Value"])
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.setRootIsDecorated(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)

    def clear(self) -> None:
        self.tree.clear()

    def _add_group(self, title: str) -> QTreeWidgetItem:
        group = QTreeWidgetItem([title, ""])
        self.tree.addTopLevelItem(group)
        group.setExpanded(True)
        return group

    def _add_row(self, parent: QTreeWidgetItem, field: str, value: Any) -> None:
        text = _fmt(value)
        item = QTreeWidgetItem([field, text])
        item.setToolTip(0, field)
        item.setToolTip(1, text)
        parent.addChild(item)

    def _show_context_menu(self, position: QPoint) -> None:
        item = self.tree.itemAt(position)
        if item is None or item.parent() is None:
            return
        menu = QMenu(self.tree)

        def _copy(text: str) -> None:
            QApplication.clipboard().setText(text)

        field_text, value_text = item.text(0), item.text(1)
        copy_field = QAction("Copy field", self.tree)
        copy_field.triggered.connect(lambda: _copy(field_text))
        copy_value = QAction("Copy value", self.tree)
        copy_value.triggered.connect(lambda: _copy(value_text))
        copy_row = QAction("Copy row", self.tree)
        copy_row.triggered.connect(lambda: _copy(f"{field_text}\t{value_text}"))
        menu.addAction(copy_field)
        menu.addAction(copy_value)
        menu.addAction(copy_row)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    def set_resolution(self, resolution: GeometryResolution) -> None:
        self.clear()
        geometry = resolution.geometry
        readiness = resolution.readiness
        summary = compute_geometry_summary(geometry)

        status = self._add_group("A. Geometry status")
        self._add_row(
            status,
            "Coordinate mode",
            _coordinate_mode_label(geometry.coordinate_mode, geometry.crs_validation_status),
        )
        self._add_row(status, "Geometry revision", geometry.geometry_revision)
        self._add_row(status, "Index view readiness", _fmt_ready(readiness.index_view_ready))
        self._add_row(
            status, "Local parameter-grid readiness", _fmt_ready(readiness.local_parameter_grid_ready)
        )
        self._add_row(status, "Rectilinear C-scan readiness", _fmt_ready(readiness.rectilinear_cscan_ready))
        self._add_row(
            status, "Actual X/Y point-grid readiness", _fmt_ready(readiness.actual_xy_point_grid_ready)
        )
        self._add_row(status, "Global C-scan readiness", _fmt_ready(readiness.global_cscan_ready))
        self._add_row(status, "Time-volume readiness", _fmt_ready(readiness.time_volume_ready))
        self._add_row(status, "Depth-volume readiness", _fmt_ready(readiness.depth_volume_ready))

        axes = self._add_group("B. Dataset axes")
        self._add_row(axes, "Trace count", geometry.trace_count)
        self._add_row(axes, "Channel count", geometry.channel_count)
        self._add_row(axes, "Axis mapping", resolution.source_summary.get("axis_order"))
        self._add_row(
            axes,
            "Along-track extent (derived parameter grid)",
            f"{summary.along_track_min:.6g} – {summary.along_track_max:.6g}"
            if summary.along_track_min is not None
            else None,
        )
        self._add_row(
            axes,
            "Cross-track extent (derived parameter grid)",
            f"{summary.cross_track_min:.6g} – {summary.cross_track_max:.6g}"
            if summary.cross_track_min is not None
            else None,
        )

        spacing = self._add_group("C. Spacing and orientation")
        self._add_row(
            spacing,
            "Trace spacing (m)",
            _fmt_with_provenance(geometry.trace_spacing_m, geometry.provenance_for("trace_spacing_m")),
        )
        self._add_row(
            spacing,
            "Channel spacing (m)",
            _fmt_with_provenance(geometry.channel_spacing_m, geometry.provenance_for("channel_spacing_m")),
        )
        self._add_row(
            spacing,
            "Channel zero offset (m)",
            _fmt_with_provenance(
                geometry.channel_zero_offset_m, geometry.provenance_for("channel_zero_offset_m")
            ),
        )
        self._add_row(
            spacing,
            "Azimuth (deg)",
            _fmt_with_provenance(geometry.azimuth_deg, geometry.provenance_for("azimuth_deg")),
        )
        self._add_row(
            spacing,
            "Cross-track direction",
            _fmt_with_provenance(
                geometry.cross_track_direction.value, geometry.provenance_for("cross_track_direction")
            ),
        )

        georef = self._add_group("D. Georeferencing")
        self._add_row(
            georef,
            "Origin Easting/X",
            _fmt_with_provenance(geometry.origin_x, geometry.provenance_for("origin_x")),
        )
        self._add_row(
            georef,
            "Origin Northing/Y",
            _fmt_with_provenance(geometry.origin_y, geometry.provenance_for("origin_y")),
        )
        self._add_row(
            georef,
            "CRS/EPSG",
            _fmt_with_provenance(geometry.crs_identifier, geometry.provenance_for("crs_identifier")),
        )
        self._add_row(
            georef,
            "CRS validation status",
            geometry.crs_validation_status.value,
        )
        self._add_row(
            georef,
            "Global X/Y grid source",
            _PROVENANCE_LABELS[geometry.provenance_for("x_coordinates")]
            if geometry.x_coordinates is not None
            else None,
        )
        self._add_row(
            georef,
            "Global X extent (actual point grid)",
            f"{summary.x_min:.6g} – {summary.x_max:.6g}" if summary.x_min is not None else None,
        )
        self._add_row(
            georef,
            "Global Y extent (actual point grid)",
            f"{summary.y_min:.6g} – {summary.y_max:.6g}" if summary.y_min is not None else None,
        )

        provenance_group = self._add_group("E. Provenance")
        for field_name, label in _TRACKED_FIELDS:
            self._add_row(provenance_group, label, _PROVENANCE_LABELS[geometry.provenance_for(field_name)])

        validation = self._add_group("F. Validation")
        all_gates = (
            readiness.index_view_ready,
            readiness.local_parameter_grid_ready,
            readiness.rectilinear_cscan_ready,
            readiness.actual_xy_point_grid_ready,
            readiness.global_cscan_ready,
            readiness.time_volume_ready,
            readiness.depth_volume_ready,
        )
        all_errors = list(geometry.errors)
        all_blocking = [issue for gate in all_gates for issue in gate.blocking_issues]
        all_warnings = (
            list(geometry.warnings)
            + [warning for gate in all_gates for warning in gate.warnings]
            + list(summary.warnings)
        )
        if not all_errors:
            self._add_row(validation, "Errors", "(none)")
        for i, error in enumerate(all_errors):
            self._add_row(validation, f"Error [{i}]", error)
        if not all_blocking:
            self._add_row(validation, "Blocking issues", "(none)")
        for i, issue in enumerate(all_blocking):
            self._add_row(validation, f"Blocking [{i}]", issue)
        if not all_warnings:
            self._add_row(validation, "Warnings", "(none)")
        for i, warning in enumerate(all_warnings):
            self._add_row(validation, f"Warning [{i}]", warning)

        regularity_group = self._add_group("G. Grid Regularity")
        reg = summary.grid_regularity
        self._add_row(
            regularity_group,
            "Actual X/Y point grid",
            "Available" if reg.actual_point_grid_available else "Missing",
        )
        self._add_row(
            regularity_group,
            "Sampling regularity",
            _fmt_tri_state(reg.sampling_regular, "Regular", "Not regular"),
        )
        self._add_row(
            regularity_group,
            "Direction consistency",
            _fmt_tri_state(reg.direction_consistent, "Consistent", "Not consistent"),
        )
        self._add_row(
            regularity_group,
            "Rectilinear fit",
            _fmt_tri_state(reg.rectilinear_fit_acceptable, "Acceptable", "Not acceptable"),
        )
        self._add_row(regularity_group, "Maximum lateral residual (m)", reg.residual_max_m)
        self._add_row(regularity_group, "RMSE lateral residual (m)", reg.residual_rmse_m)
        self._add_row(
            regularity_group,
            "Residual / channel spacing (max)",
            _fmt_ratio(reg.residual_max_over_channel_spacing),
        )
        self._add_row(
            regularity_group,
            "Residual / channel spacing (RMSE)",
            _fmt_ratio(reg.residual_rmse_over_channel_spacing),
        )
        self._add_row(
            regularity_group,
            "Residual / along-track span (max)",
            _fmt_ratio(reg.residual_max_over_along_track_span),
        )
        self._add_row(
            regularity_group,
            "Rectilinear parameter-grid area (m2)",
            summary.rectilinear_parameter_grid_area_m2,
        )
        self._add_row(regularity_group, "Approximate ribbon area (m2)", summary.approximate_ribbon_area_m2)
        self._add_row(regularity_group, "Actual polygon area (m2)", summary.actual_polygon_area_m2)

        self.tree.expandAll()
