"""Deterministic fallback rule for graceful degradation (BOREAS design doc §5.4).

When `ConfidenceScorer` flags a forecast as degraded (out-of-distribution
inputs, or a wide ensemble spread), the routing engine must not silently keep
trusting the ML output. Instead it substitutes a conservative, physically
bounded hazard buffer around the last confirmed observation: it will never be
more precise than the ML forecast, but it fails safe rather than failing
silently.
"""

from dataclasses import dataclass

import numpy as np

# A conservative upper bound on Antarctic iceberg/current-driven drift speed
# used only for the fallback buffer, not the physics model itself (see
# physics/forces.py for the real drift dynamics).
MAX_PLAUSIBLE_DRIFT_SPEED_MS = 1.5


@dataclass
class ConservativeBuffer:
    center_lon: float
    center_lat: float
    radius_km: float
    valid_for_hours: float


def conservative_buffer_forecast(
    *,
    last_lon: float,
    last_lat: float,
    hours_since_observation: float,
    base_safety_margin_km: float = 5.0,
) -> ConservativeBuffer:
    """A worst-case circular exclusion zone, independent of any model output.

    radius = safety margin + (max plausible drift speed) * (time elapsed),
    so the buffer grows the longer it has been since the object was last
    confidently located -- exactly the behaviour an operator expects from a
    system admitting "I don't trust my own forecast right now."
    """
    if hours_since_observation < 0:
        raise ValueError("hours_since_observation must be non-negative.")
    growth_km = MAX_PLAUSIBLE_DRIFT_SPEED_MS * hours_since_observation * 3600 / 1000.0
    radius_km = base_safety_margin_km + growth_km
    return ConservativeBuffer(
        center_lon=last_lon,
        center_lat=last_lat,
        radius_km=radius_km,
        valid_for_hours=hours_since_observation,
    )


def buffer_contains_point(buffer: ConservativeBuffer, lon: float, lat: float) -> bool:
    """Great-circle-ish (equirectangular, fine at buffer scale) containment check."""
    lat_scale = 111.32
    lon_scale = 111.32 * np.cos(np.radians(buffer.center_lat))
    dx_km = (lon - buffer.center_lon) * lon_scale
    dy_km = (lat - buffer.center_lat) * lat_scale
    return bool(np.hypot(dx_km, dy_km) <= buffer.radius_km)
