"""GUI Survey Geometry Inspector tests (Sprint 3D-0). Run with ``QT_QPA_PLATFORM=offscreen``.

Every test here is marked ``@pytest.mark.gui`` (module-level ``pytestmark``),
collected separately from the core suite exactly like ``test_gui.py``/
``test_gui_processing.py`` (see their own module docstrings).

Item numbers in each test's docstring match the sprint's own GUI test plan
(items 26-55; 1-25 are the Qt-free domain tests in ``tests/test_geometry.py``)
so each test name can be traced back to the specific behavior requested.
"""

from __future__ import annotations

import hashlib
import json
import threading
import warnings
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QFileDialog, QMessageBox

from archaeogpr.geometry import CoordinateMode
from archaeogpr.gui.main_window import MainWindow
from archaeogpr.gui.processing.models import ProcessingOperationSpec
from archaeogpr.gui.processing.registry import DC_OFFSET, REGISTRY
from archaeogpr.gui.workers import file_loader as file_loader_module
from archaeogpr.io.ogpr_reader import read_ogpr

pytestmark = pytest.mark.gui

pg.setConfigOptions(imageAxisOrder="row-major")


@pytest.fixture
def no_blocking_dialogs(monkeypatch):
    """Prevent QMessageBox.critical/warning/question from hanging offscreen tests.

    See test_gui_processing.py's fixture of the same name -- kept local to
    avoid cross-test-file coupling.
    """
    calls: list[tuple[str, tuple, dict]] = []
    monkeypatch.setattr(
        QMessageBox, "critical", staticmethod(lambda *a, **k: calls.append(("critical", a, k)))
    )
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls.append(("warning", a, k))))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: (calls.append(("question", a, k)), QMessageBox.StandardButton.Yes)[1]),
    )
    return calls


class _GatedFileReader:
    """Same shape as test_gui.py's ``_GatedReader`` -- kept local to avoid cross-test-file coupling."""

    def __init__(self, dataset):
        self.started = threading.Event()
        self._release_event = threading.Event()
        self.dataset = dataset

    def __call__(self, _path):
        self.started.set()
        released = self._release_event.wait(timeout=5.0)
        assert released, "test never called release()"
        return self.dataset

    def release(self) -> None:
        self._release_event.set()


class _GatedApply:
    """Same shape as test_gui_processing.py's ``_GatedApply`` -- kept local to avoid cross-file coupling."""

    def __init__(self, real_apply):
        self.started = threading.Event()
        self._release_event = threading.Event()
        self._real_apply = real_apply

    def __call__(self, dataset, params, valid_mask):
        self.started.set()
        released = self._release_event.wait(timeout=5.0)
        assert released, "test never called release() -- see _GatedApply"
        return self._real_apply(dataset, params, valid_mask)

    def release(self) -> None:
        self._release_event.set()


def _spec_with_apply(base_spec: ProcessingOperationSpec, apply_fn) -> ProcessingOperationSpec:
    """A throwaway spec, identical to ``base_spec`` but with ``apply_fn``. Never mutates the registry."""
    return ProcessingOperationSpec(
        operation_id=base_spec.operation_id,
        display_name=base_spec.display_name,
        description=base_spec.description,
        parameters=base_spec.parameters,
        changes_time_axis=base_spec.changes_time_axis,
        apply=apply_fn,
        validate=base_spec.validate,
    )


def _select_operation(window: MainWindow, operation_id: str) -> None:
    index = [spec.operation_id for spec in REGISTRY].index(operation_id)
    window.operation_combo.setCurrentIndex(index)


def _make_dataset(dataset_factory, **kwargs):
    kwargs.setdefault("slices_count", 6)
    kwargs.setdefault("channels_count", 2)
    kwargs.setdefault("samples_count", 200)
    kwargs.setdefault("sampling_time_ns", 0.5)
    return dataset_factory(**kwargs)


def _make_real_geolocation_dataset(ogpr_builder, tmp_path, name="geo.ogpr", **kwargs):
    """A dataset with real per-trace geolocation (GLOBAL_PROJECTED-mode-capable), via the real reader."""
    path = tmp_path / name
    path.write_bytes(ogpr_builder(**kwargs))
    return read_ogpr(path)


def _load_dataset(window: MainWindow, dataset, path: Path) -> None:
    """Synchronously commit a dataset and run the exact post-load refresh MainWindow itself runs."""
    window.session.commit_dataset(dataset, path)
    window._refresh_for_new_dataset()


