---
type: adr
id: ADR-014
status: accepted
date: 2026-07-18
---

# ADR-014 — GUI Background Worker and Cancellation Policy

## Context

Sprint GUI-1/GUI-2 both loaded a `.ogpr` file **synchronously**, on the Qt
main thread, inside `DatasetSession.load()`. This was explicitly deferred
work, not an oversight: `Sprint_GUI_1_Viewer_Shell.md` acceptable for the
~8 MB reference sample, and `dataset_session.py` carried a
`TODO: GUI-1B: file loading background worker` comment ever since. With the
GUI now merged to `main` (Sprint GUI-0/GUI-1/GUI-2, PR #2), the user
requested Sprint GUI-1B specifically to close that TODO: move the read
off the main thread, show progress, and make it safely cancellable —
**no processing/3D/gain work in this sprint.**

This ADR records the worker architecture, the cancellation guarantee, the
file-load state machine, and the shutdown policy — one place, rather than
scattered across `workers/file_loader.py` and `main_window.py` docstrings.

## Decision

### 1. Worker-object + QThread, never a `QThread` subclass

`FileLoadWorker` (`src/archaeogpr/gui/workers/file_loader.py`) is a plain
`QObject` moved onto a bare `QThread` via `moveToThread()` — not a
`QThread` subclass with an overridden `run()`. This is the pattern Qt's own
documentation recommends: it keeps the worker's logic independent of
thread lifecycle management, and it means `FileLoadWorker` can be
unit-tested by calling `.run()` directly on the test's own thread (no
`QThread` involved at all) for the success/failure-signal tests, while
still running on a real background thread in the full integration tests.

### 2. Cross-thread signals must connect to bound methods of a QObject, never a lambda

