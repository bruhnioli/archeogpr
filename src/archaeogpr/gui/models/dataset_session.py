"""GUI-side session state: which dataset/channel/trace is currently shown.

Axis-semantics decision (see also ``obsidian/ArchaeoGPR_Vault/02_SPRINTS/
Sprint_GUI_1_Viewer_Shell.md`` and ``03_ARCHITECTURE/GUI_Architecture.md``):
``GPRDataset.amplitudes`` is ``(slice, channel, sample)`` (ADR-001). For this
project's survey geometry, ``slice`` is the along-track acquisition index --
i.e. each "slice" *is* one trace/A-scan position along the survey line, not a
depth/time slice and not a separate physical axis a user would want a second,
independent selector for. ``src/archaeogpr/qc/bscan.py`` already treats it
this way: ``plot_bscan`` indexes ``dataset.amplitudes[:, channel, :]`` (shape
``(slice, sample)``) and plots it with the slice axis as the along-track
(horizontal) axis of one channel's B-scan.

Consequently this GUI deliberately has **no "slice selector"** as a concept
distinct from trace selection -- that would double-expose the same physical
axis under two different names and controls. Instead:

- a **channel selector** picks which of the ``channels_count`` antennas/
  channels to view (a real, independent physical axis), and
- a **selected trace** (an index into the slice axis) is chosen by clicking
  on the B-scan, exactly as "which along-track position is the A-scan panel
  currently showing".

**Raw / Current / Preview (Sprint GUI-3A, see ADR-015)**: ``DatasetSession``
now tracks three separate, independently-referenced ``GPRDataset`` values,
never three copies of the same array data (``GPRDataset`` is immutable --
ADR-001 -- so holding the same object under multiple names is always safe):

- :attr:`raw_dataset` -- exactly what :func:`archaeogpr.io.ogpr_reader.read_ogpr`
  returned for the currently-open file. Set once, on file load
  (:meth:`commit_dataset`); never reassigned by any processing operation.
- :attr:`current_dataset` -- the dataset the rest of the GUI (B-scan/A-scan/
  metadata/export) treats as "the" dataset when no preview is being
  inspected; this is what :attr:`dataset` (kept for backwards compatibility
  with GUI-1/GUI-2/GUI-1B code that predates this split) returns. Only ever
  replaced by :meth:`apply_preview` or :meth:`reset_to_raw` -- both atomic,
  both bump :attr:`current_revision`.
- :attr:`preview_dataset` -- a processing result computed against
  :attr:`current_dataset` but not yet committed; never touched by anything
  outside :meth:`set_preview`/:meth:`apply_preview`/:meth:`discard_preview`.

:attr:`current_valid_mask` threads a processing ``ProcessingResult.valid_mask``
across chained operations exactly like ``cli.py``'s ``sprint2`` pipeline does
(e.g. time-zero's padding mask feeding into DC-offset) -- see ADR-015. It is
``None`` whenever :attr:`current_dataset` is the raw, freshly-read dataset
(freshly-read data has no padding to mask).

:attr:`current_revision` is the stale-preview guard (see ADR-015): every
:meth:`apply_preview`/:meth:`reset_to_raw` call increments it, and a preview
records the revision it was computed against
(:attr:`preview_base_revision`) -- :meth:`apply_preview` refuses to commit a
preview that no longer matches the current revision.

``DatasetSession`` remains a thin, mutable container -- not a
processing/undo framework (a full undo/redo stack and recipe system are
still deferred; see ``Processing_Preview_and_Commit_Model.md`` and
ADR-015's Alternatives Considered). It never mutates a ``GPRDataset``'s
``amplitudes``/``processing_history`` in place (still immutable/read-only
per ADR-001) -- every transition here reassigns which *object* a field
points to, never edits one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from archaeogpr.io.ogpr_reader import read_ogpr
from archaeogpr.model.dataset import GPRDataset


@dataclass
class DatasetSession:
    """Current GUI view state: raw/current/preview datasets, one channel, one selected trace."""

    raw_dataset: GPRDataset | None = field(default=None)
    current_dataset: GPRDataset | None = field(default=None)
    preview_dataset: GPRDataset | None = field(default=None)
    #: ``ProcessingResult.valid_mask`` belonging to :attr:`current_dataset` --
    #: ``None`` for the raw dataset, otherwise whatever the operation that
    #: produced :attr:`current_dataset` returned (see module docstring).
    current_valid_mask: np.ndarray | None = field(default=None)
    #: The ``ProcessingResult.valid_mask`` that would become
    #: :attr:`current_valid_mask` if :attr:`preview_dataset` is applied.
    preview_valid_mask: np.ndarray | None = field(default=None)
    source_path: Path | None = field(default=None)
    selected_channel: int = 0
    selected_trace: int | None = None
    #: Bumped by :meth:`apply_preview`/:meth:`reset_to_raw`; also the value a
    #: preview was computed against -- see :attr:`preview_base_revision`.
    current_revision: int = 0
    #: The :attr:`current_revision` a not-yet-applied :attr:`preview_dataset`
    #: was computed against, or ``None`` if there is no preview. See
    #: :meth:`has_fresh_preview`.
    preview_base_revision: int | None = None

    @property
    def dataset(self) -> GPRDataset | None:
        """Backwards-compatible alias for :attr:`current_dataset`.

        Everything written before Sprint GUI-3A (``main_window.py``'s
        display/export code, ``tests/test_gui.py``) reads ``session.dataset``
        -- this alias means none of that code needs to know raw/current/
        preview exist at all; it always sees exactly the dataset GUI-1/
        GUI-2/GUI-1B would have shown it.
        """
        return self.current_dataset

    @dataset.setter
    def dataset(self, value: GPRDataset | None) -> None:
        """Setter kept for pre-GUI-3A call sites that assign ``session.dataset = ...`` directly.

        Sets :attr:`raw_dataset` to the same value -- pre-GUI-3A code has no
        concept of a separate raw dataset, so this preserves the invariant
        that :attr:`raw_dataset` is never ``None`` once a dataset has been
        assigned by any means. Does not touch channel/trace selection or
        revision counters (unlike :meth:`commit_dataset`); existing callers
        manage those themselves.
        """
        self.current_dataset = value
        self.raw_dataset = value

    @property
    def is_loaded(self) -> bool:
        return self.current_dataset is not None

    @property
    def channel_count(self) -> int:
        return self.current_dataset.shape[1] if self.current_dataset is not None else 0

    @property
    def trace_count(self) -> int:
        """Number of along-track traces -- ``dataset.amplitudes.shape[0]`` (the "slice" axis)."""
        return self.current_dataset.shape[0] if self.current_dataset is not None else 0

    @property
    def sample_count(self) -> int:
        return self.current_dataset.shape[2] if self.current_dataset is not None else 0

    @property
    def has_fresh_preview(self) -> bool:
        """``True`` iff a preview exists and was computed against the *current* committed revision.

        A preview computed against an older revision (because the user
        applied a different operation, or reset to raw, after the preview
        was produced but before it was applied) is stale -- see ADR-015 --
        and must never be applied. This is the one property both the
        Processing panel's "Apply Preview" enablement and
        :meth:`apply_preview` itself rely on.
        """
        return self.preview_dataset is not None and self.preview_base_revision == self.current_revision

    def load(self, path: str | Path) -> None:
        """Read ``path`` as an OpenGPR file (synchronously) and replace the current session.

        Reads fully into a local variable via the existing, unmodified
        :func:`archaeogpr.io.ogpr_reader.read_ogpr` before touching ``self``
        -- if reading raises (any ``OGPRError`` subclass, or an ``OSError``
        for a missing/unreadable file), this session's previous
        dataset/channel/trace are left completely untouched, so a failed
        open never leaves a half-updated session. The file is opened
        read-only by the reader (never written to) -- see
        ``archaeogpr.io.ogpr_reader`` / CLAUDE.md's raw-data-read-only rule.

        Blocks the calling thread for the duration of the read. The GUI
        itself no longer calls this directly (see ``GUI-1B``,
        ``archaeogpr.gui.workers.file_loader.FileLoadWorker`` /
        :meth:`commit_dataset`) -- ``load`` remains here for any
        synchronous/non-GUI caller (e.g. tests, scripts) that wants the same
        atomic-replace behavior without a background thread.
        """
        resolved_path = Path(path).resolve()
        dataset = read_ogpr(resolved_path)  # raises before any attribute below is touched
        self.commit_dataset(dataset, resolved_path)

    def commit_dataset(self, dataset: GPRDataset, source_path: Path) -> None:
        """Atomically replace the current session with an already-loaded dataset.

        The GUI-1B background loader (``FileLoadWorker``) does the actual
        disk read/parse off the Qt main thread; once it reports success,
        ``MainWindow`` calls this method -- on the main thread -- to commit
        the result. This is the one place session state actually changes for
        a new file, whether the read happened synchronously (:meth:`load`)
        or via the background worker.

        A new file resets the raw/current/preview split entirely: the
        freshly-read dataset becomes both :attr:`raw_dataset` and
        :attr:`current_dataset` (there is no processing history yet --
        they're the same object), any in-flight preview from a *previous*
        file is discarded, and :attr:`current_revision` resets to ``0``
        (Sprint GUI-3A processing revisions are scoped to one open file, not
        carried across a new load).
        """
        self.raw_dataset = dataset
        self.current_dataset = dataset
        self.preview_dataset = None
        self.current_valid_mask = None
        self.preview_valid_mask = None
        self.current_revision = 0
        self.preview_base_revision = None
        self.source_path = source_path
        self.selected_channel = 0
        self.selected_trace = 0 if dataset.shape[0] > 0 else None

    def set_preview(self, dataset: GPRDataset, valid_mask: np.ndarray | None) -> None:
        """Record a freshly-computed, not-yet-committed processing result.

        Tags it with :attr:`current_revision` at the moment it was computed
        (:attr:`preview_base_revision`) -- this is what lets
        :attr:`has_fresh_preview`/:meth:`apply_preview` detect a stale
        preview later. Never touches :attr:`current_dataset`.
        """
        self.preview_dataset = dataset
        self.preview_valid_mask = valid_mask
        self.preview_base_revision = self.current_revision

    def discard_preview(self) -> None:
        """Drop the current preview (if any). :attr:`current_dataset` is untouched."""
        self.preview_dataset = None
        self.preview_valid_mask = None
        self.preview_base_revision = None

    def apply_preview(self) -> None:
        """Atomically commit the current preview as the new :attr:`current_dataset`.

        Raises ``ValueError`` if there is no preview, or if it is stale
        (:attr:`has_fresh_preview` is ``False``) -- callers (the Processing
        panel's "Apply Preview" button) are expected to only ever call this
        when :attr:`has_fresh_preview` is already ``True``, so this is a
        defensive assertion, not a user-facing validation path.
        """
        if not self.has_fresh_preview:
            raise ValueError("No fresh preview to apply -- it is missing or stale")
        assert self.preview_dataset is not None
        self.current_dataset = self.preview_dataset
        self.current_valid_mask = self.preview_valid_mask
        self.current_revision += 1
        self.preview_dataset = None
        self.preview_valid_mask = None
        self.preview_base_revision = None

    def reset_to_raw(self) -> None:
        """Discard the entire committed processing chain; :attr:`current_dataset` becomes the raw read.

        Not undo/redo (see ADR-015): this collapses straight back to
        :attr:`raw_dataset`, it does not step back one operation at a time.
        Any in-flight preview is discarded (it was computed against a
        dataset that, after this call, is no longer the current one).
        """
        if self.raw_dataset is None:
            return
        self.current_dataset = self.raw_dataset
        self.current_valid_mask = None
        self.current_revision += 1
        self.preview_dataset = None
        self.preview_valid_mask = None
        self.preview_base_revision = None

    def clamp_channel(self, channel: int) -> int:
        """Clamp ``channel`` into ``[0, channel_count)``; 0 if no dataset is loaded."""
        if self.channel_count == 0:
            return 0
        return max(0, min(channel, self.channel_count - 1))

    def clamp_trace(self, trace: int) -> int:
        """Clamp ``trace`` into ``[0, trace_count)``; 0 if no dataset is loaded."""
        if self.trace_count == 0:
            return 0
        return max(0, min(trace, self.trace_count - 1))
