"""Background processing preview: a plain ``QObject`` worker run on a ``QThread``.

**Sprint GUI-3A** (see ``ADR-015`` for the full policy this module
implements). Computing a preview for one of the five stable
``archaeogpr.processing`` operations (via
:mod:`archaeogpr.gui.processing.adapters`) can take long enough on a large
dataset to freeze the GUI if run on the main thread -- this module reuses
Sprint GUI-1B's worker pattern (``ADR-014``,
:mod:`archaeogpr.gui.workers.file_loader`) almost unchanged: ``QObject`` +
``moveToThread`` (never a ``QThread`` subclass), every signal connected only
to bound methods of ``MainWindow`` (never a lambda -- a lambda/monkeypatched
wrapper gives Qt no ``QObject`` to resolve a receiver thread from, so a
cross-thread connection silently runs on the *worker* thread instead of
being queued to the main thread; this caused a real crash while building
GUI-1B, see ``ADR-014``), cooperative-only cancellation via a caller-owned
``threading.Event`` checked before and after the one (opaque,
uninterruptible) processing call, and a ``finished`` signal that always
fires last, exactly once, regardless of which terminal outcome preceded it.

**Two differences from ``FileLoadWorker`` (see ``ADR-015``):**

1. Every terminal signal also carries ``base_revision`` -- the
   ``DatasetSession.current_revision`` the input dataset was captured at
   when this worker was constructed. A token alone (GUI-1B's stale-result
   guard) only detects "a *newer* request superseded this one"; it cannot
   detect "the committed dataset itself changed underneath this preview"
   (e.g. the user applied a *different* operation, or reset to raw, while
   this one was still computing) -- ``base_revision`` is what lets
   ``MainWindow`` reject that case too, by comparing it against
   ``DatasetSession.current_revision`` at the moment the signal is handled.
2. A successful run produces a **preview**, never a commit -- the success
   signal is ``preview_ready``, not ``loaded``; nothing in this module ever
   touches ``DatasetSession.current_dataset``. Only ``MainWindow``'s Apply
   Preview action (via ``DatasetSession.apply_preview()``) ever does that,
   and only for a still-fresh preview (see
   ``DatasetSession.has_fresh_preview``).

**Cancellation is cooperative only, never forced** -- identical guarantee
to ``ADR-014``: a cancel request may not interrupt a processing call already
in flight (none of the five processing functions accept a cancellation
callback), but a cancelled result is *never* turned into a preview.
``QThread.terminate()`` is never used anywhere in this module or its caller.
"""

from __future__ import annotations

import enum
import logging
import threading
import time
import traceback
from typing import TYPE_CHECKING, Any

import numpy as np
from PySide6.QtCore import QObject, Signal, Slot

if TYPE_CHECKING:
    from archaeogpr.gui.processing.models import ProcessingOperationSpec
    from archaeogpr.model.dataset import GPRDataset

_LOGGER = logging.getLogger("archaeogpr.gui")


