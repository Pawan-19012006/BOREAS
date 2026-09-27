"""Spatial synoptic weather field for the mission domain.

WHY THIS EXISTS
---------------
`environment.py` produces ONE `EnvironmentalForecastPoint` per horizon -- a
single scalar synoptic state with no position -- and `mission/fields.py` spread
it over the domain with a latitude-only factor. That is enough to say "the
Southern Ocean is rougher than the sub-tropics", but it cannot support weather
hotspots or weather-driven route avoidance: a latitude band spans every
longitude, so no lateral deviation can ever reduce a route's weather cost.

This module adds the missing spatial structure by placing a small number of
deterministic low-pressure systems that track eastward across the domain as the
forecast horizon advances, which is the dominant Southern Ocean synoptic
pattern. The existing scalar forecast is kept as the BACKGROUND state, so
`/forecast/environment` keeps its meaning and its contract; the cyclones are
anomalies on top of it.

PROVENANCE -- READ THIS
-----------------------
This is SIMULATED weather. No real forecast provider (ERA5, GFS, ECMWF,
Open-Meteo) is connected to BOREAS, so nothing here is, or may be presented as,
a measurement or a real forecast. It is deterministic, reproducible and
physically shaped, and that is all it claims to be. `WEATHER_PROVENANCE` and the
`DEMO` weather status exist so this never reaches an operator as real data.

Known prototype simplifications, stated rather than hidden:
  * Wind peaks AT the centre of each low. A real cyclone has a calm eye with a
    peak-wind annulus around it. Peak-at-centre keeps a hotspot's centroid the
    same point as its worst weather, which is what makes the map legible.
  * Systems translate along a fixed latitude at a constant speed. They neither
    deepen, decay, nor recurve.
  * Wave height is diagnosed from local wind, with no fetch, duration or swell
    propagation.
"""

import math
from dataclasses import dataclass

import numpy as np

from .environment import EnvironmentalForecastEngine
from .models import EnvironmentalForecastPoint

WEATHER_PROVENANCE = "SIMULATED SYNOPTIC POLAR FORECAST — NOT A REAL WEATHER FEED"

# Eastward translation speed of a Southern Ocean low, in degrees of longitude
# per hour (~0.38 deg/h is ~500 km/day at 60S).
SYSTEM_DRIFT_DEG_LON_PER_HOUR = 0.38


@dataclass(frozen=True)
class CycloneSystem:
    """One simulated low-pressure system at a given forecast horizon."""

    system_id: str
    lon: float
    lat: float
    radius_km: float
    peak_wind_kt: float
    central_pressure_hpa: float


# Seed systems at T+0. Longitudes are spaced so the domain (-10..95E) holds two
# or three of them at any horizon, and latitudes sit in the westerly belt where
# Southern Ocean lows actually track. Deliberately a fixed, readable table
# rather than a random draw: the same mission must always plan the same way.
_SEED_SYSTEMS: tuple[tuple[str, float, float, float, float, float], ...] = (
    # (id, lon0, lat, radius_km, peak_wind_kt, central_pressure_hpa)
    # LOW_A and LOW_B are seeded on the two mission corridors (Cape Town ->
    # Maitri runs down ~12-18E; Cape Town -> Bharati crosses ~50E around 50S),
    # so the hazard is live at T+0 rather than only appearing at later horizons.
    # This is scenario placement for a prototype, exactly like the seeded iceberg
    # roster -- it is not a claim that a low is really there.
    ("LOW_A", 14.0, -52.0, 560.0, 54.0, 982.0),
    ("LOW_B", 52.0, -50.0, 600.0, 57.0, 978.0),
    ("LOW_C", -16.0, -45.0, 480.0, 39.0, 990.0),
    ("LOW_D", 78.0, -60.0, 540.0, 47.0, 984.0),
)

_engine = EnvironmentalForecastEngine()


def background_state(horizon_hours: int, base_time=None) -> EnvironmentalForecastPoint:
    """The existing scalar synoptic forecast, unchanged, used as the background
    on which the systems below are superimposed."""
    return _engine.predict_at_horizon(horizon_hours=horizon_hours, base_time=base_time)