# ============================================================
# Geometry Inspector dock and summary
# ============================================================


def test_geometry_dock_is_created(qtbot):
    """26: the Survey Geometry dock, its panel, and the Plan View all exist."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert window._geometry_dock.windowTitle() == "Survey Geometry"
    assert window.geometry_panel is not None
    assert window.plan_view is not None
    assert window._plan_view_dock.windowTitle() == "Plan View"


def test_geometry_summary_updates_after_load(qtbot, dataset_factory):
    """27: geometry summary (the info tree) populates after a successful load."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.geometry_panel.tree.topLevelItemCount() == 0

    _load_dataset(window, dataset, Path("x.ogpr"))
    assert window.geometry_session.resolution is not None
    assert window.geometry_panel.tree.topLevelItemCount() == 7


def test_geometry_controls_disabled_with_no_dataset(qtbot):
    """28: override form/buttons/export are disabled before any file is loaded."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert not window.geometry_apply_button.isEnabled()
    assert not window.geometry_discard_button.isEnabled()
    assert not window.geometry_reset_button.isEnabled()
    assert not window.geometry_trace_spacing_spin.isEnabled()
    assert not window.export_geometry_action.isEnabled()


# ============================================================
# Coordinate mode axis labels / CRS
# ============================================================


def test_index_mode_axis_labels_correct(qtbot, dataset_factory):
    """29: index-mode plan view axis labels are 'Trace index'/'Channel index'."""
    dataset = _make_dataset(dataset_factory, metadata={})
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    assert window.geometry_session.geometry.coordinate_mode is CoordinateMode.INDEX
    assert window.plan_view.plot_widget.getAxis("bottom").labelText == "Trace index"
    assert window.plan_view.plot_widget.getAxis("left").labelText == "Channel index"


def test_local_metric_mode_axis_labels_correct(qtbot, dataset_factory):
    """30: local-metric-mode plan view axis labels are 'Along-track (m)'/'Cross-track (m)'."""
    dataset = _make_dataset(dataset_factory, metadata={})
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    window._on_geometry_override_changed("trace_spacing_m", 0.5)
    window._on_geometry_override_changed("channel_spacing_m", 0.2)
    window._on_apply_geometry_clicked()

    assert window.geometry_session.geometry.coordinate_mode is CoordinateMode.LOCAL_METRIC
    assert window.plan_view.plot_widget.getAxis("bottom").labelText == "Along-track (m)"
    assert window.plan_view.plot_widget.getAxis("left").labelText == "Cross-track (m)"


def test_global_mode_axis_labels_and_crs_correct(qtbot, ogpr_builder, tmp_path):
    """31: global-mode plan view axis labels are 'Easting (m)'/'Northing (m)', CRS shown correctly."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    assert window.geometry_session.geometry.coordinate_mode is CoordinateMode.GLOBAL_PROJECTED
    assert window.plan_view.plot_widget.getAxis("bottom").labelText == "Easting (m)"
    assert window.plan_view.plot_widget.getAxis("left").labelText == "Northing (m)"
    assert window.geometry_session.geometry.crs_identifier == "EPSG:32632"

    georef_group = window.geometry_panel.tree.topLevelItem(3)
    assert georef_group.text(0) == "D. Georeferencing"
    crs_row_text = [georef_group.child(i).text(1) for i in range(georef_group.childCount())]
    assert any("EPSG:32632" in text and "File metadata" in text for text in crs_row_text)


