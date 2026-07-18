"""Background (off-GUI-thread) workers.

See :mod:`archaeogpr.gui.workers.file_loader` and ``ADR-014`` for the one
worker this package currently defines and the cancellation/shutdown policy
that governs it.
"""

from __future__ import annotations
