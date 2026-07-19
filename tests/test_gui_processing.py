"""GUI processing preview/apply tests (Sprint GUI-3A). Run with ``QT_QPA_PLATFORM=offscreen``.

Every test here is marked ``@pytest.mark.gui`` (module-level ``pytestmark``)
and collected separately from the core suite, exactly like ``test_gui.py``
(see its own module docstring) -- ``pytest.importorskip`` below makes this
whole module skip cleanly, not error, when PySide6/pyqtgraph are not
installed.

Section labels below (A-F) and item numbers match the sprint's own test
plan (see ``ADR-015`` / ``Sprint_GUI_3A_Processing_Preview_Apply.md``) so
each real test name here can be traced back to the specific behavior it was
requested to cover.
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QObject, QThread
from PySide6.QtWidgets import QMessageBox

from archaeogpr.gui import main_window as main_window_module
from archaeogpr.gui.main_window import MainWindow
from archaeogpr.gui.processing.models import ProcessingOperationSpec
from archaeogpr.gui.processing.registry import BANDPASS, DEWOW, REGISTRY, TIME_ZERO, get_operation
from archaeogpr.gui.workers import file_loader as file_loader_module
from archaeogpr.processing import ProcessingResult

pytestmark = pytest.mark.gui

# Must be set before any ImageItem/PlotWidget is constructed -- see
# archaeogpr/gui/views/bscan_view.py's module docstring. Harmless to set
# twice if test_gui.py already did it in the same session.
pg.setConfigOptions(imageAxisOrder="row-major")


@pytest.fixture
def no_blocking_dialogs(monkeypatch):
    """Prevent QMessageBox.critical/warning/question from hanging offscreen tests.

    See test_gui.py's ``no_blocking_error_dialog`` for the same problem with
    ``.critical`` alone -- this sprint's Processing panel also opens
    ``.warning`` (invalid parameters) and ``.question`` (Reset to Raw
    confirmation), both modal and equally blocking offscreen.
    """
    calls: list[tuple[str, tuple, dict]] = []
    monkeypatch.setattr(
        QMessageBox, "critical", staticmethod(lambda *a, **k: calls.append(("critical", a, k)))
    )
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: calls.append(("warning", a, k))))
    monkeypatch.setattr(
        QMessageBox,
        "question",
        staticmethod(lambda *a, **k: (calls.append(("question", a, k)), QMessageBox.StandardButton.Yes)[1]),
    )
    return calls


class _GatedApply:
    """Blocks a ``ProcessingOperationSpec.apply`` call until the test releases it.

    Lets tests deterministically control exactly when the "blocking
    processing call" returns -- mirrors ``test_gui.py``'s ``_GatedReader``
    for file loading. No real-time sleep.
    """

    def __init__(self, real_apply):
        self.started = threading.Event()
        self._release_event = threading.Event()
        self._real_apply = real_apply
        self.call_count = 0

    def __call__(self, dataset, params, valid_mask):
        self.call_count += 1
        self.started.set()
        released = self._release_event.wait(timeout=5.0)
        assert released, "test never called release() -- see _GatedApply"
        return self._real_apply(dataset, params, valid_mask)

    def release(self) -> None:
        self._release_event.set()


def _spec_with_apply(base_spec: ProcessingOperationSpec, apply_fn) -> ProcessingOperationSpec:
    """A throwaway spec identical to ``base_spec`` except for a substituted ``apply``.

    Never mutates the shared registry singleton -- ``ProcessingOperationSpec``
    is a frozen dataclass, and rebuilding a fresh instance means no test has
    to restore any global state afterward.
    """
    return ProcessingOperationSpec(
        operation_id=base_spec.operation_id,
        display_name=base_spec.display_name,
        description=base_spec.description,
        parameters=base_spec.parameters,
        changes_time_axis=base_spec.changes_time_axis,
        apply=apply_fn,
        validate=base_spec.validate,
    )


class _ProcessingThreadRecorder(QObject):
    """Records which thread a connected slot actually ran on -- see ``test_gui.py``'s ``_ThreadRecorder``.

    Must be a real ``QObject`` subclass with a genuine, class-defined method
    for the same reason documented there: PySide6 only reliably resolves a
    cross-thread signal to a ``QueuedConnection`` when the connected
    callable is a bound method of a QObject whose thread affinity it can
    determine from the class's original definition.
    """

    def __init__(self) -> None:
        super().__init__()
        self.thread_seen = None

    def record(self, _token, _base_revision, _result):
        self.thread_seen = QThread.currentThread()


def _select_operation(window: MainWindow, operation_id: str) -> None:
    index = [spec.operation_id for spec in REGISTRY].index(operation_id)
    window.operation_combo.setCurrentIndex(index)


def _make_dataset(dataset_factory, **kwargs):
    kwargs.setdefault("slices_count", 6)
    kwargs.setdefault("channels_count", 2)
    kwargs.setdefault("samples_count", 200)
    kwargs.setdefault("sampling_time_ns", 0.5)
    return dataset_factory(**kwargs)


# ============================================================
# A. Session/model
# ============================================================


def test_raw_and_current_are_same_object_initially(dataset_factory):
    """A1: raw and current are the exact same dataset object right after a fresh load."""
    from archaeogpr.gui.models.dataset_session import DatasetSession

    session = DatasetSession()
    dataset = _make_dataset(dataset_factory)
    session.commit_dataset(dataset, Path("x.ogpr"))
    assert session.raw_dataset is dataset
    assert session.current_dataset is dataset
    assert session.dataset is dataset


def test_set_preview_does_not_change_current_dataset(dataset_factory):
    """A2: recording a preview never touches current_dataset."""
    from archaeogpr.gui.models.dataset_session import DatasetSession

    session = DatasetSession()
    dataset = _make_dataset(dataset_factory)
    session.commit_dataset(dataset, Path("x.ogpr"))
    preview = _make_dataset(dataset_factory)
    session.set_preview(preview, None)
    assert session.current_dataset is dataset
    assert session.preview_dataset is preview
    assert session.has_fresh_preview


def test_apply_preview_updates_current_dataset(dataset_factory):
    """A3: Apply Preview atomically replaces current_dataset with the preview."""
    from archaeogpr.gui.models.dataset_session import DatasetSession

    session = DatasetSession()
    dataset = _make_dataset(dataset_factory)
    session.commit_dataset(dataset, Path("x.ogpr"))
    preview = _make_dataset(dataset_factory)
    session.set_preview(preview, None)
    session.apply_preview()
    assert session.current_dataset is preview
    assert session.preview_dataset is None


def test_apply_preview_increments_revision(dataset_factory):
    """A4: Apply Preview bumps current_revision by exactly 1."""
    from archaeogpr.gui.models.dataset_session import DatasetSession

    session = DatasetSession()
    dataset = _make_dataset(dataset_factory)
    session.commit_dataset(dataset, Path("x.ogpr"))
    assert session.current_revision == 0
    session.set_preview(_make_dataset(dataset_factory), None)
    session.apply_preview()
    assert session.current_revision == 1


def test_discard_preview_preserves_current_dataset(dataset_factory):
    """A5: Discard Preview leaves current_dataset completely untouched."""
    from archaeogpr.gui.models.dataset_session import DatasetSession

    session = DatasetSession()
    dataset = _make_dataset(dataset_factory)
    session.commit_dataset(dataset, Path("x.ogpr"))
    session.set_preview(_make_dataset(dataset_factory), None)
    session.discard_preview()
    assert session.current_dataset is dataset
    assert session.preview_dataset is None
    assert session.current_revision == 0


def test_reset_to_raw_restores_raw_dataset(dataset_factory):
    """A6: Reset to Raw makes current_dataset the raw dataset again."""
    from archaeogpr.gui.models.dataset_session import DatasetSession

    session = DatasetSession()
    dataset = _make_dataset(dataset_factory)
    session.commit_dataset(dataset, Path("x.ogpr"))
    session.set_preview(_make_dataset(dataset_factory), None)
    session.apply_preview()
    assert session.current_dataset is not dataset

    session.reset_to_raw()
    assert session.current_dataset is dataset
    assert session.raw_dataset is dataset


def test_raw_dataset_unchanged_through_apply_and_reset(dataset_factory):
    """A7: raw_dataset's own amplitude bytes are identical before/after an apply+reset cycle."""
    from archaeogpr.gui.models.dataset_session import DatasetSession

    session = DatasetSession()
    dataset = _make_dataset(dataset_factory)
    before = dataset.amplitudes.tobytes()
    session.commit_dataset(dataset, Path("x.ogpr"))
    session.set_preview(_make_dataset(dataset_factory), None)
    session.apply_preview()
    session.reset_to_raw()

    assert session.raw_dataset is dataset
    assert session.raw_dataset.amplitudes.tobytes() == before


