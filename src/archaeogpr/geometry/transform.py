"""Local-to-global coordinate transform, shared by ``resolve.py`` and ``regularity.py``.

Kept in its own module (rather than living in ``resolve.py``, where it was
first needed) so both the resolver and the rectilinear-fit checker
(:mod:`archaeogpr.geometry.regularity`) can import it without a circular
import between the two.
"""

from __future__ import annotations

import math

import numpy as np

from archaeogpr.geometry.models import CrossTrackDirection

__all__ = ["project_global_from_local"]


def project_global_from_local(
    along_track: np.ndarray,
    cross_track: np.ndarray,
    origin_x: float,
    origin_y: float,
    azimuth_deg: float,
    cross_track_direction: CrossTrackDirection,
) -> tuple[np.ndarray, np.ndarray]:
    """The section-9 azimuth transform: local (s, c) grid -> global (E, N) grid.

    ``azimuth_deg`` is degrees clockwise from grid north. For
    ``CHANNEL_ASCENDING_RIGHT``: ``E = E0 + s*sin(th) + c*cos(th)``,
    ``N = N0 + s*cos(th) - c*sin(th)``. For ``CHANNEL_ASCENDING_LEFT`` the
    cross-track term's sign is flipped. Never called with
    ``CrossTrackDirection.UNKNOWN`` -- see the caller in
    :func:`archaeogpr.geometry.resolve.resolve_survey_geometry`.
    """
    theta = math.radians(azimuth_deg)
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    s_grid = along_track[:, np.newaxis]
    c_grid = cross_track[np.newaxis, :]
    sign = 1.0 if cross_track_direction is CrossTrackDirection.CHANNEL_ASCENDING_RIGHT else -1.0
    x_coordinates = origin_x + s_grid * sin_t + sign * c_grid * cos_t
    y_coordinates = origin_y + s_grid * cos_t - sign * c_grid * sin_t
    return x_coordinates, y_coordinates
