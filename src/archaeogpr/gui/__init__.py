"""ArchaeoGPR native desktop viewer (Sprint GUI-1: B-scan/A-scan viewer shell).

Non-destructive processing preview & apply for five stable
``archaeogpr.processing`` functions (time-zero, DC offset, dewow, band-pass,
background removal) was added in Sprint GUI-3A -- see ``gui/processing/``
and ``gui/workers/processing_worker.py``. No gain and no 3D/volume code
lives here yet. This package only ever calls the existing, unmodified
``archaeogpr.io``/``archaeogpr.model``/``archaeogpr.processing`` functions
(via a thin adapter layer for processing -- see
``obsidian/ArchaeoGPR_Vault/06_DECISIONS/
ADR_015_GUI_Processing_Preview_and_Atomic_Apply.md``), never reimplementing
them. See ``obsidian/ArchaeoGPR_Vault/02_SPRINTS/`` for the sprint records
and ``obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/GUI_Architecture.md`` for
the design this implements.
"""

from __future__ import annotations