def test_crs_validation_status_shown_unverified(qtbot, ogpr_builder, tmp_path):
    """Pre-commit audit: the GUI must never show a bare 'Global projected' --
    the coordinate-mode row and a dedicated georeferencing row must both make
    the CRS's unverified status explicit (see ADR-016 / ISSUE-001)."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    status_group = window.geometry_panel.tree.topLevelItem(0)
    assert status_group.text(0) == "A. Geometry status"
    mode_row = next(
        status_group.child(i)
        for i in range(status_group.childCount())
        if status_group.child(i).text(0) == "Coordinate mode"
    )
    assert mode_row.text(1) == "Global projected — declared CRS, unverified"

    georef_group = window.geometry_panel.tree.topLevelItem(3)
    validation_row = next(
        georef_group.child(i)
        for i in range(georef_group.childCount())
        if georef_group.child(i).text(0) == "CRS validation status"
    )
    assert validation_row.text(1) == "declared_unverified"

    validation_group = window.geometry_panel.tree.topLevelItem(5)
    assert validation_group.text(0) == "F. Validation"
    warning_texts = [validation_group.child(i).text(1) for i in range(validation_group.childCount())]
    assert any("not authority-verified" in text for text in warning_texts)


def test_gui_shows_sampling_and_rectilinearity_separately(qtbot, ogpr_builder, tmp_path):
    """Pre-commit audit round 2: sampling regularity, direction consistency, and
    rectilinear fit must appear as distinct rows -- never collapsed into one
    "is regular" flag. Real file: sampling/direction pass, rectilinear fit fails."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    status_group = window.geometry_panel.tree.topLevelItem(0)
    assert status_group.text(0) == "A. Geometry status"
    status_rows = {
        status_group.child(i).text(0): status_group.child(i).text(1) for i in range(status_group.childCount())
    }
    assert status_rows["Rectilinear C-scan readiness"] == "Not ready"
    assert status_rows["Actual X/Y point-grid readiness"] == "Ready"

    regularity_group = window.geometry_panel.tree.topLevelItem(6)
    assert regularity_group.text(0) == "G. Grid Regularity"
    rows = {
        regularity_group.child(i).text(0): regularity_group.child(i).text(1)
        for i in range(regularity_group.childCount())
    }
    assert rows["Actual X/Y point grid"] == "Available"
    assert rows["Sampling regularity"] == "Regular"
    assert rows["Direction consistency"] == "Consistent"
    assert rows["Rectilinear fit"] == "Not acceptable"
    # This fixture's synthetic geolocation (see conftest.py::_build_geo_bytes) is a nearly
    # degenerate, non-perpendicular-width sliver at only 2 channels -- the rectilinear
    # parameter-grid area and the shoelace polygon area are both correctly withheld here
    # (see summary.py's rough-agreement safety check); only the ribbon estimate survives.
    assert rows["Rectilinear parameter-grid area (m2)"] == "—"
    assert rows["Approximate ribbon area (m2)"] != "—"
    assert rows["Actual polygon area (m2)"] == "—"


# ============================================================
# Provenance / readiness / validation display
# ============================================================


def test_provenance_labels_correct(qtbot, ogpr_builder, tmp_path):
    """32: the dedicated Provenance section shows the correct label for each tracked field."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    provenance_group = window.geometry_panel.tree.topLevelItem(4)
    assert provenance_group.text(0) == "E. Provenance"
    rows = {
        provenance_group.child(i).text(0): provenance_group.child(i).text(1)
        for i in range(provenance_group.childCount())
    }
    assert rows["Trace spacing"] == "File metadata"
    assert rows["Global X coordinates"] == "File metadata"
    assert rows["CRS/EPSG"] == "File metadata"


def test_readiness_statuses_shown_correctly(qtbot, ogpr_builder, tmp_path):
    """33: readiness statuses in section A read 'Ready'/'Not ready' as expected."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    status_group = window.geometry_panel.tree.topLevelItem(0)
    rows = {
        status_group.child(i).text(0): status_group.child(i).text(1) for i in range(status_group.childCount())
    }
    assert rows["Global C-scan readiness"] == "Ready"
    assert rows["Depth-volume readiness"] == "Not ready"


def test_blocking_issue_and_warning_separated(qtbot, dataset_factory):
    """34: validation section separates 'Blocking [i]' rows from 'Warning [i]' rows."""
    dataset = _make_dataset(dataset_factory, metadata={})
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    validation_group = window.geometry_panel.tree.topLevelItem(5)
    assert validation_group.text(0) == "F. Validation"
    field_names = [validation_group.child(i).text(0) for i in range(validation_group.childCount())]
    assert any(name.startswith("Blocking") for name in field_names)
    assert not any(name.startswith("Warning") and "Blocking" in name for name in field_names)


# ============================================================
# Override apply / discard / reset
# ============================================================


def test_override_apply_increments_geometry_revision(qtbot, dataset_factory):
    """35: a valid Apply Geometry bumps geometry_revision and updates the resolved value."""
    dataset = _make_dataset(dataset_factory, metadata={})
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    revision_before = window.geometry_session.geometry_revision

    window._on_geometry_override_changed("trace_spacing_m", 0.5)
    window._on_apply_geometry_clicked()

    assert window.geometry_session.geometry_revision == revision_before + 1
    assert window.geometry_session.geometry.trace_spacing_m == pytest.approx(0.5)


