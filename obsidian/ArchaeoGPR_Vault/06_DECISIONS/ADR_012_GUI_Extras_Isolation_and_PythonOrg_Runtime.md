---
type: adr
tags: [decision]
id: ADR-012
status: accepted
date: 2026-07-17
---

# ADR-012 — GUI Extras Isolation and python.org Runtime (not Anaconda) for GUI Development

## Context

Sprint GUI-0 ([[06_DECISIONS/ADR_011_GUI_Technology_Decision]]) chose
PySide6 + PyQtGraph + optional PyVista/pyvistaqt, but only declared the
`pyproject.toml` extras — no GUI code existed yet, so the actual runtime
import path was never exercised. Starting Sprint GUI-1 (the first real
viewer shell), two problems surfaced immediately, both discovered
empirically (not assumed) before any GUI code was written:

1. **`PySide6.QtCore` failed to import** in the project's existing venv
   (`from PySide6.QtCore import qVersion` → `ImportError: DLL load failed
   while importing QtCore: The specified procedure could not be found.`).
   That venv's base interpreter was `C:\Users\baran\anaconda3\python.exe`.
   VC++ runtime was confirmed present and recent (14.51.36247.0 — ruling
   out the most common cause of this exact error). An isolated smoke-test
   venv built from a genuine **python.org CPython 3.13.3** interpreter
   (`C:\Users\baran\AppData\Local\Programs\Python\Python313\python.exe`,
   not Anaconda, not Miniconda, not the Microsoft Store stub) imported
   `PySide6.QtCore`/`QtWidgets`/`pyqtgraph` and ran an offscreen
   `QApplication` successfully on the **first try**, with the exact same
   PySide6 6.11.1 wheel. This isolates the fault to the Anaconda-based
   Python installation/environment, not to PySide6 itself, this machine's
   VC++ runtime, or this project's code.
2. **`pytest-qt`'s `pytest_configure` hook crashes the entire test run**
   (a pytest `INTERNALERROR`, not a clean per-test failure) if it cannot
   import a working Qt binding while guessing which one to use. Because
   Sprint GUI-0 had added `pytest-qt` to the shared `dev` extra, *any*
   environment where PySide6 fails to import — for any reason, on any
   future contributor's machine — would take down `pytest` entirely, even
   for someone doing purely headless processing work who never asked for
   GUI dependencies at all.

## Decision

1. **Development for the GUI/3D track uses a python.org CPython interpreter
   (3.12 or 3.13 x64), never Anaconda, Miniconda, or the Microsoft Store
   Python**, for the project's own `.venv`. `scripts/build_windows.ps1`
   enforces this at build time (refuses to proceed if the interpreter path
   matches `anaconda|miniconda|WindowsApps`) rather than relying on a
   developer remembering the rule.
2. **`pytest-qt` is removed from the shared `dev` extra** and now lives
   only in a new `gui-test` extra (`PySide6` + `pyqtgraph` + `pytest-qt`,
   self-contained — not self-referencing `gui`). `dev` stays
   Qt-dependency-free: `ruff`, `mypy`, `pytest` only. A broken or absent
   Qt installation can now never take down headless `pytest` for someone
   who only ran `pip install -e ".[dev]"`.
3. **New `packaging` extra** (`pyinstaller>=6.10`) — isolated from both
   `dev` and the `gui*` extras; only `scripts/build_windows.ps1` needs it.
4. Every GUI test module (`tests/test_gui.py`) opens with
   `pytest.importorskip("PySide6")` / `pytest.importorskip("pyqtgraph")` —
   confirmed empirically (see [[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]]
   Validation Results) to make the whole module skip cleanly, not error,
   in a `dev`-only environment with no Qt packages installed at all —
   this is a second, independent safeguard on top of (2).

## Alternatives Considered

- **Debug and fix the Anaconda-based PySide6 install in place** (matching
  DLL versions, chasing a PATH conflict, reinstalling VC++ runtimes):
  rejected. The task's own instructions explicitly forbade this class of
  fix (no ad-hoc PySide6 version churn, no copying DLLs into `System32`,
  no permanent PATH edits, no mixing conda packages), and — more
  importantly — a from-scratch python.org venv reproduced the *identical*
  PySide6 6.11.1 wheel working correctly on the first attempt, which is
  strong evidence the fault was environmental (Anaconda's own bundled/
  shadowing DLLs) rather than something specific to this project that
  would need its own fix.