**This is the one, hard-won implementation detail this ADR most needs to
document.** The first working version of this sprint connected `worker`'s
signals via `worker.loaded.connect(lambda dataset, p, g=generation: self._on_worker_loaded(g, dataset, p))`
(a lambda capturing a generation counter, to solve stale-result rejection).
This **crashed** — a genuine Windows access violation inside
`pyqtgraph`/Qt — because the slot ran directly on the *worker* thread, not
the main thread: PySide6/Qt can only resolve a cross-thread `AutoConnection`
to `QueuedConnection` when it can determine the *receiver's* thread
affinity, and a plain Python callable (a lambda, or a function patched onto
an object/class after its definition — also confirmed while writing this
sprint's tests) gives Qt no QObject to resolve that from, so it silently
falls back to `DirectConnection` and the slot executes on the emitting
(worker) thread — touching `QWidget`/`pyqtgraph` objects from off the GUI
thread, which is illegal in Qt and corrupted memory in this case.

**Fix, and the rule this sprint's code now follows everywhere:** every
cross-thread signal is connected directly to a bound method of `self`
(`MainWindow`, a `QObject` whose thread is the main thread) —
`worker.loaded.connect(self._on_worker_loaded)`, never a lambda or a
monkeypatched wrapper. Stale-result rejection (below) is solved a
different way as a direct consequence of this constraint.

### 3. Stale-result rejection via a token in the signal payload, not `sender()` and not a lambda closure

Since a generation counter can no longer be captured via a lambda closure
(rule 2), and `QObject.sender()` is explicitly documented as unreliable
across a queued/cross-thread connection (confirmed empirically: a second
test using `sender()` for this same purpose non-deterministically
misidentified a legitimate, first-time result as stale), the token instead
travels **as an explicit signal argument**: `FileLoadWorker.__init__(self,
path, token)` stores the caller-assigned `token`, and every signal
(`progress`, `loaded`, `failed`, `cancelled`, `finished`) carries it as its
first parameter. `MainWindow` compares the token against
`self._current_load_token` inside each handler (a plain bound method,
satisfying rule 2) and discards anything that doesn't match — this is what
guarantees a superseded/late-arriving result can never overwrite a newer
session, and it's directly unit-tested
(`test_stale_worker_result_cannot_overwrite_newer_session`).

### 4. Cancellation is cooperative only — never `QThread.terminate()` — carried by a `threading.Event`

`read_ogpr()` is a single, opaque, blocking call with no internal
cancellation point (chunking/streaming the OGPR reader itself is out of
scope for this sprint). Cancellation is carried by a plain
`threading.Event` (`cancel_event`), created by `MainWindow.open_path()` and
passed into `FileLoadWorker`'s constructor:

- **`MainWindow` calls `cancel_event.set()` directly** (see
  `_request_cancel_current_load()`) — never through a queued signal/slot.
  This was a real design question this sprint's review raised: if
  cancellation were instead delivered as a queued call to a worker-owned
  slot, and the worker is blocked inside `read_ogpr()` (which has no event
  loop of its own to process that queued call), the request would not
  actually be observed until the blocking call returns anyway, making a
  "queued cancel" pointless. A `threading.Event.set()` call is a direct,
  thread-safe, standard-library operation that mutates shared state
  immediately regardless of what the worker thread is doing — it does not
  depend on any event loop. (An earlier revision used a plain `bool`
  attribute instead; a simple attribute write is *in practice* safe enough
  under CPython's GIL, but that safety is an implementation detail of
  CPython, not a documented contract the way `threading.Event` is — the
  switch removes that implicit dependency.)
  `test_cancel_token_is_set_immediately_even_while_worker_is_blocked`
  verifies the set() call returns and is observed as set without needing
  the worker's blocking call to return first.
- **A cancel request may not stop disk parsing/parsing already in
  flight.** If the user clicks Cancel (or closes the window) while
  `read_ogpr()` is running, the read keeps running until it returns
  (successfully or with an exception).
- **What it guarantees instead: a cancelled result is never committed to
  the GUI session.** Once the event is set, the worker emits `cancelled`
  (never `loaded`, even if the read had actually succeeded, and never
  `failed`, even if the read had actually raised) — the dataset or
  exception is discarded, and `DatasetSession` is never touched.
  `test_cancelled_load_preserves_previous_session` and
  `test_cancellation_takes_precedence_over_a_late_failure` cover both
  outcomes explicitly.
- `QThread.terminate()` is never called anywhere in this sprint's code.
  Forcibly killing a thread mid-`read_ogpr()` (mid file I/O, mid NumPy
  buffer construction) could leave interpreter or C-extension state
  corrupted for the rest of the process — an unacceptable risk for a
  "make loading safer" sprint to introduce itself.

### 5. An explicit `FileLoadState` enum, not scattered booleans

`FileLoadState` (`IDLE`, `LOADING`, `CANCELLING`, `SUCCESS`, `ERROR`,
`CANCELLED`) lives in `workers/file_loader.py`. `SUCCESS`/`ERROR`/
`CANCELLED` are momentary: `MainWindow` performs the associated action
(commit the dataset / show a `QMessageBox` / discard the result) and
settles back to `IDLE` within the same slot call, rather than lingering —
they exist as named states so every transition and its UI consequence
(which widgets are enabled, whether the progress panel is visible) is
explicit and unit-testable, not because the GUI visibly sits in them.
`MainWindow._set_file_load_state()` is the one place that translates the
enum into widget state (`open_action.setEnabled`,
`load_cancel_button.setEnabled`, the progress panel's visibility) — it is
called once at the end of `__init__` too (a fresh `QPushButton` defaults
to enabled, and the constructor path was originally missed, causing a real
test failure caught while writing this sprint's own tests).

### 6. Atomic session commit stays `DatasetSession`'s job

`DatasetSession.load()` (synchronous, still used directly by
non-GUI/test callers) was split into `read_ogpr()` + a new
`commit_dataset(dataset, source_path)` method that does the actual atomic
field assignment. `MainWindow._on_worker_loaded()` calls
`commit_dataset()` only after a full, uncancelled, successful read — the
previous dataset/channel/trace selection is left completely untouched
until that exact point, matching the pre-existing behavior `load()`
already had for a synchronous failure (see `Sprint_GUI_1_Viewer_Shell.md`).

### 7. Progress is always indeterminate — no fabricated percentage

`read_ogpr()` has no internal progress callback, so there is no real
byte-level or stage-level completion percentage to report.
`load_progress_bar` is always set to Qt's indeterminate range (`0, 0`) —
this sprint does not synthesize a fake percentage or a fake multi-stage
sequence that doesn't correspond to real, separately-timed work. The
status label's text (`"Preparing …"` / `"Reading OGPR…"` /
`"Updating viewer…"` / `"Load complete"` / `"Cancelling…"` /
`"Load cancelled"` / `"Load failed"`) is still informative, and each phrase
corresponds to something actually happening at that point (file prep on
the main thread, the blocking read on the worker thread, view refresh on
the main thread after commit) rather than being invented.

### 8. Shutdown: deferred close, never a blocking wait, never an orphaned/force-killed thread

**This section was rewritten after a pre-commit review found the first
version's shutdown design unsafe; see the Issues Discovered timeline in
[[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]].** The original
`closeEvent()` requested cancellation, called `thread.quit()`, blocked the
GUI thread for up to 3000 ms waiting for the worker, and — if that timed
out — called `self._load_thread.setParent(None)` to stop Qt from trying to
destroy a still-running `QThread`. Two problems with that design:

- A 3-second **blocking `wait()` on the GUI thread inside `closeEvent()`**
  contradicts this sprint's own goal (a responsive GUI) and is exactly the
  kind of freeze Sprint GUI-1B exists to eliminate, just moved to shutdown
  instead of load-start.
- **`setParent(None)` does not make a running `QThread` safe to abandon.**
  It only detaches the Python/Qt parent-child relationship so Qt's object
  tree does not try to delete the thread object while it's still running;
  it does not guarantee the underlying OS thread ever finishes cleanly,
  and if the *window itself* (or the application) were destroyed while
  that detached thread was still alive, the risk the review flagged
  (`QThread: Destroyed while thread is still running`, a non-exiting
  process, or worse, a crash) was still real.

**Fixed design — deferred close, no wait, no orphaning:**

```
closeEvent() while a load is in flight:
  1. self._close_pending = True
  2. cancel_event.set()                      -- immediate, thread-safe (item 4)
  3. state -> CANCELLING, status "Cancelling load before exit…"
  4. event.ignore()                          -- the close is refused *for now*
  5. self.hide()                             -- the user still perceives "it closed"
  (returns immediately -- no wait(), no blocking)

... (arbitrarily long real time later, whenever read_ogpr() actually returns) ...

_on_load_thread_finished() (connected to QThread.finished):
  1. clear self._load_thread / _load_worker / _load_cancel_event
  2. state -> IDLE
  3. if self._close_pending: QTimer.singleShot(0, self.close)  -- retries the close
       -> closeEvent() runs again; is_loading is now False -> super().closeEvent()
          accepts normally
```

`MainWindow`/the worker/the `QThread` are never destroyed while the thread
is running -- the window is only *hidden*, kept fully alive in memory
until `thread.finished` fires naturally, at which point the retried
`close()` completes for real. No `wait()` call exists anywhere in
`closeEvent()` any more; the GUI event loop is never blocked by it (see
`test_gui_remains_responsive_while_close_is_pending`).

This is also why `self._load_thread`/`self._load_worker`/
`self._load_cancel_event` are cleared in `_on_load_thread_finished`
(connected to Qt's own argument-less `QThread.finished`), **not** in the
outcome handlers (`_on_worker_loaded`/`_on_worker_failed`/
`_on_worker_cancelled`, connected to `worker.finished`'s token-carrying
siblings) as an earlier revision did: `thread.finished` only fires once
the underlying OS thread has genuinely stopped, which is a strictly later
point than "the outcome is known" -- moving cleanup here means nothing is
cleared, and no deferred close is retried, until the thread is actually,
fully gone. `is_loading` (`self._load_thread is not None`) is the single
authoritative "is a load-cycle still in flight" guard both `open_path()`
and `closeEvent()` rely on; because it is only cleared in
`_on_load_thread_finished`, a concurrent second load is not merely
rejected by a check, it is *structurally impossible* -- which is also
what makes `_on_load_thread_finished` safe to write with no token/identity
check of its own (see `test_outcome_handled_does_not_prematurely_clear_thread_reference`):
by the time it runs, `self._load_thread` cannot refer to anything other
than the thread that just finished, because nothing else could have
replaced it in the meantime.

**Documented guarantee (verbatim, matches the code and this ADR):**
"Blocking OGPR parsing cannot be forcefully interrupted. Closing the
window requests cancellation and defers final application shutdown until
the reader returns. The cancelled result is never committed."

**Second fix-round finding: a residual close-pending race in the gap
between cleanup and the deferred retry.** A further pre-commit review of
the design above found one more gap: `_on_load_thread_finished` used to
clear `self._close_pending` back to `False` in the same call that cleared
`self._load_thread` and scheduled the `QTimer.singleShot(0, self.close)`
retry. Between that handler returning and the queued retry actually
running -- a real event-loop turnaround, not instantaneous -- both
`is_loading` (`self._load_thread is not None`) and `_close_pending` were
already `False`, so a programmatic `open_path()` call landing in exactly
that gap would not have been rejected by either guard and would have
started a genuine new load while a shutdown was already underway.

**Fix:** `_on_load_thread_finished` no longer clears `_close_pending` --
only `closeEvent()`'s `if not self.is_loading:` branch does, exactly when
it is about to actually accept the close (`super().closeEvent(event)`).
This keeps `_close_pending` latched continuously from the first deferred
`closeEvent()` call all the way through to the window actually closing,
with no gap. `open_path()` also gained an explicit, first-checked guard --
`if self._close_pending: return` (ahead of the existing
`if self.is_loading: return`) -- so a load requested at any point during a
pending shutdown, including that exact gap, is rejected outright; the
guard does not depend on the window's visibility, so a programmatic caller
is rejected exactly like the menu action.
`test_new_load_is_rejected_while_deferred_close_is_pending` reproduces the
gap deterministically (a monkeypatched `QTimer.singleShot` captures the
retry instead of scheduling it in real time) and verifies no new
thread/worker/token is created and the reader is never invoked a second
time.

## Alternatives Considered

- **`QThreadPool` + `QRunnable`** instead of a dedicated `QThread`: rejected
  for this sprint — a single, named worker with typed signals is simpler
  to reason about and test than a pool for a GUI that only ever has one
  load in flight at a time (concurrent loads are explicitly rejected, see
  Decision below); revisit if a future sprint needs multiple concurrent
  background operations.
- **Byte-level cancellable reads** (reading `read_ogpr()`'s underlying file
  in chunks with a cancellation check between chunks): rejected as
  out-of-scope engineering for this sprint — it would require changing
  `archaeogpr.io.ogpr_reader`, a module this project treats as stable and
  shared with the CLI. The cooperative-cancellation guarantee (a
  cancelled result is never committed) is judged sufficient without it.
- **`sender()`-based stale-result rejection**: tried first, rejected after
  it non-deterministically misidentified fresh results as stale for a
  queued cross-thread connection — Qt's own documentation flags `sender()`
  as unreliable in exactly this situation. The explicit-token-in-signal-
  payload design (Decision item 3) replaced it.
- **Rejecting a second concurrent load with a `QMessageBox`**: considered,
  rejected in favor of silently logging and ignoring the second
  `open_path()` call — the UI already disables File → Open while a load is
  in progress, so this path is only reachable programmatically (e.g. a
  script or test), and a second dialog would be a confusing, unreachable-
  from-the-UI edge case to surface to an interactive user.
- **Bounded blocking `wait()` + `setParent(None)`-on-timeout in
  `closeEvent()`**: this sprint's *first* shutdown design, rejected on
  pre-commit review (see Decision item 8) — a blocking wait on the GUI
  thread during close contradicts the sprint's own responsiveness goal,
  and detaching a still-running `QThread`'s parent does not make it safe
  to abandon (it only stops Qt's object tree from trying to delete it).
  Replaced by the deferred-close design (`event.ignore()` + `hide()` +
  retry `close()` from `_on_load_thread_finished`), which never blocks and
  never destroys anything while the thread is alive.
- **Plain `bool` cancellation flag**: this sprint's *first* cancellation
  design. Reviewed and replaced with `threading.Event` (Decision item 4)
  — not because the `bool` was demonstrated to fail (a direct Python
  attribute write is effectively immediate under CPython's GIL), but
  because that safety is an implicit interpreter detail rather than a
  documented, standard-library guarantee, and the fix is nearly free.

## Consequences

- `src/archaeogpr/gui/workers/file_loader.py` (new) is the one place
  `FileLoadWorker` and `FileLoadState` live.
- `src/archaeogpr/gui/models/dataset_session.py` gained `commit_dataset()`;
  `load()` now delegates to it and remains available for synchronous
  callers.
- `main_window.py` gained the load-state machine, the progress/Cancel UI,
  and a `closeEvent()` override; every other GUI-2 display feature
  (colormap, contrast, A-scan modes, metadata panel, PNG export, cursor/
  selected-trace status) is unchanged by this sprint.
- `app.py`'s `--open --smoke-test` path now pumps the event loop until the
  load reaches a terminal state (bounded by `_SMOKE_TEST_LOAD_TIMEOUT_S`,
  15s) instead of a fixed 5-iteration loop, and maps the outcome
  (`last_load_outcome`) to the process exit code.
- No processing GUI, no background worker *for processing* (only for file
  loading), no undo/redo, no recipe, no 3D — all remain exactly as scoped
  out in [[03_ARCHITECTURE/Processing_Preview_and_Commit_Model]] and
  [[03_ARCHITECTURE/3D_Volume_Data_Model]].

## Validation

- `tests/test_gui.py` (Sprint GUI-1B additions): worker success/failure
  signal tests (no `QThread` involved), a real-background-thread test
  proving `open_path()` never blocks the main thread, two thread-safety
  tests (the reader call runs off the main thread; a genuinely
  QObject-bound slot runs on the main thread), the full
  IDLE/LOADING/CANCELLING/SUCCESS/ERROR/CANCELLED state-machine coverage,
  concurrent-load rejection, progress-bar-always-indeterminate,
  progress-UI-hides-after-each-terminal-state, `--open` exit codes
  (success/invalid-file), dataset/raw-file hash preservation through the
  async path, mid-load state immutability, and the stale-token-rejection
  unit test.
- **Deferred-close fix-round additions**: closing while blocked defers
  destruction (nothing torn down, `QThread` still running, `_close_pending`
  set), close completes once the worker actually finishes (references
  cleared, deferred `close()` retried, cancelled outcome recorded),
  cancellation token set synchronously even while the worker is blocked,
  cleanup is idempotent across repeated calls, an outcome signal alone
  never clears bookkeeping (only `thread.finished` does — this is what
  makes a stale `thread.finished` structurally unable to clear a different,
  active load's references), no "`QThread: Destroyed while thread is still
  running`" warning across a full deferred-close cycle, a normal close
  with no load in flight accepts immediately (the deferred path is never
  entered), and the GUI event loop keeps processing other events/timers
  while a close is pending (proving `closeEvent()` never blocks). See
  [[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]] Validation Results for the
  exact pass count.
- The lambda/DirectConnection crash described in Decision item 2 was
  reproduced, root-caused, and fixed during this sprint's own test-writing
  — not found in review after the fact. The shutdown-lifecycle risk in
  Decision item 8, by contrast, *was* caught by the user's own review of
  the first delivered version, before commit — see that sprint note's
  Issues Discovered for both timelines.

## Related Files

- `src/archaeogpr/gui/workers/file_loader.py`
- `src/archaeogpr/gui/models/dataset_session.py`
- `src/archaeogpr/gui/main_window.py`
- `src/archaeogpr/gui/app.py`
- [[02_SPRINTS/Sprint_GUI_1B_Background_Tasks]]
- [[06_DECISIONS/ADR_001_OpenGPR_Internal_Data_Model]] (the immutability
  guarantee `commit_dataset` extends the same atomic-replace discipline to)
- [[06_DECISIONS/ADR_013_Display_Policy_and_Non_Destructive_Visualization]]
- [[03_ARCHITECTURE/GUI_Architecture]]
