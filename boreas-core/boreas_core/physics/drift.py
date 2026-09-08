"""Numerical integration of the iceberg force balance into a drift trajectory.

Position is integrated in a local metres tangent-plane (standard for
short-to-medium-range drift forecasts of days-to-weeks, where curvature of
the Earth within the displacement is negligible) and converted back to
lon/lat at each step using the local metres-per-degree scale factors.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from .forces import (
    DEFAULT_AIR_DRAG_COEFFICIENT,
    DEFAULT_WATER_DRAG_COEFFICIENT,
    net_acceleration,
)
from .geometry import IcebergGeometry

METRES_PER_DEGREE_LAT = 111_320.0

# A (wind_velocity, current_velocity) pair in m/s, each as [u_east, v_north].
ForcingFn = Callable[[float, float, float], tuple[np.ndarray, np.ndarray]]


def metres_per_degree_lon(latitude_deg: float) -> float:
    return METRES_PER_DEGREE_LAT * np.cos(np.radians(latitude_deg))


@dataclass
class DriftState:
    time_s: np.ndarray
    lon: np.ndarray
    lat: np.ndarray
    velocity: np.ndarray  # (N, 2) m/s, [u_east, v_north]

    @property
    def track(self) -> list[tuple[float, float]]:
        """[(lon, lat), ...] for plotting / API responses."""
        return list(zip(self.lon.tolist(), self.lat.tolist(), strict=True))


@dataclass
class PhysicsDriftModel:
    """Force-balance drift model: wind drag + water drag + Coriolis."""

    geometry: IcebergGeometry
    air_drag_coefficient: float = DEFAULT_AIR_DRAG_COEFFICIENT
    water_drag_coefficient: float = DEFAULT_WATER_DRAG_COEFFICIENT
    residual_correction: Callable[[dict], np.ndarray] | None = field(
        default=None, repr=False
    )

    def _acceleration(
        self,
        velocity: np.ndarray,
        wind: np.ndarray,
        current: np.ndarray,
        lat: float,
    ) -> np.ndarray:
        return net_acceleration(
            iceberg_velocity=velocity,
            wind_velocity=wind,
            current_velocity=current,
            latitude_deg=lat,
            mass_kg=self.geometry.mass_kg,
            sail_area_m2=self.geometry.sail_area_m2,
            draft_area_m2=self.geometry.draft_area_m2,
            air_drag_coefficient=self.air_drag_coefficient,
            water_drag_coefficient=self.water_drag_coefficient,
        )

    def simulate(
        self,
        *,
        start_lon: float,
        start_lat: float,
        start_velocity: np.ndarray,
        forcing_fn: ForcingFn,
        duration_hours: float,
        dt_seconds: float = 900.0,
    ) -> DriftState:
        """RK4-integrate the trajectory under time-varying wind/current forcing.

        Args:
            forcing_fn: called as ``forcing_fn(t_seconds, lon, lat)`` and must
                return ``(wind_velocity, current_velocity)`` in m/s.
        """
        n_steps = max(1, int(duration_hours * 3600 / dt_seconds))
        times = np.zeros(n_steps + 1)
        lons = np.zeros(n_steps + 1)
        lats = np.zeros(n_steps + 1)
        velocities = np.zeros((n_steps + 1, 2))

        lon, lat = start_lon, start_lat
        velocity = np.array(start_velocity, dtype=float)
        lons[0], lats[0], velocities[0] = lon, lat, velocity

        for i in range(1, n_steps + 1):
            t = (i - 1) * dt_seconds
            wind, current = forcing_fn(t, lon, lat)

            # RK4 on velocity (position is then advanced with the RK4-averaged velocity)
            k1_v = self._acceleration(velocity, wind, current, lat)
            k1_x = velocity

            k2_v = self._acceleration(velocity + 0.5 * dt_seconds * k1_v, wind, current, lat)
            k2_x = velocity + 0.5 * dt_seconds * k1_v

            k3_v = self._acceleration(velocity + 0.5 * dt_seconds * k2_v, wind, current, lat)
            k3_x = velocity + 0.5 * dt_seconds * k2_v

            k4_v = self._acceleration(velocity + dt_seconds * k3_v, wind, current, lat)
            k4_x = velocity + dt_seconds * k3_v

            velocity = velocity + (dt_seconds / 6.0) * (k1_v + 2 * k2_v + 2 * k3_v + k4_v)
            displacement_m = (dt_seconds / 6.0) * (k1_x + 2 * k2_x + 2 * k3_x + k4_x)

            if self.residual_correction is not None:
                correction = self.residual_correction(
                    {
                        "velocity": velocity,
                        "wind": wind,
                        "current": current,
                        "lat": lat,
                        "lon": lon,
                        "geometry": self.geometry,
                    }
                )
                velocity = velocity + correction
                displacement_m = displacement_m + correction * dt_seconds

            lon = lon + displacement_m[0] / metres_per_degree_lon(lat)
            lat = lat + displacement_m[1] / METRES_PER_DEGREE_LAT

            times[i] = t + dt_seconds
            lons[i] = lon
            lats[i] = lat
            velocities[i] = velocity

        return DriftState(time_s=times, lon=lons, lat=lats, velocity=velocities)


def constant_forcing(wind_velocity: np.ndarray, current_velocity: np.ndarray) -> ForcingFn:
    """A forcing function that ignores (t, lon, lat) and returns fixed fields.

    Useful for short-horizon forecasts where reanalysis fields are
    approximated as locally constant over the forecast window.
    """

    def _forcing(_t: float, _lon: float, _lat: float) -> tuple[np.ndarray, np.ndarray]:
        return np.array(wind_velocity, dtype=float), np.array(current_velocity, dtype=float)

    return _forcing
