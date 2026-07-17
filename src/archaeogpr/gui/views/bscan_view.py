"""B-scan (radargram) view: one channel, every trace, non-destructive display controls.

**Single centralized transpose point** (per the GUI-1 axis-semantics
requirement, unchanged in GUI-2): the only place this module reads
``dataset.amplitudes`` is :meth:`BScanView.set_data`, where ``channel_data =
dataset.amplitudes[:, channel, :]`` (shape ``(trace, sample)``) is
transposed exactly once, into ``channel_data.T`` (shape ``(sample,
trace)``), before handing it to pyqtgraph -- the same transpose
``src/archaeogpr/qc/bscan.py::plot_bscan`` uses for its matplotlib
``imshow``. No other code in this GUI transposes or re-orients the
amplitude array.

Coordinate mapping (verified empirically -- see
``obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_1_Viewer_Shell.md``):
``pg.setConfigOptions(imageAxisOrder='row-major')`` (set once in
``app.py``) + ``ImageItem.setRect(...)`` + ``ViewBox.invertY(True)`` puts
``time_ns[0]`` at the top, increasing downward -- matching ``plot_bscan``'s
``origin="upper"`` matplotlib convention.

**Render pipeline (GUI-2), explicit stages, every ``set_data``/settings
change**  (see ``ADR-013``):

1. Take the source amplitude view (``dataset.amplitudes[:, channel, :]``,
   still a read-only view -- never copied here).
2. Determine the finite subset (``display_settings.compute_display_levels``
   ignores NaN/Inf).
3. Compute levels from the active :class:`DisplaySettings` policy.
4. Update the ``ImageItem``'s data/LUT/levels.
5. **Never** write to the source amplitude array.

Colormap LUTs are built by the one centralized :func:`colormap_lookup_table`
function (`ADR-013`) -- sampled directly from matplotlib's own "gray"/
"seismic" colormaps, so the GUI's "Seismic" is visually the same palette as
``qc/bscan.py``'s ``cmap="seismic"`` matplotlib exports, not a
lookalike reimplementation.
"""

from __future__ import annotations

import math

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, QTimer, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from archaeogpr.gui.models.display_settings import DisplaySettings, compute_display_levels
from archaeogpr.model.dataset import GPRDataset

#: Debounce delay for visible-region autoscale recomputation after a zoom/pan
#: -- avoids an expensive percentile recompute on every intermediate drag
#: frame (see CLAUDE.md-adjacent performance rule in the sprint note).
_VISIBLE_RANGE_DEBOUNCE_MS = 200

_LUT_SIZE = 256


def colormap_lookup_table(name: str) -> np.ndarray:
    """The one centralized LUT builder for every colormap this GUI offers.

    Samples matplotlib's own ``"gray"``/``"seismic"`` colormaps into a
    ``(256, 3)`` ``uint8`` lookup table for ``pyqtgraph.ImageItem.
    setLookupTable`` -- this makes the GUI's "Seismic" pixel-for-pixel the
    same palette ``qc/bscan.py``'s ``cmap="seismic"`` matplotlib exports use
    for the same data, not an independent approximation. Building a LUT does
    not require matplotlib's plotting/backend machinery (no ``pyplot``
    import), so this has no interaction with Qt's own event loop or
    ``qc/bscan.py``'s ``matplotlib.use("Agg")`` backend selection.
    """
    from matplotlib import colormaps as mpl_colormaps

    if name not in ("gray", "seismic"):
        raise ValueError(f"colormap must be 'gray' or 'seismic', got {name!r}")
    cmap = mpl_colormaps[name]
    samples = cmap(np.linspace(0.0, 1.0, _LUT_SIZE))  # (256, 4) RGBA in [0, 1]
    return (samples[:, :3] * 255).astype(np.uint8)