def test_stale_preview_revision_cannot_be_applied(dataset_factory):
    """A8: has_fresh_preview/apply_preview reject a preview tagged with a stale base revision.

    Directly bumps current_revision after set_preview() to construct the
    (structurally rare) stale state -- proves the *defensive* guard itself
    works, mirroring how GUI-1B's own tests directly manipulate a stale
    token to prove a structurally-rare race is still defended against (see
    ADR-014/ADR-015).
    """
    from archaeogpr.gui.models.dataset_session import DatasetSession

    session = DatasetSession()
    dataset = _make_dataset(dataset_factory)
    session.commit_dataset(dataset, Path("x.ogpr"))
    session.set_preview(_make_dataset(dataset_factory), None)
    assert session.has_fresh_preview

    session.current_revision += 1  # simulate the committed dataset moving on
    assert not session.has_fresh_preview
    with pytest.raises(ValueError):
        session.apply_preview()
    assert session.current_dataset is dataset


# ============================================================
# B. Registry/forms
# ============================================================


def test_registry_contains_exactly_five_operations():
    """B9: the registry has exactly the five stable operations, no more, no fewer."""
    assert len(REGISTRY) == 5
    assert {spec.operation_id for spec in REGISTRY} == {
        "time_zero",
        "dc_offset",
        "dewow",
        "bandpass",
        "background",
    }


