"""Background C-scan compute: a plain ``QObject`` worker run on a ``QThread``.

**Sprint 3D-1.** Reuses the exact worker pattern established by Sprint
GUI-1B (``ADR-014``, :mod:`archaeogpr.gui.workers.file_loader`) and Sprint
GUI-3A (:mod:`archaeogpr.gui.workers.processing_worker`) unchanged:
``QObject`` + ``moveToThread`` (never a ``QThread`` subclass), every signal
connected only to bound methods of ``MainWindow`` (never a lambda),
cooperative-only cancellation via a caller-owned ``threading.Event`` checked
before and after the one opaque ``compute_cscan`` call, and a ``finished``
signal that always fires last, exactly once.

Unlike ``ProcessingWorker``, there is no separate ``base_revision`` signal
parameter — ``CScanResult`` already self-describes the
``source_revision``/``geometry_revision`` it was computed against (see
``archaeogpr.cscan.models.CScanResult``), so ``MainWindow`` can check
staleness directly off the result it receives (via
``CScanSession.is_stale``) without a second parallel value to keep in sync.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, Slot

from archaeogpr.cscan.compute import compute_cscan

if TYPE_CHECKING:
    import numpy as np

    from archaeogpr.cscan.models import CScanRequest
    from archaeogpr.model.dataset import GPRDataset

_LOGGER = logging.getLogger("archaeogpr.gui")

__all__ = ["CScanWorker"]


class CScanWorker(QObject):
    """Runs one :func:`~archaeogpr.cscan.compute.compute_cscan` call off the Qt main thread.

    Usage (see ``MainWindow._start_cscan_compute`` for the full wiring):
    construct with the dataset/valid_mask/request it should run against, a
    caller-owned ``threading.Event``; ``moveToThread(a_new_QThread)``;
    connect ``thread.started`` to :meth:`run`; connect the signals below
    directly to bound methods of a main-thread ``QObject``; then
    ``thread.start()``.
    """

    #: ``(token, message)`` — status text only, harmless if stale.
    progress = Signal(int, str)
    #: ``(token, result)`` — ``result`` is a ``CScanResult``. Only emitted
    #: for a full, uncancelled, successful run.
    result_ready = Signal(int, object)
    #: ``(token, short_message, traceback_text)``.
    failed = Signal(int, str, str)
    #: ``(token,)`` — emitted instead of ``result_ready``/``failed`` whenever
    #: cancellation was requested, regardless of what the run would
    #: otherwise have produced.
    cancelled = Signal(int)
    #: ``(token,)`` — always emitted exactly once, last.
    finished = Signal(int)

    def __init__(
        self,
        dataset: GPRDataset,
        valid_mask: np.ndarray | None,
        request: CScanRequest,
        token: int,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self._dataset = dataset
        self._valid_mask = valid_mask
        self._request = request
        self.token = token
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        """Entry point connected to ``QThread.started``. Runs entirely on the worker thread."""
        started_at = time.monotonic()
        _LOGGER.info("C-scan worker started: aggregation=%s", self._request.aggregation.value)

        if self._cancel_event.is_set():
            _LOGGER.info("Cancellation requested before C-scan compute started")
            self.cancelled.emit(self.token)
            self.finished.emit(self.token)
            return

        self.progress.emit(self.token, "Computing C-scan…")
        try:
            result = compute_cscan(self._dataset, self._request, valid_mask=self._valid_mask)
        except Exception as exc:  # noqa: BLE001 - any compute failure must reach the caller, never crash the worker thread
            elapsed = time.monotonic() - started_at
            if self._cancel_event.is_set():
                _LOGGER.info("Cancellation completed (compute had also failed after %.3fs)", elapsed)
                self.cancelled.emit(self.token)
            else:
                _LOGGER.error("C-scan compute failed after %.3fs: %s", elapsed, exc)
                self.failed.emit(self.token, str(exc), traceback.format_exc())
            self.finished.emit(self.token)
            return

        elapsed = time.monotonic() - started_at
        if self._cancel_event.is_set():
            _LOGGER.info(
                "Cancellation completed (result discarded, shape=%s, %.3fs)", result.values.shape, elapsed
            )
            self.cancelled.emit(self.token)
            self.finished.emit(self.token)
            return

        _LOGGER.info("C-scan compute succeeded: shape=%s in %.3fs", result.values.shape, elapsed)
        self.result_ready.emit(self.token, result)
        self.finished.emit(self.token)
