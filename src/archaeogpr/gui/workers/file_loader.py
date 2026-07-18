"""Background OGPR file loading: a plain ``QObject`` worker run on a ``QThread``.

**Sprint GUI-1B** (see ``ADR-014`` for the full policy this module
implements). Reading a large ``.ogpr`` file on the Qt main thread freezes the
whole GUI for the duration of the read -- this module moves that one call
(:func:`archaeogpr.io.ogpr_reader.read_ogpr`) onto a background ``QThread``
so the window stays responsive (repaint, resize, move) while a file loads.

**Worker isolation**: :class:`FileLoadWorker` never touches a ``QWidget``,
never opens a ``QMessageBox``, and never reaches into ``MainWindow`` state.
It only reads one file and emits typed signals; every UI update happens in
the slots connected to those signals, which Qt always runs on the *receiving*
object's thread (the main thread, since ``MainWindow`` lives there) -- a
cross-thread signal/slot connection is queued automatically, but **only when
connected to a bound method of a QObject** (Qt resolves the receiver's thread
from ``method.__self__``). Connecting a cross-thread signal to a plain
Python callable (e.g. a lambda) has no such receiver to resolve a thread
from, so it silently runs as ``DirectConnection`` *on the emitting (worker)
thread* instead -- this crashed the GUI (Windows access violation touching
pyqtgraph/Qt widgets from off the main thread) during this sprint's own
development; see ``ADR-014``. ``MainWindow`` therefore always connects these
signals directly to its own bound methods, never to a lambda.

Every signal below carries a ``token`` (the ``int`` ``MainWindow`` assigned
this worker at construction) as its first argument -- this is the
stale-result rejection mechanism (see ``ADR-014``): ``QObject.sender()`` is
explicitly documented as unreliable across a queued/cross-thread connection,
so ``MainWindow`` compares this token against its own "current load" token
instead of trying to identify the emitting object after the fact.

**Cancellation is cooperative only, never forced**:

- Cancellation is carried by a plain :class:`threading.Event` (``cancel_event``),
  created and owned by ``MainWindow``, passed into :class:`FileLoadWorker`'s
  constructor. ``MainWindow`` calls ``cancel_event.set()`` **directly** --
  never via a queued signal/slot -- so a cancel request takes effect
  immediately regardless of whether the worker's (nonexistent, in this
  design) event loop has a chance to run; ``threading.Event`` is a
  standard-library thread-safe primitive built exactly for this, unlike a
  plain ``bool`` attribute (whose thread-safety would otherwise rely on
  CPython's GIL as an implementation detail rather than a documented
  guarantee). The worker only ever *reads* it (``is_set()``), before and
  after the one blocking ``read_ogpr()`` call.
- It *cannot* interrupt a read/parse already in progress, because
  ``read_ogpr()`` is a single opaque call with no internal cancellation
  point (see ``ADR-014`` for why this isn't solved by chunking the read in
  this sprint).
- Concretely: **a cancel request may not stop disk parsing immediately.**
- What it does guarantee: **a cancelled result is never committed to the GUI
  session.** If the event is set before ``read_ogpr()`` starts, the read is
  skipped entirely; if it's set while the read is in flight, the worker
  still emits ``cancelled`` (not ``loaded``, and not ``failed`` even if the
  read raised) once the read returns, whatever its outcome -- the dataset
  (or exception) is discarded, never touching ``DatasetSession``.
- ``QThread.terminate()`` is never used anywhere in this module or its
  caller (``main_window.py``) -- forcibly killing a thread mid-read could
  leave interpreter/C-extension state corrupted; see ``ADR-014``.
"""

from __future__ import annotations

import enum
import logging
import threading
import time
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from archaeogpr.io.ogpr_reader import read_ogpr

_LOGGER = logging.getLogger("archaeogpr.gui")


