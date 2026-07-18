"""ArchaeoGPR native desktop viewer (Sprint GUI-1: B-scan/A-scan viewer shell).

No processing (time-zero, dewow, band-pass, background removal, gain) and no
3D/volume code lives here yet -- this package only opens an OpenGPR (.ogpr)
file with the existing, unmodified ``archaeogpr.io``/``archaeogpr.model``
readers and displays it. See ``obsidian/ArchaeoGPR_Vault/02_SPRINTS/`` for the
sprint record and ``obsidian/ArchaeoGPR_Vault/03_ARCHITECTURE/
GUI_Architecture.md`` for the design this implements.
"""

from __future__ import annotations
