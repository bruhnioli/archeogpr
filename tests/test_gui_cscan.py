"""GUI C-scan / Time Slice tests (Sprint 3D-1). Run with ``QT_QPA_PLATFORM=offscreen``.

Every test here is marked ``@pytest.mark.gui`` (module-level ``pytestmark``),
collected separately from the core suite exactly like ``test_gui_geometry.py``.

Item numbers in each test's docstring match the sprint's own GUI test plan
(items 26-66; 1-25 are the Qt-free domain tests in ``tests/test_cscan.py``).
"""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QMessageBox

import archaeogpr.gui.workers.cscan_worker as cscan_worker_module
from archaeogpr.cscan.compute import compute_cscan
from archaeogpr.cscan.models import CScanAggregation, CScanGeometryView, CScanSourceKind
from archaeogpr.gui.main_window import MainWindow
from archaeogpr.gui.models.cscan_session import CScanState
from archaeogpr.gui.processing.registry import DEWOW
from archaeogpr.io.ogpr_reader import read_ogpr

pytestmark = pytest.mark.gui

pg.setConfigOptions(imageAxisOrder="row-major")

_REAL_FILE = Path(__file__).resolve().parents[1] / "data" / "raw" / "Swath003_Array02.ogpr"


@pytest.fixture
def no_blocking_dialogs(monkeypatch):
    """Prevent QMessageBox.critical/warning/question from hanging offscreen tests.

    See test_gui_geometry.py's fixture of the same name -- kept local to
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


class _GatedCompute:
    """Same shape as test_gui_processing.py's ``_GatedApply`` -- kept local to avoid cross-file coupling."""

    def __init__(self):
        self.started = threading.Event()
        self._release_event = threading.Event()
        self.call_count = 0

    def __call__(self, dataset, request, *, valid_mask=None):
        self.call_count += 1
        self.started.set()
        released = self._release_event.wait(timeout=5.0)
        assert released, "test never called release() -- see _GatedCompute"
        return compute_cscan(dataset, request, valid_mask=valid_mask)

    def release(self) -> None:
        self._release_event.set()


class _CScanThreadRecorder(QObject):
    """Records which thread a connected slot actually ran on -- see ``test_gui_processing.py``'s
    ``_ProcessingThreadRecorder``.

    Must be a real ``QObject`` subclass with a genuine, class-defined method
    for the same reason documented there: PySide6 only reliably resolves a
    cross-thread signal to a ``QueuedConnection`` when the connected
    callable is a bound method of a QObject whose thread affinity it can
    determine from the class's original definition.
    """

    def __init__(self) -> None:
        super().__init__()
        self.thread_seen = None

    def record(self, _token, _result):
        self.thread_seen = QThread.currentThread()


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


def _select_geometry_view(window: MainWindow, view: CScanGeometryView) -> None:
    from archaeogpr.gui.main_window import _CSCAN_GEOMETRY_VIEW_ITEMS

    idx = [v for _label, v in _CSCAN_GEOMETRY_VIEW_ITEMS].index(view)
    window.cscan_geometry_view_combo.setCurrentIndex(idx)


def _select_aggregation(window: MainWindow, aggregation: CScanAggregation) -> None:
    from archaeogpr.gui.main_window import _CSCAN_AGGREGATION_ITEMS

    idx = [v for _label, v in _CSCAN_AGGREGATION_ITEMS].index(aggregation)
    window.cscan_aggregation_combo.setCurrentIndex(idx)


def _compute_and_wait(window: MainWindow, qtbot) -> None:
    window._on_cscan_compute_clicked()
    qtbot.waitUntil(lambda: not window.is_computing_cscan, timeout=5000)


# ============================================================
# 26-33: dock creation, defaults, labels
# ============================================================


def test_cscan_dock_is_created(qtbot):
    """26: the C-scan / Time Slice dock exists with its controls."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.cscan_view is not None
    assert window.cscan_compute_button is not None
    assert window.cscan_source_combo is not None


def test_cscan_controls_disabled_with_no_dataset(qtbot):
    """27: with no dataset loaded, Compute is disabled."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert not window.cscan_compute_button.isEnabled()


