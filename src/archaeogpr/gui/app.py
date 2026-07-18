"""GUI entry point: ``python -m archaeogpr.gui`` / the frozen ``ArchaeoGPR.exe``.

``main()`` is the one place a ``QApplication`` is constructed (guarded by
``QApplication.instance()``, so calling it more than once in the same
process -- e.g. from multiple GUI tests -- never creates a second one).
Nothing here depends on the process's current working directory: the log
path is derived from ``%LOCALAPPDATA%`` (see ``logging_setup.py``) and
``--open`` paths are resolved to absolute paths by
``DatasetSession.load()``. Works identically under a normal interpreter and
a PyInstaller-frozen build (neither branch below is frozen-specific).
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

_LOGGER_NAME = "archaeogpr.gui"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="archaeogpr.gui", description="ArchaeoGPR native desktop viewer")
    parser.add_argument(
        "--open", metavar="PATH", default=None, help="Open an OpenGPR (.ogpr) file on startup"
    )
    parser.add_argument("--version", action="store_true", help="Print the archaeogpr version and exit")
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Create the main window, process a few events, close it, exit 0 (no blocking event loop)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and run the GUI. Returns a process exit code."""
    args = _build_arg_parser().parse_args(list(argv) if argv is not None else sys.argv[1:])

    if args.version:
        from archaeogpr import __version__

        print(f"archaeogpr {__version__}")
        return 0

    from archaeogpr.gui.logging_setup import install_excepthook, setup_logging

    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        logger = setup_logging()
        install_excepthook(logger)

    import pyqtgraph as pg
    from PySide6.QtWidgets import QApplication

    # Must be set before any PlotWidget/ImageItem is constructed -- see
    # views/bscan_view.py's module docstring for why row-major matters here.
    pg.setConfigOptions(imageAxisOrder="row-major")

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])

    from archaeogpr.gui.main_window import MainWindow

    window = MainWindow()

    if args.open:
        window.open_path(args.open)

    window.show()

    if args.smoke_test:
        for _ in range(5):
            app.processEvents()
        window.close()
        logger.info("smoke test passed")
        return 0

    exit_code = app.exec()
    logger.info("Session end, exit code %s", exit_code)
    return exit_code
