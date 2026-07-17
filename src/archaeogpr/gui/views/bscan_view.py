"""B-scan (radargram) view: one channel, every trace, grayscale/zero-centered.

**Single centralized transpose point** (per the GUI-1 axis-semantics
requirement): the only place this module reads ``dataset.amplitudes`` is
:meth:`BScanView.set_data`, where ``channel_data = dataset.amplitudes[:,
channel, :]`` (shape ``(trace, sample)``) is transposed exactly once, into
``channel_data.T`` (shape ``(sample, trace)``), before handing it to
pyqtgraph. This is the same transpose ``src/archaeogpr/qc/bscan.py::
plot_bscan`` uses for its matplotlib ``imshow`` -- the two renderers agree on
which array axis is "along-track" and which is "time" for exactly this
reason. No other code in this GUI transposes or re-orients the amplitude
array.

Coordinate mapping (verified empirically, not assumed -- see
``obsidian/ArchaeoGPR_Vault/02_SPRINTS/Sprint_GUI_1_Viewer_Shell.md``
Implementation Notes for the pyqtgraph experiment this is based on):
with ``pg.setConfigOptions(imageAxisOrder='row-major')`` (set once in
``app.py``), an image array's row 0 is its lowest data-Y value under
``ImageItem.setRect(...)``; pyqtgraph's ``ViewBox`` Y axis increases
*upward* on screen by default, so row 0 (the earliest time sample) would
render at the *bottom* of the plot unless the view is Y-inverted. This view
calls ``ViewBox.invertY(True)`` so ``time_ns[0]`` renders at the top and
time increases downward -- matching ``plot_bscan``'s ``origin="upper"``
matplotlib convention and standard radargram display.

Display-only contrast: percentile clipping here only sets pyqtgraph's
``levels`` (the color-mapping range) -- it never modifies
``dataset.amplitudes`` (same guarantee as ``qc/bscan.py``, see its module
docstring).
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QPointF, QRectF, Signal
from PySide6.QtWidgets import QWidget

from archaeogpr.model.dataset import GPRDataset

DEFAULT_CLIP_PERCENTILE = 99.0


def _symmetric_clip_limit(data: np.ndarray, percentile: float = DEFAULT_CLIP_PERCENTILE) -> float:
    """Symmetric, zero-centered display limit at ``+/- percentile(|data|, percentile)``.

    Display-only: used solely to set color-mapping ``levels``, mirroring
    ``qc/bscan.py::compute_shared_clip_limit``'s semantics without importing
    that (matplotlib-coupled) module into the GUI's import graph.
    """
    finite = data[np.isfinite(data)]
    if finite.size == 0:
        return 1.0
    limit = float(np.percentile(np.abs(finite), percentile))
    return limit if limit > 0 else 1.0


class BScanView(QWidget):
    """One channel's B-scan: grayscale image, click-to-select-trace, zoom/pan."""

    traceClicked = Signal(int)
    pointHovered = Signal(int, float, float)  # trace_index, time_ns, amplitude

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from PySide6.QtWidgets import QVBoxLayout

        self._time_ns: np.ndarray | None = None
        self._channel_data: np.ndarray | None = None  # (trace, sample), read-only view onto dataset

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Trace index")
        self.plot_widget.setLabel("left", "Time (ns)")
        self.view_box = self.plot_widget.getPlotItem().getViewBox()
        self.view_box.invertY(True)  # time_ns[0] at top, increasing downward -- see module docstring

        self.image_item = pg.ImageItem()
        self.plot_widget.addItem(self.image_item)

        self.trace_marker = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("y", width=1))
        self.trace_marker.setVisible(False)
        self.plot_widget.addItem(self.trace_marker)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_clicked)
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def set_data(
        self, dataset: GPRDataset, channel: int, *, clip_percentile: float = DEFAULT_CLIP_PERCENTILE
    ) -> None:
        """Display ``dataset.amplitudes[:, channel, :]``. Does not modify ``dataset``."""
        channel_data = dataset.amplitudes[:, channel, :]  # (trace, sample), read-only view
        self._channel_data = channel_data
        self._time_ns = dataset.time_ns

        image = channel_data.T  # (sample, trace) -- see module docstring: the one transpose point
        limit = _symmetric_clip_limit(image, clip_percentile)

        trace_count = channel_data.shape[0]
        t0 = float(dataset.time_ns[0])
        t1 = float(dataset.time_ns[-1])
        self.image_item.setImage(image, autoLevels=False, levels=(-limit, limit))
        self.image_item.setRect(QRectF(0.0, t0, float(trace_count), t1 - t0))
        self.plot_widget.setLabel("left", "Time (ns)")

    def set_selected_trace(self, trace: int | None) -> None:
        if trace is None:
            self.trace_marker.setVisible(False)
            return
        self.trace_marker.setPos(trace + 0.5)
        self.trace_marker.setVisible(True)

    def _trace_and_sample_at(self, view_point: QPointF) -> tuple[int, int] | None:
        if self._channel_data is None or self._time_ns is None:
            return None
        trace_count, sample_count = self._channel_data.shape
        trace = int(view_point.x())
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
