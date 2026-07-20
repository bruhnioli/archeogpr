"""GUI dock-layout / window-state tests (Sprint 3D-1 dock-overlap fix, ADR-018).

Run with ``QT_QPA_PLATFORM=offscreen``. Every test here is marked
``@pytest.mark.gui``, collected separately from the core suite exactly like
``test_gui_geometry.py``/``test_gui_cscan.py``.

**Settings isolation (ADR-018 Addendum)**: every ``@pytest.mark.gui`` test in
the whole suite -- not just this file -- is isolated from the real
``%LOCALAPPDATA%\\ArchaeoGPR\\window_state.ini`` by ``tests/conftest.py``'s
autouse ``_isolate_gui_window_state`` fixture, which points the
``ARCHAEOGPR_WINDOW_STATE_PATH`` override at a per-test ``tmp_path`` file
before any test body runs. The local ``isolated_window_settings`` fixture
below performs no isolation of its own any more; it is kept only so this
file's existing test signatures did not need to change, and to make the
per-test file path available to the two tests that open it directly
(``open_window_settings()`` with no arguments, relying on the same env
override).

Just calling ``isVisible()`` on a dock is not sufficient to tell whether it is
the currently-frontmost tab of a tabified group: Qt keeps every tabified
dock's own ``isVisible()`` ``True`` regardless of which tab is on top, and
parks the non-frontmost one(s) at degenerate, off-window coordinates instead
(confirmed empirically while writing this suite). ``_onscreen_rect()`` below
is the actual "is this dock the one really being displayed right now" check
used throughout: a dock whose geometry does not intersect the window's own
``rect()`` at all is the backgrounded tab of some group, not a real overlap
candidate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import pyqtgraph as pg
from PySide6.QtCore import QRect, QThread
from PySide6.QtWidgets import QApplication, QDockWidget, QScrollArea

from archaeogpr.gui.main_window import MainWindow
from archaeogpr.gui.window_state import WINDOW_STATE_SCHEMA_VERSION, open_window_settings

pytestmark = pytest.mark.gui

pg.setConfigOptions(imageAxisOrder="row-major")


@pytest.fixture
def isolated_window_settings(tmp_path):
    """The per-test window-state file path -- isolation itself is autouse (see module docstring)."""
    return tmp_path / "window_state.ini"


def _make_dataset(dataset_factory, **kwargs):
    kwargs.setdefault("slices_count", 6)
    kwargs.setdefault("channels_count", 2)
    kwargs.setdefault("samples_count", 200)
    kwargs.setdefault("sampling_time_ns", 0.5)
    return dataset_factory(**kwargs)


def _load_dataset(window: MainWindow, dataset, path: Path) -> None:
    window.session.commit_dataset(dataset, path)
    window._refresh_for_new_dataset()


def _all_docks(window: MainWindow) -> tuple[QDockWidget, ...]:
    return window._all_docks


def _onscreen_rect(window: MainWindow, dock: QDockWidget) -> QRect | None:
    """``dock.geometry()`` if it actually intersects the window's own rect, else ``None``.

    See module docstring: a tabified-but-not-frontmost dock reports
    ``isVisible()==True`` yet is parked off at degenerate coordinates -- this
    filters those out without relying on the specific negative-coordinate
    pattern itself.
    """
    if not dock.isVisible():
        return None
    geom = dock.geometry()
    if not window.rect().intersects(geom):
        return None
    return geom


def _prepare_window(qtbot, window_size: tuple[int, int] = (1280, 800)) -> MainWindow:
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(*window_size)
    window.show()
    qtbot.waitExposed(window)
    return window


# ============================================================
# 1-2: objectName + restore-order
# ============================================================


def test_all_docks_have_unique_object_names(qtbot, isolated_window_settings):
    """1: every dock has a non-empty objectName, and no two docks share one."""
    window = _prepare_window(qtbot)
    names = [dock.objectName() for dock in _all_docks(window)]
    assert all(name for name in names), f"empty objectName found: {names!r}"
    assert len(names) == len(set(names)), f"duplicate objectName found: {names!r}"


def test_restore_state_called_after_all_docks_constructed(qtbot, isolated_window_settings):
    """2: a valid, current-schema saved state restores correctly -- proving every dock
    (including the newest, C-scan) already existed with its objectName set at the
    moment ``restoreState()`` ran, since Qt can only restore docks it can look up by
    objectName.
    """
    first = _prepare_window(qtbot)
    first._save_window_state()
    first.close()

    second = _prepare_window(qtbot)
    assert second._restore_window_state() is True


# ============================================================
# 3-7: default layout shape
# ============================================================


def test_clean_settings_default_layout_has_no_floating_docks(qtbot, isolated_window_settings):
    """3: with no saved settings, the default layout has zero floating docks."""
    window = _prepare_window(qtbot)
    assert all(not dock.isFloating() for dock in _all_docks(window))


def test_dataset_and_processing_are_tabified(qtbot, isolated_window_settings):
    """4."""
    window = _prepare_window(qtbot)
    assert window._processing_dock in window.tabifiedDockWidgets(window._dataset_dock)


def test_metadata_and_geometry_are_tabified(qtbot, isolated_window_settings):
    """5."""
    window = _prepare_window(qtbot)
    assert window._geometry_dock in window.tabifiedDockWidgets(window._metadata_dock)


def test_plan_view_and_cscan_are_tabified(qtbot, isolated_window_settings):
    """6."""
    window = _prepare_window(qtbot)
    assert window._cscan_dock in window.tabifiedDockWidgets(window._plan_view_dock)


def test_central_widget_visible_with_positive_area(qtbot, isolated_window_settings):
    """7."""
    window = _prepare_window(qtbot)
    center = window.centralWidget()
    assert center is not None
    assert center.isVisible()
    assert center.width() > 0
    assert center.height() > 0


# ============================================================
# 8-9: overlap at specific resolutions
# ============================================================


def _assert_no_onscreen_overlaps(window: MainWindow) -> None:
    # Qt's dock layout is lazy: right after a restoreGeometry/restoreState (or a
    # resize) the geometry() values are mid-transition until pending layout events
    # run -- settle them first, per this suite's own spec (processEvents +
    # layout().activate(), not just isVisible()).
    if window.layout() is not None:
        window.layout().activate()
    QApplication.processEvents()
    QApplication.processEvents()

    center = window.centralWidget()
    center_rect = center.geometry()
    onscreen = [(dock, r) for dock in _all_docks(window) if (r := _onscreen_rect(window, dock)) is not None]

    for dock, rect in onscreen:
        assert not center_rect.intersects(rect) or center_rect.intersected(rect).isEmpty(), (
            f"{dock.objectName()} overlaps the central widget: dock={rect}, center={center_rect}"
        )
    for i, (dock_a, rect_a) in enumerate(onscreen):
        for dock_b, rect_b in onscreen[i + 1 :]:
            inter = rect_a.intersected(rect_b)
            assert inter.isEmpty(), (
                f"{dock_a.objectName()} overlaps {dock_b.objectName()}: {rect_a} vs {rect_b} -> {inter}"
            )


def test_no_dock_overlaps_center_at_1280x800(qtbot, isolated_window_settings):
    """8."""
    window = _prepare_window(qtbot, (1280, 800))
    _assert_no_onscreen_overlaps(window)


def test_no_dock_overlaps_center_at_1366x768(qtbot, isolated_window_settings):
    """9."""
    window = _prepare_window(qtbot, (1366, 768))
    _assert_no_onscreen_overlaps(window)


# ============================================================
# 10-12: long-content scroll wrapping
# ============================================================


def test_processing_content_scrolls_within_dock_bounds(qtbot, isolated_window_settings):
    """10."""
    window = _prepare_window(qtbot)
    scroll = window._processing_dock.widget()
    assert isinstance(scroll, QScrollArea)
    assert scroll.widgetResizable() is True


def test_geometry_content_scrolls_within_dock_bounds(qtbot, isolated_window_settings):
    """11."""
    window = _prepare_window(qtbot)
    scroll = window._geometry_dock.widget()
    assert isinstance(scroll, QScrollArea)
    assert scroll.widgetResizable() is True


def test_cscan_content_scrolls_within_dock_bounds(qtbot, isolated_window_settings):
    """12."""
    window = _prepare_window(qtbot)
    scroll = window._cscan_dock.widget()
    assert isinstance(scroll, QScrollArea)
    assert scroll.widgetResizable() is True


# ============================================================
# 13-15, 21: schema fallback
# ============================================================


def test_stale_schema_state_falls_back_to_default(qtbot, isolated_window_settings):
    """13, 21: a lower/mismatched schema version (as an older release, or one predating
    a newly-added dock, would have written) is never restored -- the default layout
    (already correctly built) is left untouched, so no partial/overlapping restore
    from a dock set that no longer matches can occur.
    """
    first = _prepare_window(qtbot)
    first.close()  # clean close saves current-schema state -- tamper only afterwards
    settings = open_window_settings()
    settings.setValue("layout/schemaVersion", WINDOW_STATE_SCHEMA_VERSION - 1)
    settings.sync()

    second = _prepare_window(qtbot)
    assert second._restore_window_state() is False
    assert second._processing_dock in second.tabifiedDockWidgets(second._dataset_dock)
    _assert_no_onscreen_overlaps(second)


def test_corrupt_state_falls_back_to_default(qtbot, isolated_window_settings):
    """14."""
    first = _prepare_window(qtbot)
    first.close()  # clean close saves current-schema state -- tamper only afterwards
    settings = open_window_settings()
    settings.setValue("layout/dockState", b"not-a-real-qbytearray-state")
    settings.sync()

    second = _prepare_window(qtbot)
    assert second._restore_window_state() is False
    _assert_no_onscreen_overlaps(second)


def test_current_schema_valid_state_is_restored(qtbot, isolated_window_settings):
    """15."""
    first = _prepare_window(qtbot)
    first._cscan_dock.raise_()  # deliberately deviate from the default frontmost tab
    first._save_window_state()
    first.close()

    second = _prepare_window(qtbot)
    assert second._restore_window_state() is True


# ============================================================
# 16-19: Reset Window Layout
# ============================================================


def test_reset_window_layout_restores_default_arrangement(qtbot, isolated_window_settings):
    """16."""
    window = _prepare_window(qtbot)
    window._dataset_dock.setFloating(True)
    window._on_reset_window_layout_triggered()
    assert window._processing_dock in window.tabifiedDockWidgets(window._dataset_dock)
    assert window._geometry_dock in window.tabifiedDockWidgets(window._metadata_dock)
    assert window._cscan_dock in window.tabifiedDockWidgets(window._plan_view_dock)


def test_reset_makes_all_docks_visible(qtbot, isolated_window_settings):
    """17."""
    window = _prepare_window(qtbot)
    window._geometry_dock.setVisible(False)
    window._on_reset_window_layout_triggered()
    assert all(dock.isVisible() for dock in _all_docks(window))


def test_reset_redocks_floating_docks(qtbot, isolated_window_settings):
    """18."""
    window = _prepare_window(qtbot)
    window._cscan_dock.setFloating(True)
    assert window._cscan_dock.isFloating()
    window._on_reset_window_layout_triggered()
    assert not window._cscan_dock.isFloating()


def test_reset_window_layout_preserves_dataset_and_processing_state(
    qtbot, dataset_factory, isolated_window_settings
):
    """19: Reset Window Layout touches only window/dock placement -- never the loaded
    dataset or the processing-panel's own selected operation/parameters.
    """
    window = _prepare_window(qtbot)
    dataset = _make_dataset(dataset_factory)
    _load_dataset(window, dataset, Path("x.ogpr"))
    window._selected_operation_id = "dewow"
    window._operation_params["dewow"]["window_ns"] = 12.5

    window._on_reset_window_layout_triggered()

    assert window.session.is_loaded
    assert window._selected_operation_id == "dewow"
    assert window._operation_params["dewow"]["window_ns"] == 12.5


# ============================================================
# 20: stability across cycles
# ============================================================


def test_layout_stable_after_two_open_close_cycles(qtbot, isolated_window_settings):
    """20."""
    first = _prepare_window(qtbot)
    first._save_window_state()
    first.close()

    second = _prepare_window(qtbot)
    assert second._restore_window_state() is True
    _assert_no_onscreen_overlaps(second)
    second._save_window_state()
    second.close()

    third = _prepare_window(qtbot)
    assert third._restore_window_state() is True
    _assert_no_onscreen_overlaps(third)


# ============================================================
# 22: deferred close does not crash layout save
# ============================================================


def test_deferred_close_does_not_crash_layout_save(qtbot, isolated_window_settings):
    """22: closing while a background task is (simulated) in flight must defer, not save
    state, and must not raise -- ``_save_window_state()`` is only ever reached from
    ``closeEvent``'s clean-close branch.
    """
    window = _prepare_window(qtbot)
    window._cscan_thread = QThread(
        window
    )  # constructed, never started -- is_computing_cscan only checks is-not-None

    window.close()

    assert window._close_pending is True
    assert window.isHidden()

    window._cscan_thread = None  # bypass the full worker-finished lifecycle; not what this test targets
    window.close()


# ============================================================
# 23-24: dataset-state interaction
# ============================================================


def test_default_layout_valid_with_no_dataset(qtbot, isolated_window_settings):
    """23."""
    window = _prepare_window(qtbot)
    assert not window.session.is_loaded
    _assert_no_onscreen_overlaps(window)


def test_no_overlap_after_file_load(qtbot, dataset_factory, isolated_window_settings):
    """24."""
    window = _prepare_window(qtbot)
    dataset = _make_dataset(dataset_factory)
    _load_dataset(window, dataset, Path("x.ogpr"))
    _assert_no_onscreen_overlaps(window)


# ============================================================
# 25-26: center view never collapses
# ============================================================


def test_center_view_nonzero_when_processing_tab_active(qtbot, isolated_window_settings):
    """25."""
    window = _prepare_window(qtbot)
    window._processing_dock.raise_()
    qtbot.wait(10)
    center = window.centralWidget()
    assert center.width() > 0
    assert center.height() > 0


def test_center_view_nonzero_when_cscan_tab_active(qtbot, isolated_window_settings):
    """26."""
    window = _prepare_window(qtbot)
    window._cscan_dock.raise_()
    qtbot.wait(10)
    center = window.centralWidget()
    assert center.width() > 0
    assert center.height() > 0


# ============================================================
# 27: content stays within viewport
# ============================================================


def test_dock_content_stays_within_viewport(qtbot, isolated_window_settings):
    """27: each scroll-wrapped dock's viewport never exceeds its own dock's geometry."""
    window = _prepare_window(qtbot)
    for dock in (window._processing_dock, window._geometry_dock, window._cscan_dock):
        scroll = dock.widget()
        assert isinstance(scroll, QScrollArea)
        viewport = scroll.viewport()
        assert viewport.width() <= scroll.width()
        assert viewport.height() <= scroll.height()


# ============================================================
# 28: no Qt warnings
# ============================================================


def test_no_qt_layout_warnings_during_construction_and_resize(qtbot, isolated_window_settings, capsys):
    """28: construction, a resize, and Reset Window Layout together must not print any
    QLayout/QWidget geometry warning to stderr (Qt logs these via its own message
    handler / stderr, not Python warnings -- so this greps captured stderr text
    rather than using ``pytest.warns``).
    """
    window = _prepare_window(qtbot, (1280, 800))
    window.resize(1366, 768)
    qtbot.wait(10)
    window._on_reset_window_layout_triggered()
    qtbot.wait(10)

    captured = capsys.readouterr()
    combined = (captured.out + captured.err).lower()
    for marker in ("qlayout", "does not have a layout", "qwidget::setgeometry", "runtimewarning"):
        assert marker not in combined, f"Qt warning marker {marker!r} found in output:\n{combined}"
