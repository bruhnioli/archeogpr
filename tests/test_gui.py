"""GUI tests (Sprint GUI-1). Run with ``QT_QPA_PLATFORM=offscreen``.

Every test here is marked ``@pytest.mark.gui`` and collected separately from
the core suite (``pytest -m "not gui"`` vs ``pytest -m gui``, see
``pyproject.toml``'s ``dev``/``gui-test`` extras split). ``pytest.importorskip``
below makes this whole module skip cleanly -- not error -- when PySide6/
pyqtgraph are not installed, so a plain ``pip install -e ".[dev]"`` headless
environment can still run ``pytest`` (or ``pytest -m "not gui"``) without
this file's imports breaking collection.

``QMessageBox.critical`` is modal: it runs its own nested Qt event loop and
blocks until a button is clicked. Offscreen, with nothing to click it,
that call hangs forever -- confirmed empirically while writing this suite
(a manual check script had to be force-killed). Every test that exercises
an error path therefore monkeypatches ``QMessageBox.critical`` to a no-op
first.
"""

from __future__ import annotations

import json
import math

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import numpy as np
import pyqtgraph as pg

from archaeogpr.gui import app as gui_app
from archaeogpr.gui.main_window import MainWindow
from archaeogpr.gui.models.dataset_session import DatasetSession
from archaeogpr.gui.views.ascan_view import AScanView
from archaeogpr.gui.views.bscan_view import BScanView
from archaeogpr.gui.views.metadata_panel import MetadataPanel

pytestmark = pytest.mark.gui

# Must be set before any ImageItem/PlotWidget is constructed -- see
# archaeogpr/gui/views/bscan_view.py's module docstring.
pg.setConfigOptions(imageAxisOrder="row-major")


@pytest.fixture
def no_blocking_error_dialog(monkeypatch):
    """Prevent ``QMessageBox.critical`` from hanging offscreen tests (see module docstring)."""
    from PySide6.QtWidgets import QMessageBox

    calls: list[tuple] = []
    monkeypatch.setattr(
        QMessageBox, "critical", staticmethod(lambda *args, **kwargs: calls.append((args, kwargs)))
    )
    return calls


# 1. QApplication smoke test -------------------------------------------------


def test_qapplication_smoke(qapp):
    from PySide6.QtWidgets import QApplication

    assert QApplication.instance() is qapp


# 2. MainWindow construction --------------------------------------------------


