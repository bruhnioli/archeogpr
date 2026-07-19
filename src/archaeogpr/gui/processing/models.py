"""Data models for the GUI processing registry (Sprint GUI-3A, see ADR-015).

Nothing here duplicates a ``processing/*.py`` algorithm: a
:class:`ParameterSpec` only describes one form field (name/label/kind/unit/
range/default) for a generically-rendered form, and
:class:`ProcessingOperationSpec`'s ``apply``/``validate`` callables are
always one of the small adapter functions in ``adapters.py`` -- never a
``processing/*.py`` function called directly -- so the registry/panel code
never needs to know each function's real keyword-argument names.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from archaeogpr.model.dataset import GPRDataset
from archaeogpr.processing import ProcessingResult

#: ``"bool"`` renders a checkbox, ``"choice"`` a combo box (from
#: :attr:`ParameterSpec.choices`), ``"float"``/``"int"`` a bounded spin box.
ParameterKind = Literal["float", "int", "choice", "bool"]


@dataclass(frozen=True)
class ParameterSpec:
    """One form field -- a single keyword parameter of a real processing function."""

    name: str
    label: str
    kind: ParameterKind
    default: Any
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None
    choices: tuple[str, ...] = ()
    description: str = ""


#: ``(dataset, params, valid_mask) -> ProcessingResult`` -- see ``adapters.py``.
ApplyCallable = Callable[[GPRDataset, dict[str, Any], "np.ndarray | None"], ProcessingResult]
#: ``(params, dataset) -> error_messages`` -- ``dataset`` may be ``None`` (no
#: file open yet); empty tuple means "valid". Runs on the GUI thread, before
#: any worker is started -- see ``adapters.py``.
ValidateCallable = Callable[[dict[str, Any], "GPRDataset | None"], tuple[str, ...]]


@dataclass(frozen=True)
class ProcessingOperationSpec:
    """One registry entry: everything the Processing panel needs for one stable operation."""

    operation_id: str
    display_name: str
    description: str
    parameters: tuple[ParameterSpec, ...]
    #: Whether this operation rewrites ``dataset.time_ns`` (only time-zero
    #: correction does -- see ADR-015 / the processing API audit).
    changes_time_axis: bool
    apply: ApplyCallable = field(repr=False)
    validate: ValidateCallable = field(repr=False)

    def defaults(self) -> dict[str, Any]:
        """A fresh ``{parameter_name: default_value}`` dict -- a form's starting values."""
        return {p.name: p.default for p in self.parameters}
