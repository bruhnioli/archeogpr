"""Main window: File > Open OGPR, channel selector, B-scan/A-scan, metadata, status bar."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QSplitter,
    QWidget,
)

from archaeogpr.gui.models.dataset_session import DatasetSession
from archaeogpr.gui.views.ascan_view import AScanView
from archaeogpr.gui.views.bscan_view import BScanView
from archaeogpr.gui.views.metadata_panel import MetadataPanel

_LOGGER = logging.getLogger("archaeogpr.gui")

_BASE_TITLE = "ArchaeoGPR"
_OGPR_FILE_FILTER = "OpenGPR Files (*.ogpr)"


class MainWindow(QMainWindow):
    """Native PySide6 shell: no processing, no 3D -- open + view only (Sprint GUI-1)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = DatasetSession()
        self.setWindowTitle(_BASE_TITLE)
        self.resize(1280, 800)

        self._build_central_views()
        self._build_docks()
        self._build_menu()
        self._build_status_bar()

    # -- construction -----------------------------------------------------

    def _build_central_views(self) -> None:
        self.bscan_view = BScanView()
        self.ascan_view = AScanView()

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.bscan_view)
        splitter.addWidget(self.ascan_view)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self.bscan_view.traceClicked.connect(self._on_trace_clicked)
        self.bscan_view.pointHovered.connect(self._on_point_hovered)

    def _build_docks(self) -> None:
        dataset_widget = QWidget()
        form = QFormLayout(dataset_widget)
        self.channel_spin = QSpinBox()
        self.channel_spin.setMinimum(0)
        self.channel_spin.setMaximum(0)
        self.channel_spin.setEnabled(False)
        self.channel_spin.valueChanged.connect(self._on_channel_changed)
        form.addRow("Channel", self.channel_spin)

        dataset_dock = QDockWidget("Dataset", self)
        dataset_dock.setWidget(dataset_widget)
        dataset_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dataset_dock)

        self.metadata_panel = MetadataPanel()
        metadata_dock = QDockWidget("Metadata", self)
        metadata_dock.setWidget(self.metadata_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, metadata_dock)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        open_action = QAction("&Open OGPR...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._on_open_triggered)
        file_menu.addAction(open_action)

    def _build_status_bar(self) -> None:
        self.status_label = QLabel("No file open")
        self.statusBar().addWidget(self.status_label)

    # -- file opening -------------------------------------------------------

    def _on_open_triggered(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(self, "Open OGPR", "", _OGPR_FILE_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str | Path) -> None:
        """Load ``path`` into the session. Never raises -- errors become a QMessageBox.

        On failure, the previous session (if any) is left completely
        untouched: :meth:`DatasetSession.load` only replaces its own state
        after a fully successful read, so nothing here needs to "roll back".
        """
        _LOGGER.info("Opening OGPR file: %s", path)
        try:
            self.session.load(path)
        except Exception as exc:  # noqa: BLE001 - any reader failure must reach the user, not crash the app
            _LOGGER.error("Failed to open %s", path, exc_info=True)
            QMessageBox.critical(
                self,
                "Could not open file",
                f"Failed to open:\n{path}\n\n{type(exc).__name__}: {exc}",
            )
            return
        _LOGGER.info(
            "Opened %s: shape=%s", path, self.session.dataset.shape if self.session.dataset else None
        )
        self._refresh_for_new_dataset()

    # -- refresh/update helpers ---------------------------------------------

    def _refresh_for_new_dataset(self) -> None:
        assert self.session.dataset is not None
        self.channel_spin.blockSignals(True)
        self.channel_spin.setMaximum(max(0, self.session.channel_count - 1))
        self.channel_spin.setValue(self.session.selected_channel)
        self.channel_spin.setEnabled(True)
        self.channel_spin.blockSignals(False)

        self._update_views()
        self.metadata_panel.set_dataset(self.session.dataset, self.session.source_path)

        name = self.session.source_path.name if self.session.source_path else "?"
        self.setWindowTitle(f"{_BASE_TITLE} — {name}")
        self._refresh_status_bar()

    def _update_views(self) -> None:
        if not self.session.is_loaded:
            return
        dataset = self.session.dataset
        assert dataset is not None
        channel = self.session.selected_channel
        self.bscan_view.set_data(dataset, channel)
        if self.session.selected_trace is not None:
            self.bscan_view.set_selected_trace(self.session.selected_trace)
            self.ascan_view.set_data(dataset, channel, self.session.selected_trace)
        else:
            self.bscan_view.set_selected_trace(None)
            self.ascan_view.clear()

    def _on_channel_changed(self, value: int) -> None:
        if not self.session.is_loaded:
            return
        self.session.selected_channel = self.session.clamp_channel(value)
        self._update_views()
        self._refresh_status_bar()

    def _on_trace_clicked(self, trace: int) -> None:
        if not self.session.is_loaded:
            return
        self.session.selected_trace = self.session.clamp_trace(trace)
        dataset = self.session.dataset
        assert dataset is not None
        self.bscan_view.set_selected_trace(self.session.selected_trace)
        self.ascan_view.set_data(dataset, self.session.selected_channel, self.session.selected_trace)
        self._refresh_status_bar()

    def _on_point_hovered(self, trace: int, time_ns: float, amplitude: float) -> None:
        self._refresh_status_bar(trace=trace, time_ns=time_ns, amplitude=amplitude)

    def _refresh_status_bar(
        self, *, trace: int | None = None, time_ns: float | None = None, amplitude: float | None = None
    ) -> None:
        if not self.session.is_loaded:
            self.status_label.setText("No file open")
            return
        shown_trace = trace if trace is not None else self.session.selected_trace
        parts = [f"Channel {self.session.selected_channel:02d}"]
        if shown_trace is not None:
            parts.append(f"Trace {shown_trace}")
        if time_ns is not None:
            parts.append(f"Time {time_ns:.3f} ns")
        if amplitude is not None:
            parts.append(f"Amplitude {amplitude:.4g}")
        self.status_label.setText(" · ".join(parts))
