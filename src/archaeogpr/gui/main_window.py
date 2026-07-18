"""Main window: File > Open OGPR / Export PNG, dataset+display controls,
B-scan/A-scan, metadata, status bar.

**Non-destructive display principle** (GUI-2, see ``ADR-013``): every
control in the left "Display" group only changes a
:class:`~archaeogpr.gui.models.display_settings.DisplaySettings` instance
and re-renders from it -- none of them ever touch ``self.session.dataset``
or its ``amplitudes``/``processing_history``. ``_apply_display_settings()``
is the one place that pushes the current settings into the views.

**Background file loading** (GUI-1B, see ``ADR-014``): :meth:`open_path`
never reads the file itself -- it starts a
:class:`~archaeogpr.gui.workers.file_loader.FileLoadWorker` on a ``QThread``
and returns immediately, so the window stays responsive while a file loads.
``self.session`` (the previous dataset) is only ever replaced in
:meth:`_on_worker_loaded`, after a full, uncancelled, successful read.

**Shutdown is deferred, never blocking, never forced** (see ``ADR-014``):
closing the window while a load is in flight does not destroy it. Blocking
OGPR parsing cannot be forcefully interrupted -- closing the window
requests cancellation and defers final window destruction until the
reader actually returns; the cancelled result is never committed. There is
no ``wait()`` call anywhere in :meth:`closeEvent`.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from archaeogpr.gui.export import export_bscan_png, write_display_sidecar
from archaeogpr.gui.models.dataset_session import DatasetSession
from archaeogpr.gui.models.display_settings import (
    MAX_CLIP_PERCENTILE,
    MIN_CLIP_PERCENTILE,
    DisplaySettings,
    default_display_settings,
)
from archaeogpr.gui.views.ascan_view import AScanView
from archaeogpr.gui.views.bscan_view import BScanView
from archaeogpr.gui.views.metadata_panel import MetadataPanel
from archaeogpr.gui.workers.file_loader import FileLoadState, FileLoadWorker
from archaeogpr.model.dataset import GPRDataset

_LOGGER = logging.getLogger("archaeogpr.gui")

_BASE_TITLE = "ArchaeoGPR"
_OGPR_FILE_FILTER = "OpenGPR Files (*.ogpr)"
_PNG_FILE_FILTER = "PNG Files (*.png)"
_MANUAL_LEVEL_RANGE = 1.0e12  # generous bound; real amplitude magnitudes are far smaller
_PERCENTILE_SLIDER_SCALE = 10  # slider is int-only; 90.0-100.0 step 0.1 -> 900-1000 step 1
_ACTIVE_LOAD_STATES = (FileLoadState.LOADING, FileLoadState.CANCELLING)

_COLORMAP_ITEMS = (("Gray", "gray"), ("Seismic", "seismic"))
_ASCAN_MODE_ITEMS = (
    ("Full amplitude", "full"),
    ("Robust autoscale", "robust"),
    ("Normalize for display", "normalize"),
)


class _PaddedSpinBox(QSpinBox):
    """A QSpinBox that zero-pads its display (e.g. ``05`` not ``5``) -- never truncates."""

    def __init__(self, digits: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._digits = digits

    def textFromValue(self, value: int) -> str:  # noqa: N802 - Qt override signature
        return str(value).zfill(self._digits)


class MainWindow(QMainWindow):
    """Native PySide6 shell: view + non-destructive display controls (Sprint GUI-2)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = DatasetSession()
        self.display_settings = DisplaySettings()
        self.setWindowTitle(_BASE_TITLE)
        self.resize(1280, 800)
        self.setMinimumSize(900, 600)

        # -- GUI-1B background file-load state (see ADR-014) -----------------
        self._file_load_state = FileLoadState.IDLE
        self._load_thread: QThread | None = None
        self._load_worker: FileLoadWorker | None = None
        # Thread-safe (threading.Event, not a plain bool -- see ADR-014):
        # MainWindow owns it and calls .set() directly, never through a
        # queued slot, so a cancel/close request always takes effect
        # immediately regardless of what the worker's thread is doing.
        self._load_cancel_event: threading.Event | None = None
        # Every worker is constructed with the token current at that time;
        # the outcome handlers below (_on_worker_loaded/_failed/_cancelled)
        # compare its signal's token against this field, not `sender()`
        # (documented-unreliable across a queued/cross-thread connection --
        # see ADR-014) -- this is the stale-result rejection mechanism: a
        # result from a superseded load can never overwrite a newer session.
        self._current_load_token = 0
        # Set once per load, alongside the terminal state -- lets --smoke-test
        # (app.py) distinguish success/error/cancelled after the transient
        # SUCCESS/ERROR/CANCELLED state has already settled back to IDLE.
        self._last_load_outcome: str | None = None
        # True from closeEvent() until the in-flight load's thread has
        # actually finished -- see closeEvent()/_on_load_thread_finished().
        self._close_pending = False

        self._build_central_views()
        self._build_docks()
        self._build_menu()
        self._build_status_bar()
        self._sync_controls_from_settings()
        self._set_file_load_state(FileLoadState.IDLE)  # a fresh QPushButton defaults to enabled otherwise

    @property
    def is_loading(self) -> bool:
        """``True`` from the moment a load starts until its worker thread has actually finished.

        Deliberately keyed on ``self._load_thread`` (cleared only once
        ``QThread.finished`` fires -- see :meth:`_on_load_thread_finished`),
        not on ``self._file_load_state`` -- this is the single, authoritative
        "is a load-cycle still in flight" guard :meth:`open_path` and
        :meth:`closeEvent` both rely on, and it is what makes a concurrent
        second load structurally impossible (not just checked-for): a new
        load can never start while a previous one's thread object still
        exists, which is exactly the window during which a stale
        ``thread.finished`` could otherwise race a fresh one.
        """
        return self._load_thread is not None

    @property
    def last_load_outcome(self) -> str | None:
        """``"success"``/``"error"``/``"cancelled"`` for the most recent load, or ``None`` before any load.

        Used by ``app.py``'s ``--open --smoke-test`` to tell success apart
        from failure after the transient SUCCESS/ERROR/CANCELLED state has
        already settled back to IDLE.
        """
        return self._last_load_outcome

    # -- construction -----------------------------------------------------

    def _build_central_views(self) -> None:
        self.bscan_view = BScanView()
        self.ascan_view = AScanView()

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.bscan_view)
        splitter.addWidget(self.ascan_view)
        # B-scan gets most of the space by default but the user can drag the
        # splitter handle to resize the A-scan panel (GUI-2 layout ask).
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([560, 200])
        self.setCentralWidget(splitter)

        self.bscan_view.traceClicked.connect(self._on_trace_clicked)
        self.bscan_view.pointHovered.connect(self._on_point_hovered)

    def _build_docks(self) -> None:
        dataset_dock = QDockWidget("Dataset", self)
        dataset_dock.setWidget(self._build_dataset_display_widget())
        dataset_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        dataset_dock.setMinimumWidth(220)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dataset_dock)

        self.metadata_panel = MetadataPanel()
        metadata_dock = QDockWidget("Metadata", self)
        metadata_dock.setWidget(self.metadata_panel)
        metadata_dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        metadata_dock.setMinimumWidth(280)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, metadata_dock)
        self.resizeDocks([dataset_dock], [240], Qt.Orientation.Horizontal)
        self.resizeDocks([metadata_dock], [360], Qt.Orientation.Horizontal)
        self._metadata_dock = metadata_dock

    def _build_dataset_display_widget(self) -> QWidget:
        container = QWidget()
        outer = QVBoxLayout(container)

        # -- Dataset group: channel + selected trace -------------------------
        dataset_group = QGroupBox("Dataset")
        dataset_form = QFormLayout(dataset_group)

        self.channel_spin = _PaddedSpinBox(digits=2)
        self.channel_spin.setMinimum(0)
        self.channel_spin.setMaximum(0)
        self.channel_spin.setEnabled(False)
        self.channel_spin.valueChanged.connect(self._on_channel_changed)
        dataset_form.addRow("Channel", self.channel_spin)

        trace_row = QWidget()
        trace_row_layout = QHBoxLayout(trace_row)
        trace_row_layout.setContentsMargins(0, 0, 0, 0)
        self.trace_spin = _PaddedSpinBox(digits=3)
        self.trace_spin.setMinimum(0)
        self.trace_spin.setMaximum(0)
        self.trace_spin.setEnabled(False)
        self.trace_spin.valueChanged.connect(self._on_trace_spin_changed)
        self.trace_count_label = QLabel("/ 0")
        trace_row_layout.addWidget(self.trace_spin)
        trace_row_layout.addWidget(self.trace_count_label)
        dataset_form.addRow("Selected trace", trace_row)

        outer.addWidget(dataset_group)

        # -- Display group: colormap/contrast/A-scan mode --------------------
        display_group = QGroupBox("Display")
        display_form = QFormLayout(display_group)

        self.colormap_combo = QComboBox()
        for label, _value in _COLORMAP_ITEMS:
            self.colormap_combo.addItem(label)
        self.colormap_combo.currentIndexChanged.connect(self._on_colormap_changed)
        display_form.addRow("Colormap", self.colormap_combo)

        percentile_row = QWidget()
        percentile_layout = QHBoxLayout(percentile_row)
        percentile_layout.setContentsMargins(0, 0, 0, 0)
        self.percentile_spin = QDoubleSpinBox()
        self.percentile_spin.setRange(MIN_CLIP_PERCENTILE, MAX_CLIP_PERCENTILE)
        self.percentile_spin.setSingleStep(0.1)
        self.percentile_spin.setDecimals(1)
        self.percentile_slider = QSlider(Qt.Orientation.Horizontal)
        self.percentile_slider.setRange(
            int(MIN_CLIP_PERCENTILE * _PERCENTILE_SLIDER_SCALE),
            int(MAX_CLIP_PERCENTILE * _PERCENTILE_SLIDER_SCALE),
        )
        percentile_layout.addWidget(self.percentile_spin)
        percentile_layout.addWidget(self.percentile_slider)
        self.percentile_spin.valueChanged.connect(self._on_percentile_spin_changed)
        self.percentile_slider.valueChanged.connect(self._on_percentile_slider_changed)
        display_form.addRow("Clip percentile", percentile_row)

        self.symmetric_check = QCheckBox("Symmetric around zero")
        self.symmetric_check.toggled.connect(self._on_symmetric_toggled)
        display_form.addRow(self.symmetric_check)

        self.manual_check = QCheckBox("Manual levels")
        self.manual_check.toggled.connect(self._on_manual_toggled)
        display_form.addRow(self.manual_check)

        self.manual_min_spin = QDoubleSpinBox()
        self.manual_min_spin.setRange(-_MANUAL_LEVEL_RANGE, _MANUAL_LEVEL_RANGE)
        self.manual_min_spin.setDecimals(2)
        self.manual_min_spin.setEnabled(False)
        self.manual_min_spin.valueChanged.connect(self._on_manual_levels_changed)
        display_form.addRow("Minimum", self.manual_min_spin)

        self.manual_max_spin = QDoubleSpinBox()
        self.manual_max_spin.setRange(-_MANUAL_LEVEL_RANGE, _MANUAL_LEVEL_RANGE)
        self.manual_max_spin.setDecimals(2)
        self.manual_max_spin.setEnabled(False)
        self.manual_max_spin.valueChanged.connect(self._on_manual_levels_changed)
        display_form.addRow("Maximum", self.manual_max_spin)

        self.autoscale_check = QCheckBox("Auto-scale from visible time range")
        self.autoscale_check.toggled.connect(self._on_autoscale_toggled)
        display_form.addRow(self.autoscale_check)

        self.auto_levels_button = QPushButton("Auto Levels")
        self.auto_levels_button.clicked.connect(self._on_auto_levels_clicked)
        display_form.addRow(self.auto_levels_button)

        self.reset_view_button = QPushButton("Reset View")
        self.reset_view_button.clicked.connect(self._on_reset_view_clicked)
        display_form.addRow(self.reset_view_button)

        self.reset_display_button = QPushButton("Reset Display")
        self.reset_display_button.clicked.connect(self._on_reset_display_clicked)
        display_form.addRow(self.reset_display_button)

        self.ascan_mode_combo = QComboBox()
        for label, _value in _ASCAN_MODE_ITEMS:
            self.ascan_mode_combo.addItem(label)
        self.ascan_mode_combo.currentIndexChanged.connect(self._on_ascan_mode_changed)
        display_form.addRow("A-scan scale", self.ascan_mode_combo)

        outer.addWidget(display_group)
        outer.addStretch(1)
        return container

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        self.open_action = QAction("&Open OGPR...", self)
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self._on_open_triggered)
        file_menu.addAction(self.open_action)

        file_menu.addSeparator()
        self.export_png_action = QAction("&Export Current B-scan PNG...", self)
        self.export_png_action.setEnabled(False)
        self.export_png_action.triggered.connect(self._on_export_png_triggered)
        file_menu.addAction(self.export_png_action)

    def _build_status_bar(self) -> None:
        self.selected_label = QLabel("No file open")
        self.cursor_label = QLabel("Cursor — (hover over B-scan)")
        self.display_summary_label = QLabel("")
        self.statusBar().addWidget(self.selected_label)
        self.statusBar().addWidget(self.cursor_label, 1)
        self.statusBar().addPermanentWidget(self.display_summary_label)

        # -- GUI-1B: background load progress (hidden unless loading) --------
        self.load_status_label = QLabel("")
        self.load_progress_bar = QProgressBar()
        self.load_progress_bar.setMaximumWidth(140)
        self.load_progress_bar.setTextVisible(False)
        self.load_progress_bar.setRange(0, 0)  # indeterminate: no real byte-level progress is available
        self.load_cancel_button = QPushButton("Cancel")
        self.load_cancel_button.clicked.connect(self._on_cancel_load_clicked)

        self._load_progress_widget = QWidget()
        load_progress_layout = QHBoxLayout(self._load_progress_widget)
        load_progress_layout.setContentsMargins(0, 0, 0, 0)
        load_progress_layout.addWidget(self.load_status_label)
        load_progress_layout.addWidget(self.load_progress_bar)
        load_progress_layout.addWidget(self.load_cancel_button)
        self._load_progress_widget.setVisible(False)
        self.statusBar().addPermanentWidget(self._load_progress_widget)

    # -- file opening (GUI-1B: background worker, see ADR-014) ---------------

    def _on_open_triggered(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(self, "Open OGPR", "", _OGPR_FILE_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str | Path) -> None:
        """Start a background load of ``path``. Returns immediately -- never blocks the GUI thread.

        Rejects a second concurrent load outright (:attr:`is_loading` is
        only ``False`` once a previous load's ``QThread`` has actually
        finished -- see ``ADR-014``). Also rejects any load once shutdown
        has been requested (:attr:`_close_pending`): that flag stays
        latched from the first deferred :meth:`closeEvent` call all the
        way to the window actually closing, which covers the brief gap
        where :meth:`_on_load_thread_finished` has already cleared
        ``_load_thread`` (so :attr:`is_loading` alone would say "no more
        load in flight") but the deferred retry of :meth:`close` has not
        run yet -- a programmatic ``open_path`` call landing in exactly
        that gap must not be able to sneak a new load past a pending
        shutdown. Neither guard depends on the window's visibility, so a
        programmatic caller is rejected exactly like the menu action. The
        previous session is only ever replaced in :meth:`_on_worker_loaded`,
        after a full, uncancelled, successful read; a failed, cancelled, or
        shutdown-rejected load leaves it completely untouched.
        """
        if self._close_pending:
            _LOGGER.info("File load ignored because application shutdown is pending.")
            return

        if self.is_loading:
            _LOGGER.info("Load already in progress -- rejecting new request for %s", path)
            return

        resolved = Path(path).resolve()
        _LOGGER.info("Load requested: %s", resolved)

        self._current_load_token += 1
        token = self._current_load_token
        cancel_event = threading.Event()

        thread = QThread(self)
        worker = FileLoadWorker(resolved, token, cancel_event)
        worker.moveToThread(thread)

        # Connected to bound methods of `self` (a QObject living on the main
        # thread), never lambdas -- this is what makes Qt actually deliver
        # these cross-thread signals as QueuedConnection. A signal connected
        # to a plain Python callable (e.g. a lambda) has no QObject for Qt to
        # resolve a receiver thread from, so AutoConnection silently falls
        # back to DirectConnection and the slot runs *on the worker thread*,
        # touching widgets from off the GUI thread -- this crashed
        # (Windows access violation in pyqtgraph/Qt) during development; see
        # ADR-014.
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_worker_progress)
        worker.loaded.connect(self._on_worker_loaded)
        worker.failed.connect(self._on_worker_failed)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        # `thread.finished` (Qt's own, argument-less signal) is what actually
        # gates `self._load_thread`/`self._load_worker` being cleared -- see
        # _on_load_thread_finished for why this, and not `worker.finished`,
        # is the right place for that (ADR-014's cleanup-ordering fix).
        thread.finished.connect(self._on_load_thread_finished)
        thread.finished.connect(thread.deleteLater)

        self._load_thread = thread
        self._load_worker = worker
        self._load_cancel_event = cancel_event
        self._last_load_outcome = None
        self._set_file_load_state(FileLoadState.LOADING)
        self.load_status_label.setText(f"Preparing {resolved.name}…")

        thread.start()

    def _on_cancel_load_clicked(self) -> None:
        if self._file_load_state != FileLoadState.LOADING:
            return
        _LOGGER.info("Cancellation requested by user")
        self._request_cancel_current_load()
        self._set_file_load_state(FileLoadState.CANCELLING)
        self.load_status_label.setText("Cancelling…")

    def _request_cancel_current_load(self) -> None:
        """Set the current load's cancellation token directly (thread-safe, not queued).

        ``threading.Event.set()`` takes effect immediately regardless of
        what the worker thread is doing -- it does not depend on the
        worker's (nonexistent) event loop processing anything, unlike a
        queued slot invocation would. See ``ADR-014``.
        """
        if self._load_cancel_event is not None:
            self._load_cancel_event.set()

    # -- worker signal handlers (run on the main thread; see open_path) ------
    #
    # Every handler below first checks `token != self._current_load_token` --
    # this is the stale-result rejection guarantee (ADR-014). `sender()` is
    # not used for this: Qt documents it as unreliable across a queued/
    # cross-thread connection, so each signal instead carries the token its
    # worker was constructed with (see file_loader.py). These handlers
    # report the outcome (commit/error/discard) but deliberately do **not**
    # clear `self._load_thread`/`self._load_worker` or move to IDLE -- that
    # only happens in `_on_load_thread_finished`, once the thread has
    # actually, fully finished (see that method's docstring).

    def _on_worker_progress(self, token: int, _percent: int, message: str) -> None:
        if token != self._current_load_token:
            return
        self.load_status_label.setText(message)

    def _on_worker_loaded(self, token: int, dataset: GPRDataset, path: str) -> None:
        if token != self._current_load_token:
            _LOGGER.info("Discarding stale successful load (superseded by a newer request): %s", path)
            return
        self.load_status_label.setText("Updating viewer…")
        self.session.commit_dataset(dataset, Path(path))
        _LOGGER.info("Load succeeded: %s shape=%s", path, dataset.shape)
        self._refresh_for_new_dataset()
        self.load_status_label.setText("Load complete")
        self._last_load_outcome = "success"
        self._set_file_load_state(FileLoadState.SUCCESS)

    def _on_worker_failed(self, token: int, short_message: str, traceback_text: str, path: str) -> None:
        if token != self._current_load_token:
            return
        _LOGGER.error("Load failed: %s\n%s", path, traceback_text)
        self.load_status_label.setText("Load failed")
        self._last_load_outcome = "error"
        self._set_file_load_state(FileLoadState.ERROR)
        QMessageBox.critical(self, "Could not open file", f"Failed to open:\n{path}\n\n{short_message}")

    def _on_worker_cancelled(self, token: int) -> None:
        if token != self._current_load_token:
            return
        _LOGGER.info("Load cancelled")
        self.load_status_label.setText("Load cancelled")
        self._last_load_outcome = "cancelled"
        self._set_file_load_state(FileLoadState.CANCELLED)

    def _on_load_thread_finished(self) -> None:
        """Connected to the in-flight load's ``QThread.finished`` -- the one place cleanup happens.

        No token/identity check is needed here the way the outcome handlers
        above need one: :attr:`is_loading` (``self._load_thread is not
        None``) is the sole gate :meth:`open_path` uses to reject a
        concurrent load, so a new load structurally cannot start until this
        exact handler has already run for the previous one -- by
        construction, ``self._load_thread`` still refers to exactly the
        thread that just finished. This is also the deterministic point
        every terminal outcome (success/error/cancelled) converges on
        (idempotent: clearing already-``None`` fields and moving
        already-``IDLE`` state is harmless), and where a deferred
        :meth:`closeEvent` gets retried -- never earlier, so the window is
        never destroyed while its worker thread is still alive.

        Deliberately does **not** clear :attr:`_close_pending` -- that flag
        stays latched until the retried :meth:`close` below actually
        reaches :meth:`closeEvent` again and accepts. Clearing it here
        instead would reopen exactly the race a stale shutdown guard must
        close: the gap between this handler returning (``is_loading`` is
        already ``False``) and the queued retry actually running, during
        which a programmatic :meth:`open_path` call must still see a
        pending shutdown and refuse to start a new load.
        """
        self._load_thread = None
        self._load_worker = None
        self._load_cancel_event = None
        self._set_file_load_state(FileLoadState.IDLE)
        if self._close_pending:
            QTimer.singleShot(0, self.close)

    def _set_file_load_state(self, state: FileLoadState) -> None:
        self._file_load_state = state
        self.open_action.setEnabled(state == FileLoadState.IDLE)
        self.load_cancel_button.setEnabled(state == FileLoadState.LOADING)
        self._load_progress_widget.setVisible(state in _ACTIVE_LOAD_STATES)

    # -- shutdown: deferred, never blocking, never forced (see ADR-014) ------

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt override signature
        """Defers window destruction until an in-flight load's worker thread has actually finished.

        Blocking OGPR parsing cannot be forcefully interrupted. Closing the
        window requests cancellation and defers final window destruction
        until the reader returns; the cancelled result is never committed.
        There is no ``wait()`` here -- the window is hidden immediately (so
        the user sees it "close"), but the ``MainWindow``/thread/worker
        objects stay alive and the GUI event loop keeps running,
        unblocked, until :meth:`_on_load_thread_finished` retries the
        close. ``QThread.terminate()`` is never used.

        :attr:`_close_pending` is only cleared in the branch below, once a
        close is actually being accepted -- never in
        :meth:`_on_load_thread_finished`. This keeps the flag latched
        continuously from the very first deferred call here through to
        this final accepted one, with no gap in between where
        :meth:`open_path` would see shutdown as no-longer-pending while the
        window is still only hidden, not actually closed.
        """
        if not self.is_loading:
            self._close_pending = False
            super().closeEvent(event)
            return

        _LOGGER.info("Window closing while a load is in progress -- deferring close until it finishes")
        self._close_pending = True
        self._request_cancel_current_load()
        self._set_file_load_state(FileLoadState.CANCELLING)
        self.load_status_label.setText("Cancelling load before exit…")
        event.ignore()
        self.hide()

    # -- refresh/update helpers ---------------------------------------------

    def _refresh_for_new_dataset(self) -> None:
        assert self.session.dataset is not None
        self.channel_spin.blockSignals(True)
        self.channel_spin.setMaximum(max(0, self.session.channel_count - 1))
        self.channel_spin.setValue(self.session.selected_channel)
        self.channel_spin.setEnabled(True)
        self.channel_spin.blockSignals(False)

        self.trace_spin.blockSignals(True)
        self.trace_spin.setMaximum(max(0, self.session.trace_count - 1))
        self.trace_spin.setValue(self.session.selected_trace or 0)
        self.trace_spin.setEnabled(True)
        self.trace_spin.blockSignals(False)
        self.trace_count_label.setText(f"/ {max(0, self.session.trace_count - 1)}")

        self.export_png_action.setEnabled(True)
        self._update_views()
        self.metadata_panel.set_dataset(self.session.dataset, self.session.source_path)

        name = self.session.source_path.name if self.session.source_path else "?"
        self.setWindowTitle(f"{_BASE_TITLE} — {name}")
        self._refresh_selected_label()

    def _update_views(self) -> None:
        if not self.session.is_loaded:
            return
        dataset = self.session.dataset
        assert dataset is not None
        channel = self.session.selected_channel
        self.bscan_view.set_data(dataset, channel)
        self.bscan_view.set_display_settings(self.display_settings)
        if self.session.selected_trace is not None:
            self.bscan_view.set_selected_trace(self.session.selected_trace)
            self.ascan_view.set_data(dataset, channel, self.session.selected_trace)
            self.ascan_view.set_mode(self.display_settings.ascan_mode)
        else:
            self.bscan_view.set_selected_trace(None)
            self.ascan_view.clear()
        self._refresh_display_summary()

    def _on_channel_changed(self, value: int) -> None:
        if not self.session.is_loaded:
            return
        self.session.selected_channel = self.session.clamp_channel(value)
        self._update_views()
        self._refresh_selected_label()

    def _on_trace_clicked(self, trace: int) -> None:
        if not self.session.is_loaded:
            return
        self._select_trace(trace)

    def _on_trace_spin_changed(self, value: int) -> None:
        if not self.session.is_loaded:
            return
        self._select_trace(value)

    def _select_trace(self, trace: int) -> None:
        dataset = self.session.dataset
        assert dataset is not None
        clamped = self.session.clamp_trace(trace)
        self.session.selected_trace = clamped
        self.bscan_view.set_selected_trace(clamped)
        self.ascan_view.set_data(dataset, self.session.selected_channel, clamped)
        self.ascan_view.set_mode(self.display_settings.ascan_mode)
        self.trace_spin.blockSignals(True)
        self.trace_spin.setValue(clamped)
        self.trace_spin.blockSignals(False)
        self._refresh_selected_label()

    def _on_point_hovered(self, trace: int, time_ns: float, amplitude: float) -> None:
        self.cursor_label.setText(
            f"Cursor — trace {trace}, channel {self.session.selected_channel:02d}, "
            f"time {time_ns:.3f} ns, amplitude {amplitude:.4g}"
        )

    def _refresh_selected_label(self) -> None:
        if not self.session.is_loaded:
            self.selected_label.setText("No file open")
            return
        trace_count = max(0, self.session.trace_count - 1)
        trace_text = str(self.session.selected_trace) if self.session.selected_trace is not None else "—"
        self.selected_label.setText(
            f"Channel {self.session.selected_channel:02d} · Selected trace {trace_text} / {trace_count}"
        )

    # -- display settings ----------------------------------------------------

    def _apply_display_settings(self) -> None:
        """The one place `self.display_settings` is pushed into the views. Never touches the dataset."""
        self.bscan_view.set_display_settings(self.display_settings)
        self.ascan_view.set_mode(self.display_settings.ascan_mode)
        self._refresh_display_summary()

    def _sync_controls_from_settings(self) -> None:
        """Reflect `self.display_settings` in every widget, without re-triggering their handlers."""
        settings = self.display_settings
        widgets = (
            self.colormap_combo,
            self.percentile_spin,
            self.percentile_slider,
            self.symmetric_check,
            self.manual_check,
            self.manual_min_spin,
            self.manual_max_spin,
            self.autoscale_check,
            self.ascan_mode_combo,
        )
        for widget in widgets:
            widget.blockSignals(True)
        try:
            self.colormap_combo.setCurrentIndex(
                [value for _label, value in _COLORMAP_ITEMS].index(settings.colormap)
            )
            self.percentile_spin.setValue(settings.clip_percentile)
            self.percentile_slider.setValue(round(settings.clip_percentile * _PERCENTILE_SLIDER_SCALE))
            self.symmetric_check.setChecked(settings.symmetric_levels)
            self.manual_check.setChecked(settings.manual_levels_enabled)
            self.manual_min_spin.setValue(settings.manual_min if settings.manual_min is not None else 0.0)
            self.manual_max_spin.setValue(settings.manual_max if settings.manual_max is not None else 0.0)
            self.manual_min_spin.setEnabled(settings.manual_levels_enabled)
            self.manual_max_spin.setEnabled(settings.manual_levels_enabled)
            self.autoscale_check.setChecked(settings.visible_region_autoscale)
            self.autoscale_check.setEnabled(not settings.manual_levels_enabled)
            self.ascan_mode_combo.setCurrentIndex(
                [value for _label, value in _ASCAN_MODE_ITEMS].index(settings.ascan_mode)
            )
        finally:
            for widget in widgets:
                widget.blockSignals(False)
        self._set_manual_fields_validity(True)

    def _on_colormap_changed(self, index: int) -> None:
        value = _COLORMAP_ITEMS[index][1]
        self.display_settings = self.display_settings.with_changes(colormap=value)
        self._apply_display_settings()

    def _on_percentile_spin_changed(self, value: float) -> None:
        self.percentile_slider.blockSignals(True)
        self.percentile_slider.setValue(round(value * _PERCENTILE_SLIDER_SCALE))
        self.percentile_slider.blockSignals(False)
        self.display_settings = self.display_settings.with_changes(clip_percentile=value)
        self._apply_display_settings()

    def _on_percentile_slider_changed(self, value: int) -> None:
        percentile = value / _PERCENTILE_SLIDER_SCALE
        self.percentile_spin.blockSignals(True)
        self.percentile_spin.setValue(percentile)
        self.percentile_spin.blockSignals(False)
        self.display_settings = self.display_settings.with_changes(clip_percentile=percentile)
        self._apply_display_settings()

    def _on_symmetric_toggled(self, checked: bool) -> None:
        self.display_settings = self.display_settings.with_changes(symmetric_levels=checked)
        self._apply_display_settings()

    def _on_manual_toggled(self, checked: bool) -> None:
        # Decision (see ADR-013 / Sprint_GUI_2_Display_Controls.md): enabling
        # manual levels disables symmetric mode, rather than trying to
        # reconcile "symmetric AND manual" as a third, ambiguous state.
        # Manual levels and visible-range autoscale are two competing level
        # *sources* -- a manual-test finding was that the UI let both stay
        # checked at once, which is never a coherent state, so enabling one
        # here always turns the other off (and disables its checkbox while
        # this one is active).
        self.manual_min_spin.setEnabled(checked)
        self.manual_max_spin.setEnabled(checked)
        self.autoscale_check.setEnabled(not checked)
        if checked:
            # Seed the manual fields with the current auto-computed levels so
            # the user edits a sensible starting point instead of 0/0.
            low, high = self.bscan_view.compute_full_range_levels()
            self.manual_min_spin.blockSignals(True)
            self.manual_max_spin.blockSignals(True)
            self.manual_min_spin.setValue(low)
            self.manual_max_spin.setValue(high)
            self.manual_min_spin.blockSignals(False)
            self.manual_max_spin.blockSignals(False)
            self.symmetric_check.blockSignals(True)
            self.symmetric_check.setChecked(False)
            self.symmetric_check.blockSignals(False)
            self.autoscale_check.blockSignals(True)
            self.autoscale_check.setChecked(False)
            self.autoscale_check.blockSignals(False)
            self.display_settings = self.display_settings.with_changes(
                manual_levels_enabled=True,
                symmetric_levels=False,
                visible_region_autoscale=False,
                manual_min=self.manual_min_spin.value(),
                manual_max=self.manual_max_spin.value(),
            )
        else:
            self.display_settings = self.display_settings.with_changes(manual_levels_enabled=False)
        self._set_manual_fields_validity(True)
        self._apply_display_settings()

    def _on_manual_levels_changed(self, _value: float) -> None:
        low, high = self.manual_min_spin.value(), self.manual_max_spin.value()
        valid = low < high
        self._set_manual_fields_validity(valid)
        self.display_settings = self.display_settings.with_changes(manual_min=low, manual_max=high)
        self._apply_display_settings()

    def _set_manual_fields_validity(self, valid: bool) -> None:
        # Invalid (min >= max) is shown to the user via style, not applied to
        # the render pipeline -- compute_display_levels() already falls back
        # to the automatic levels for an invalid manual range on its own.
        stylesheet = "" if valid else "background-color: #5a1f1f;"
        self.manual_min_spin.setStyleSheet(stylesheet)
        self.manual_max_spin.setStyleSheet(stylesheet)

    def _on_autoscale_toggled(self, checked: bool) -> None:
        # Mirrors _on_manual_toggled's mutual exclusion: this checkbox is
        # normally disabled while manual levels are active (so a user can't
        # reach this path from the UI), but a defensive guard keeps the
        # invariant true even if toggled programmatically.
        if checked and self.manual_check.isChecked():
            self.manual_check.blockSignals(True)
            self.manual_check.setChecked(False)
            self.manual_check.blockSignals(False)
            self.manual_min_spin.setEnabled(False)
            self.manual_max_spin.setEnabled(False)
            self.display_settings = self.display_settings.with_changes(manual_levels_enabled=False)
        self.display_settings = self.display_settings.with_changes(visible_region_autoscale=checked)
        self._apply_display_settings()

    def _on_ascan_mode_changed(self, index: int) -> None:
        value = _ASCAN_MODE_ITEMS[index][1]
        self.display_settings = self.display_settings.with_changes(ascan_mode=value)
        self._apply_display_settings()

    def _on_auto_levels_clicked(self) -> None:
        self._apply_display_settings()

    def _on_reset_view_clicked(self) -> None:
        self.bscan_view.reset_view()
        self.ascan_view.reset_view()

    def _on_reset_display_clicked(self) -> None:
        self.display_settings = default_display_settings()
        self._sync_controls_from_settings()
        self._apply_display_settings()

    def _refresh_display_summary(self) -> None:
        settings = self.display_settings
        colormap_label = dict((v, k) for k, v in _COLORMAP_ITEMS)[settings.colormap]
        # Exactly one of these four labels -- manual/visible-range-auto take
        # priority over symmetric/asymmetric because they change *which
        # samples* the levels come from, not just the symmetric/asymmetric
        # policy applied to the full range (see ADR-013 addendum: manual and
        # visible-range-auto are mutually exclusive level *sources*).
        if settings.manual_levels_enabled and settings.manual_levels_are_valid():
            mode_text = "manual"
        elif settings.visible_region_autoscale:
            mode_text = "visible-range auto"
        else:
            mode_text = "symmetric" if settings.symmetric_levels else "asymmetric"
        self.display_summary_label.setText(
            f"Display: {colormap_label} | {settings.clip_percentile:.1f}% | {mode_text} | "
            "raw amplitudes unchanged"
        )

    # -- PNG export -----------------------------------------------------------

    def _on_export_png_triggered(self) -> None:
        if not self.session.is_loaded:
            return
        default_name = "bscan.png"
        if self.session.source_path is not None:
            default_name = (
                f"{self.session.source_path.stem}_channel{self.session.selected_channel:02d}_bscan.png"
            )
        path, _selected_filter = QFileDialog.getSaveFileName(
            self, "Export Current B-scan PNG", default_name, _PNG_FILE_FILTER
        )
        if not path:
            return
        dataset = self.session.dataset
        assert dataset is not None
        channel = self.session.selected_channel
        levels = self.bscan_view.compute_full_range_levels()
        source_filename = self.session.source_path.name if self.session.source_path else None
        try:
            png_path = export_bscan_png(
                dataset,
                channel,
                levels,
                self.display_settings.colormap,
                path,
                source_filename=source_filename,
                selected_trace=self.session.selected_trace,
            )
            write_display_sidecar(
                png_path, dataset, channel, self.display_settings, levels, source_filename=source_filename
            )
        except Exception as exc:  # noqa: BLE001 - export failure must reach the user, not crash the app
            _LOGGER.error("Failed to export PNG to %s", path, exc_info=True)
            QMessageBox.critical(
                self, "Export failed", f"Could not export PNG:\n{path}\n\n{type(exc).__name__}: {exc}"
            )
            return
        _LOGGER.info("Exported B-scan PNG: %s", png_path)