def test_invalid_override_prevents_apply(qtbot, dataset_factory):
    """36: an invalid override is rejected by Apply Geometry -- revision does not change."""
    dataset = _make_dataset(dataset_factory, metadata={})
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    revision_before = window.geometry_session.geometry_revision

    window._on_geometry_override_changed("trace_spacing_m", -1.0)
    window._on_apply_geometry_clicked()

    assert window.geometry_session.geometry_revision == revision_before
    assert window.geometry_validation_label.text() != ""


def test_discard_overrides_does_not_change_geometry(qtbot, dataset_factory):
    """37: Discard Overrides never touches the resolved geometry, only the pending form."""
    dataset = _make_dataset(dataset_factory, metadata={})
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    resolution_before = window.geometry_session.resolution
    revision_before = window.geometry_session.geometry_revision

    window._on_geometry_override_changed("trace_spacing_m", 0.5)
    assert window.geometry_session.has_pending_changes
    window._on_discard_geometry_overrides_clicked()

    assert not window.geometry_session.has_pending_changes
    assert window.geometry_session.resolution is resolution_before
    assert window.geometry_session.geometry_revision == revision_before


def test_reset_geometry_returns_to_file_metadata(qtbot, dataset_factory):
    """38: Reset Geometry to File Metadata clears an applied override back to file-derived values."""
    dataset = _make_dataset(dataset_factory, metadata={})
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    window._on_geometry_override_changed("trace_spacing_m", 0.5)
    window._on_apply_geometry_clicked()
    assert window.geometry_session.geometry.provenance_for("trace_spacing_m").value == "user_supplied"

    window._on_reset_geometry_clicked()
    assert window.geometry_session.geometry.provenance_for("trace_spacing_m").value == "missing"
    assert window.geometry_session.applied_overrides.trace_spacing_m is None


# ============================================================
# Busy-state interaction (file load / processing)
# ============================================================


def test_apply_geometry_disabled_during_processing(qtbot, no_blocking_dialogs, dataset_factory):
    """39: Apply Geometry is rejected while a processing preview is running."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    revision_before = window.geometry_session.geometry_revision

    gated = _GatedApply(DC_OFFSET.apply)
    spec = _spec_with_apply(DC_OFFSET, gated)
    window._start_processing_preview(spec, DC_OFFSET.defaults())
    assert gated.started.wait(timeout=5.0)

    window._on_geometry_override_changed("trace_spacing_m", 0.5)
    window._on_apply_geometry_clicked()
    assert window.geometry_session.geometry_revision == revision_before

    gated.release()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)


def test_geometry_controls_disabled_during_file_load(qtbot, monkeypatch, dataset_factory):
    """40: Apply/Reset Geometry are rejected while a file load is running."""
    initial_dataset = _make_dataset(dataset_factory)
    incoming_dataset = _make_dataset(dataset_factory)
    reader = _GatedFileReader(incoming_dataset)
    monkeypatch.setattr(file_loader_module, "read_ogpr", reader)

    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, initial_dataset, Path("x.ogpr"))
    revision_before = window.geometry_session.geometry_revision

    window.open_path("second.ogpr")
    assert reader.started.wait(timeout=5.0)
    assert window.is_loading

    window._on_geometry_override_changed("trace_spacing_m", 0.5)
    window._on_apply_geometry_clicked()
    window._on_reset_geometry_clicked()
    assert window.geometry_session.geometry_revision == revision_before

    reader.release()
    qtbot.waitUntil(lambda: not window.is_loading, timeout=5000)


def test_failed_load_preserves_previous_geometry(qtbot, monkeypatch, dataset_factory, no_blocking_dialogs):
    """41: a failed load leaves the previous file's resolved geometry completely untouched."""
    dataset = _make_dataset(dataset_factory)
    monkeypatch.setattr(file_loader_module, "read_ogpr", lambda _path: (_ for _ in ()).throw(OSError("boom")))

    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    resolution_before = window.geometry_session.resolution

    window.open_path("bad.ogpr")
    qtbot.waitUntil(lambda: not window.is_loading, timeout=5000)

    assert window.geometry_session.resolution is resolution_before