- **Keep `pytest-qt` in `dev` and just fix the environment for everyone**:
  rejected as the sole mitigation. Even with a fixed environment, `dev`
  should not gain a hard Qt dependency for headless processing
  contributors who never asked for one; a future Qt regression (a
  driver update, a different machine, CI) should degrade to "GUI tests
  skip" — not "the entire test suite crashes." Both fixes were made:
  moved off the broken interpreter *and* re-isolated `pytest-qt`.
- **Self-reference `gui-test = ["archaeogpr[gui]", "pytest-qt>=4.4"]`**:
  possible per PEP 621, but this project's existing `gui3d` extra already
  established the convention of literal duplication over self-reference
  (see ADR-011 Consequences) specifically to avoid relying on
  extra-to-extra resolution; `gui-test` follows the same, already-decided
  pattern for consistency.

## Consequences

- `pyproject.toml` `optional-dependencies`: `dev` (Qt-free), `gui`
  (PySide6 + pyqtgraph), `gui-test` (`gui` + pytest-qt), `gui3d`
  (`gui` + pyvista + pyvistaqt, unchanged from ADR-011), `packaging`
  (pyinstaller). README's install section documents all four use cases
  (headless / 2D GUI / GUI dev+test / Windows build).
- The project's `.venv` at `C:\Dev\archaeogpr` was rebuilt from python.org
  CPython 3.13.3 (renamed the old one to
  `.venv_anaconda_broken_20260717/` rather than deleting it, preserving it
  as evidence/rollback until this ADR's fix is trusted). `py -0p` on this
  machine only lists CPython 3.13 (not 3.12/3.11) — 3.13 was used since it
  is a genuine python.org build and satisfies `requires-python = ">=3.11"`;
  it is not on the forbidden list (Anaconda/Miniconda/Microsoft Store).
- `scripts/build_windows.ps1` treats the Qt import smoke test as a hard
  gate before ever invoking PyInstaller — a broken Qt environment fails
  fast with a clear message instead of producing a broken build.
- No `src/archaeogpr` package outside `archaeogpr.gui` is affected —
  `io`/`model`/`processing`/`qc`/`export`/`cli.py` are unchanged.

## Validation

- Isolated smoke venv (`C:\Dev\qt-pyside-smoke`, python.org CPython
  3.13.3): `from PySide6.QtCore import qVersion` → `6.11.1`; `QtWidgets`
  import OK; `pyqtgraph.__version__` → `0.14.0`; an offscreen
  (`QT_QPA_PLATFORM=offscreen`) `QApplication`/`QWidget` construction and
  `processEvents()` succeeded.
- Project venv (same interpreter family): identical four checks pass;
  `PySide6`/`PySide6_Essentials`/`PySide6_Addons`/`shiboken6` all report
  `6.11.1` (`pip show`, matching — see
  [[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]]).
- `pytest` (plain, no marker filter) with `pytest-qt` installed in this
  environment: **318 passed, 26 skipped, 0 failed** — no `INTERNALERROR`
  (contrast with the pre-fix Anaconda environment, where the same
  `pytest-qt` plugin crashed the entire run).
- A separate, throwaway `dev`-only venv (no PySide6/pyqtgraph/pytest-qt at
  all): `pip list` confirms their absence; `pytest`, `pytest -m "not gui"`
  both ran **318 passed, 27 skipped, 0 failed** (27 = 26 real-data skips +
  `tests/test_gui.py` itself, skipped cleanly via `importorskip`, not a
  collection error).

## Related Files

- [[06_DECISIONS/ADR_011_GUI_Technology_Decision]]
- [[02_SPRINTS/Sprint_GUI_1_Viewer_Shell]]
- [[09_REFERENCES/Windows_Executable_Build]]
- `pyproject.toml`
- `scripts/build_windows.ps1`
- `tests/test_gui.py`
