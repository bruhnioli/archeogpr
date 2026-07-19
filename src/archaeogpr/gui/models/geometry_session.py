"""GUI-side session state for Sprint 3D-0's Survey Geometry Inspector.

Deliberately a separate session object from
:class:`~archaeogpr.gui.models.dataset_session.DatasetSession`, not a new
field bolted onto it (see ``ADR_016_Geometry_Provenance_and_Readiness_
Gates.md``): geometry state is orthogonal to raw/current/preview processing
state. A processing preview/apply/discard/reset-to-raw never touches this
class at all -- geometry is resolved once per file load
(:meth:`GeometrySession.resolve_for_new_dataset`) and stays exactly as it
was through every subsequent processing transition, because none of the
five registered processing operations change the trace or channel count.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from archaeogpr.geometry import GeometryOverrides, GeometryResolution, resolve_survey_geometry
from archaeogpr.geometry.models import CoordinateMode, ReadinessGates, SurveyGeometry
from archaeogpr.model.dataset import GPRDataset


@dataclass
class GeometrySession:
    """Resolved geometry + pending/applied overrides for the currently-open file.

    ``pending_overrides`` is what the override form is currently showing
    (may differ from ``applied_overrides`` while the user is mid-edit);
    ``applied_overrides`` is what :attr:`resolution` was actually resolved
    with. Applying always re-resolves atomically and bumps
    :attr:`geometry_revision` -- it never mutates ``resolution`` in place.
    """

    resolution: GeometryResolution | None = field(default=None)
    pending_overrides: GeometryOverrides = field(default_factory=GeometryOverrides)
    applied_overrides: GeometryOverrides = field(default_factory=GeometryOverrides)
    geometry_revision: int = 0

    @property
    def geometry(self) -> SurveyGeometry | None:
        return self.resolution.geometry if self.resolution is not None else None

    @property
    def readiness(self) -> ReadinessGates | None:
        return self.resolution.readiness if self.resolution is not None else None

    @property
    def coordinate_mode(self) -> CoordinateMode | None:
        geometry = self.geometry
        return geometry.coordinate_mode if geometry is not None else None

    @property
    def has_pending_changes(self) -> bool:
        """``True`` if the override form has edits not yet applied."""
        return self.pending_overrides != self.applied_overrides

    def resolve_for_new_dataset(self, dataset: GPRDataset) -> None:
        """Reset all overrides and resolve geometry fresh. Called once per successful file load.

        A new file means a new survey -- any overrides entered for a
        *previous* file's missing metadata must not silently carry over and
        be misapplied to a different dataset.
        """
        self.pending_overrides = GeometryOverrides()
        self.applied_overrides = GeometryOverrides()
        self.geometry_revision = 0
        self.resolution = resolve_survey_geometry(
            dataset, self.applied_overrides, geometry_revision=self.geometry_revision
        )

    def stage_override(self, **changes: object) -> None:
        """Update the pending (not-yet-applied) override values shown in the form."""
        self.pending_overrides = replace(self.pending_overrides, **changes)  # type: ignore[arg-type]

    def apply_overrides(self, dataset: GPRDataset) -> tuple[str, ...]:
        """Validate and, if valid, atomically apply :attr:`pending_overrides`.

        Returns validation error messages (empty tuple means success and
        that :attr:`resolution` was just re-resolved with the new
        overrides, bumping :attr:`geometry_revision`). Never touches
        ``dataset`` itself, its ``metadata``, or ``processing_history``.
        """
        errors = self.pending_overrides.validate()
        if errors:
            return errors
        self.applied_overrides = self.pending_overrides
        self.geometry_revision += 1
        self.resolution = resolve_survey_geometry(
            dataset, self.applied_overrides, geometry_revision=self.geometry_revision
        )
        return ()

    def discard_pending_overrides(self) -> None:
        """Reset the override form back to whatever is currently applied (or file metadata, if none)."""
        self.pending_overrides = self.applied_overrides

    def reset_to_file_metadata(self, dataset: GPRDataset) -> None:
        """Clear every override (pending and applied) and re-resolve from file metadata alone."""
        self.pending_overrides = GeometryOverrides()
        self.applied_overrides = GeometryOverrides()
        self.geometry_revision += 1
        self.resolution = resolve_survey_geometry(
            dataset, self.applied_overrides, geometry_revision=self.geometry_revision
        )