def test_time_controls_updated_after_load(qtbot, dataset_factory):
    """28: loading a dataset seeds center time/window width to sensible defaults."""
    dataset = _make_dataset(dataset_factory, samples_count=100, sampling_time_ns=1.0)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    assert window.cscan_center_time_spin.value() == pytest.approx(float(dataset.time_ns[0]))
    assert window.cscan_window_width_spin.value() > 0
    assert window.cscan_compute_button.isEnabled()


def test_actual_xy_mode_is_default(qtbot, dataset_factory):
    """29: Actual X/Y point map is the default geometry view."""
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.cscan_display_settings.geometry_view is CScanGeometryView.ACTUAL_XY_POINT_MAP
    assert window.cscan_geometry_view_combo.currentIndex() == 0


def test_no_interpolation_label_visible_in_actual_xy_mode(qtbot, ogpr_builder, tmp_path):
    """30: the Actual X/Y view's mode label says "no interpolation"."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)

    assert "no interpolation" in window.cscan_view.mode_label.text


def test_derived_grid_label_visible(qtbot, ogpr_builder, tmp_path):
    """31: switching to Derived parameter grid updates the mode label."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)

    _select_geometry_view(window, CScanGeometryView.DERIVED_PARAMETER_GRID)
    assert "Derived" in window.cscan_view.mode_label.text


@pytest.mark.skipif(not _REAL_FILE.is_file(), reason=f"Real sample file not found at {_REAL_FILE}.")
def test_rectilinear_warning_visible_for_real_file(qtbot):
    """32: the real file's known-non-rectilinear geometry produces a visible warning/stale status."""
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, read_ogpr(_REAL_FILE), _REAL_FILE)

    assert window.geometry_session.resolution is not None
    readiness = window.geometry_session.resolution.readiness
    assert readiness.rectilinear_cscan_ready.ready is False
    assert readiness.actual_xy_point_grid_ready.ready is True


@pytest.mark.skipif(not _REAL_FILE.is_file(), reason=f"Real sample file not found at {_REAL_FILE}.")
def test_crs_unverified_warning_visible_for_real_file(qtbot):
    """33: the real file's CRS is declared-unverified, matching the Survey Geometry panel's own finding."""
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, read_ogpr(_REAL_FILE), _REAL_FILE)

    geometry = window.geometry_session.geometry
    assert geometry.crs_validation_status.value == "declared_unverified"


# ============================================================
# 34-37: compute correctness + threading
# ============================================================


def test_single_sample_compute_result_shown(qtbot, ogpr_builder, tmp_path):
    """34: a Single Sample compute produces a result rendered in the view."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)

    assert window.cscan_session.has_result
    assert window.cscan_session.result.aggregation is CScanAggregation.SINGLE_SAMPLE
    assert window.cscan_view._result is window.cscan_session.result


def test_rms_compute_result_shown(qtbot, ogpr_builder, tmp_path):
    """35: an RMS compute produces a non-negative result."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _select_aggregation(window, CScanAggregation.RMS)
    window.cscan_window_width_spin.setValue(5.0)
    _compute_and_wait(window, qtbot)

    assert window.cscan_session.has_result
    result = window.cscan_session.result
    assert result.aggregation is CScanAggregation.RMS
    assert np.all(result.values[result.valid_mask] >= 0)


def test_result_handler_runs_on_qt_main_thread(qtbot, ogpr_builder, tmp_path):
    """36: the result_ready handler executes on the Qt main thread, not the worker thread."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    window._on_cscan_compute_clicked()
    recorder = _CScanThreadRecorder()
    window._cscan_worker.result_ready.connect(recorder.record)
    qtbot.waitUntil(lambda: not window.is_computing_cscan, timeout=5000)

    assert recorder.thread_seen is QThread.currentThread()


def test_compute_runs_off_gui_thread(qtbot, ogpr_builder, tmp_path, monkeypatch):
    """37: compute_cscan itself executes on a worker thread, not the GUI main thread."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    seen_thread_idents: list[int] = []

    def recording_compute(ds, request, *, valid_mask=None):
        seen_thread_idents.append(threading.get_ident())
        return compute_cscan(ds, request, valid_mask=valid_mask)

    monkeypatch.setattr(cscan_worker_module, "compute_cscan", recording_compute)
    main_thread_ident = threading.get_ident()
    _compute_and_wait(window, qtbot)

    assert seen_thread_idents
    assert seen_thread_idents[0] != main_thread_ident


