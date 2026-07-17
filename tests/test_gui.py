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