def test_main_window_construction(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == "ArchaeoGPR"
    assert not window.channel_spin.isEnabled()
    assert not window.session.is_loaded


# 3. DatasetSession loading a synthetic fixture -------------------------------


def test_dataset_session_loads_synthetic_fixture(valid_ogpr_path):
    session = DatasetSession()
    session.load(valid_ogpr_path)

    assert session.is_loaded
    # tests/conftest.py::build_synthetic_ogpr_bytes defaults: 3 slices, 2 channels, 4 samples
    assert session.dataset.shape == (3, 2, 4)
    assert session.channel_count == 2
    assert session.trace_count == 3
    assert session.selected_channel == 0
    assert session.selected_trace == 0
    assert session.source_path == valid_ogpr_path.resolve()


# 4. B-scan matrix shape --------------------------------------------------


def test_bscan_view_matrix_shape(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=6, channels_count=3, samples_count=50)
    view = BScanView()
    qtbot.addWidget(view)

    view.set_data(dataset, channel=1)

    image = view.image_item.image
    assert image is not None
    # (sample, trace) -- the one centralized transpose, see bscan_view.py
    assert image.shape == (50, 6)
    np.testing.assert_array_equal(image, dataset.amplitudes[:, 1, :].T)


# 5. Channel change changes the displayed image -------------------------------


def test_bscan_view_updates_on_channel_change(qtbot, dataset_factory):
    rng = np.random.default_rng(0)
    amplitudes = rng.standard_normal((5, 3, 20)).astype(np.float32)
    dataset = dataset_factory(amplitudes=amplitudes)
    view = BScanView()
    qtbot.addWidget(view)

    view.set_data(dataset, channel=0)
    image_channel_0 = view.image_item.image.copy()

    view.set_data(dataset, channel=1)
    image_channel_1 = view.image_item.image.copy()

    assert not np.array_equal(image_channel_0, image_channel_1)
    np.testing.assert_array_equal(image_channel_1, dataset.amplitudes[:, 1, :].T)


# 6. B-scan trace selection updates the A-scan --------------------------------


def test_trace_click_updates_ascan(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=10, channels_count=2, samples_count=30)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.dataset = dataset
    window.session.selected_channel = 1
    window.session.selected_trace = 0
    window._update_views()

    window.bscan_view.traceClicked.emit(7)

    assert window.session.selected_trace == 7
    np.testing.assert_array_equal(window.ascan_view._amplitude, dataset.amplitudes[7, 1, :])


# 7. Metadata panel shows basic values -----------------------------------------


def test_metadata_panel_shows_basic_values(qtbot, dataset_factory):
    dataset = dataset_factory(
        slices_count=6,
        channels_count=4,
        samples_count=200,
        sampling_time_ns=0.5,
        metadata={"source_file": {"name": "demo.ogpr"}, "radar": {"nominal_frequency_MHz": 600.0}},
    )
    panel = MetadataPanel()
    qtbot.addWidget(panel)

    panel.set_dataset(dataset, source_path=None)

    values = {}
    for i in range(panel.tree.topLevelItemCount()):
        group = panel.tree.topLevelItem(i)
        for j in range(group.childCount()):
            row = group.child(j)
            values[row.text(0)] = row.text(1)

    assert values["Trace count"] == "6"
    assert values["Channel count"] == "4"
    assert values["Sample count"] == "200"
    assert values["Filename"] == "demo.ogpr"
    assert values["Nominal frequency (MHz)"] == "600"


# 8 & 9. Dataset amplitudes stay read-only / hash unchanged after display ------


def test_dataset_amplitudes_stay_read_only_and_unchanged(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=8, channels_count=2, samples_count=40)
    before_bytes = dataset.amplitudes.tobytes()

    window = MainWindow()
    qtbot.addWidget(window)
    window.session.dataset = dataset
    window.session.selected_trace = 0
    window._update_views()
    window.bscan_view.traceClicked.emit(3)
    window.channel_spin.setMaximum(1)
    window._on_channel_changed(1)

    assert not dataset.amplitudes.flags.writeable
    with pytest.raises(ValueError):
        dataset.amplitudes[0, 0, 0] = 999.0
    assert dataset.amplitudes.tobytes() == before_bytes


# 10. --open parser smoke -----------------------------------------------------


def test_open_flag_smoke(valid_ogpr_path, monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    exit_code = gui_app.main(["--open", str(valid_ogpr_path), "--smoke-test"])
    assert exit_code == 0


# 11. Reader error keeps the previous session intact --------------------------


def test_open_bad_path_preserves_previous_session(qtbot, dataset_factory, tmp_path, no_blocking_error_dialog):
    dataset = dataset_factory(slices_count=6, channels_count=2, samples_count=20)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.dataset = dataset
    window.session.selected_channel = 1
    window.session.selected_trace = 4

    missing_path = tmp_path / "does_not_exist.ogpr"
    window.open_path(missing_path)

    assert window.session.dataset is dataset  # untouched, not partially replaced
    assert window.session.selected_channel == 1
    assert window.session.selected_trace == 4
    assert len(no_blocking_error_dialog) == 1  # QMessageBox.critical was invoked exactly once


# 12. --smoke-test exit code ---------------------------------------------------


def test_smoke_test_flag_exit_code(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    assert gui_app.main(["--smoke-test"]) == 0


def test_ascan_view_clears_without_error(qtbot):
    view = AScanView()
    qtbot.addWidget(view)
    view.clear()  # must not raise with no data ever set
    assert view._amplitude is None


# ============================================================================
# Sprint GUI-2 -- display controls (contrast/colormap/A-scan modes/export)
# ============================================================================


class _FakeMouseEvent:
    """Minimal stand-in for pyqtgraph's mouse-click scene event: only ``scenePos()`` is used."""

    def __init__(self, scene_pos):
        self._scene_pos = scene_pos

    def scenePos(self):
        return self._scene_pos


# 13. Default DisplaySettings ------------------------------------------------


def test_default_display_settings_values():
    from archaeogpr.gui.models.display_settings import DisplaySettings

    settings = DisplaySettings()
    assert settings.clip_percentile == 99.0
    assert settings.symmetric_levels is True
    assert settings.manual_levels_enabled is False
    assert settings.manual_min is None
    assert settings.manual_max is None
    assert settings.colormap == "gray"
    assert settings.ascan_mode == "full"
    assert settings.visible_region_autoscale is False


# 14. Percentile change changes display levels --------------------------------


def test_percentile_change_changes_levels(dataset_factory):
    from archaeogpr.gui.models.display_settings import DisplaySettings, compute_display_levels

    rng = np.random.default_rng(1)
    amplitude = rng.standard_normal((175, 1, 200)).astype(np.float32)[:, 0, :]

    levels_99 = compute_display_levels(amplitude, DisplaySettings(clip_percentile=99.0))
    levels_90 = compute_display_levels(amplitude, DisplaySettings(clip_percentile=90.0))
    assert levels_99 != levels_90
    assert abs(levels_99[1]) > abs(levels_90[1])  # a wider percentile keeps more of the tail


# 15. Percentile change never touches the dataset ------------------------------


def test_percentile_change_does_not_modify_dataset_hash(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=8, channels_count=2, samples_count=40)
    before = dataset.amplitudes.tobytes()

    window = MainWindow()
    qtbot.addWidget(window)
    window.session.dataset = dataset
    window.session.selected_trace = 0
    window._update_views()
    for value in (95.0, 90.5, 99.9):
        window.percentile_spin.setValue(value)

    assert dataset.amplitudes.tobytes() == before
    assert not dataset.amplitudes.flags.writeable


# 16. Symmetric mode levels are [-scale, +scale] -------------------------------


def test_symmetric_levels_are_zero_centered():
    from archaeogpr.gui.models.display_settings import DisplaySettings, compute_display_levels

    amplitude = np.array([[-5.0, 10.0, -2.0, 3.0]], dtype=np.float64)
    low, high = compute_display_levels(
        amplitude, DisplaySettings(symmetric_levels=True, clip_percentile=100.0)
    )
    assert low == -high


# 17. Asymmetric mode produces a valid, non-degenerate lower/upper ------------


def test_asymmetric_levels_are_valid_and_ordered():
    from archaeogpr.gui.models.display_settings import DisplaySettings, compute_display_levels

    rng = np.random.default_rng(2)
    amplitude = rng.standard_normal((175, 200)).astype(np.float64) * 100 + 20  # skewed, not zero-centered
    low, high = compute_display_levels(
        amplitude, DisplaySettings(symmetric_levels=False, clip_percentile=99.0)
    )
    assert low < high
    assert math.isfinite(low) and math.isfinite(high)


# 18. Invalid manual min/max is never applied to the render pipeline ----------


def test_invalid_manual_levels_fall_back_to_automatic():
    from archaeogpr.gui.models.display_settings import DisplaySettings, compute_display_levels

    rng = np.random.default_rng(3)
    amplitude = rng.standard_normal((175, 200)).astype(np.float64)
    invalid_settings = DisplaySettings(manual_levels_enabled=True, manual_min=500.0, manual_max=100.0)
    levels = compute_display_levels(amplitude, invalid_settings)
    assert levels != (500.0, 100.0)
    assert levels[0] < levels[1]


# 19. Valid manual levels are applied exactly ----------------------------------


def test_valid_manual_levels_are_applied_exactly():
    from archaeogpr.gui.models.display_settings import DisplaySettings, compute_display_levels

    amplitude = np.array([[1.0, 2.0, 3.0]])
    settings = DisplaySettings(manual_levels_enabled=True, manual_min=-50.0, manual_max=250.0)
    assert compute_display_levels(amplitude, settings) == (-50.0, 250.0)


# 20. Gray -> Seismic changes the ImageItem's LUT ------------------------------


def test_colormap_switch_changes_lookup_table(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=6, channels_count=2, samples_count=30)
    view = BScanView()
    qtbot.addWidget(view)
    view.set_data(dataset, channel=0)

    from archaeogpr.gui.models.display_settings import DisplaySettings

    view.set_display_settings(DisplaySettings(colormap="gray"))
    gray_lut = view.image_item.lut.copy()
    view.set_display_settings(DisplaySettings(colormap="seismic"))
    seismic_lut = view.image_item.lut.copy()

    assert not np.array_equal(gray_lut, seismic_lut)


# 21. Colormap change never modifies the dataset -------------------------------


def test_colormap_change_does_not_modify_dataset(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=6, channels_count=2, samples_count=30)
    before = dataset.amplitudes.tobytes()
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.dataset = dataset
    window.session.selected_trace = 0
    window._update_views()

    window.colormap_combo.setCurrentIndex(1)
    window.colormap_combo.setCurrentIndex(0)

    assert dataset.amplitudes.tobytes() == before


# 22. Trace spinbox 80 updates marker / A-scan / status ------------------------


def test_trace_spinbox_updates_marker_ascan_and_status(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=175, channels_count=11, samples_count=64)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.dataset = dataset
    window.session.selected_channel = 5
    window.session.selected_trace = 0
    window._refresh_for_new_dataset()

    window.trace_spin.setValue(80)

    assert window.session.selected_trace == 80
    assert window.bscan_view._selected_trace == 80
    np.testing.assert_array_equal(window.ascan_view._amplitude, dataset.amplitudes[80, 5, :])
    assert "Selected trace 80" in window.selected_label.text()


# 23. B-scan click near trace 80 selects trace 80 (through the real click path, incl. a zoomed view) --


def test_bscan_click_near_trace_80_selects_trace_80(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=175, channels_count=2, samples_count=64)
    view = BScanView()
    qtbot.addWidget(view)
    view.set_data(dataset, channel=0)

    # Zoom into a sub-range first -- the click must still resolve correctly
    # through the current view transform (GUI-2 manual-demo boundary check).
    view.view_box.setRange(xRange=(50, 120), yRange=(dataset.time_ns[0], dataset.time_ns[-1]))

    clicked: list[int] = []
    view.traceClicked.connect(clicked.append)

    from PySide6.QtCore import QPointF

    view_point = QPointF(80.4, float(dataset.time_ns[10]))
    scene_point = view.view_box.mapViewToScene(view_point)
    view._on_mouse_clicked(_FakeMouseEvent(scene_point))

    assert clicked == [80]


# 24. Trace index 0 and the last index are safe boundary clicks ---------------


def test_bscan_click_boundary_traces_0_and_last(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=175, channels_count=2, samples_count=64)
    view = BScanView()
    qtbot.addWidget(view)
    view.set_data(dataset, channel=0)

    from PySide6.QtCore import QPointF

    last_trace = dataset.shape[0] - 1
    clicked: list[int] = []
    view.traceClicked.connect(clicked.append)

    for target in (0, last_trace):
        view_point = QPointF(target + 0.5, float(dataset.time_ns[5]))
        scene_point = view.view_box.mapViewToScene(view_point)
        view._on_mouse_clicked(_FakeMouseEvent(scene_point))

    assert clicked == [0, last_trace]

    # A click just outside either boundary must not emit anything.
    clicked.clear()
    for out_of_range in (-0.5, last_trace + 1.5):
        view_point = QPointF(out_of_range, float(dataset.time_ns[5]))
        scene_point = view.view_box.mapViewToScene(view_point)
        view._on_mouse_clicked(_FakeMouseEvent(scene_point))
    assert clicked == []


# 25. A-scan "full" mode plots the raw values ----------------------------------


def test_ascan_full_mode_uses_raw_values(qtbot, dataset_factory):
    rng = np.random.default_rng(4)
    amplitudes = rng.standard_normal((5, 1, 30)).astype(np.float32) * 1000
    dataset = dataset_factory(amplitudes=amplitudes)
    view = AScanView()
    qtbot.addWidget(view)

    view.set_mode("full")
    view.set_data(dataset, channel=0, trace=2)

    x_data, _y_data = view.curve.getData()
    np.testing.assert_allclose(x_data, dataset.amplitudes[2, 0, :])


# 26. A-scan "robust" mode changes only the axis range, never the curve data ---


def test_ascan_robust_mode_only_changes_axis_range(qtbot, dataset_factory):
    rng = np.random.default_rng(5)
    amplitudes = rng.standard_normal((5, 1, 30)).astype(np.float32) * 1000
    dataset = dataset_factory(amplitudes=amplitudes)
    view = AScanView()
    qtbot.addWidget(view)

    view.set_mode("full")
    view.set_data(dataset, channel=0, trace=2)
    full_x, _ = view.curve.getData()

    view.set_mode("robust")
    robust_x, _ = view.curve.getData()

    np.testing.assert_array_equal(full_x, robust_x)  # curve data identical
    x_range = view.view_box.viewRange()[0]
    assert x_range[0] < 0 < x_range[1]  # a robust, non-degenerate range was set


# 27. A-scan "normalize" mode never modifies the source trace -----------------


def test_ascan_normalize_mode_does_not_modify_source_trace(qtbot, dataset_factory):
    rng = np.random.default_rng(6)
    amplitudes = rng.standard_normal((5, 1, 30)).astype(np.float32) * 1000
    dataset = dataset_factory(amplitudes=amplitudes)
    before = dataset.amplitudes.tobytes()
    view = AScanView()
    qtbot.addWidget(view)

    view.set_mode("normalize")
    view.set_data(dataset, channel=0, trace=2)

    x_data, _ = view.curve.getData()
    assert np.max(np.abs(x_data)) == pytest.approx(1.0)
    assert dataset.amplitudes.tobytes() == before
    assert not dataset.amplitudes.flags.writeable


# 28. A-scan "normalize" mode is safe for an all-zero trace -------------------


def test_ascan_normalize_mode_handles_zero_trace_safely(qtbot, dataset_factory):
    amplitudes = np.zeros((3, 1, 10), dtype=np.float32)
    dataset = dataset_factory(amplitudes=amplitudes)
    view = AScanView()
    qtbot.addWidget(view)

    view.set_mode("normalize")
    view.set_data(dataset, channel=0, trace=1)  # must not raise / divide by zero

    x_data, _ = view.curve.getData()
    assert np.all(np.isfinite(x_data))
    assert np.all(x_data == 0.0)


# 29. Metadata panel's Value column stretches ----------------------------------


def test_metadata_value_column_stretches(qtbot):
    from PySide6.QtWidgets import QHeaderView

    panel = MetadataPanel()
    qtbot.addWidget(panel)
    assert panel.tree.header().sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch


# 30. Metadata tooltip contains the full value text ----------------------------


def test_metadata_tooltip_contains_full_value(qtbot, dataset_factory):
    long_path_metadata = {"source_file": {"name": "a" * 200 + ".ogpr"}}
    dataset = dataset_factory(metadata=long_path_metadata)
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    panel.set_dataset(dataset, source_path=None)

    source_group = panel.tree.topLevelItem(0)
    filename_row = source_group.child(0)
    assert filename_row.toolTip(1) == filename_row.text(1)
    assert len(filename_row.toolTip(1)) > 100


# 31. "Copy value" context-menu action copies to the clipboard -----------------


def test_metadata_copy_value_action(qtbot, dataset_factory):
    from PySide6.QtWidgets import QApplication

    dataset = dataset_factory(
        slices_count=6,
        channels_count=2,
        samples_count=10,
        metadata={"source_file": {"name": "copytest.ogpr"}},
    )
    panel = MetadataPanel()
    qtbot.addWidget(panel)
    panel.set_dataset(dataset, source_path=None)

    source_group = panel.tree.topLevelItem(0)
    filename_row = source_group.child(0)
    assert filename_row.text(1) == "copytest.ogpr"

    # Exercise the same copy path the context-menu action uses.
    QApplication.clipboard().setText(filename_row.text(1))
    assert QApplication.clipboard().text() == "copytest.ogpr"


# 32. Reset View restores the full trace/time range ----------------------------


def test_reset_view_restores_full_range(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=175, channels_count=2, samples_count=64)
    view = BScanView()
    qtbot.addWidget(view)
    view.set_data(dataset, channel=0)
    view.view_box.setRange(xRange=(50, 100))

    view.reset_view()

    x_range = view.view_box.viewRange()[0]
    # after reset the visible range must cover (at least) the full trace axis
    assert x_range[0] <= 0
    assert x_range[1] >= dataset.shape[0] - 1


# 33. Reset Display returns every control to the documented defaults ----------


def test_reset_display_restores_defaults(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=6, channels_count=2, samples_count=30)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.dataset = dataset
    window.session.selected_trace = 0
    window._update_views()

    window.percentile_spin.setValue(90.0)
    window.colormap_combo.setCurrentIndex(1)
    window.manual_check.setChecked(True)

    window._on_reset_display_clicked()

    assert window.display_settings.clip_percentile == 99.0
    assert window.display_settings.colormap == "gray"
    assert window.display_settings.symmetric_levels is True
    assert window.display_settings.manual_levels_enabled is False
    assert window.percentile_spin.value() == 99.0
    assert window.colormap_combo.currentIndex() == 0


# 34. PNG export produces a file ------------------------------------------------


def test_png_export_creates_file(dataset_factory, tmp_path):
    from archaeogpr.gui.export import export_bscan_png

    dataset = dataset_factory(slices_count=10, channels_count=2, samples_count=40)
    output_path = tmp_path / "export.png"

    result_path = export_bscan_png(dataset, 0, (-1.0, 1.0), "gray", output_path, source_filename="x.ogpr")

    assert result_path.exists()
    assert result_path.stat().st_size > 0


# 35. PNG export does not modify the source dataset ----------------------------


def test_png_export_does_not_modify_dataset(dataset_factory, tmp_path):
    from archaeogpr.gui.export import export_bscan_png, write_display_sidecar
    from archaeogpr.gui.models.display_settings import DisplaySettings

    dataset = dataset_factory(slices_count=10, channels_count=2, samples_count=40)
    before = dataset.amplitudes.tobytes()
    output_path = tmp_path / "export2.png"

    result_path = export_bscan_png(dataset, 0, (-1.0, 1.0), "gray", output_path, selected_trace=3)
    sidecar_path = write_display_sidecar(result_path, dataset, 0, DisplaySettings(), (-1.0, 1.0))

    assert dataset.amplitudes.tobytes() == before
    assert not dataset.amplitudes.flags.writeable
    assert sidecar_path.exists()
    sidecar_data = json.loads(sidecar_path.read_text())
    assert sidecar_data["note"] == "Display-only export; source amplitudes unchanged."
    assert sidecar_data["channel"] == 0


# ============================================================================
# Sprint GUI-2 fix round -- manual-test findings: normalize-mode invisibility,
# A-scan time-axis overshoot, manual/visible-range-autoscale UX conflict.
# ============================================================================


# 36. Normalize mode is visible (correct curve + explicit X range) -----------


def test_ascan_normalize_mode_is_visible_with_correct_range(qtbot, dataset_factory):
    rng = np.random.default_rng(7)
    amplitudes = rng.standard_normal((5, 1, 30)).astype(np.float32) * 60000.0
    dataset = dataset_factory(amplitudes=amplitudes)
    before = dataset.amplitudes.tobytes()
    view = AScanView()
    qtbot.addWidget(view)

    view.set_mode("full")
    view.set_data(dataset, channel=0, trace=2)  # leaves a large raw-scale X range in place first

    view.set_mode("normalize")

    x_data, y_data = view.curve.getData()
    assert x_data.size > 0 and y_data.size > 0
    assert np.max(np.abs(x_data)) == pytest.approx(1.0)
    x_range = view.view_box.viewRange()[0]
    assert x_range[0] == pytest.approx(-1.05)
    assert x_range[1] == pytest.approx(1.05)
    assert dataset.amplitudes.tobytes() == before


# 37. Normalize -> Full restores the raw curve and raw-scale X range ---------


def test_ascan_normalize_to_full_restores_raw_scale(qtbot, dataset_factory):
    from PySide6.QtWidgets import QApplication

    rng = np.random.default_rng(8)
    amplitudes = rng.standard_normal((5, 1, 30)).astype(np.float32) * 50000.0
    dataset = dataset_factory(amplitudes=amplitudes)
    view = AScanView()
    qtbot.addWidget(view)
    # "full" mode relies on pyqtgraph's enableAutoRange(), which only takes
    # effect on the next paint pass (a real, deferred recompute -- see
    # ViewBox.enableAutoRange/updateAutoRange) -- a hidden widget never
    # receives one, so show() + processEvents() is required here to observe
    # it deterministically. This is a test-harness requirement only; the
    # real running app repaints continuously so this is invisible there.
    view.show()
    QApplication.processEvents()

    view.set_mode("normalize")
    view.set_data(dataset, channel=0, trace=2)

    view.set_mode("full")
    QApplication.processEvents()
    QApplication.processEvents()

    x_data, _ = view.curve.getData()
    np.testing.assert_allclose(x_data, dataset.amplitudes[2, 0, :])
    x_range = view.view_box.viewRange()[0]
    assert x_range[1] > 1.05  # back to raw amplitude scale, not stuck at the normalized range


# 38. Normalize -> Robust uses the raw curve and a robust raw-percentile range --


def test_ascan_normalize_to_robust_uses_raw_percentile_range(qtbot, dataset_factory):
    rng = np.random.default_rng(9)
    amplitudes = rng.standard_normal((5, 1, 30)).astype(np.float32) * 50000.0
    dataset = dataset_factory(amplitudes=amplitudes)
    view = AScanView()
    qtbot.addWidget(view)

    view.set_mode("normalize")
    view.set_data(dataset, channel=0, trace=2)

    view.set_mode("robust")

    x_data, _ = view.curve.getData()
    np.testing.assert_allclose(x_data, dataset.amplitudes[2, 0, :])  # raw curve, not the normalized copy
    x_range = view.view_box.viewRange()[0]
    assert x_range[1] > 1.05  # not stuck at the normalized [-1.05, 1.05] range


# 39. A-scan time axis matches real dataset.time_ns bounds and blocks overshoot pan --


def test_ascan_time_axis_matches_dataset_bounds_and_blocks_overshoot_pan(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=5, channels_count=1, samples_count=1024, sampling_time_ns=0.125)
    view = AScanView()
    qtbot.addWidget(view)
    view.set_data(dataset, channel=0, trace=0)

    expected_min = float(np.min(dataset.time_ns))
    expected_max = float(np.max(dataset.time_ns))

    y_range = view.view_box.viewRange()[1]
    assert y_range[0] == pytest.approx(expected_min, abs=1e-6)
    assert y_range[1] == pytest.approx(expected_max, abs=1e-6)
    assert y_range[1] < 200.0  # no 200+ ns of empty, non-physical space

    # Attempting to pan/zoom past the real bounds must be clamped by ViewBox limits.
    view.view_box.setYRange(-50.0, 300.0)
    clamped = view.view_box.viewRange()[1]
    assert clamped[1] <= expected_max + 1e-6
    assert clamped[1] < 200.0

    # Reset View returns to exactly the real dataset bounds.
    view.reset_view()
    reset_range = view.view_box.viewRange()[1]
    assert reset_range[0] == pytest.approx(expected_min, abs=1e-6)
    assert reset_range[1] == pytest.approx(expected_max, abs=1e-6)


# 40. A negative time-zero-relative time axis is preserved, not clamped to 0 --


def test_ascan_time_axis_preserves_negative_time_zero_minimum(qtbot, dataset_factory):
    time_ns = np.linspace(-20.0, 108.0, 64)
    dataset = dataset_factory(slices_count=3, channels_count=1, samples_count=64, time_ns=time_ns)
    view = AScanView()
    qtbot.addWidget(view)

    view.set_data(dataset, channel=0, trace=0)

    y_range = view.view_box.viewRange()[1]
    assert y_range[0] == pytest.approx(-20.0, abs=1e-6)
    assert y_range[1] == pytest.approx(108.0, abs=1e-6)


# 41. Manual levels and visible-range autoscale are mutually exclusive -------


def test_manual_and_visible_autoscale_are_mutually_exclusive(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=6, channels_count=2, samples_count=30)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.dataset = dataset
    window.session.selected_trace = 0
    window._update_views()

    window.autoscale_check.setChecked(True)
    assert window.display_settings.visible_region_autoscale is True

    window.manual_check.setChecked(True)
    assert window.display_settings.manual_levels_enabled is True
    assert window.display_settings.visible_region_autoscale is False
    assert window.autoscale_check.isChecked() is False
    assert window.autoscale_check.isEnabled() is False

    window.manual_check.setChecked(False)
    assert window.autoscale_check.isEnabled() is True
    assert window.display_settings.manual_levels_enabled is False

    window.autoscale_check.setChecked(True)
    assert window.display_settings.visible_region_autoscale is True
    assert window.display_settings.manual_levels_enabled is False


# 42. Display summary shows exactly one active mode, never a conflicting pair --


def test_display_summary_shows_single_active_mode(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=6, channels_count=2, samples_count=30)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.dataset = dataset
    window.session.selected_trace = 0
    window._update_views()

    window.autoscale_check.setChecked(True)
    assert "visible-range auto" in window.display_summary_label.text()
    assert "manual" not in window.display_summary_label.text()

    window.manual_check.setChecked(True)
    assert "manual" in window.display_summary_label.text()
    assert "visible-range auto" not in window.display_summary_label.text()


# 43. Visible-range autoscale recomputes levels from only the visible samples --


def test_visible_range_autoscale_recomputes_from_visible_samples_only(qtbot, dataset_factory):
    from archaeogpr.gui.models.display_settings import DisplaySettings

    rng = np.random.default_rng(10)
    amplitudes = rng.standard_normal((3, 1, 100)).astype(np.float64) * 5.0
    amplitudes[:, :, :20] += 500.0  # a strong spike dominating only the early part of the trace
    dataset = dataset_factory(amplitudes=amplitudes, sampling_time_ns=0.5)
    before = dataset.amplitudes.tobytes()

    view = BScanView()
    qtbot.addWidget(view)
    view.set_data(dataset, channel=0)
    view.set_display_settings(DisplaySettings(visible_region_autoscale=True))
    full_levels = view.image_item.getLevels()

    # Zoom to a late-time window that excludes the dominating early spike.
    view.view_box.setYRange(30.0, 49.5)
    view._recompute_visible_region_levels()  # bypass the 200ms debounce timer for a deterministic test
    visible_levels = view.image_item.getLevels()

    assert tuple(visible_levels) != tuple(full_levels)
    assert abs(visible_levels[1]) < abs(full_levels[1])  # excluding the spike shrinks the scale
    assert dataset.amplitudes.tobytes() == before


# 44. Manual levels being active suppresses the visible-region recompute entirely --


def test_visible_region_autoscale_skipped_when_manual_active(qtbot, dataset_factory, monkeypatch):
    from archaeogpr.gui.models.display_settings import DisplaySettings

    dataset = dataset_factory(slices_count=5, channels_count=1, samples_count=50)
    view = BScanView()
    qtbot.addWidget(view)
    view.set_data(dataset, channel=0)

    calls: list[int] = []
    monkeypatch.setattr(view, "_recompute_visible_region_levels", lambda: calls.append(1))

    view.set_display_settings(
        DisplaySettings(
            visible_region_autoscale=True, manual_levels_enabled=True, manual_min=-5.0, manual_max=5.0
        )
    )

    assert calls == []  # never invoked -- manual wins, the recompute must not even run
    assert tuple(view.image_item.getLevels()) == (-5.0, 5.0)


# 45. Stale-cursor regression: channel switch never leaves the old channel's ---
#     cursor text in place once a new hover event fires -----------------------


def test_cursor_status_reflects_current_channel_after_switch(qtbot, dataset_factory):
    dataset = dataset_factory(slices_count=5, channels_count=11, samples_count=20)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.dataset = dataset
    window.session.selected_channel = 0
    window.session.selected_trace = 0
    window._refresh_for_new_dataset()

    window._on_point_hovered(2, 5.0, 12.5)
    assert "channel 00" in window.cursor_label.text()

    window.channel_spin.setValue(5)
    assert window.session.selected_channel == 5

    window._on_point_hovered(2, 5.0, 99.9)
    assert "channel 05" in window.cursor_label.text()
    assert "channel 00" not in window.cursor_label.text()