# ============================================================
# 38-41: mutual exclusion
# ============================================================


def test_second_cscan_compute_rejected(qtbot, ogpr_builder, tmp_path, monkeypatch):
    """38: a second Compute click is rejected while one is already running."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    gated = _GatedCompute()
    monkeypatch.setattr(cscan_worker_module, "compute_cscan", gated)
    window._on_cscan_compute_clicked()
    assert gated.started.wait(timeout=5.0)

    window._on_cscan_compute_clicked()
    assert gated.call_count == 1

    gated.release()
    qtbot.waitUntil(lambda: not window.is_computing_cscan, timeout=5000)


def test_file_load_rejected_during_cscan_compute(qtbot, ogpr_builder, tmp_path, monkeypatch):
    """39: File → Open is rejected while a C-scan compute is running."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    gated = _GatedCompute()
    monkeypatch.setattr(cscan_worker_module, "compute_cscan", gated)
    window._on_cscan_compute_clicked()
    assert gated.started.wait(timeout=5.0)

    window.open_path(str(tmp_path / "geo.ogpr"))
    assert not window.is_loading

    gated.release()
    qtbot.waitUntil(lambda: not window.is_computing_cscan, timeout=5000)


def test_processing_rejected_during_cscan_compute(qtbot, ogpr_builder, tmp_path, monkeypatch):
    """40: Processing preview is rejected while a C-scan compute is running."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    gated = _GatedCompute()
    monkeypatch.setattr(cscan_worker_module, "compute_cscan", gated)
    window._on_cscan_compute_clicked()
    assert gated.started.wait(timeout=5.0)

    window._on_preview_clicked()
    assert not window.is_processing

    gated.release()
    qtbot.waitUntil(lambda: not window.is_computing_cscan, timeout=5000)


def test_cscan_rejected_during_processing(qtbot, dataset_factory):
    """41: C-scan Compute is rejected while a processing preview is running."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    window._start_processing_preview(DEWOW, DEWOW.defaults())
    assert window.is_processing

    window._on_cscan_compute_clicked()
    assert not window.is_computing_cscan

    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)


# ============================================================
# 42-46: cancellation and staleness
# ============================================================


def test_cancel_preserves_previous_valid_result(qtbot, ogpr_builder, tmp_path, monkeypatch):
    """42: cancelling a second compute preserves the previous valid result."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)
    first_result = window.cscan_session.result
    assert first_result is not None

    window.cscan_center_time_spin.setValue(float(dataset.time_ns[-1]))
    gated = _GatedCompute()
    monkeypatch.setattr(cscan_worker_module, "compute_cscan", gated)
    window._on_cscan_compute_clicked()
    assert gated.started.wait(timeout=5.0)

    window._on_cscan_cancel_clicked()
    gated.release()
    qtbot.waitUntil(lambda: not window.is_computing_cscan, timeout=5000)

    assert window.cscan_session.result is first_result
    assert window.cscan_session.state == CScanState.CANCELLED


def test_late_result_after_cancel_is_discarded(qtbot, ogpr_builder, tmp_path, monkeypatch):
    """43: a result arriving after the token was superseded is discarded."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    gated = _GatedCompute()
    monkeypatch.setattr(cscan_worker_module, "compute_cscan", gated)
    window._on_cscan_compute_clicked()
    assert gated.started.wait(timeout=5.0)
    stale_token = window._current_cscan_token

    window._on_cscan_cancel_clicked()
    gated.release()
    qtbot.waitUntil(lambda: not window.is_computing_cscan, timeout=5000)

    assert stale_token == window._current_cscan_token  # no new request was made
    assert not window.cscan_session.has_result


