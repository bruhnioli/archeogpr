"""2D acquisition-footprint plan view (Sprint 3D-0): every (trace, channel) point, in the
resolved geometry's current coordinate mode.

Mirrors :mod:`archaeogpr.gui.views.bscan_view`'s conventions: a single
``pg.PlotWidget``, a vectorized ``pg.ScatterPlotItem`` for every point
(**never** one ``QWidget`` per point -- this project's real dataset already
has 175*11 = 1925 acquisition points, and a future multi-swath session could
have far more), ``sigMouseClicked``/``sigMouseMoved`` for
click-to-select/hover, and a ``reset_view``-equivalent (:meth:`fit_to_data`).

Never reads ``dataset.amplitudes`` -- this view only ever renders a
:class:`~archaeogpr.geometry.models.SurveyGeometry`, never the dataset
itself, so it has nothing to do with -- and cannot accidentally corrupt --
the amplitude/processing pipeline.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from archaeogpr.geometry.models import CoordinateMode, SurveyGeometry

_VALID_POINT_BRUSH = pg.mkBrush("#4a90d9")
_INVALID_POINT_PEN = pg.mkPen("#cc3333", width=1.5)
_SELECTED_PEN = pg.mkPen("#ffe100", width=2)
_START_BRUSH = pg.mkBrush("#33aa33")
_END_BRUSH = pg.mkBrush("#cc3333")
_DIRECTION_PEN = pg.mkPen("#888888", width=1.0)
_CROSS_TRACK_PEN = pg.mkPen("#d98c4a", width=2.0)

_AXIS_LABELS: dict[CoordinateMode, tuple[str, str]] = {
    CoordinateMode.INDEX: ("Trace index", "Channel index"),
    CoordinateMode.LOCAL_METRIC: ("Along-track (m)", "Cross-track (m)"),
    CoordinateMode.GLOBAL_PROJECTED: ("Easting (m)", "Northing (m)"),
    CoordinateMode.GLOBAL_GEOGRAPHIC: ("Longitude", "Latitude"),
}


class PlanView(QWidget):
    """Acquisition footprint: one point per (trace, channel), equal-aspect, mode-aware axes."""

    pointClicked = Signal(int, int)  # trace_index, channel_index
    pointHovered = Signal(int, int, float, float)  # trace_index, channel_index, coord_a, coord_b

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._x_grid: np.ndarray | None = None  # (trace_count, channel_count)
        self._y_grid: np.ndarray | None = None
        self._selected_trace: int | None = None
        self._selected_channel: int = 0

        self.plot_widget = pg.PlotWidget()
        self.view_box = self.plot_widget.getPlotItem().getViewBox()
        self.view_box.setAspectLocked(True)  # equal aspect ratio -- a survey footprint must not be sheared
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)

        self.valid_scatter = pg.ScatterPlotItem(size=6, pen=pg.mkPen(None), brush=_VALID_POINT_BRUSH)
        self.plot_widget.addItem(self.valid_scatter)

        self.invalid_scatter = pg.ScatterPlotItem(
            size=8, pen=_INVALID_POINT_PEN, brush=pg.mkBrush(None), symbol="x"
        )
        self.plot_widget.addItem(self.invalid_scatter)

        self.direction_line = pg.PlotDataItem(pen=_DIRECTION_PEN)
        self.plot_widget.addItem(self.direction_line)
        self.start_marker = pg.ScatterPlotItem(size=10, pen=pg.mkPen(None), brush=_START_BRUSH, symbol="o")
        self.plot_widget.addItem(self.start_marker)
        self.end_marker = pg.ScatterPlotItem(size=10, pen=pg.mkPen(None), brush=_END_BRUSH, symbol="s")
        self.plot_widget.addItem(self.end_marker)
        # Channel-0 -> last-channel line at the first trace: shows which
        # physical direction increasing channel index points (the
        # "channel ascending direction" the spec asks the plan view to
        # display), independent of the along-track direction line above.
        self.cross_track_line = pg.PlotDataItem(pen=_CROSS_TRACK_PEN)
        self.plot_widget.addItem(self.cross_track_line)

        self.selected_marker = pg.ScatterPlotItem(
            size=14, pen=_SELECTED_PEN, brush=pg.mkBrush(None), symbol="o"
        )
        self.plot_widget.addItem(self.selected_marker)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_clicked)
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

    # -- data -----------------------------------------------------------------

    def set_geometry(self, geometry: SurveyGeometry) -> None:
        """Render every (trace, channel) acquisition point for ``geometry``. Never reads amplitude data."""
        x_grid, y_grid = _acquisition_point_grid(geometry)
        self._x_grid, self._y_grid = x_grid, y_grid

        x_label, y_label = _AXIS_LABELS[geometry.coordinate_mode]
        self.plot_widget.setLabel("bottom", x_label)
        self.plot_widget.setLabel("left", y_label)

        finite_mask = np.isfinite(x_grid) & np.isfinite(y_grid)
        self.valid_scatter.setData(x=x_grid[finite_mask], y=y_grid[finite_mask])

        invalid_x, invalid_y = x_grid[~finite_mask], y_grid[~finite_mask]
        # pyqtgraph's own view-range bookkeeping runs np.nanmin/np.nanmax per axis
        # on whatever setData() is given; if an entire axis has zero finite values
        # across the invalid subset (e.g. one whole trace's along-track value is
        # NaN, so every point in that row shares the same NaN x), that raises
        # "RuntimeWarning: All-NaN slice encountered" even though nothing is
        # rendered at a non-finite location anyway. A point missing either
        # coordinate has no plottable 2D position by definition, so render
        # nothing rather than feed an all-non-finite axis into pyqtgraph -- the
        # invalid/non-finite count itself comes from compute_geometry_summary(),
        # not from what this scatter draws.
        if invalid_x.size and np.isfinite(invalid_x).any() and np.isfinite(invalid_y).any():
            self.invalid_scatter.setData(x=invalid_x, y=invalid_y)
        else:
            self.invalid_scatter.setData(x=[], y=[])

        self._update_direction_markers(x_grid, y_grid, finite_mask)
        self._update_selected_marker()

    def clear(self) -> None:
        self._x_grid = None
        self._y_grid = None
        self.valid_scatter.setData(x=[], y=[])
        self.invalid_scatter.setData(x=[], y=[])
        self.direction_line.setData(x=[], y=[])
        self.start_marker.setData(x=[], y=[])
        self.end_marker.setData(x=[], y=[])
        self.cross_track_line.setData(x=[], y=[])
        self.selected_marker.setData(x=[], y=[])

    def _update_direction_markers(
        self, x_grid: np.ndarray, y_grid: np.ndarray, finite_mask: np.ndarray
    ) -> None:
        trace_count, channel_count = x_grid.shape
        if trace_count < 1:
            self.direction_line.setData(x=[], y=[])
            self.start_marker.setData(x=[], y=[])
            self.end_marker.setData(x=[], y=[])
            self.cross_track_line.setData(x=[], y=[])
            return
        first_mask, last_mask = finite_mask[0, :], finite_mask[-1, :]
        if not first_mask.any() or not last_mask.any():
            self.direction_line.setData(x=[], y=[])
            self.start_marker.setData(x=[], y=[])
            self.end_marker.setData(x=[], y=[])
        else:
            start_x, start_y = float(np.mean(x_grid[0, first_mask])), float(np.mean(y_grid[0, first_mask]))
            end_x, end_y = float(np.mean(x_grid[-1, last_mask])), float(np.mean(y_grid[-1, last_mask]))
            self.direction_line.setData(x=[start_x, end_x], y=[start_y, end_y])
            self.start_marker.setData(x=[start_x], y=[start_y])
            self.end_marker.setData(x=[end_x], y=[end_y])

        if channel_count >= 2 and finite_mask[0, 0] and finite_mask[0, -1]:
            self.cross_track_line.setData(
                x=[float(x_grid[0, 0]), float(x_grid[0, -1])], y=[float(y_grid[0, 0]), float(y_grid[0, -1])]
            )
        else:
            self.cross_track_line.setData(x=[], y=[])

    # -- selection --------------------------------------------------------------

    def set_selected_trace_channel(self, trace: int | None, channel: int) -> None:
        self._selected_trace = trace
        self._selected_channel = channel
        self._update_selected_marker()

    def _update_selected_marker(self) -> None:
        if self._x_grid is None or self._y_grid is None or self._selected_trace is None:
            self.selected_marker.setData(x=[], y=[])
            return
        trace_count, channel_count = self._x_grid.shape
        if not (0 <= self._selected_trace < trace_count) or not (0 <= self._selected_channel < channel_count):
            self.selected_marker.setData(x=[], y=[])
            return
        x = self._x_grid[self._selected_trace, self._selected_channel]
        y = self._y_grid[self._selected_trace, self._selected_channel]
        if not (np.isfinite(x) and np.isfinite(y)):
            self.selected_marker.setData(x=[], y=[])
            return
        self.selected_marker.setData(x=[float(x)], y=[float(y)])

    # -- view ---------------------------------------------------------------

    def fit_to_data(self) -> None:
        self.plot_widget.getPlotItem().autoRange()

    # -- hit testing / mouse interaction -------------------------------------

    def _nearest_point(self, view_point: QPointF) -> tuple[int, int, float, float] | None:
        if self._x_grid is None or self._y_grid is None:
            return None
        finite_mask = np.isfinite(self._x_grid) & np.isfinite(self._y_grid)
        if not finite_mask.any():
            return None
        dx = self._x_grid - view_point.x()
        dy = self._y_grid - view_point.y()
        distance_sq = dx * dx + dy * dy
        distance_sq = np.where(finite_mask, distance_sq, np.inf)
        flat_index = int(np.argmin(distance_sq))
        trace, channel = np.unravel_index(flat_index, self._x_grid.shape)
        return (
            int(trace),
            int(channel),
            float(self._x_grid[trace, channel]),
            float(self._y_grid[trace, channel]),
        )

    def _on_mouse_clicked(self, event) -> None:  # type: ignore[no-untyped-def]
        view_point = self.view_box.mapSceneToView(event.scenePos())
        hit = self._nearest_point(view_point)
        if hit is None:
            return
        trace, channel, _x, _y = hit
        self.pointClicked.emit(trace, channel)

    def _on_mouse_moved(self, scene_pos) -> None:  # type: ignore[no-untyped-def]
        if not self.plot_widget.sceneBoundingRect().contains(scene_pos):
            return
        view_point = self.view_box.mapSceneToView(scene_pos)
        hit = self._nearest_point(view_point)
        if hit is None:
            return
        trace, channel, x, y = hit
        self.pointHovered.emit(trace, channel, x, y)


def _acquisition_point_grid(geometry: SurveyGeometry) -> tuple[np.ndarray, np.ndarray]:
    """The full ``(trace_count, channel_count)`` point grid this geometry's current mode implies.

    Global mode already has a genuine per-point grid
    (:attr:`SurveyGeometry.x_coordinates`/``y_coordinates``). Index/local
    modes only have one 1-D array per axis -- broadcast them into the same
    ``(trace_count, channel_count)`` shape for a uniform caller.
    """
    if geometry.x_coordinates is not None and geometry.y_coordinates is not None:
        return geometry.x_coordinates, geometry.y_coordinates
    trace_count, channel_count = geometry.trace_count, geometry.channel_count
    along = (
        geometry.along_track_coordinates
        if geometry.along_track_coordinates is not None
        else np.arange(trace_count, dtype=np.float64)
    )
    cross = (
        geometry.cross_track_offsets
        if geometry.cross_track_offsets is not None
        else np.arange(channel_count, dtype=np.float64)
    )
    x_grid = np.broadcast_to(along[:, np.newaxis], (trace_count, channel_count))
    y_grid = np.broadcast_to(cross[np.newaxis, :], (trace_count, channel_count))
    return x_grid, y_grid