def test_cancelled_load_preserves_previous_geometry(qtbot, monkeypatch, dataset_factory):
    """42: a cancelled load leaves the previous file's resolved geometry completely untouched."""
    old_dataset = _make_dataset(dataset_factory)
    new_dataset = _make_dataset(dataset_factory, slices_count=9)
    reader = _GatedFileReader(new_dataset)
    monkeypatch.setattr(file_loader_module, "read_ogpr", reader)

    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, old_dataset, Path("x.ogpr"))
    resolution_before = window.geometry_session.resolution

    window.open_path("new.ogpr")
    assert reader.started.wait(timeout=5.0)
    window._on_cancel_load_clicked()
    reader.release()
    qtbot.waitUntil(lambda: not window.is_loading, timeout=5000)

    assert window.geometry_session.resolution is resolution_before


# ============================================================
# Trace/channel <-> Plan View selection sync
# ============================================================


def test_plan_point_selection_updates_trace_and_channel(qtbot, dataset_factory):
    """43: clicking a plan-view point updates the selected trace and channel."""
    dataset = _make_dataset(dataset_factory, slices_count=10, channels_count=4)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    window._on_plan_point_clicked(7, 2)
    assert window.session.selected_trace == 7
    assert window.session.selected_channel == 2


def test_trace_channel_selection_updates_plan_highlight(qtbot, dataset_factory):
    """44: selecting a trace/channel via the B-scan/spinboxes updates the Plan View's highlight."""
    dataset = _make_dataset(dataset_factory, slices_count=10, channels_count=4)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    window._select_trace(6)
    assert window.plan_view._selected_trace == 6
    window._on_channel_changed(3)
    assert window.plan_view._selected_channel == 3


def test_selected_trace_channel_clamped_after_load(qtbot, dataset_factory):
    """45: the Plan View's selection reflects the (already-clamped) session selection after load."""
    dataset = _make_dataset(dataset_factory, slices_count=5, channels_count=2)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    assert window.session.selected_trace == 0
    assert window.plan_view._selected_trace == 0
    assert window.plan_view._selected_channel == 0


# ============================================================
# Geometry stability across processing transitions
# ============================================================


def test_processing_transitions_do_not_change_geometry(qtbot, no_blocking_dialogs, dataset_factory):
    """46: Preview -> Apply -> Discard -> Reset-to-Raw processing transitions never touch geometry."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    resolution_before = window.geometry_session.resolution
    revision_before = window.geometry_session.geometry_revision

    _select_operation(window, "dc_offset")
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: window.session.has_fresh_preview, timeout=5000)
    window._on_apply_preview_clicked()

    assert window.geometry_session.resolution is resolution_before
    assert window.geometry_session.geometry_revision == revision_before


def test_time_zero_preview_does_not_change_geometry_xy(qtbot, no_blocking_dialogs, ogpr_builder, tmp_path):
    """47: a time-zero preview/apply (which changes time_ns) never changes geometry X/Y."""
    # samples_count/sampling_time_ns large enough that time_zero's default
    # search window ([5, 15) ns) actually falls inside the recorded time
    # range -- the builder's own tiny defaults (4 samples * 0.5 ns = 2 ns
    # total) don't, and correct_time_zero correctly raises for an
    # out-of-range window (a test-setup bug, not a production one; see
    # ADR-015's documented dewow-test-bug precedent).
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path, samples_count=200, sampling_time_ns=0.5)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    x_before = window.geometry_session.geometry.x_coordinates.copy()
    revision_before = window.geometry_session.geometry_revision

    _select_operation(window, "time_zero")
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: window.session.has_fresh_preview, timeout=5000)
    window._on_apply_preview_clicked()

    assert window.geometry_session.geometry_revision == revision_before
    assert np.array_equal(window.geometry_session.geometry.x_coordinates, x_before)


# ============================================================
# Plan View rendering behavior
# ============================================================


def test_plan_view_uses_equal_aspect(qtbot, dataset_factory):
    """48: the Plan View locks an equal aspect ratio."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.plan_view.view_box.state["aspectLocked"] is not False


