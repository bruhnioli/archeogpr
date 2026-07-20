"""Window-state settings-isolation tests (ADR-018 Addendum, dock-fix Iso turn).

Run with ``QT_QPA_PLATFORM=offscreen``. Every test here is marked
``@pytest.mark.gui``, collected separately from the core suite.

These tests exist because Sprint 3D-1's manual acceptance review flagged a
release-blocking risk: automated verification (pytest, ``--smoke-test``, the
build script) must never read, write, create, or clear the developer's real
``%LOCALAPPDATA%\\ArchaeoGPR\\window_state.ini``. ``tests/conftest.py``'s
autouse ``_isolate_gui_window_state`` fixture already redirects every
``@pytest.mark.gui`` test's ``ARCHAEOGPR_WINDOW_STATE_PATH`` to a per-test
file -- this file tests the underlying dependency-injection seam
(``open_window_settings``'s ``path_override``/``ephemeral`` parameters,
``MainWindow``'s ``persist_window_state``/``window_settings_factory``
parameters) directly, including cases the autouse fixture's blanket
redirection does not itself exercise (production-path resolution,
ephemeral-mode file location, cross-instance isolation).

A "fake real" LOCALAPPDATA directory (``fake_real_localappdata`` fixture,
always a ``tmp_path`` subdirectory -- never the developer's actual
``%LOCALAPPDATA%``) stands in for "the real settings file" in every test
that needs to prove something is never touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import pyqtgraph as pg
from PySide6.QtCore import QSettings, QThread

from archaeogpr.gui.main_window import MainWindow
from archaeogpr.gui.window_state import (
    WINDOW_STATE_PATH_ENV_VAR,
    WINDOW_STATE_SCHEMA_VERSION,
    default_window_state_path,
    open_window_settings,
)

pytestmark = pytest.mark.gui

pg.setConfigOptions(imageAxisOrder="row-major")


@pytest.fixture
def fake_real_localappdata(monkeypatch, tmp_path):
    """A tmp_path subdirectory standing in for "the real %LOCALAPPDATA%" -- never the real one.

    Also clears ``ARCHAEOGPR_WINDOW_STATE_PATH`` (the autouse conftest fixture normally sets
    it) so tests in this file can observe genuine production-path resolution against this
    fake root.
    """
    fake_root = tmp_path / "fake_localappdata"
    fake_root.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(fake_root))
    monkeypatch.delenv(WINDOW_STATE_PATH_ENV_VAR, raising=False)
    return fake_root


# ============================================================
# 1-3: settings-factory path resolution
# ============================================================


def test_production_factory_resolves_to_local_app_data(fake_real_localappdata):
    """1: with no override, the production factory resolves under the real LOCALAPPDATA root."""
    path = default_window_state_path()
    assert path == fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"
    settings = open_window_settings()
    assert Path(settings.fileName()) == path


def test_path_override_is_used_exactly(tmp_path, fake_real_localappdata):
    """2: an explicit path_override is used verbatim, never redirected to LOCALAPPDATA."""
    override = tmp_path / "explicit" / "custom_state.ini"
    settings = open_window_settings(path_override=override)
    assert Path(settings.fileName()) == override
    assert not (fake_real_localappdata / "ArchaeoGPR").exists()


def test_ephemeral_mode_never_opens_real_local_app_data(fake_real_localappdata):
    """3: ephemeral=True never resolves anywhere under the real LOCALAPPDATA root."""
    settings = open_window_settings(ephemeral=True)
    ephemeral_path = Path(settings.fileName())
    assert fake_real_localappdata not in ephemeral_path.parents
    assert ephemeral_path != default_window_state_path()


def test_env_override_is_honored_when_absolute(tmp_path, fake_real_localappdata, monkeypatch):
    """14: the ARCHAEOGPR_WINDOW_STATE_PATH env override (as build_windows.ps1 sets for its
    subprocess smoke test) is honored when absolute, and never falls back to LOCALAPPDATA.
    """
    override = tmp_path / "env_override" / "state.ini"
    monkeypatch.setenv(WINDOW_STATE_PATH_ENV_VAR, str(override))
    assert default_window_state_path() == override


def test_env_override_rejected_when_relative(fake_real_localappdata, monkeypatch):
    """A relative env override is rejected safely -- falls back to the real default, never
    resolved against the process's current working directory.
    """
    monkeypatch.setenv(WINDOW_STATE_PATH_ENV_VAR, "relative/state.ini")
    assert default_window_state_path() == fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"


def test_env_override_rejected_when_empty(fake_real_localappdata, monkeypatch):
    monkeypatch.setenv(WINDOW_STATE_PATH_ENV_VAR, "")
    assert default_window_state_path() == fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"


# ============================================================
# 4-5, 15-17: smoke-test mode (persist_window_state=False)
# ============================================================


def test_smoke_mode_restore_never_reads_real_state(qtbot, tmp_path, fake_real_localappdata):
    """4: persist_window_state=False makes _restore_window_state() a pure no-op -- it never
    opens any settings backend, so even a valid, current-schema file at the real path is
    never restored.
    """
    real_path = fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"
    real_path.parent.mkdir(parents=True, exist_ok=True)
    real_settings = QSettings(str(real_path), QSettings.Format.IniFormat)
    real_settings.setValue("layout/schemaVersion", WINDOW_STATE_SCHEMA_VERSION)
    real_settings.setValue("layout/geometry", b"not-empty")
    real_settings.setValue("layout/dockState", b"not-empty")
    real_settings.setValue("layout/windowWidth", 1280)
    real_settings.setValue("layout/windowHeight", 800)
    real_settings.sync()
    before = real_path.read_bytes()

    window = MainWindow(persist_window_state=False)
    qtbot.addWidget(window)
    assert window._restore_window_state() is False
    assert real_path.read_bytes() == before


def test_smoke_mode_clean_close_never_writes_real_state(qtbot, tmp_path, fake_real_localappdata):
    """5: persist_window_state=False makes a clean close's _save_window_state() a no-op --
    the real settings file is neither created nor modified.
    """
    real_path = fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"
    window = MainWindow(persist_window_state=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    window.close()

    assert not real_path.exists()


def test_smoke_mode_never_creates_file_when_absent(qtbot, tmp_path, fake_real_localappdata):
    """15: if the real state file does not exist before a smoke run, it does not exist after."""
    real_path = fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"
    assert not real_path.exists()

    window = MainWindow(persist_window_state=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.close()

    assert not real_path.exists()


def test_smoke_mode_preserves_existing_real_state_byte_for_byte(qtbot, tmp_path, fake_real_localappdata):
    """16: if the real state file exists before a smoke run, its hash/size/mtime are unchanged
    after (verified here as an exact byte comparison, which subsumes hash/size; mtime is
    additionally checked since a no-op must not even touch the file's metadata).
    """
    real_path = fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"
    real_path.parent.mkdir(parents=True, exist_ok=True)
    real_path.write_bytes(b"pre-existing real settings content")
    before_bytes = real_path.read_bytes()
    before_mtime = real_path.stat().st_mtime

    window = MainWindow(persist_window_state=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window.close()

    assert real_path.read_bytes() == before_bytes
    assert real_path.stat().st_mtime == before_mtime


def test_deferred_close_in_ephemeral_mode_never_writes_state(qtbot, tmp_path, fake_real_localappdata):
    """17: a deferred close (background task in flight) under persist_window_state=False
    writes nothing, at either the deferred moment or once the task later "finishes".
    """
    real_path = fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"
    window = MainWindow(persist_window_state=False)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    window._cscan_thread = QThread(window)  # constructed, never started -- see test_gui_dock_layout.py

    window.close()
    assert window._close_pending is True
    assert not real_path.exists()

    window._cscan_thread = None
    window.close()
    assert not real_path.exists()


# ============================================================
# 6-8: end-to-end app.py / pytest construction never touch real state
# ============================================================


def test_app_smoke_test_never_touches_real_state(tmp_path, fake_real_localappdata, monkeypatch):
    """6/7/8: archaeogpr.gui.app.main(["--smoke-test"]) -- the exact code path
    `--smoke-test` and `--open ... --smoke-test` both go through -- never touches the real
    settings file, and merely constructing/closing a MainWindow during a GUI pytest run
    (this test itself, and by extension every other GUI test) does not either.
    """
    from archaeogpr.gui import app as app_module

    real_path = fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"
    exit_code = app_module.main(["--smoke-test"])
    assert exit_code == 0
    assert not real_path.exists()


def test_app_open_and_smoke_test_never_touches_real_state(
    tmp_path, fake_real_localappdata, ogpr_builder, monkeypatch
):
    """6: `--open <file> --smoke-test` -- the real-file-loading smoke path -- also never
    touches the real settings file.
    """
    from archaeogpr.gui import app as app_module

    ogpr_path = tmp_path / "synthetic.ogpr"
    ogpr_path.write_bytes(ogpr_builder())
    real_path = fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"

    exit_code = app_module.main(["--open", str(ogpr_path), "--smoke-test"])

    assert exit_code == 0
    assert not real_path.exists()


# ============================================================
# 9-10: Reset Window Layout backend scoping
# ============================================================


def test_reset_layout_clears_only_the_active_backend(qtbot, tmp_path, fake_real_localappdata):
    """9: Reset Window Layout clears only the settings backend this window would itself save
    to (the injected one) -- a separate "real" settings store is left completely untouched.
    """
    real_path = fake_real_localappdata / "ArchaeoGPR" / "window_state.ini"
    real_path.parent.mkdir(parents=True, exist_ok=True)
    real_settings = QSettings(str(real_path), QSettings.Format.IniFormat)
    real_settings.setValue("layout/schemaVersion", WINDOW_STATE_SCHEMA_VERSION)
    real_settings.sync()
    before = real_path.read_bytes()

    injected_path = tmp_path / "injected" / "state.ini"
    window = MainWindow(window_settings_factory=lambda: open_window_settings(path_override=injected_path))
    qtbot.addWidget(window)
    window._save_window_state()
    assert injected_path.exists()

    window._on_reset_window_layout_triggered()

    assert real_path.read_bytes() == before  # untouched throughout
    # The injected backend was cleared-then-resaved by Reset -- it exists again
    # (Reset always re-persists the fresh default as the new baseline) but was
    # genuinely cleared in between, not left as its pre-Reset content.
    assert injected_path.exists()


def test_production_clean_close_writes_to_injected_persistent_settings(qtbot, tmp_path):
    """10: with persist_window_state=True (the default) and an injected factory, a clean
    close DOES write state -- proving the isolation guard only suppresses writes in
    smoke/ephemeral mode, never in normal persistent operation.
    """
    injected_path = tmp_path / "persisted" / "state.ini"
    window = MainWindow(window_settings_factory=lambda: open_window_settings(path_override=injected_path))
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)

    window.close()

    assert injected_path.exists()
    settings = QSettings(str(injected_path), QSettings.Format.IniFormat)
    assert settings.value("layout/schemaVersion") is not None


def test_corrupt_injected_state_falls_back_to_default(qtbot, tmp_path):
    """11: corrupt state at an explicitly-injected path falls back to the default layout,
    exactly like the real-path case already covered in test_gui_dock_layout.py -- pinned
    here directly against the DI seam itself, not just the env-var override.
    """
    injected_path = tmp_path / "corrupt" / "state.ini"

    def factory() -> QSettings:
        return open_window_settings(path_override=injected_path)

    first = MainWindow(window_settings_factory=factory)
    qtbot.addWidget(first)
    first.close()

    corrupt_settings = QSettings(str(injected_path), QSettings.Format.IniFormat)
    corrupt_settings.setValue("layout/dockState", b"not-a-real-qbytearray-state")
    corrupt_settings.sync()

    second = MainWindow(window_settings_factory=factory)
    qtbot.addWidget(second)
    assert second._restore_window_state() is False


# ============================================================
# 12-13: cross-test / cross-instance isolation
# ============================================================


def test_two_injected_settings_paths_do_not_leak_into_each_other(qtbot, tmp_path):
    """12: two distinct injected settings files (simulating "test A" and "test B" state)
    never cross-contaminate -- writing to one never appears in the other.
    """
    path_a = tmp_path / "a" / "state.ini"
    path_b = tmp_path / "b" / "state.ini"

    window_a = MainWindow(window_settings_factory=lambda: open_window_settings(path_override=path_a))
    qtbot.addWidget(window_a)
    window_a.resize(1400, 900)
    window_a._save_window_state()

    window_b = MainWindow(window_settings_factory=lambda: open_window_settings(path_override=path_b))
    qtbot.addWidget(window_b)
    window_b._save_window_state()

    settings_a = QSettings(str(path_a), QSettings.Format.IniFormat)
    settings_b = QSettings(str(path_b), QSettings.Format.IniFormat)
    assert settings_a.value("layout/windowWidth") != settings_b.value("layout/windowWidth")


def test_two_main_window_instances_do_not_affect_each_others_layout(qtbot, tmp_path):
    """13: two simultaneously-open MainWindow instances, each with its own injected
    settings, never read or write each other's dock layout.
    """
    path_a = tmp_path / "instance_a" / "state.ini"
    path_b = tmp_path / "instance_b" / "state.ini"

    window_a = MainWindow(window_settings_factory=lambda: open_window_settings(path_override=path_a))
    qtbot.addWidget(window_a)
    window_b = MainWindow(window_settings_factory=lambda: open_window_settings(path_override=path_b))
    qtbot.addWidget(window_b)

    window_a._save_window_state()
    assert path_a.exists()
    assert not path_b.exists()

    window_b._save_window_state()
    assert path_b.exists()
