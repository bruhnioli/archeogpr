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

``DatasetSession`` is intentionally a thin, mutable container -- not a
processing/undo framework (that design is deferred; see
``Processing_Preview_and_Commit_Model.md``). It never mutates
``GPRDataset.amplitudes`` (still immutable/read-only per ADR-001); it only
tracks *which* view of the read-only dataset the GUI is currently showing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from archaeogpr.io.ogpr_reader import read_ogpr
from archaeogpr.model.dataset import GPRDataset


@dataclass
class DatasetSession:
    """Current GUI view state: one dataset, one channel, one selected trace."""

    dataset: GPRDataset | None = field(default=None)
    source_path: Path | None = field(default=None)
    selected_channel: int = 0
    selected_trace: int | None = None

    @property
    def is_loaded(self) -> bool:
        return self.dataset is not None

    @property
    def channel_count(self) -> int:
        return self.dataset.shape[1] if self.dataset is not None else 0

    @property
    def trace_count(self) -> int:
        """Number of along-track traces -- ``dataset.amplitudes.shape[0]`` (the "slice" axis)."""
        return self.dataset.shape[0] if self.dataset is not None else 0

    @property
    def sample_count(self) -> int:
        return self.dataset.shape[2] if self.dataset is not None else 0

    def load(self, path: str | Path) -> None:
        """Read ``path`` as an OpenGPR file and replace the current session.

        Reads fully into local variables via the existing, unmodified
        :func:`archaeogpr.io.ogpr_reader.read_ogpr` before touching ``self``
        -- if reading raises (any ``OGPRError`` subclass, or an ``OSError``
        for a missing/unreadable file), this session's previous
        dataset/channel/trace are left completely untouched, so a failed
        open never leaves a half-updated session. The file is opened
        read-only by the reader (never written to) -- see
        ``archaeogpr.io.ogpr_reader`` / CLAUDE.md's raw-data-read-only rule.

        TODO: GUI-1B: file loading background worker -- this sprint loads
        synchronously (see ``Sprint_GUI_1_Viewer_Shell.md``: acceptable for
        the ~8 MB reference sample; a worker thread is deferred, not
        forgotten).
        """
        resolved_path = Path(path).resolve()
        dataset = read_ogpr(resolved_path)  # raises before any attribute below is touched

        self.dataset = dataset
        self.source_path = resolved_path
        self.selected_channel = 0
        self.selected_trace = 0 if dataset.shape[0] > 0 else None

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