def test_registry_does_not_contain_gain():
    """B10: no gain/AGC entry exists in the registry (see ADR-015 scope)."""
    for spec in REGISTRY:
        assert "gain" not in spec.operation_id.lower()
        assert "agc" not in spec.operation_id.lower()
        assert "gain" not in spec.display_name.lower()


def test_operation_form_builds_correct_parameter_widgets(qtbot):
    """B11: the Parameters form's widgets match the selected operation's real ParameterSpec names."""
    window = MainWindow()
    qtbot.addWidget(window)
    for index, spec in enumerate(REGISTRY):
        window.operation_combo.setCurrentIndex(index)
        assert set(window._parameter_widgets.keys()) == {p.name for p in spec.parameters}


def test_invalid_parameter_does_not_start_worker(qtbot, no_blocking_dialogs, dataset_factory):
    """B12: an invalid parameter value blocks Preview from ever starting a worker."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    _select_operation(window, "dewow")
    window._operation_params["dewow"]["window_ns"] = -1.0  # invalid: must be > 0

    window._on_preview_clicked()

    assert not window.is_processing
    assert any(call[0] == "warning" for call in no_blocking_dialogs)


def test_bandpass_nyquist_validation_rejects_too_high_highcut(dataset_factory):
    """B13: band-pass's client-side validate() rejects a highcut above the Nyquist frequency."""
    dataset = _make_dataset(dataset_factory, sampling_time_ns=0.5)  # Nyquist = 1000 MHz
    spec = get_operation("bandpass")
    params = spec.defaults()
    params["highcut_mhz"] = 5000.0
    errors = spec.validate(params, dataset)
    assert errors
    assert any("Nyquist" in message for message in errors)


