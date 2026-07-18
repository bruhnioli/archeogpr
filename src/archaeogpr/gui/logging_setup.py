"""File logging for the no-console frozen executable.

A windowed (``--windowed``/no-console) PyInstaller build has no visible
stdout/stderr, so uncaught exceptions must be written somewhere the user (or
the person supporting them) can actually find -- ``%LOCALAPPDATA%\\ArchaeoGPR\\
logs\\archaeogpr.log``. Never logs raw amplitude/radar-volume data, only
paths, metadata summaries, and error text. A failure to set up logging must
never prevent the application from starting.
"""

from __future__ import annotations

import logging
import platform
import sys
from pathlib import Path

_LOGGER_NAME = "archaeogpr.gui"


def log_directory() -> Path:
    """``%LOCALAPPDATA%\\ArchaeoGPR\\logs`` (falls back to a temp dir if unset)."""
    import os
    import tempfile

    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path(tempfile.gettempdir())
    return root / "ArchaeoGPR" / "logs"


def setup_logging() -> logging.Logger:
    """Configure and return the ``archaeogpr.gui`` logger.

    Best-effort: if the log file/directory cannot be created (e.g. a
    read-only install location), falls back to a stderr handler (or, if even
    that fails, a no-op ``NullHandler``) rather than raising -- logging setup
    must never be the reason the application fails to start.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger  # already configured (e.g. re-entered from a test)
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    handler: logging.Handler
    try:
        directory = log_directory()
        directory.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(directory / "archaeogpr.log", encoding="utf-8")
    except OSError:
        try:
            handler = logging.StreamHandler(sys.stderr)
        except Exception:  # noqa: BLE001 - logging setup must never crash startup
            handler = logging.NullHandler()

    handler.setFormatter(formatter)
    logger.addHandler(handler)

    from archaeogpr import __version__ as archaeogpr_version

    logger.info("=== ArchaeoGPR session start ===")
    logger.info("archaeogpr version: %s", archaeogpr_version)
    logger.info("frozen: %s", getattr(sys, "frozen", False))
    logger.info("platform: %s", platform.platform())
    logger.info("python: %s (%s)", platform.python_version(), sys.executable)
    return logger


def install_excepthook(logger: logging.Logger) -> None:
    """Route uncaught exceptions to the log instead of losing them silently."""

    def _handle(exc_type: type[BaseException], exc_value: BaseException, exc_tb) -> None:  # type: ignore[no-untyped-def]
        logger.error("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _handle
