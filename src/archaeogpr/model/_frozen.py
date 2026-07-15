"""Shared immutability helpers used by both ``GPRDataset`` and ``ProcessingResult``.

Extracted from ``model/dataset.py`` in Sprint 2 so ``processing/result.py``
can enforce the exact same read-only-array / JSON-serializable-metadata
guarantees without duplicating the logic.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import numpy as np


class FrozenDict(dict):
    """A ``dict`` subclass that blocks mutation but stays a plain dict to everyone else.

    Unlike ``types.MappingProxyType``, this remains ``isinstance(x, dict)``,
    so ``json.dumps(...)`` works directly with no unwrapping. Only the top
    level is protected — nested dicts/lists are ordinary and can still be
    mutated, the same shallow guarantee ``MappingProxyType`` would have given.
    """

    def _read_only(self, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError("this mapping is read-only")

    __setitem__ = _read_only
    __delitem__ = _read_only
    update = _read_only
    pop = _read_only
    popitem = _read_only
    setdefault = _read_only
    clear = _read_only


def freeze_array(name: str, array: np.ndarray | None, *, ndim: int) -> np.ndarray | None:
    """Copy ``array`` and mark the copy read-only, or return ``None`` unchanged.

    Raises ``ValueError`` if ``array`` is neither ``None`` nor an ndarray of
    the expected dimensionality.
    """
    if array is None:
        return None
    if not isinstance(array, np.ndarray):
        raise ValueError(f"{name} must be a numpy.ndarray or None, got {type(array).__name__}")
    if array.ndim != ndim:
        raise ValueError(f"{name} must have {ndim} dimension(s), got shape {array.shape}")
    frozen = array.copy()
    frozen.setflags(write=False)
    return frozen


def freeze_metadata(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate JSON-serializability and return an immutable, plain-dict-like mapping.

    Raises ``ValueError`` if ``metadata`` cannot be serialized with ``json.dumps``.
    """
    try:
        json.dumps(dict(metadata))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"metadata must be JSON-serializable: {exc}") from exc
    return FrozenDict(metadata)
