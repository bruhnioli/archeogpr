"""C-scan / time-slice view (Sprint 3D-1): renders one ``CScanResult`` value
grid on either of two geometry views, never both blended and never
resampled between them (see ADR-017).

Mirrors :mod:`archaeogpr.gui.views.plan_view`'s conventions closely for the
**Actual X/Y point map**: a single vectorized ``pg.ScatterPlotItem`` (never
one ``QWidget`` per point), ``sigMouseClicked``/``sigMouseMoved`` for
click-to-select/hover, the same nearest-point vectorized hit test. The
**Derived s/c parameter grid** instead reuses
:mod:`archaeogpr.gui.views.bscan_view`'s ``ImageItem`` + centralized
:func:`~archaeogpr.gui.views.bscan_view.colormap_lookup_table` pattern, with
its own single transpose point (see :meth:`_render_derived_grid`) so trace
is always the along-track/X axis and channel the cross-track/Y axis.

Never reads ``dataset.amplitudes`` directly -- only a ``CScanResult`` (a
value grid already computed by :func:`archaeogpr.cscan.compute.compute_cscan`)
and a :class:`~archaeogpr.geometry.models.SurveyGeometry` (for point
positions), exactly like ``PlanView`` never reads the dataset either.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from archaeogpr.cscan.models import CScanGeometryView, CScanResult
from archaeogpr.geometry.models import SurveyGeometry
from archaeogpr.gui.models.cscan_display_settings import CScanDisplaySettings, compute_cscan_display_levels
from archaeogpr.gui.views.bscan_view import colormap_lookup_table

_SELECTED_PEN = pg.mkPen("#ffe100", width=2)
_INVALID_POINT_PEN = pg.mkPen("#cc3333", width=1.5)

_ACTUAL_XY_LABEL = "Actual X/Y point map — no interpolation"
_DERIVED_GRID_LABEL = "Derived s/c parameter grid"


def _map_values_to_colors(values: np.ndarray, levels: tuple[float, float], lut: np.ndarray) -> np.ndarray:
    """``values`` (any shape) -> ``(*values.shape, 3)`` ``uint8`` colors via ``lut`` (256, 3).

    Non-finite entries map to index 0 of the LUT (never used for a finite
    point, since callers only pass finite values in) -- the caller is
    responsible for excluding invalid points from what actually gets drawn.
    """
    low, high = levels
    span = high - low
    normalized = np.zeros_like(values, dtype=np.float64) if span <= 0 else (values - low) / span
    normalized = np.clip(np.nan_to_num(normalized, nan=0.0), 0.0, 1.0)
    indices = np.clip((normalized * (lut.shape[0] - 1)).round().astype(np.int64), 0, lut.shape[0] - 1)
    return lut[indices]


def _derived_parameter_grid(geometry: SurveyGeometry) -> tuple[np.ndarray, np.ndarray] | None:
    """The idealized ``(trace_count, channel_count)`` s/c grid, or ``None`` if unavailable.

    Always broadcasts the 1-D ``along_track_coordinates``/``cross_track_offsets``
    into a 2-D grid -- unlike ``plan_view._acquisition_point_grid``, this
    never substitutes the actual ``x_coordinates``/``y_coordinates`` even
    when they exist, because this view is specifically the *idealized*
    parameter-space rendering (see ADR-017): the two geometry views must
    never silently become the same data.
    """
    if geometry.along_track_coordinates is None or geometry.cross_track_offsets is None:
        return None
    along = geometry.along_track_coordinates
    cross = geometry.cross_track_offsets
    s_grid = np.broadcast_to(along[:, np.newaxis], (geometry.trace_count, geometry.channel_count))
    c_grid = np.broadcast_to(cross[np.newaxis, :], (geometry.trace_count, geometry.channel_count))
    return np.asarray(s_grid), np.asarray(c_grid)


class CScanView(QWidget):
    """One rendered C-scan: Actual X/Y point map or Derived s/c parameter grid, never both at once."""

    pointClicked = Signal(int, int)  # trace_index, channel_index
    pointHovered = Signal(int, int, float, float)  # trace_index, channel_index, coord_a, coord_b

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._geometry: SurveyGeometry | None = None
        self._result: CScanResult | None = None
        self._settings = CScanDisplaySettings()
        self._x_grid: np.ndarray | None = (
            None  # whichever grid is currently active (trace_count, channel_count)
        )
        self._y_grid: np.ndarray | None = None
        self._selected_trace: int | None = None
        self._selected_channel: int = 0

        self.plot_widget = pg.PlotWidget()
        self.view_box = self.plot_widget.getPlotItem().getViewBox()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)

        self.value_scatter = pg.ScatterPlotItem(size=self._settings.point_size, pen=pg.mkPen(None))
        self.plot_widget.addItem(self.value_scatter)

        self.invalid_scatter = pg.ScatterPlotItem(
            size=8, pen=_INVALID_POINT_PEN, brush=pg.mkBrush(None), symbol="x"
        )
        self.plot_widget.addItem(self.invalid_scatter)

        self.image_item = pg.ImageItem()
        self.image_item.setVisible(False)
        self.plot_widget.addItem(self.image_item)

        self.selected_marker = pg.ScatterPlotItem(
            size=14, pen=_SELECTED_PEN, brush=pg.mkBrush(None), symbol="o"
        )
        self.plot_widget.addItem(self.selected_marker)

        self.mode_label = pg.LabelItem(_ACTUAL_XY_LABEL, color="#cccccc", size="9pt")
        self.plot_widget.getPlotItem().layout.addItem(self.mode_label, 4, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_clicked)
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

    # -- data -----------------------------------------------------------------

    def set_geometry(self, geometry: SurveyGeometry | None) -> None:
        self._geometry = geometry
        self._render()

    def set_result(self, result: CScanResult | None) -> None:
        self._result = result
        self._render()

    def set_display_settings(self, settings: CScanDisplaySettings) -> None:
        self._settings = settings
        self.value_scatter.setSize(settings.point_size)
        self._render()

    def clear(self) -> None:
        """Fully resets stored state (geometry, result) *and* every rendered visual.

        Distinct from :meth:`_clear_visuals` — that one is used internally by
        :meth:`_render` whenever there isn't (yet) enough data to draw
        anything, and must never wipe ``self._geometry``/``self._result``:
        ``set_geometry``/``set_result`` are normally called independently
        (once per file load, once per compute) — clearing either one's
        stored reference as a side effect of the *other* not being set yet
        would make a legitimate ``set_geometry(...)`` call get silently
        undone the instant it runs, before ``set_result`` ever has a chance
        to follow it (a real bug caught while writing this view's own
        manual smoke test).
        """
        self._geometry = None
        self._result = None
        self._clear_visuals()

    def _clear_visuals(self) -> None:
        self._x_grid = None
        self._y_grid = None
        self.value_scatter.setData(x=[], y=[])
        self.invalid_scatter.setData(x=[], y=[])
        self.image_item.setVisible(False)
        self.selected_marker.setData(x=[], y=[])

    def _render(self) -> None:
        if self._geometry is None or self._result is None:
            self._clear_visuals()
            return
        if self._settings.geometry_view is CScanGeometryView.ACTUAL_XY_POINT_MAP:
            self._render_actual_xy()
        else:
            self._render_derived_grid()
        self._update_selected_marker()

    def _levels(self) -> tuple[float, float]:
        assert self._result is not None
        return compute_cscan_display_levels(self._result.values, self._result.aggregation, self._settings)

    def _render_actual_xy(self) -> None:
        assert self._geometry is not None and self._result is not None
        self.image_item.setVisible(False)
        self.mode_label.setText(_ACTUAL_XY_LABEL)
        x_grid, y_grid = self._geometry.x_coordinates, self._geometry.y_coordinates
        if x_grid is None or y_grid is None:
            self._clear_visuals()
            return
        self._x_grid, self._y_grid = x_grid, y_grid
        values = self._result.values
        point_valid = self._result.valid_mask & np.isfinite(x_grid) & np.isfinite(y_grid)

        lut = colormap_lookup_table(self._settings.colormap)
        levels = self._levels()
        if point_valid.any():
            colors = _map_values_to_colors(values[point_valid], levels, lut)
            brushes = [pg.mkBrush(int(r), int(g), int(b)) for r, g, b in colors]
            self.value_scatter.setData(x=x_grid[point_valid], y=y_grid[point_valid], brush=brushes)
        else:
            self.value_scatter.setData(x=[], y=[])

        invalid_mask = (~point_valid) & np.isfinite(x_grid) & np.isfinite(y_grid)
        if self._settings.show_invalid_points and invalid_mask.any():
            self.invalid_scatter.setData(x=x_grid[invalid_mask], y=y_grid[invalid_mask])
        else:
            self.invalid_scatter.setData(x=[], y=[])
        self.view_box.setAspectLocked(True)

    def _render_derived_grid(self) -> None:
        """The one transpose point for this view: ``values.T`` puts trace on X, channel on Y.

        ``result.values`` is ``(trace_count, channel_count)``;
        ``pg.setConfigOptions(imageAxisOrder='row-major')`` (set once in
        ``app.py``, same as ``BScanView``) means ``ImageItem`` reads axis 0
        as the row (Y) and axis 1 as the column (X) -- so without a
        transpose, trace would land on Y and channel on X, backwards from
        the along-track=X/cross-track=Y convention this view must show (see
        ADR-017 and ``test_gui_cscan.py``'s synthetic index-coded check).
        """
        assert self._geometry is not None and self._result is not None
        grid = _derived_parameter_grid(self._geometry)
        if grid is None:
            self._clear_visuals()
            return
        s_grid, c_grid = grid
        self._x_grid, self._y_grid = s_grid, c_grid
        self.value_scatter.setData(x=[], y=[])
        self.invalid_scatter.setData(x=[], y=[])
        self.view_box.setAspectLocked(False)

        label = _DERIVED_GRID_LABEL
        self.mode_label.setText(label)
        self.plot_widget.setLabel("bottom", "Along-track (m)")
        self.plot_widget.setLabel("left", "Cross-track (m)")

        values = self._result.values
        display_values = np.where(self._result.valid_mask, values, np.nan)
        image = display_values.T  # (channel_count, trace_count) -- see method docstring
        self.image_item.setLookupTable(colormap_lookup_table(self._settings.colormap))
        self.image_item.setImage(image, autoLevels=False, levels=self._levels())
        along_min, along_max = float(s_grid[0, 0]), float(s_grid[-1, 0])
        cross_min, cross_max = float(c_grid[0, 0]), float(c_grid[0, -1])
        self.image_item.setRect(
            QRectF(
                min(along_min, along_max),
                min(cross_min, cross_max),
                abs(along_max - along_min) or 1.0,
                abs(cross_max - cross_min) or 1.0,
            )
        )
        self.image_item.setVisible(True)

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

    # -- view -----------------------------------------------------------------

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