def test_changing_operation_rebuilds_parameter_form(qtbot):
    """B14: selecting a different operation rebuilds the form with that operation's own parameters."""
    window = MainWindow()
    qtbot.addWidget(window)

    _select_operation(window, "time_zero")
    assert set(window._parameter_widgets.keys()) == {p.name for p in TIME_ZERO.parameters}

    _select_operation(window, "bandpass")
    assert set(window._parameter_widgets.keys()) == {p.name for p in BANDPASS.parameters}


def test_changing_parameter_discards_existing_preview(qtbot, dataset_factory):
    """B15: editing a parameter while a preview exists discards it (Sprint GUI-3A scope decision)."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()
    _select_operation(window, "dewow")
    window.session.set_preview(_make_dataset(dataset_factory), None)
    assert window.session.preview_dataset is not None

    window._on_parameter_changed("window_ns", 12.0)

    assert window.session.preview_dataset is None


# ============================================================
# C. Processing worker
# ============================================================


def test_processing_apply_runs_off_the_main_thread(qtbot, dataset_factory):
    """C16: the real processing function is invoked on the worker thread, not the GUI main thread."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    seen_thread_idents: list[int] = []

    def recording_apply(ds, params, valid_mask):
        seen_thread_idents.append(threading.get_ident())
        return DEWOW.apply(ds, params, valid_mask)

    main_thread_ident = threading.get_ident()
    spec = _spec_with_apply(DEWOW, recording_apply)
    window._start_processing_preview(spec, DEWOW.defaults())
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    assert seen_thread_idents
    assert seen_thread_idents[0] != main_thread_ident


def test_processing_result_handler_runs_on_qt_main_thread(qtbot, dataset_factory):
    """C17: MainWindow's preview_ready handler executes on the Qt main thread, not the worker thread."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    recorder = _ProcessingThreadRecorder()
    spec = _spec_with_apply(DEWOW, DEWOW.apply)
    window._start_processing_preview(spec, DEWOW.defaults())
    window._processing_worker.preview_ready.connect(recorder.record)
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    assert recorder.thread_seen is QThread.currentThread()


def test_successful_processing_produces_preview_not_commit(qtbot, dataset_factory):
    """C18: a successful run only ever produces a preview -- current_dataset is never touched."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    _select_operation(window, "dewow")
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    assert window.session.current_dataset is dataset
    assert window.session.has_fresh_preview
    assert window.session.preview_dataset is not None
    assert window.session.preview_dataset is not dataset


def test_processing_runtime_error_preserves_current_session(qtbot, no_blocking_dialogs, dataset_factory):
    """C19: a processing runtime error leaves current_dataset completely untouched."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    def failing_apply(ds, params, valid_mask):
        raise ValueError("synthetic processing failure")

    spec = _spec_with_apply(DEWOW, failing_apply)
    window._start_processing_preview(spec, DEWOW.defaults())
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    assert window.session.current_dataset is dataset
    assert window.session.preview_dataset is None
    assert window._last_preview_outcome == "error"
    assert any(call[0] == "critical" for call in no_blocking_dialogs)


def test_cancel_processing_preserves_current_session(qtbot, dataset_factory):
    """C20: cancelling a running preview leaves current_dataset untouched and discards the result."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    gated = _GatedApply(DEWOW.apply)
    spec = _spec_with_apply(DEWOW, gated)
    window._start_processing_preview(spec, DEWOW.defaults())
    assert gated.started.wait(timeout=5.0)

    window._on_cancel_processing_clicked()
    assert window._processing_cancel_event.is_set()

    gated.release()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    assert window.session.current_dataset is dataset
    assert window.session.preview_dataset is None
    assert window._last_preview_outcome == "cancelled"