class FileLoadState(enum.Enum):
    """The GUI's file-load state machine (see ``main_window.py`` / ``ADR-014``).

    ``SUCCESS``/``ERROR``/``CANCELLED`` are momentary: ``MainWindow`` performs
    the associated action (commit dataset / show error / discard) and settles
    back to ``IDLE`` within the same slot call -- they exist as named states
    (rather than scattered booleans) so every transition and its UI
    consequence is explicit and testable, not because the GUI lingers in them.
    """

    IDLE = "idle"
    LOADING = "loading"
    CANCELLING = "cancelling"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class FileLoadWorker(QObject):
    """Reads one ``.ogpr`` file off the Qt main thread. Touches no ``QWidget``.

    Usage (see ``MainWindow.open_path`` for the full wiring): construct with
    a caller-assigned ``token`` and a caller-owned ``threading.Event``,
    ``moveToThread(a_new_QThread)``, connect ``thread.started`` to
    :meth:`run`, connect the signals below directly to bound methods of a
    main-thread ``QObject`` (never a lambda -- see the module docstring),
    then ``thread.start()``.
    """

    #: ``(token, percent, message)`` -- ``percent`` is always ``-1`` today (no
    #: real byte-level progress is available from a single opaque
    #: ``read_ogpr()`` call; see ``ADR-014``). Kept typed as ``int`` so a
    #: future incremental reader can report real percentages without
    #: changing this signal's shape.
    progress = Signal(int, int, str)
    #: ``(token, dataset, resolved_source_path)`` -- only emitted for a full,
    #: uncancelled, successful read.
    loaded = Signal(int, object, str)
    #: ``(token, short_message, traceback_text, resolved_source_path)``.
    failed = Signal(int, str, str, str)
    #: ``(token,)`` -- emitted instead of ``loaded``/``failed`` whenever
    #: cancellation was requested, regardless of whether the read itself
    #: would otherwise have succeeded or failed.
    cancelled = Signal(int)
    #: ``(token,)`` -- always emitted exactly once, last, after exactly one
    #: of ``loaded``/``failed``/``cancelled``; the caller uses this (not the
    #: outcome signals) to know the worker is done and safe to tear down.
    finished = Signal(int)

    def __init__(self, path: str | Path, token: int, cancel_event: threading.Event) -> None:
        super().__init__()
        self._path = Path(path)
        self.token = token
        self._cancel_event = cancel_event

    @Slot()
    def run(self) -> None:
        """Entry point connected to ``QThread.started``. Runs entirely on the worker thread."""
        resolved = self._path.resolve()
        started_at = time.monotonic()
        _LOGGER.info("Worker started for %s", resolved)

        if self._cancel_event.is_set():
            _LOGGER.info("Cancellation requested before read started for %s", resolved)
            self.cancelled.emit(self.token)
            self.finished.emit(self.token)
            return

        self.progress.emit(self.token, -1, "Reading OGPR…")
        try:
            dataset = read_ogpr(resolved)
        except Exception as exc:  # noqa: BLE001 - any reader failure must reach the caller, never crash the worker thread
            elapsed = time.monotonic() - started_at
            if self._cancel_event.is_set():
                _LOGGER.info(
                    "Cancellation completed (read had also failed after %.3fs) for %s", elapsed, resolved
                )
                self.cancelled.emit(self.token)
            else:
                _LOGGER.error("Load failed for %s after %.3fs: %s", resolved, elapsed, exc)
                self.failed.emit(self.token, str(exc), traceback.format_exc(), str(resolved))
            self.finished.emit(self.token)
            return

        elapsed = time.monotonic() - started_at
        if self._cancel_event.is_set():
            _LOGGER.info(
                "Cancellation completed (result discarded, shape=%s, %.3fs) for %s",
                dataset.shape,
                elapsed,
                resolved,
            )
            self.cancelled.emit(self.token)
            self.finished.emit(self.token)
            return

        _LOGGER.info("Load succeeded for %s: shape=%s in %.3fs", resolved, dataset.shape, elapsed)
        self.loaded.emit(self.token, dataset, str(resolved))
        self.finished.emit(self.token)