def systems_at(horizon_hours: int) -> list[CycloneSystem]:
    """Where each simulated low sits at T+horizon.

    Systems translate east at a constant rate. Longitude is wrapped into
    [-180, 180) so a system leaving the eastern edge of the domain does not
    reappear as an absurd coordinate.
    """
    h = float(max(0, horizon_hours))
    out: list[CycloneSystem] = []
    for sid, lon0, lat, radius, wind, pressure in _SEED_SYSTEMS:
        lon = lon0 + SYSTEM_DRIFT_DEG_LON_PER_HOUR * h
        lon = (lon + 180.0) % 360.0 - 180.0
        out.append(
            CycloneSystem(
                system_id=sid,
                lon=float(lon),
                lat=float(lat),
                radius_km=float(radius),
                peak_wind_kt=float(wind),
                central_pressure_hpa=float(pressure),
            )
        )
    return out


def _influence(lon, lat, system: CycloneSystem) -> np.ndarray:
    """Smooth 0-1 radial influence of a system, 1 at the centre and reaching ~0
    at its radius. Gaussian rather than linear so the resulting severity field
    has no hard edges for the hotspot clustering to trip over."""
    # Local equirectangular metric -- adequate at this grid resolution and far
    # cheaper than haversine over a whole grid per system.
    dlon = (np.asarray(lon, dtype=float) - system.lon) * np.cos(math.radians(system.lat))
    dlat = np.asarray(lat, dtype=float) - system.lat
    km_per_deg = 111.32
    d_km = km_per_deg * np.sqrt(dlon**2 + dlat**2)
    return np.exp(-((d_km / (0.6 * system.radius_km)) ** 2))


@dataclass
class WeatherField:
    """Per-location weather at one horizon. Every array broadcasts to the shape
    of the (lon, lat) query."""

    wind_kt: np.ndarray
    wave_m: np.ndarray
    visibility_nm: np.ndarray
    pressure_hpa: np.ndarray
    background: EnvironmentalForecastPoint
    systems: list[CycloneSystem]
    provenance: str = WEATHER_PROVENANCE


def latitude_weather_factor(lat) -> np.ndarray:
    """Prototype spatial scaling of the background synoptic state: strongest in
    the westerly belt, weaker toward the coast and the sub-tropics.

    Unchanged from the original `mission/fields.py` helper -- it still shapes the
    BACKGROUND field. It is the cyclone systems, not this, that give the field
    the longitudinal structure a route can actually steer around."""
    return np.interp(lat, [-71.0, -65.0, -60.0, -40.0, -33.0], [0.6, 0.8, 1.0, 1.0, 0.7])


def evaluate_weather(
    lon,
    lat,
    horizon_hours: int,
    *,
    base_time=None,
    background: EnvironmentalForecastPoint | None = None,
) -> WeatherField:
    """Background synoptic state plus the simulated low-pressure systems.

    Pass `background` to reuse a synoptic state that has already been computed
    (the mission planner passes its hazard snapshot's own `env`), so the routing
    cost field and the reported environmental state cannot drift apart.
    """
    bg = background if background is not None else background_state(horizon_hours, base_time=base_time)
    systems = systems_at(horizon_hours)

    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    shape = np.broadcast(lon, lat).shape

    wf = latitude_weather_factor(lat)
    wind = np.broadcast_to(bg.wind_speed_kt * wf, shape).astype(float).copy()
    wave = np.broadcast_to(bg.wave_height_m * wf, shape).astype(float).copy()
    vis = np.broadcast_to(float(bg.visibility_nm), shape).astype(float).copy()
    pressure = np.broadcast_to(float(bg.pressure_hpa), shape).astype(float).copy()

    for s in systems:
        w = _influence(lon, lat, s)
        # A system raises wind toward its peak rather than adding to the
        # background, so overlapping systems cannot stack into impossible winds.
        wind = np.maximum(wind, wind + (s.peak_wind_kt - wind) * w)
        # Wave height diagnosed from the local wind: no fetch or swell model.
        wave = np.maximum(wave, 0.14 * wind * np.sqrt(np.clip(w, 0.0, 1.0)) + wave * (1.0 - w))
        vis = np.minimum(vis, vis * (1.0 - 0.75 * w))
        pressure = np.minimum(pressure, pressure + (s.central_pressure_hpa - pressure) * w)

    return WeatherField(
        wind_kt=wind,
        wave_m=wave,
        visibility_nm=np.clip(vis, 0.2, None),
        pressure_hpa=pressure,
        background=bg,
        systems=systems,
    )