def test_stale_current_source_revision_discards_result_after_processing_apply(qtbot, dataset_factory):
    """44/49: applying a processing preview advances current_revision, marking a Current result stale."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    _compute_and_wait(window, qtbot)
    assert window.cscan_session.has_result

    window._start_processing_preview(DEWOW, DEWOW.defaults())
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)
    window._on_apply_preview_clicked()

    assert window.cscan_session.is_stale(
        current_source_revision=window._cscan_source_revision_for(CScanSourceKind.CURRENT),
        current_geometry_revision=window.geometry_session.geometry_revision,
    )
    assert window._cscan_status_text() == "Stale"


def test_stale_geometry_revision_discards_result_after_geometry_apply(qtbot, ogpr_builder, tmp_path):
    """45/50: applying a geometry override advances geometry_revision, marking any result stale."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)
    assert window.cscan_session.has_result

    window.geometry_azimuth_spin.setValue(12.5)
    window._on_apply_geometry_clicked()

    assert window._cscan_status_text() == "Stale"


def test_stale_preview_source_discards_result_after_reapply(qtbot, dataset_factory):
    """46: recomputing a preview with different parameters marks a Preview-sourced result stale."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    window._start_processing_preview(DEWOW, DEWOW.defaults())
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)
    window.cscan_source_combo.setCurrentIndex(2)  # Preview
    _compute_and_wait(window, qtbot)
    assert window.cscan_session.has_result

    # Re-preview against the same committed dataset (same base_revision, but a
    # genuinely new preview_dataset object) -- this must still invalidate.
    window._start_processing_preview(DEWOW, DEWOW.defaults())
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    assert window._cscan_status_text() == "Stale"


# ============================================================
# 47-48: file load interaction
# ============================================================


def test_successful_file_load_clears_cscan_result(qtbot, dataset_factory):
    """47: a new successful file load clears the old C-scan result outright."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    _compute_and_wait(window, qtbot)
    assert window.cscan_session.has_result

    dataset2 = _make_dataset(dataset_factory)
    _load_dataset(window, dataset2, Path("y.ogpr"))

    assert not window.cscan_session.has_result
    assert window.cscan_session.state == CScanState.IDLE


def test_failed_file_load_preserves_previous_cscan_result(
    qtbot, dataset_factory, monkeypatch, no_blocking_dialogs
):
    """48: a failed file load leaves the previous C-scan result untouched."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    _compute_and_wait(window, qtbot)
    previous_result = window.cscan_session.result
    assert previous_result is not None

    def failing_read(_path):
        raise RuntimeError("simulated read failure")

    monkeypatch.setattr("archaeogpr.gui.workers.file_loader.read_ogpr", failing_read)
    window.open_path("nonexistent.ogpr")
    qtbot.waitUntil(lambda: not window.is_loading, timeout=5000)

    assert window.cscan_session.result is previous_result


# ============================================================
# 51-57: selection/cursor synchronization
# ============================================================


def test_actual_point_click_selects_trace_and_channel(qtbot, ogpr_builder, tmp_path):
    """51: clicking an Actual X/Y point updates the shared trace/channel selection."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)

    window._on_cscan_point_clicked(2, 1)
    assert window.session.selected_trace == 2
    assert window.session.selected_channel == 1


def test_parameter_grid_click_selects_trace_and_channel(qtbot, ogpr_builder, tmp_path):
    """52: clicking a Derived parameter-grid cell updates the shared trace/channel selection."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)
    _select_geometry_view(window, CScanGeometryView.DERIVED_PARAMETER_GRID)

    window._on_cscan_point_clicked(1, 0)
    assert window.session.selected_trace == 1
    assert window.session.selected_channel == 0


def test_trace_channel_change_updates_cscan_highlight(qtbot, ogpr_builder, tmp_path):
    """53: changing trace/channel via the spin boxes updates the C-scan view's highlight."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)

    window._select_trace(2)
    assert window.cscan_view._selected_trace == 2