def test_late_result_after_cancel_is_discarded(qtbot, dataset_factory):
    """C21: a processing result that arrives after cancellation was requested is discarded, not committed.

    Uses the *real* ``DEWOW.apply`` (via ``_GatedApply``) so the underlying
    call genuinely succeeds once released -- proving the outcome is
    determined by "was cancellation requested", not "did the call fail".
    """
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    gated = _GatedApply(DEWOW.apply)
    spec = _spec_with_apply(DEWOW, gated)
    window._start_processing_preview(spec, DEWOW.defaults())
    assert gated.started.wait(timeout=5.0)

    window._request_cancel_current_processing()  # requested BEFORE the real apply() returns
    gated.release()  # the real apply() now succeeds "late"
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    assert window._last_preview_outcome == "cancelled"
    assert window.session.preview_dataset is None
    assert window.session.current_dataset is dataset


def test_stale_token_result_is_discarded(dataset_factory):
    """C22: a preview_ready signal carrying an old token is discarded (superseded by a newer request)."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    stale_token = window._current_processing_token
    fake_result = ProcessingResult(
        dataset=dataset, removed_component=np.zeros_like(dataset.amplitudes), diagnostics={}
    )
    window._current_processing_token += 1  # a "newer" request is now current

    window._on_processing_preview_ready(stale_token, window.session.current_revision, fake_result)

    assert window.session.preview_dataset is None


def test_stale_revision_result_is_discarded(dataset_factory):
    """C23: a preview_ready signal carrying a stale base_revision is discarded (base dataset moved on)."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    token = window._current_processing_token + 1
    window._current_processing_token = token
    stale_base_revision = window.session.current_revision
    window.session.current_revision += 1  # committed dataset moved on while this "ran"

    fake_result = ProcessingResult(
        dataset=dataset, removed_component=np.zeros_like(dataset.amplitudes), diagnostics={}
    )
    window._on_processing_preview_ready(token, stale_base_revision, fake_result)

    assert window.session.preview_dataset is None


def test_second_concurrent_processing_is_rejected(qtbot, dataset_factory):
    """C24: a second Preview request while one is already running is rejected outright."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    gated = _GatedApply(DEWOW.apply)
    spec = _spec_with_apply(DEWOW, gated)
    window._start_processing_preview(spec, DEWOW.defaults())
    assert gated.started.wait(timeout=5.0)
    first_thread = window._processing_thread
    first_token = window._current_processing_token

    window._on_preview_clicked()  # via the real entry point -- must be rejected

    assert window._processing_thread is first_thread
    assert window._current_processing_token == first_token
    assert gated.call_count == 1

    gated.release()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)


def test_file_load_rejected_during_processing(qtbot, dataset_factory):
    """C25: open_path() is rejected while a processing preview is running."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    gated = _GatedApply(DEWOW.apply)
    spec = _spec_with_apply(DEWOW, gated)
    window._start_processing_preview(spec, DEWOW.defaults())
    assert gated.started.wait(timeout=5.0)

    window.open_path("some_other_file.ogpr")
    assert not window.is_loading

    gated.release()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)


class _GatedFileReader:
    """Same ``_GatedReader`` shape as ``test_gui.py`` -- kept local to avoid cross-test-file coupling."""

    def __init__(self, dataset):
        self.started = threading.Event()
        self._release_event = threading.Event()
        self.dataset = dataset

    def __call__(self, _path):
        self.started.set()
        released = self._release_event.wait(timeout=5.0)
        assert released, "test never called release()"
        return self.dataset

    def release(self) -> None:
        self._release_event.set()