class ProcessingState(enum.Enum):
    """The GUI's processing-preview state machine (see ``main_window.py`` / ``ADR-015``).

    Mirrors :class:`~archaeogpr.gui.workers.file_loader.FileLoadState`'s
    shape exactly (a separate, parallel state machine -- see ADR-015 for why
    two mirrored enums were chosen over one merged ``BusyState``):
    ``SUCCESS``/``ERROR``/``CANCELLED`` are momentary -- ``MainWindow``
    performs the associated action (record the preview / show an error /
    discard) and settles back to ``IDLE`` within the same slot call. The
    Processing panel's persistent "No preview / Computing / Ready / Failed"
    label is driven separately, by ``DatasetSession.has_fresh_preview`` and
    ``MainWindow._last_preview_outcome`` -- not by this enum directly (a
    fresh, applied-but-not-yet preview must keep reading "Ready" long after
    this enum has already settled back to ``IDLE``).
    """

    IDLE = "idle"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class ProcessingWorker(QObject):
    """Runs one registered processing operation off the Qt main thread. Touches no ``QWidget``.

    Usage (see ``MainWindow._start_processing_preview`` for the full
    wiring): construct with the operation spec, the dataset/valid_mask it
    should run against, the GUI parameter values, a caller-assigned
    ``token``, the ``base_revision`` those inputs were captured at, and a
    caller-owned ``threading.Event``; ``moveToThread(a_new_QThread)``;
    connect ``thread.started`` to :meth:`run`; connect the signals below
    directly to bound methods of a main-thread ``QObject`` (never a lambda);
    then ``thread.start()``.
    """

    #: ``(token, message)`` -- status text only; harmless if stale (a
    #: superseded/cancelled worker's progress text is never decision-bearing,
    #: unlike the terminal signals below, so it carries no ``base_revision``).
    progress = Signal(int, str)
    #: ``(token, base_revision, result)`` -- ``result`` is a
    #: ``ProcessingResult``. Only emitted for a full, uncancelled, successful
    #: run; ``MainWindow`` still must check both ``token`` (superseded by a
    #: newer request) and ``base_revision`` (committed dataset changed while
    #: this ran) before turning it into a preview.
    preview_ready = Signal(int, int, object)
    #: ``(token, base_revision, short_message, traceback_text)``.
    failed = Signal(int, int, str, str)
    #: ``(token, base_revision)`` -- emitted instead of
    #: ``preview_ready``/``failed`` whenever cancellation was requested,
    #: regardless of whether the run itself would otherwise have succeeded
    #: or failed.
    cancelled = Signal(int, int)
    #: ``(token,)`` -- always emitted exactly once, last, after exactly one
    #: of ``preview_ready``/``failed``/``cancelled``; the caller uses this
    #: (not the outcome signals) to know the worker is done and safe to tear
    #: down.
    finished = Signal(int)

    def __init__(
        self,
        spec: ProcessingOperationSpec,
        dataset: GPRDataset,
        valid_mask: np.ndarray | None,
        params: dict[str, Any],
        token: int,
        base_revision: int,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self._spec = spec
        self._dataset = dataset
        self._valid_mask = valid_mask
        self._params = params
        self.token = token
        self.base_revision = base_revision
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        """Entry point connected to ``QThread.started``. Runs entirely on the worker thread."""
        operation_id = self._spec.operation_id
        started_at = time.monotonic()
        _LOGGER.info("Processing worker started: %s", operation_id)

        if self._cancel_event.is_set():
            _LOGGER.info("Cancellation requested before processing started: %s", operation_id)
            self.cancelled.emit(self.token, self.base_revision)
            self.finished.emit(self.token)
            return

        self.progress.emit(self.token, f"Running {self._spec.display_name}…")
        try:
            result = self._spec.apply(self._dataset, self._params, self._valid_mask)
        except Exception as exc:  # noqa: BLE001 - any adapter/processing failure must reach the caller, never crash the worker thread
            elapsed = time.monotonic() - started_at
            if self._cancel_event.is_set():
                _LOGGER.info(
                    "Cancellation completed (processing had also failed after %.3fs): %s",
                    elapsed,
                    operation_id,
                )
                self.cancelled.emit(self.token, self.base_revision)
            else:
                _LOGGER.error("Processing failed for %s after %.3fs: %s", operation_id, elapsed, exc)
                self.failed.emit(self.token, self.base_revision, str(exc), traceback.format_exc())
            self.finished.emit(self.token)
            return

        elapsed = time.monotonic() - started_at
        if self._cancel_event.is_set():
            _LOGGER.info(
                "Cancellation completed (preview discarded, shape=%s, %.3fs): %s",
                result.dataset.shape,
                elapsed,
                operation_id,
            )
            self.cancelled.emit(self.token, self.base_revision)
            self.finished.emit(self.token)
            return

        _LOGGER.info(
            "Processing succeeded for %s: shape=%s in %.3fs", operation_id, result.dataset.shape, elapsed
        )
        self.preview_ready.emit(self.token, self.base_revision, result)
        self.finished.emit(self.token)
