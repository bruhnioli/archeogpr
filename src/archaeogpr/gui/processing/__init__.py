"""GUI-side processing registry/adapters (Sprint GUI-3A, see ADR-015).

Every module here is GUI-package-only -- ``src/archaeogpr/processing/*.py``
itself is never imported by anything outside this ``gui`` package's own
adapter layer, and nothing here imports Qt, so it stays importable and
testable in a headless (no PySide6) environment exactly like the rest of
``archaeogpr.processing``.
"""

from __future__ import annotations
