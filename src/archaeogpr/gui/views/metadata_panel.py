"""Read-only metadata panel: what's in the currently open dataset.

Reads only ``dataset.metadata`` (a plain, JSON-serializable ``FrozenDict``,
see ADR-001) and ``derive_metadata()`` (``archaeogpr.qc.metadata`` -- the
same pure derivation used by the ``inspect`` CLI, reused here rather than
reimplemented). Every lookup goes through :func:`_get`, which never assumes
a key exists -- missing/partial metadata renders as ``"—"`` rather than
raising, since CLAUDE.md requires the reader to tolerate an incomplete or
unusual header without crashing downstream consumers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QHeaderView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.qc.metadata import derive_metadata

_MISSING = "—"  # em dash: "no value", not "0" or an empty string


def _get(mapping: Any, *keys: str, default: Any = None) -> Any:
    """Chained, missing-safe ``mapping[keys[0]][keys[1]]...`` lookup."""
    current = mapping
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current if current is not None else default


def _fmt(value: Any) -> str:
    if value is None:
        return _MISSING
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


class MetadataPanel(QWidget):
    """Two-column (field, value) tree of the current dataset's metadata."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Field", "Value"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setRootIsDecorated(True)

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
        parent.addChild(QTreeWidgetItem([field, _fmt(value)]))

    def set_dataset(self, dataset: GPRDataset, source_path: Path | None) -> None:
        self.clear()
        metadata = dataset.metadata
        derived = derive_metadata(dataset)
        slices_count, channels_count, samples_count = dataset.shape

        source = self._add_group("Source")
        self._add_row(
            source, "Filename", source_path.name if source_path else _get(metadata, "source_file", "name")
        )
        self._add_row(source, "Path", str(source_path) if source_path else None)

        dims = self._add_group("Dimensions")
        self._add_row(
            dims, "Shape (trace, channel, sample)", f"{slices_count}, {channels_count}, {samples_count}"
        )
        self._add_row(dims, "Trace count", slices_count)
        self._add_row(dims, "Channel count", channels_count)
        self._add_row(dims, "Sample count", samples_count)
        self._add_row(dims, "dtype", _get(metadata, "dtype"))

        sampling = self._add_group("Sampling")
        self._add_row(sampling, "Sampling interval (ns)", _get(metadata, "sampling", "sampling_time_ns"))
        self._add_row(
            sampling, "Along-track sampling step (m)", _get(metadata, "sampling", "sampling_step_m")
        )
        self._add_row(sampling, "Time window (ns)", derived.get("time_window_ns"))

        radar = self._add_group("Radar")
        self._add_row(radar, "Nominal frequency (MHz)", _get(metadata, "radar", "nominal_frequency_MHz"))
        self._add_row(radar, "Polarization", _get(metadata, "radar", "polarization"))
        velocity = _get(metadata, "radar", "propagation_velocity_m_per_ns")
        self._add_row(
            radar,
            "Propagation velocity (m/ns)",
            f"{velocity:.6g} (unvalidated -- file metadata assumption)" if velocity is not None else None,
        )

        geo = self._add_group("Geolocation")
        self._add_row(geo, "Geolocation present", dataset.has_geolocation)
        spatial_reference = _get(metadata, "spatial_reference")
        self._add_row(
            geo,
            "Spatial reference",
            f"{spatial_reference} (unvalidated -- not reprojected/checked)" if spatial_reference else None,
        )

        history = self._add_group("Processing history")
        self._add_row(history, "Step count", len(dataset.processing_history))
        for i, step in enumerate(dataset.processing_history):
            self._add_row(
                history, f"  [{i}] operation", step.get("operation") if isinstance(step, dict) else None
            )

        warnings_group = self._add_group("Warnings")
        warnings = list(_get(metadata, "warnings", default=[]) or []) + list(derived.get("warnings") or [])
        if not warnings:
            self._add_row(warnings_group, "(none)", "")
        for i, warning in enumerate(warnings):
            self._add_row(warnings_group, f"[{i}]", warning)

        self.tree.expandAll()
