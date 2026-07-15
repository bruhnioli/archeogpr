"""Exceptions raised while reading OpenGPR (.ogpr) files.

Each class corresponds to one failure mode of the binary/header format so
callers (e.g. the CLI) can present a specific, user-facing message instead of
a raw traceback.
"""

from __future__ import annotations


class OGPRError(Exception):
    """Base class for all OpenGPR reader errors."""


class InvalidMagicError(OGPRError):
    """The file does not start with the expected ``ogpr`` magic line."""


class InvalidHeaderError(OGPRError):
    """The header line/JSON block is missing, malformed, or lacks a required field."""


class MissingRadarBlockError(OGPRError):
    """No ``Radar Volume`` entry was found in ``dataBlockDescriptors``."""


class UnsupportedValueTypeError(OGPRError):
    """The radar block declares a ``valueType`` this reader does not know how to decode."""


class TruncatedBlockError(OGPRError):
    """A data block's declared byte range extends beyond the actual file size."""


class InconsistentDimensionsError(OGPRError):
    """A block's declared byte size does not match its declared dimensions/dtype."""


class InvalidGeolocationBlockError(OGPRError):
    """A ``Sample Geolocations`` block is present but its size/record layout is invalid."""