def test_processing_rejected_during_file_load(qtbot, monkeypatch, dataset_factory):
    """C26: _on_preview_clicked() is rejected while a file load is running."""
    initial_dataset = _make_dataset(dataset_factory)
    incoming_dataset = _make_dataset(dataset_factory)
    reader = _GatedFileReader(incoming_dataset)
    monkeypatch.setattr(file_loader_module, "read_ogpr", reader)

    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(initial_dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    window.open_path("second.ogpr")
    assert reader.started.wait(timeout=5.0)
    assert window.is_loading

    window._on_preview_clicked()
    assert not window.is_processing

    reader.release()
    qtbot.waitUntil(lambda: not window.is_loading, timeout=5000)


def test_new_processing_can_start_after_previous_finishes(qtbot, dataset_factory):
    """C27: once a processing run's thread has finished, a new one can start immediately.

    Uses dc_offset for the second run (not dewow again) deliberately: dewow
    guards against being re-applied on top of a dataset that already has
    ``"dewow_correction"`` in its history (see the processing API audit /
    ADR-015) -- reusing the same operation twice here would just exercise
    that unrelated guard instead of "a new, independent run starts cleanly".
    """
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    _select_operation(window, "dewow")
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)
    assert window.session.has_fresh_preview

    window._on_apply_preview_clicked()
    _select_operation(window, "dc_offset")
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    assert window.session.has_fresh_preview


def test_close_while_processing_defers_destruction(qtbot, dataset_factory):
    """C28: closing the window while a preview is computing defers destruction (see ADR-015)."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    gated = _GatedApply(DEWOW.apply)
    spec = _spec_with_apply(DEWOW, gated)
    window._start_processing_preview(spec, DEWOW.defaults())
    assert gated.started.wait(timeout=5.0)
    thread = window._processing_thread

    window.close()  # must return immediately -- no wait(), no blocking

    assert window._close_pending is True
    assert window._processing_thread is thread  # still tracked -- not cleared early
    assert thread.isRunning()

    gated.release()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)


def test_no_qthread_destroyed_warning_during_processing_close(qtbot, dataset_factory, capsys):
    """C29: no "QThread: Destroyed while thread is still running" during a full deferred-close cycle."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    gated = _GatedApply(DEWOW.apply)
    spec = _spec_with_apply(DEWOW, gated)
    window._start_processing_preview(spec, DEWOW.defaults())
    assert gated.started.wait(timeout=5.0)

    window.close()
    gated.release()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    captured = capsys.readouterr()
    assert "Destroyed while thread is still running" not in captured.err
    assert "Destroyed while thread is still running" not in captured.out


def test_shutdown_pending_rejects_new_processing_and_load(qtbot, dataset_factory):
    """C30: once shutdown is pending, no new load or processing may start."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    gated = _GatedApply(DEWOW.apply)
    spec = _spec_with_apply(DEWOW, gated)
    window._start_processing_preview(spec, DEWOW.defaults())
    assert gated.started.wait(timeout=5.0)

    window.close()
    assert window._close_pending is True

    window.open_path("x.ogpr")
    assert not window.is_loading

    window._on_preview_clicked()
    assert window._processing_thread is not None  # still the original worker
    assert gated.call_count == 1

    gated.release()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)


# ============================================================
# D. Views
# ============================================================


def test_display_source_selection_shows_correct_dataset(qtbot, dataset_factory):
    """D31: Raw/Current/Preview selections each render the correspondingly correct dataset."""
    raw = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(raw, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    window.session.set_preview(_make_dataset(dataset_factory), None)
    window.session.apply_preview()
    current = window.session.current_dataset
    assert current is not raw

    second_preview = _make_dataset(dataset_factory)
    window.session.set_preview(second_preview, None)

    window._set_display_source("raw")
    assert window._dataset_for_display() is raw
    window._set_display_source("current")
    assert window._dataset_for_display() is current
    window._set_display_source("preview")
    assert window._dataset_for_display() is second_preview


def test_preview_not_applied_label_visible_in_history(qtbot, dataset_factory):
    """D32: while viewing a preview, its pending history entry is clearly marked "not applied"."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    _select_operation(window, "dewow")
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    assert window._display_source == "preview"
    items_text = [window.history_list.item(i).text() for i in range(window.history_list.count())]
    assert any("PREVIEW, NOT APPLIED" in text for text in items_text)