class BScanView(QWidget):
    """One channel's B-scan: image + contrast controls' effect, click-to-select-trace, zoom/pan."""

    traceClicked = Signal(int)
    pointHovered = Signal(int, float, float)  # trace_index, time_ns, amplitude

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._time_ns: np.ndarray | None = None
        self._channel_data: np.ndarray | None = None  # (trace, sample), read-only view onto dataset
        self._display_settings = DisplaySettings()
        self._selected_trace: int | None = None

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Trace index")
        self.plot_widget.setLabel("left", "Time (ns)")
        self.view_box = self.plot_widget.getPlotItem().getViewBox()
        self.view_box.invertY(True)  # time_ns[0] at top, increasing downward -- see module docstring

        self.image_item = pg.ImageItem()
        self.image_item.setLookupTable(colormap_lookup_table("gray"))
        self.plot_widget.addItem(self.image_item)

        # Wider + brighter than a default InfiniteLine so a selected trace is
        # unambiguous at a glance (GUI-2: "trace seçiminin daha belirgin
        # olması" feedback from the manual GUI-1 demo).
        self.trace_marker = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#ffe100", width=2))
        self.trace_marker.setVisible(False)
        self.plot_widget.addItem(self.trace_marker)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_clicked)
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

        self._visible_range_timer = QTimer(self)
        self._visible_range_timer.setSingleShot(True)
        self._visible_range_timer.setInterval(_VISIBLE_RANGE_DEBOUNCE_MS)
        self._visible_range_timer.timeout.connect(self._recompute_visible_region_levels)
        self.view_box.sigRangeChanged.connect(self._on_view_range_changed)

    # -- data / display settings ------------------------------------------

    def set_data(self, dataset: GPRDataset, channel: int) -> None:
        """Stage 1: take the source amplitude view. Never modifies ``dataset``."""
        channel_data = dataset.amplitudes[:, channel, :]  # (trace, sample), read-only view
        self._channel_data = channel_data
        self._time_ns = dataset.time_ns

        trace_count = channel_data.shape[0]
        t0 = float(dataset.time_ns[0])
        t1 = float(dataset.time_ns[-1])
        image = channel_data.T  # (sample, trace) -- see module docstring: the one transpose point
        self.image_item.setImage(image, autoLevels=False)
        self.image_item.setRect(QRectF(0.0, t0, float(trace_count), t1 - t0))
        self._apply_levels()

    def set_display_settings(self, settings: DisplaySettings) -> None:
        """Stages 2-4: recompute levels/LUT for the already-loaded image. Never touches ``dataset``."""
        self._display_settings = settings
        self.image_item.setLookupTable(colormap_lookup_table(settings.colormap))
        self._apply_levels()

    def compute_full_range_levels(self) -> tuple[float, float]:
        """The levels ``set_display_settings`` would apply right now, over the *full* trace/time range.

        Exposed so ``main_window.py``'s "Auto Levels"/status-bar code can
        report the actual current levels without duplicating the policy
        logic living in ``display_settings.compute_display_levels``.
        """
        if self._channel_data is None:
            return (-1.0, 1.0)
        return compute_display_levels(self._channel_data.T, self._display_settings)

    def _apply_levels(self) -> None:
        if self._channel_data is None:
            return
        if self._visible_region_autoscale_active():
            self._recompute_visible_region_levels()
            return
        levels = compute_display_levels(self._channel_data.T, self._display_settings)
        self.image_item.setLevels(levels)

    def _visible_region_autoscale_active(self) -> bool:
        # Manual levels always win (see ADR-013 addendum / main_window.py's
        # UI-level mutual exclusion) -- this is the render-pipeline backstop
        # that guarantees the visible-region percentile recompute never even
        # runs while manual is active, not just that its result gets
        # overridden.
        settings = self._display_settings
        return settings.visible_region_autoscale and not settings.manual_levels_enabled

    # -- visible-region autoscale (debounced) ------------------------------

    def _on_view_range_changed(self, *_args: object) -> None:
        if self._visible_region_autoscale_active():
            self._visible_range_timer.start()

    def _recompute_visible_region_levels(self) -> None:
        if self._channel_data is None or self._time_ns is None:
            return
        y_min, y_max = self.view_box.viewRange()[1]
        sample_count = self._channel_data.shape[1]
        start = int(np.searchsorted(self._time_ns, y_min, side="left"))
        end = int(np.searchsorted(self._time_ns, y_max, side="right"))
        start = max(0, min(start, sample_count - 1))
        end = max(start + 1, min(end, sample_count))
        visible_slice = self._channel_data[:, start:end]
        levels = compute_display_levels(visible_slice, self._display_settings)
        self.image_item.setLevels(levels)

    # -- trace selection ----------------------------------------------------

    def set_selected_trace(self, trace: int | None) -> None:
        self._selected_trace = trace
        if trace is None:
            self.trace_marker.setVisible(False)
            return
        self.trace_marker.setPos(trace + 0.5)
        self.trace_marker.setVisible(True)

    def reset_view(self) -> None:
        """Full trace range + full time range. Never touches contrast or the dataset."""
        self.plot_widget.getPlotItem().autoRange()

    def _trace_and_sample_at(self, view_point: QPointF) -> tuple[int, int] | None:
        if self._channel_data is None or self._time_ns is None:
            return None
        trace_count, sample_count = self._channel_data.shape
        # floor (not int()/truncate-toward-zero) so a click fractionally
        # left of trace 0 is correctly rejected rather than silently
        # snapping to trace 0 -- see Sprint_GUI_2_Display_Controls.md
        # Implementation Notes for the boundary case this fixes.
        trace = math.floor(view_point.x())
        if not (0 <= trace < trace_count):
            return None
        # nearest sample index for this view-space (time_ns) Y coordinate
        sample = int(np.searchsorted(self._time_ns, view_point.y()))
        sample = max(0, min(sample, sample_count - 1))
        return trace, sample

    def _on_mouse_clicked(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._channel_data is None:
            return
        view_point = self.view_box.mapSceneToView(event.scenePos())
        hit = self._trace_and_sample_at(view_point)
        if hit is None:
            return
        trace, _sample = hit
        self.traceClicked.emit(trace)

    def _on_mouse_moved(self, scene_pos) -> None:  # type: ignore[no-untyped-def]
        if self._channel_data is None or not self.plot_widget.sceneBoundingRect().contains(scene_pos):
            return
        view_point = self.view_box.mapSceneToView(scene_pos)
        hit = self._trace_and_sample_at(view_point)
        if hit is None:
            return
        trace, sample = hit
        amplitude = float(self._channel_data[trace, sample])
        time_ns = float(self._time_ns[sample])  # type: ignore[index]
        self.pointHovered.emit(trace, time_ns, amplitude)