def test_fit_to_data_works(qtbot, dataset_factory):
    """49: fit_to_data() runs without error after geometry is set."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    window.plan_view.fit_to_data()  # must not raise


def test_invalid_point_display_does_not_crash(qtbot, dataset_factory):
    """50: a geometry with non-finite coordinates renders without crashing or warning.

    Pre-commit audit: the broken row (along_track_coordinates[0] = NaN)
    broadcasts to an all-NaN X value across every channel in that row --
    exactly the shape that used to make pyqtgraph's internal np.nanmin/
    np.nanmax bounds computation raise "RuntimeWarning: All-NaN slice
    encountered" (see PlanView.set_geometry()'s invalid_scatter handling).
    dataBounds() is called directly (rather than relying on autoRange()/show()
    timing) so the check is deterministic.
    """
    from dataclasses import replace as dc_replace

    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    window._on_geometry_override_changed("trace_spacing_m", 1.0)
    window._on_geometry_override_changed("channel_spacing_m", 1.0)
    window._on_apply_geometry_clicked()

    geometry = window.geometry_session.geometry
    broken_along = geometry.along_track_coordinates.copy()
    broken_along.setflags(write=True)
    broken_along[0] = float("nan")
    broken_geometry = dc_replace(geometry, along_track_coordinates=broken_along)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        window.plan_view.set_geometry(broken_geometry)  # must not raise
        window.plan_view.invalid_scatter.dataBounds(ax=0)
        window.plan_view.invalid_scatter.dataBounds(ax=1)
    assert caught == []


def test_hover_readout_reports_correct_index_and_coordinate(qtbot, dataset_factory):
    """51: hovering over a plan-view point reports the correct trace/channel/coordinate."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    window._on_plan_point_hovered(3, 1, 12.5, -4.25)
    assert "trace 3" in window.cursor_label.text()
    assert "channel 01" in window.cursor_label.text()
    assert "12.5" in window.cursor_label.text()


# ============================================================
# Geometry report export
# ============================================================


def test_export_geometry_report_produces_correct_json(qtbot, monkeypatch, dataset_factory, tmp_path):
    """52: File -> Export Geometry Report produces a correct, loadable JSON file."""
    dataset = _make_dataset(dataset_factory, metadata={})
    # export_geometry_report hashes the *source* file from disk -- unlike
    # most tests here, a placeholder Path("x.ogpr") that doesn't actually
    # exist would make that hash step raise, which main_window.py correctly
    # reports via QMessageBox.critical (not mocked in this test) and hangs
    # offscreen -- give it a real, on-disk (content-irrelevant) file instead.
    source_path = tmp_path / "source.ogpr"
    source_path.write_bytes(b"placeholder")
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, source_path)

    out_path = tmp_path / "exported.geometry.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_path), "")))

    window._on_export_geometry_report_triggered()

    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["coordinate_mode"] == window.geometry_session.geometry.coordinate_mode.value
    assert payload["geometry_revision"] == window.geometry_session.geometry_revision


def test_export_cancellation_leaves_no_file(qtbot, monkeypatch, dataset_factory, tmp_path):
    """53: cancelling the save dialog leaves no geometry report file behind."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: ("", "")))
    window._on_export_geometry_report_triggered()

    assert list(tmp_path.iterdir()) == []


def test_shutdown_pending_rejects_geometry_apply_and_export(qtbot, monkeypatch, dataset_factory, tmp_path):
    """54: Apply Geometry and Export Geometry Report are both rejected once shutdown is pending."""
    dataset = _make_dataset(dataset_factory, metadata={})
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    revision_before = window.geometry_session.geometry_revision

    window._close_pending = True
    out_path = tmp_path / "should_not_exist.geometry.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out_path), "")))

    window._on_geometry_override_changed("trace_spacing_m", 0.5)
    window._on_apply_geometry_clicked()
    window._on_export_geometry_report_triggered()

    assert window.geometry_session.geometry_revision == revision_before
    assert not out_path.exists()
    window._close_pending = False  # avoid leaving the window in a deferred-close state for qtbot teardown


def test_geometry_operations_do_not_touch_raw_ogpr_file(qtbot, monkeypatch, ogpr_builder, tmp_path):
    """55: resolving/overriding/applying/exporting geometry never touches the raw .ogpr file."""
    ogpr_path = tmp_path / "real.ogpr"
    raw_bytes = ogpr_builder()
    ogpr_path.write_bytes(raw_bytes)
    hash_before = hashlib.sha256(ogpr_path.read_bytes()).hexdigest()
    mtime_before = ogpr_path.stat().st_mtime_ns

    dataset = read_ogpr(ogpr_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, ogpr_path)

    window._on_geometry_override_changed("trace_spacing_m", 0.9)
    window._on_apply_geometry_clicked()
    export_path = tmp_path / "real.geometry.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(export_path), "")))
    window._on_export_geometry_report_triggered()

    assert hashlib.sha256(ogpr_path.read_bytes()).hexdigest() == hash_before
    assert ogpr_path.stat().st_mtime_ns == mtime_before