def test_plan_view_synchronization_preserved(qtbot, ogpr_builder, tmp_path):
    """54: selecting a point in the C-scan view still updates the Plan View's own highlight."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)

    window._on_cscan_point_clicked(2, 0)
    assert window.plan_view._selected_trace == 2
    assert window.plan_view._selected_channel == 0


def test_bscan_time_cursor_synced_after_compute(qtbot, ogpr_builder, tmp_path):
    """55: a successful compute positions the B-scan's time cursor at the requested center time."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    center = float(dataset.time_ns[3])
    window.cscan_center_time_spin.setValue(center)
    _compute_and_wait(window, qtbot)

    assert window.bscan_view.time_cursor.isVisible()
    assert window.bscan_view.time_cursor.value() == pytest.approx(center)


def test_negative_time_cursor_correct(qtbot, dataset_factory):
    """56: a negative center time positions the B-scan cursor correctly."""
    time_ns = (np.arange(50, dtype=np.float64) - 20) * 1.0
    dataset = dataset_factory(slices_count=3, channels_count=2, samples_count=50, time_ns=time_ns)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))

    window.cscan_center_time_spin.setValue(-10.0)
    _compute_and_wait(window, qtbot)

    assert window.bscan_view.time_cursor.value() == pytest.approx(-10.0)


def test_hover_does_not_change_selection(qtbot, ogpr_builder, tmp_path):
    """57: hovering over the C-scan view never changes the persistent trace/channel selection."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)
    window._select_trace(1)

    window._on_cscan_point_hovered(4, 1, 10.0, 5.0)

    assert window.session.selected_trace == 1


# ============================================================
# 58-60: display settings
# ============================================================


def test_symmetric_levels_disabled_for_rms(qtbot, ogpr_builder, tmp_path):
    """58: symmetric levels is disabled when RMS (non-negative) is selected."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    _select_aggregation(window, CScanAggregation.RMS)
    assert not window.cscan_symmetric_check.isEnabled()


def test_symmetric_levels_available_for_single_sample(qtbot, ogpr_builder, tmp_path):
    """59: symmetric levels is available (enabled) for signed Single Sample."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    _select_aggregation(window, CScanAggregation.SINGLE_SAMPLE)
    assert window.cscan_symmetric_check.isEnabled()


def test_all_invalid_result_does_not_crash(qtbot, dataset_factory):
    """60: an all-invalid C-scan result renders without crashing."""
    channels_count, samples_count = 2, 20
    valid_mask = np.zeros((channels_count, samples_count), dtype=bool)
    dataset = dataset_factory(slices_count=3, channels_count=channels_count, samples_count=samples_count)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window.session.current_valid_mask = valid_mask
    window._refresh_for_new_dataset()

    _compute_and_wait(window, qtbot)

    assert window.cscan_session.has_result
    assert window.cscan_session.result.statistics.valid_count == 0


# ============================================================
# 61-66: export, shutdown, integrity
# ============================================================


def test_export_produces_png_and_json(qtbot, ogpr_builder, tmp_path, monkeypatch, no_blocking_dialogs):
    """61: File export produces both a PNG and a .cscan.json sidecar."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)

    png_path = tmp_path / "out.png"
    monkeypatch.setattr(
        "archaeogpr.gui.main_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(png_path), "")
    )
    window._on_export_cscan_triggered()

    json_path = png_path.with_suffix("").with_suffix(".cscan.json")
    assert png_path.is_file()
    assert json_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["no_interpolation"] is True


