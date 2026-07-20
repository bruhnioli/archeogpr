"""archaeogpr: read, validate, and QC OpenGPR (.ogpr) ground-penetrating radar data.

Sprint 1 scope: file reading, data modeling, metadata/QC extraction, and basic
exports only. No signal-processing algorithms (time-zero, dewow, gain,
migration, ...) are implemented yet — see CLAUDE.md.
"""

from archaeogpr.io.ogpr_reader import read_ogpr, read_ogpr_header
from archaeogpr.model.dataset import GPRDataset

__version__ = "0.5.0"

__all__ = ["read_ogpr", "read_ogpr_header", "GPRDataset", "__version__"]