def test_preview_display_source_disabled_without_preview(qtbot, dataset_factory):
    """D33: the "Preview" display-source combo item is disabled whenever there is no preview."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    preview_index = [value for _label, value in main_window_module._DISPLAY_SOURCE_ITEMS].index("preview")
    item = window.display_source_combo.model().item(preview_index)
    assert not item.isEnabled()

    window.session.set_preview(_make_dataset(dataset_factory), None)
    window._refresh_processing_panel()
    assert item.isEnabled()


def test_time_zero_preview_changes_time_axis_in_views(qtbot, dataset_factory):
    """D34: after a time-zero preview, the displayed (preview) dataset's time_ns reflects the new zero."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    _select_operation(window, "time_zero")
    window._operation_params["time_zero"]["target_sample"] = 20
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)

    assert window._display_source == "preview"
    displayed = window._dataset_for_display()
    assert displayed is not dataset
    assert displayed.time_ns[20] == pytest.approx(0.0)
    assert not np.array_equal(displayed.time_ns, dataset.time_ns)


def test_apply_updates_metadata_and_history(qtbot, dataset_factory):
    """D35: Apply Preview updates the current dataset's processing history, reflected in the History list."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()

    _select_operation(window, "dewow")
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)
    window._on_apply_preview_clicked()

    assert [r["operation"] for r in window.session.current_dataset.processing_history] == ["dewow_correction"]
    items_text = [window.history_list.item(i).text() for i in range(window.history_list.count())]
    assert any("dewow_correction" in text for text in items_text)
    assert not any("NOT APPLIED" in text for text in items_text)


def test_selected_channel_and_trace_preserved_across_apply(qtbot, dataset_factory):
    """D36: Apply Preview does not reset the user's selected channel/trace."""
    dataset = _make_dataset(dataset_factory, slices_count=10, channels_count=3)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()
    window.session.selected_channel = 2
    window.session.selected_trace = 5

    _select_operation(window, "dewow")
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)
    window._on_apply_preview_clicked()

    assert window.session.selected_channel == 2
    assert window.session.selected_trace == 5


def test_display_settings_preserved_across_apply(qtbot, dataset_factory):
    """D37: Apply Preview does not touch DisplaySettings (colormap, percentile, etc.)."""
    dataset = _make_dataset(dataset_factory)
    window = MainWindow()
    qtbot.addWidget(window)
    window.session.commit_dataset(dataset, Path("x.ogpr"))
    window._refresh_for_new_dataset()
    settings_before = window.display_settings

    _select_operation(window, "dewow")
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=5000)
    window._on_apply_preview_clicked()

    assert window.display_settings is settings_before


# ============================================================
# E. Operation integration
# ============================================================


@pytest.mark.parametrize("operation_id", ["time_zero", "dc_offset", "dewow", "bandpass", "background"])
def test_operation_preview_does_not_modify_input_dataset(operation_id, dataset_factory):
    """E38-E42: every operation's adapter leaves its input dataset completely unmodified."""
    dataset = _make_dataset(
        dataset_factory, metadata={"sampling": {"sampling_time_ns": 0.5, "sampling_step_m": 0.1}}
    )
    before_amplitudes = dataset.amplitudes.tobytes()
    before_time_ns = dataset.time_ns.tobytes()

    spec = get_operation(operation_id)
    result = spec.apply(dataset, spec.defaults(), None)

    assert dataset.amplitudes.tobytes() == before_amplitudes
    assert dataset.time_ns.tobytes() == before_time_ns
    assert not dataset.amplitudes.flags.writeable
    assert result.dataset is not dataset