def test_stale_result_export_rejected(qtbot, ogpr_builder, tmp_path, monkeypatch, no_blocking_dialogs):
    """62: exporting a stale result is rejected with a warning, not silently exported."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)

    window.geometry_azimuth_spin.setValue(30.0)
    window._on_apply_geometry_clicked()
    assert window._cscan_status_text() == "Stale"

    png_path = tmp_path / "stale.png"
    monkeypatch.setattr(
        "archaeogpr.gui.main_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(png_path), "")
    )
    window._on_export_cscan_triggered()

    assert not png_path.exists()
    assert any(call[0] == "warning" for call in no_blocking_dialogs)


def test_shutdown_pending_rejects_cscan_compute_and_export(
    qtbot, dataset_factory, monkeypatch, no_blocking_dialogs
):
    """63: once shutdown is pending, no new C-scan compute or export may start."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    _compute_and_wait(window, qtbot)

    gated = _GatedCompute()
    monkeypatch.setattr(cscan_worker_module, "compute_cscan", gated)
    window.cscan_center_time_spin.setValue(float(dataset.time_ns[-1]))
    window._on_cscan_compute_clicked()
    assert gated.started.wait(timeout=5.0)

    window.close()
    assert window._close_pending is True

    window._on_cscan_compute_clicked()
    assert gated.call_count == 1  # no new compute started

    called = []
    monkeypatch.setattr(
        "archaeogpr.gui.main_window.QFileDialog.getSaveFileName",
        lambda *a, **k: (called.append(1), ("", ""))[1],
    )
    window._on_export_cscan_triggered()
    assert not called  # export bailed out before even opening the save dialog

    gated.release()
    qtbot.waitUntil(lambda: not window.is_computing_cscan, timeout=5000)


def test_close_while_computing_is_deferred(qtbot, ogpr_builder, tmp_path, monkeypatch):
    """64: closing the window while a C-scan compute is running defers destruction, never blocks."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    gated = _GatedCompute()
    monkeypatch.setattr(cscan_worker_module, "compute_cscan", gated)
    window._on_cscan_compute_clicked()
    assert gated.started.wait(timeout=5.0)
    thread = window._cscan_thread

    window.close()  # must return immediately -- no wait(), no blocking

    assert window._close_pending is True
    assert window._cscan_thread is thread  # still tracked -- not cleared early
    assert thread.isRunning()

    gated.release()
    qtbot.waitUntil(lambda: not window.is_computing_cscan, timeout=5000)


def test_no_qthread_destroyed_warning_during_cscan_close(qtbot, ogpr_builder, tmp_path, monkeypatch, capsys):
    """65: no "QThread: Destroyed while thread is still running" during a full deferred-close cycle."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    gated = _GatedCompute()
    monkeypatch.setattr(cscan_worker_module, "compute_cscan", gated)
    window._on_cscan_compute_clicked()
    assert gated.started.wait(timeout=5.0)

    window.close()
    gated.release()
    qtbot.waitUntil(lambda: not window.is_computing_cscan, timeout=5000)

    captured = capsys.readouterr()
    assert "Destroyed while thread is still running" not in captured.err
    assert "Destroyed while thread is still running" not in captured.out


@pytest.mark.skipif(not _REAL_FILE.is_file(), reason=f"Real sample file not found at {_REAL_FILE}.")
def test_real_ogpr_hash_and_mtime_unchanged_by_cscan_operations(
    qtbot, tmp_path, monkeypatch, no_blocking_dialogs
):
    """66: computing, switching views, and exporting a C-scan never touches the raw .ogpr file."""
    before_hash = hashlib.sha256(_REAL_FILE.read_bytes()).hexdigest()
    before_mtime = _REAL_FILE.stat().st_mtime

    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, read_ogpr(_REAL_FILE), _REAL_FILE)
    _select_aggregation(window, CScanAggregation.RMS)
    window.cscan_window_width_spin.setValue(5.0)
    _compute_and_wait(window, qtbot)
    _select_geometry_view(window, CScanGeometryView.DERIVED_PARAMETER_GRID)

    png_path = tmp_path / "real_cscan.png"
    monkeypatch.setattr(
        "archaeogpr.gui.main_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(png_path), "")
    )
    window._on_export_cscan_triggered()
    assert png_path.is_file()

    after_hash = hashlib.sha256(_REAL_FILE.read_bytes()).hexdigest()
    after_mtime = _REAL_FILE.stat().st_mtime
    assert after_hash == before_hash
    assert after_mtime == before_mtime


