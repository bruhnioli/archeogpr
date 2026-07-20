"""GUI-side session state for one computed C-scan (Sprint 3D-1).

``CScanSession`` is deliberately independent of ``DatasetSession`` and
``GeometrySession`` — same design as ``GeometrySession`` itself (see its
module docstring): it holds no reference to either, only a snapshot of the
revisions a past compute used, and lets the caller (``MainWindow``) compare
those against the *live* revisions to decide staleness. This mirrors how
``ProcessingWorker``'s ``base_revision`` is compared against
``DatasetSession.current_revision`` by ``MainWindow``, not by the session
object itself.

Token-based supersede detection (matching ``FileLoadWorker``/
``ProcessingWorker``) is owned by ``MainWindow`` (a plain ``int`` counter),
not by this class — ``CScanRequest.token`` is carried through for that
purpose but never compared here.

**Design choice on failure/cancel**: ``result``/``request`` are only ever
written by :meth:`complete` and :meth:`clear` — a failed or cancelled
compute (:meth:`fail`/:meth:`cancel`) leaves the last successful result in
place, only updating ``state``/``error``. A blank display on every transient
failure would be less informative than the last valid result labeled
stale/failed; the GUI is responsible for showing that label prominently
(see ``archaeogpr.gui.views.cscan_view``).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from archaeogpr.cscan.models import CScanRequest, CScanResult

__all__ = ["CScanState", "CScanSession"]


class CScanState(enum.Enum):
    """Mirrors ``FileLoadState``/``ProcessingState`` — a deliberately separate,
    parallel enum rather than one shared three-way ``BusyState``.
    """

    IDLE = "idle"
    COMPUTING = "computing"
    CANCELLING = "cancelling"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class CScanSession:
    """Mutable state for the currently-displayed C-scan, if any."""

    result: CScanResult | None = None
    request: CScanRequest | None = None
    state: CScanState = CScanState.IDLE
    error: str | None = None

    @property
    def has_result(self) -> bool:
        return self.result is not None

    def start_compute(self) -> None:
        self.state = CScanState.COMPUTING
        self.error = None

    def begin_cancelling(self) -> None:
        self.state = CScanState.CANCELLING

    def complete(self, request: CScanRequest, result: CScanResult) -> None:
        self.request = request
        self.result = result
        self.state = CScanState.SUCCESS
        self.error = None

    def fail(self, error: str) -> None:
        self.state = CScanState.ERROR
        self.error = error

    def cancel(self) -> None:
        self.state = CScanState.CANCELLED

    def clear(self) -> None:
        """Full reset — used only on a new successful file load (see Sprint 3D-1 spec
        section 21: a successful file load always clears the old C-scan result,
        regardless of what source it was computed from).
        """
        self.result = None
        self.request = None
        self.state = CScanState.IDLE
        self.error = None

    def is_stale(self, *, current_source_revision: int, current_geometry_revision: int) -> bool:
        """``True`` if ``result`` was computed against a source/geometry revision
        that is no longer current — e.g. Processing Apply advanced
        ``DatasetSession.current_revision``, or a Geometry override was applied.
        ``False`` (never stale) if there is no result yet.
        """
        if self.request is None:
            return False
        return (
            self.request.source_revision != current_source_revision
            or self.request.geometry_revision != current_geometry_revision
        )