def test_all_operations_preserve_dataset_shape(dataset_factory):
    """E43: every operation's output shape/dtype matches the input's (all 5 preserve shape)."""
    dataset = _make_dataset(
        dataset_factory, metadata={"sampling": {"sampling_time_ns": 0.5, "sampling_step_m": 0.1}}
    )
    for spec in REGISTRY:
        result = spec.apply(dataset, spec.defaults(), None)
        assert result.dataset.shape == dataset.shape
        assert result.dataset.amplitudes.dtype == dataset.amplitudes.dtype


def test_valid_mask_threads_through_chained_operations(dataset_factory):
    """E44: a valid_mask produced by one operation threads correctly into the next (like cli.py's sprint2)."""
    dataset = _make_dataset(dataset_factory)
    tz_spec = get_operation("time_zero")
    tz_params = tz_spec.defaults()
    tz_params["target_sample"] = 20
    tz_result = tz_spec.apply(dataset, tz_params, None)
    assert tz_result.valid_mask is not None
    assert tz_result.valid_mask.any() and not tz_result.valid_mask.all()  # genuine partial padding

    dc_spec = get_operation("dc_offset")
    dc_result = dc_spec.apply(tz_result.dataset, dc_spec.defaults(), tz_result.valid_mask)
    assert dc_result.valid_mask is not None
    assert np.array_equal(dc_result.valid_mask, tz_result.valid_mask)
    assert dc_result.valid_mask is not tz_result.valid_mask  # independent copy, not aliased


def test_processing_history_records_real_operation_names(dataset_factory):
    """E45: dataset.processing_history uses the exact real operation-name strings from each function."""
    dataset = _make_dataset(
        dataset_factory, metadata={"sampling": {"sampling_time_ns": 0.5, "sampling_step_m": 0.1}}
    )
    expected = {
        "time_zero": "time_zero_correction",
        "dc_offset": "dc_offset_correction",
        "dewow": "dewow_correction",
        "bandpass": "bandpass_correction",
        "background": "background_removal",
    }
    for operation_id, expected_name in expected.items():
        spec = get_operation(operation_id)
        result = spec.apply(dataset, spec.defaults(), None)
        assert result.dataset.processing_history[-1]["operation"] == expected_name


# ============================================================
# F. Frozen smoke
# ============================================================


def test_open_flag_still_works_with_processing_panel(tmp_path, ogpr_builder, monkeypatch):
    """F46: `--open` still loads a file successfully with the Processing panel present."""
    from archaeogpr.gui import app as gui_app

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    path = tmp_path / "synthetic.ogpr"
    path.write_bytes(ogpr_builder())
    exit_code = gui_app.main(["--open", str(path), "--smoke-test"])
    assert exit_code == 0


def test_smoke_test_flag_works_with_processing_panel(monkeypatch):
    """F47: `--smoke-test` (no --open) still exits cleanly with the Processing panel constructed."""
    from archaeogpr.gui import app as gui_app

    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    exit_code = gui_app.main(["--smoke-test"])
    assert exit_code == 0


def test_processing_preview_does_not_touch_raw_ogpr_file(qtbot):
    """F48: running a processing preview on the real reference file never modifies it on disk."""
    real_path = Path("data/raw/Swath003_Array02.ogpr")
    if not real_path.exists():
        pytest.skip("reference OGPR file not present in this checkout")

    before_hash = hashlib.sha256(real_path.read_bytes()).hexdigest()
    before_mtime = real_path.stat().st_mtime

    window = MainWindow()
    qtbot.addWidget(window)
    window.open_path(real_path)
    qtbot.waitUntil(lambda: not window.is_loading, timeout=10000)
    assert window.last_load_outcome == "success"

    _select_operation(window, "dewow")
    window._on_preview_clicked()
    qtbot.waitUntil(lambda: not window.is_processing, timeout=10000)
    assert window.session.has_fresh_preview
    window._on_apply_preview_clicked()

    after_hash = hashlib.sha256(real_path.read_bytes()).hexdigest()
    after_mtime = real_path.stat().st_mtime
    assert after_hash == before_hash
    assert after_mtime == before_mtime