# ============================================================
# 67-71: Section-11 hardening (dock-fix turn)
# ============================================================


def test_preview_generation_is_monotonic(qtbot, dataset_factory):
    """67: every set/replace/clear of the preview bumps DatasetSession.preview_generation."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, Path("x.ogpr"))
    session = window.session

    values = [session.preview_generation]
    window._start_processing_preview(DEWOW, DEWOW.defaults())
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)
    values.append(session.preview_generation)

    window._start_processing_preview(DEWOW, DEWOW.defaults())  # replace at the same base revision
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)
    values.append(session.preview_generation)

    session.discard_preview()
    values.append(session.preview_generation)

    assert values == sorted(values)
    assert len(set(values)) == len(values), f"preview_generation reused a value: {values}"


def test_center_time_change_updates_bscan_cursor_immediately(qtbot, ogpr_builder, tmp_path):
    """68: changing the center-time spin moves the B-scan time cursor at once -- no compute needed."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")

    target = float(dataset.time_ns[-1])
    window.cscan_center_time_spin.setValue(target)

    assert window.bscan_view.time_cursor.isVisible()
    assert window.bscan_view.time_cursor.value() == pytest.approx(target)


def test_form_change_marks_result_stale_without_auto_compute(qtbot, ogpr_builder, tmp_path, monkeypatch):
    """69: changing a request-form value relabels the result stale but never auto-computes."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)
    assert window._cscan_status_text() == "Ready"

    gated = _GatedCompute()
    monkeypatch.setattr(cscan_worker_module, "compute_cscan", gated)
    window.cscan_center_time_spin.setValue(float(dataset.time_ns[-1]))

    assert window._cscan_status_text().startswith("Stale")
    assert window.cscan_session.has_result  # last valid result still displayed
    assert gated.call_count == 0  # and no compute auto-started
    assert not window.is_computing_cscan


def test_export_json_failure_removes_png(qtbot, ogpr_builder, tmp_path, monkeypatch, no_blocking_dialogs):
    """70: if the JSON sidecar fails after the PNG was written, the PNG is rolled back."""
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    _compute_and_wait(window, qtbot)

    png_path = tmp_path / "half.png"
    monkeypatch.setattr(
        "archaeogpr.gui.main_window.QFileDialog.getSaveFileName", lambda *a, **k: (str(png_path), "")
    )

    def _boom(*_args, **_kwargs):
        raise OSError("simulated sidecar write failure")

    monkeypatch.setattr("archaeogpr.gui.main_window.export_cscan_report", _boom)
    window._on_export_cscan_triggered()

    assert not png_path.exists(), "PNG must be rolled back when the JSON sidecar fails"
    assert not png_path.with_suffix("").with_suffix(".cscan.json").exists()
    assert any(call[0] == "critical" for call in no_blocking_dialogs)


def test_geometry_view_items_gated_on_named_readiness(qtbot, ogpr_builder, tmp_path):
    """71: geometry-view combo items follow the named ADR-016 readiness gates."""
    from PySide6.QtGui import QStandardItemModel

    window = MainWindow()
    qtbot.addWidget(window)
    model = window.cscan_geometry_view_combo.model()
    assert isinstance(model, QStandardItemModel)

    # No dataset -> no geometry resolution -> both view items disabled.
    assert not model.item(0).isEnabled()
    assert not model.item(1).isEnabled()

    # Real geolocation -> actual_xy_point_grid_ready and local_parameter_grid_ready
    # are both satisfied for the synthetic geolocation fixture.
    dataset = _make_real_geolocation_dataset(ogpr_builder, tmp_path)
    _load_dataset(window, dataset, tmp_path / "geo.ogpr")
    readiness = window.geometry_session.readiness
    assert readiness is not None
    assert model.item(0).isEnabled() == readiness.actual_xy_point_grid_ready.ready
    assert model.item(1).isEnabled() == readiness.local_parameter_grid_ready.ready
