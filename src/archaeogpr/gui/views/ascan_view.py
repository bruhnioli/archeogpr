"""A-scan (single-trace) view: amplitude vs time, same time direction as the B-scan.

Reads only ``dataset.amplitudes[trace, channel, :]`` (one trace) -- no
transpose is needed for a 1-D line plot, but the Y axis is inverted the same
way as :mod:`archaeogpr.gui.views.bscan_view` (``time_ns[0]`` at top) so the
two panels agree visually on which direction is "later in time".
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget

from archaeogpr.model.dataset import GPRDataset


class AScanView(QWidget):
    """One trace's amplitude-vs-time profile for the current channel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._time_ns: np.ndarray | None = None
        self._amplitude: np.ndarray | None = None

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Amplitude")
        self.plot_widget.setLabel("left", "Time (ns)")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.view_box = self.plot_widget.getPlotItem().getViewBox()
        self.view_box.invertY(True)  # same time direction as BScanView

        self.curve = self.plot_widget.plot([], [], pen=pg.mkPen("c", width=1))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

    def set_data(self, dataset: GPRDataset, channel: int, trace: int) -> None:
        """Display ``dataset.amplitudes[trace, channel, :]``. Does not modify ``dataset``."""
        amplitude = dataset.amplitudes[trace, channel, :]
        self._amplitude = amplitude
        self._time_ns = dataset.time_ns
        self.curve.setData(amplitude, dataset.time_ns)
        self.plot_widget.setTitle(f"A-scan — trace {trace}, channel {channel:02d}")

    def clear(self) -> None:
        self._amplitude = None
        self._time_ns = None
        self.curve.setData([], [])
        self.plot_widget.setTitle(None)
