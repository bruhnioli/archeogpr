"""Versioned window/dock-layout persistence, kept separate from all other settings.

Sprint 3D-1 dock-layout fix: prior to this, ``MainWindow`` never called
``saveState``/``restoreState``/``QSettings`` anywhere -- every launch built
the same hardcoded dock arrangement in ``_build_docks()`` from scratch, and
that hardcoded arrangement itself was broken (see ADR-018). This module adds
the persistence layer: a dedicated INI file under the same
``%LOCALAPPDATA%\\ArchaeoGPR\\`` root ``logging_setup.log_directory()``
already uses, storing only window geometry/dock state -- never processing
parameters, dataset session state, or anything else. Kept in its own file
(not a shared "app settings" file, and not the Windows registry) so it can be
reset/deleted in isolation without touching anything else, and so a corrupt
or schema-mismatched file can never affect unrelated state.

**Settings isolation (ADR-018 Addendum)**: automated tests, ``--smoke-test``
runs, and the build script's frozen-executable verification must never read,
write, create, or clear the real user file. Three explicit override
mechanisms exist, in precedence order:

1. ``path_override=`` -- a direct, absolute path (used by tests injecting a
   per-test temp file).
2. ``ephemeral=True`` -- a unique per-process temp-directory path that is
   never the user file (used by ``--smoke-test``; combined with
   ``MainWindow(persist_window_state=False)`` nothing is ever written, so
   the file is typically never even created).
3. The :data:`WINDOW_STATE_PATH_ENV_VAR` environment variable -- an explicit
   external override (used by ``scripts/build_windows.ps1`` for subprocess
   smoke tests). A relative or empty value is rejected (logged and ignored,
   falling through to the default) rather than being resolved against an
   accidental working directory.

With none of these present, production behavior is unchanged:
``%LOCALAPPDATA%\\ArchaeoGPR\\window_state.ini``, restore and save enabled.

``WINDOW_STATE_SCHEMA_VERSION`` must be incremented whenever the set of
dock ``objectName``s changes (a dock added/removed/renamed) -- ``QMainWindow.
restoreState()`` is told this version explicitly and refuses to restore
state saved under a different one, exactly the built-in Qt mechanism this
schema constant plugs into (see ``QMainWindow.saveState(version)``/
``restoreState(state, version)``).
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings

_LOGGER = logging.getLogger("archaeogpr.gui")

WINDOW_STATE_SCHEMA_VERSION = 1
"""Bump this when the dock set changes (added/removed/renamed dock objectName)."""

WINDOW_STATE_PATH_ENV_VAR = "ARCHAEOGPR_WINDOW_STATE_PATH"
"""Explicit external override for the window-state INI path (absolute paths only).

Set by ``scripts/build_windows.ps1`` for subprocess smoke tests and by the
GUI test suite's autouse isolation fixture (``tests/conftest.py``, which
hardcodes this name with a cross-reference comment, since importing this
Qt-dependent module from ``conftest.py`` would break headless collection).
"""

_SCHEMA_KEY = "layout/schemaVersion"
_GEOMETRY_KEY = "layout/geometry"
_DOCK_STATE_KEY = "layout/dockState"

__all__ = [
    "WINDOW_STATE_SCHEMA_VERSION",
    "WINDOW_STATE_PATH_ENV_VAR",
    "settings_directory",
    "default_window_state_path",
    "open_window_settings",
]


def settings_directory() -> Path:
    """``%LOCALAPPDATA%\\ArchaeoGPR`` (falls back to a temp dir if unset).

    Same root ``archaeogpr.gui.logging_setup.log_directory()`` uses (that
    function appends ``logs``; this one is the parent, since window state is
    a sibling concern, not a log).
    """
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path(tempfile.gettempdir())
    return root / "ArchaeoGPR"


def default_window_state_path() -> Path:
    """The production window-state file path, after applying the env override (if valid).

    A :data:`WINDOW_STATE_PATH_ENV_VAR` value that is empty or not absolute
    is rejected safely: logged and ignored (never resolved relative to the
    process working directory), falling through to the real
    ``%LOCALAPPDATA%`` default.
    """
    override = os.environ.get(WINDOW_STATE_PATH_ENV_VAR)
    if override is not None:
        candidate = Path(override)
        if override.strip() and candidate.is_absolute():
            return candidate
        _LOGGER.warning(
            "%s is set but not an absolute path (%r) -- ignoring the override",
            WINDOW_STATE_PATH_ENV_VAR,
            override,
        )
    return settings_directory() / "window_state.ini"


def open_window_settings(
    *,
    path_override: Path | None = None,
    ephemeral: bool = False,
) -> QSettings:
    """A dedicated ``QSettings`` for window/dock layout state only (INI-backed, not the registry).

    ``path_override`` (highest precedence) points the settings at an exact,
    absolute file path -- the dependency-injection seam tests use. A relative
    override raises ``ValueError`` (a caller bug, never silently resolved
    against the working directory).

    ``ephemeral=True`` uses a unique per-process file under the system temp
    directory -- guaranteed distinct from the user's real file. ``QSettings``
    only creates the file on first write, so an ephemeral, never-persisted
    session (``--smoke-test``) typically leaves nothing on disk at all.

    With neither, :func:`default_window_state_path` applies (env override or
    the real ``%LOCALAPPDATA%`` file). Best-effort parent-directory creation
    -- if it fails (e.g. read-only install location), ``QSettings`` itself
    silently no-ops writes/reads rather than raising, which is an acceptable
    degradation for cosmetic window placement (never for the dataset/
    processing state this module never touches).
    """
    if path_override is not None and ephemeral:
        raise ValueError("path_override and ephemeral are mutually exclusive")
    if path_override is not None:
        if not path_override.is_absolute():
            raise ValueError(f"path_override must be an absolute path, got {path_override!r}")
        target = path_override
    elif ephemeral:
        target = Path(tempfile.gettempdir()) / f"archaeogpr-window-state-ephemeral-{os.getpid()}.ini"
    else:
        target = default_window_state_path()

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return QSettings(str(target), QSettings.Format.IniFormat)
