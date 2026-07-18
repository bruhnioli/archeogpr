"""``python -m archaeogpr.gui`` entry point. Thin: all logic lives in app.py."""

from __future__ import annotations

import sys

from archaeogpr.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
