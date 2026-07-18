"""A-scan (single-trace) view: amplitude vs time, three non-destructive display modes.

Reads only ``dataset.amplitudes[trace, channel, :]`` (one trace). The Y axis
is inverted the same way as :mod:`archaeogpr.gui.views.bscan_view`
(``time_ns[0]`` at top) so the two panels agree on which direction is
"later in time".

**Display modes** (``DisplaySettings.ascan_mode``, see ``ADR-013`` -- none
of these ever modify the source trace, ``dataset.processing_history``, or
any dataset metadata; they only change what is drawn):

- ``"full"`` -- the raw amplitude values, unmodified, on the X axis. The
  scientifically "true" view.
- ``"robust"`` -- **the curve itself is identical to "full"**; only the
  X-axis *view range* is set from a robust percentile
  (``ASCAN_ROBUST_PERCENTILE`` = 99.0, from ``display_settings.py`` -- one
  documented value, not a magic number here) of ``|trace|``, so a single
  strong early-time spike cannot squash the rest of the trace into a sliver
  at screen resolution. No data is altered.
- ``"normalize"`` -- **display-only**: a *new, independently-allocated*
  array ``trace / max(|trace|)`` is drawn (never written back to the
  dataset); the X axis is relabeled "Normalized amplitude" and the mode
  label makes the "display only" nature explicit. Safe against an
  all-zero trace (division guarded, falls back to the unscaled -- already
  all-zero -- trace). The X *view range* is always explicitly set to
  ``(-1.05, 1.05)`` for this mode -- see Sprint_GUI_2_Display_Controls.md
  Issues Discovered for the manual-test bug this fixes (a leftover
  Full/Robust-mode raw-amplitude X range made the normalized, ~[-1, 1]
  curve visually disappear).

**Y (time) axis**: always derived from the current dataset's own
``time_ns`` array (:meth:`_apply_time_axis_bounds`) -- never hardcoded and
never assumes ``time_ns[0] == 0`` (a future time-zero-corrected dataset may
start negative). ``ViewBox.setLimits(yMin=..., yMax=...)`` hard-constrains
panning to the real dataset bounds; the *view* itself is only force-reset
to those bounds on first load and :meth:`reset_view` (channel/trace/mode
changes on an already-loaded dataset preserve the user's zoom, same as
``BScanView``).
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget

from archaeogpr.gui.models.display_settings import ASCAN_ROBUST_PERCENTILE, AScanMode
from archaeogpr.model.dataset import GPRDataset

_MODE_LABELS: dict[AScanMode, str] = {
    "full": "Full amplitude",
    "robust": "Robust autoscale",
    "normalize": "Normalize for display",
}


class AScanView(QWidget):
    """One trace's amplitude-vs-time profile for the current channel."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._time_ns: np.ndarray | None = None
        self._amplitude: np.ndarray | None = None  # raw trace, read-only view onto dataset
        self._mode: AScanMode = "full"
        self._trace: int | None = None
        self._channel: int | None = None
        self._dataset_ref: GPRDataset | None = None  # identity check only, never read for data

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("bottom", "Amplitude")
        self.plot_widget.setLabel("left", "Time (ns)")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.view_box = self.plot_widget.getPlotItem().getViewBox()
        self.view_box.invertY(True)  # same time direction as BScanView

        self.curve = self.plot_widget.plot([], [], pen=pg.mkPen("c", width=1))
        self.zero_line = pg.InfiniteLine(pos=0.0, angle=90, movable=False, pen=pg.mkPen("#666666", width=1))
        self.plot_widget.addItem(self.zero_line)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)

    def set_mode(self, mode: AScanMode) -> None:
        self._mode = mode
        # Re-assert the time-axis limits on every mode change too (cheap,
        # idempotent) -- defends against any future call path that reaches
        # set_mode() without a preceding set_data().
        self._apply_time_axis_bounds(force_reset=False)
        self._redraw()

    def set_data(self, dataset: GPRDataset, channel: int, trace: int) -> None:
        """Display ``dataset.amplitudes[trace, channel, :]``. Does not modify ``dataset``."""
        is_new_dataset = self._dataset_ref is not dataset
        self._dataset_ref = dataset
        self._amplitude = dataset.amplitudes[trace, channel, :]  # raw, read-only view
        self._time_ns = dataset.time_ns
        self._trace = trace
        self._channel = channel
        self._apply_time_axis_bounds(force_reset=is_new_dataset)
        self._redraw()

    def clear(self) -> None:
        self._amplitude = None
        self._time_ns = None
        self._dataset_ref = None
        self._trace = None
        self._channel = None
        self.curve.setData([], [])
        self.plot_widget.setTitle(None)
        self.plot_widget.setLabel("bottom", "Amplitude")
        self.view_box.setLimits(yMin=None, yMax=None)

    def reset_view(self) -> None:
        """Full dataset time range + mode-appropriate X range. Never touches the dataset."""
        self._apply_time_axis_bounds(force_reset=True)
        self._redraw()

    def _apply_time_axis_bounds(self, *, force_reset: bool) -> None:
        """Constrain the Y (time) axis to the real ``dataset.time_ns`` bounds -- never hardcoded.

        ``setLimits`` alone keeps any current or future view from ever
        panning past the dataset's actual time range (this is what
        previously let a ~128 ns dataset show 200+ ns of empty space -- see
        Sprint_GUI_2_Display_Controls.md Issues Discovered). ``force_reset``
        additionally snaps the *current* view to the full bounds; used only
        on first load and :meth:`reset_view` so a user's zoom/pan on an
        already-loaded dataset survives a channel/trace/mode change.
        """
        if self._time_ns is None or self._time_ns.size == 0:
            return
        # not time_ns[0] -- a time-zero-corrected axis may not start at 0
        y_min = float(np.min(self._time_ns))
        y_max = float(np.max(self._time_ns))
        self.view_box.setLimits(yMin=y_min, yMax=y_max)
        if force_reset:
            self.view_box.setYRange(y_min, y_max, padding=0.0)

    def _redraw(self) -> None:
        if self._amplitude is None or self._time_ns is None:
            return
        raw = self._amplitude

        if self._mode == "normalize":
            peak = float(np.max(np.abs(raw))) if raw.size else 0.0
            display_trace = (raw / peak) if peak > 0 else raw.astype(np.float64, copy=True)
            self.plot_widget.setLabel("bottom", "Normalized amplitude (display only)")
        else:
            display_trace = raw
            self.plot_widget.setLabel("bottom", "Amplitude")

        self.curve.setData(display_trace, self._time_ns)

        if self._mode == "robust" and raw.size:
            scale = float(np.percentile(np.abs(raw), ASCAN_ROBUST_PERCENTILE))
            if scale > 0:
                self.view_box.setXRange(-scale, scale, padding=0.05)
            else:
                self.view_box.enableAutoRange(axis="x")
        elif self._mode == "normalize":
            # Explicit, unconditional X range -- previously missing, which
            # left whatever X range Full/Robust had set (e.g. +-60000) in
            # place, making the ~[-1, 1] normalized curve visually vanish.
            self.view_box.setXRange(-1.05, 1.05, padding=0.0)
        else:  # "full"
            self.view_box.enableAutoRange(axis="x")

        peak_amplitude = float(np.max(np.abs(raw))) if raw.size else 0.0
        mode_label = _MODE_LABELS[self._mode]
        self.plot_widget.setTitle(
            f"A-scan — trace {self._trace}, channel {self._channel:02d} · "
            f"peak |amplitude|={peak_amplitude:.4g} · {mode_label}"
        )
