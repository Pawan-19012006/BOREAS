"""Hazard snapshot (from existing forecast services) and the hazard field model.

`FieldModel.evaluate(lon, lat)` is the single source of truth for every
per-location quantity (sea ice, iceberg proximity, weather, speed, fuel, risk).
The route planner evaluates it on the navigation grid; the route metrics
evaluate the *same* function along the final polyline, so what A* optimised
and what the response reports cannot disagree.

Nothing here is a new forecasting model: sea ice, iceberg positions/uncertainty
and the synoptic environment all come from `boreas_core.forecast`.
"""

import math
from dataclasses import dataclass

import numpy as np

from boreas_core.forecast.models import EnvironmentalForecastPoint
from boreas_core.forecast.service import get_future_state, get_iceberg_forecasts
from boreas_core.forecast.weather_field import evaluate_weather
from boreas_core.forecast.weather_severity import (
    CAUTION_SEVERITY,
    EXTREME_SEVERITY,
    SEVERE_SEVERITY,
    weather_severity,
)
from boreas_core.observe.service import get_observed_icebergs
from boreas_core.routing.grid import EARTH_RADIUS_KM, RiskGrid

from .config import (
    BERG_RISK_FACTOR,
    WEATHER_EXTREME_BLOCKS,
    WEATHER_RISK_BY_CATEGORY,
    DOMAIN_LAT_RANGE,
    DOMAIN_LON_RANGE,
    DOMAIN_RESOLUTION_DEG,
    IceThresholds,
    VesselProfile,
)

# Coarse-grid awareness: a halo floor keeps small bergs visible to a 1-degree grid.
BERG_HALO_MIN_KM = 75.0
BERG_HALO_MARGIN_KM = 50.0


@dataclass
class BergHazard:
    id: str
    name: str
    lon: float
    lat: float
    risk_level: str
    physical_radius_km: float
    uncertainty_radius_km: float
    confidence: float

    @property
    def exclusion_radius_km(self) -> float:
        return self.physical_radius_km + self.uncertainty_radius_km


@dataclass
class HazardSnapshot:
    horizon_hours: int
    sea_ice_lat: np.ndarray  # ascending
    sea_ice_lon: np.ndarray  # ascending
    sic: np.ndarray  # (lat, lon) in [0, 1]
    sea_ice_confidence: float
    env: EnvironmentalForecastPoint
    icebergs: list[BergHazard]
    sea_ice_provenance: str = "PROTOTYPE — DETERMINISTIC SPATIAL EVOLUTION"
    iceberg_provenance: str = "PROTOTYPE — DETERMINISTIC KINEMATIC DRIFT FORECAST"


def build_snapshot(horizon_hours: int) -> HazardSnapshot:
    """Assemble the hazard state at T+horizon from the existing forecast services."""
    future = get_future_state(horizon_hours)
    observed = {b.id: b for b in get_observed_icebergs().icebergs}
    bergs: list[BergHazard] = []
    for forecast in get_iceberg_forecasts(horizon_hours):
        point = forecast.forecast_points[0]
        obs = observed[forecast.iceberg_id]
        bergs.append(
            BergHazard(
                id=forecast.iceberg_id,
                name=forecast.iceberg_name,
                lon=point.longitude,
                lat=point.latitude,
                risk_level=obs.risk_level,
                physical_radius_km=math.sqrt(obs.area_km2 / math.pi),
                uncertainty_radius_km=point.uncertainty_radius_km,
                confidence=point.confidence,
            )
        )
    return HazardSnapshot(
        horizon_hours=horizon_hours,
        sea_ice_lat=np.asarray(future.sea_ice.grid_lat, dtype=float),
        sea_ice_lon=np.asarray(future.sea_ice.grid_lon, dtype=float),
        sic=np.asarray(future.sea_ice.sic_values, dtype=float),
        sea_ice_confidence=future.sea_ice.confidence,
        env=future.environment,
        icebergs=bergs,
        sea_ice_provenance=future.sea_ice.provenance,
    )


# ---------------------------------------------------------------- geometry ---

def haversine_km_array(lon1, lat1, lon2, lat2) -> np.ndarray:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlam = np.radians(lon2) - np.radians(lon1)
    h = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlam / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


def _bilinear(values: np.ndarray, lats: np.ndarray, lons: np.ndarray, qlat, qlon) -> np.ndarray:
    qlat = np.asarray(qlat, dtype=float)
    qlon = np.asarray(qlon, dtype=float)
    la = np.clip(qlat, lats[0], lats[-1])
    lo = np.clip(qlon, lons[0], lons[-1])
    i = np.clip(np.searchsorted(lats, la) - 1, 0, len(lats) - 2)
    j = np.clip(np.searchsorted(lons, lo) - 1, 0, len(lons) - 2)
    ty = (la - lats[i]) / (lats[i + 1] - lats[i])
    tx = (lo - lons[j]) / (lons[j + 1] - lons[j])
    v = (
        values[i, j] * (1 - ty) * (1 - tx)
        + values[i, j + 1] * (1 - ty) * tx
        + values[i + 1, j] * ty * (1 - tx)
        + values[i + 1, j + 1] * ty * tx
    )
    # The forecast grid ends at its northern edge; north of it there is no sea-ice data.
    return np.where(qlat > lats[-1], 0.0, v)


# ------------------------------------------------------------- navigation grid ---

class NavGrid(RiskGrid):
    """RiskGrid with a scalar-math haversine so the unchanged `astar_route`
    stays fast on the ~4k-cell navigation domain."""

    def __post_init__(self) -> None:
        super().__post_init__()
        self._lon_list = [float(x) for x in self.lons]
        self._lat_list = [float(x) for x in self.lats]

    def haversine_km(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        lat1, lat2 = math.radians(self._lat_list[a[0]]), math.radians(self._lat_list[b[0]])
        dphi = lat2 - lat1
        dlam = math.radians(self._lon_list[b[1]] - self._lon_list[a[1]])
        h = math.sin(dphi / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlam / 2) ** 2
        return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, h)))


def domain_axes() -> tuple[np.ndarray, np.ndarray]:
    res = DOMAIN_RESOLUTION_DEG
    lons = np.arange(DOMAIN_LON_RANGE[0], DOMAIN_LON_RANGE[1] + res / 2, res)
    lats = np.arange(DOMAIN_LAT_RANGE[0], DOMAIN_LAT_RANGE[1] + res / 2, res)
    return lons, lats


def in_domain(lon: float, lat: float) -> bool:
    return (
        DOMAIN_LON_RANGE[0] <= lon <= DOMAIN_LON_RANGE[1]
        and DOMAIN_LAT_RANGE[0] <= lat <= DOMAIN_LAT_RANGE[1]
    )


# Southern-Africa coast block, as an analytic box. Very coarse -- not a
# navigational coastline. Antarctica itself is the domain's southern edge, so
# it needs no mask of its own.
_LAND_LON_RANGE = (19.0, 35.0)
_LAND_LAT_MIN = -34.5


def land_at(lon, lat):
    """Whether a POINT is on land, evaluated analytically.

    Deliberately not "snap to the nearest grid cell and read the mask": the grid
    is 1 degree, so a point 0.25 degrees clear of the coast box snaps into a
    land cell and is wrongly rejected. Route validation samples continuous
    positions along a segment, so it needs the predicate at the point, not at
    the cell the point rounds to. `land_mask` below is this same box sampled on
    the grid, so the two cannot drift apart.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    return (lon >= _LAND_LON_RANGE[0]) & (lon <= _LAND_LON_RANGE[1]) & (lat > _LAND_LAT_MIN)


def land_mask(lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """`land_at` evaluated on the navigation grid, for the router's cell mask."""
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    return land_at(lon_grid, lat_grid)


# ------------------------------------------------------------------- fields ---

@dataclass
class FieldSet:
    sic: np.ndarray
    ice_risk: np.ndarray
    berg_risk: np.ndarray
    wx_risk: np.ndarray
    risk: np.ndarray
    speed_factor: np.ndarray  # (0, 1] multiplier on cruise speed
    fuel_extra: np.ndarray  # additive environmental fuel multiplier (>= 0)
    wave_m: np.ndarray
    wind_kt: np.ndarray
    visibility_nm: np.ndarray
    pressure_hpa: np.ndarray
    wx_severity: np.ndarray  # continuous 0-1 weather severity score


_SIC_KNOTS = [0.0, 0.15, 0.30, 0.60, 0.80, 1.0]
_ICE_RISK = [0.0, 0.0, 0.20, 0.55, 0.85, 1.0]
_ICE_FUEL = [0.0, 0.0, 0.10, 0.45, 0.90, 1.5]
_ICE_SPEED_LOSS = [0.0, 0.0, 0.15, 0.45, 0.70, 0.85]
FUEL_EXTRA_NORM = 1.5  # plausible maximum, used to normalise the fuel penalty


def _weather_risk_from_severity(severity) -> np.ndarray:
    """Map the continuous weather severity score onto navigation risk using the
    per-category multipliers in `config.WEATHER_RISK_BY_CATEGORY`.

    Interpolating between the category anchors rather than stepping at them keeps
    the A* cost field smooth -- a hard step at a threshold would put a cliff in
    the cost surface and make the chosen route hypersensitive to a rounding-level
    change in severity. The anchors themselves are exactly the values the UI
    shows, so category and cost never disagree.

    When `WEATHER_EXTREME_BLOCKS` is set, EXTREME severity is pushed to 1.0 so the
    planner's own land/blocked handling treats it as a hard constraint.
    """
    w = WEATHER_RISK_BY_CATEGORY
    risk = np.interp(
        np.asarray(severity, dtype=float),
        [0.0, CAUTION_SEVERITY, SEVERE_SEVERITY, EXTREME_SEVERITY],
        [w["NORMAL"], w["CAUTION"], w["SEVERE"], w["EXTREME"]],
    )
    if WEATHER_EXTREME_BLOCKS:
        risk = np.where(np.asarray(severity, dtype=float) >= EXTREME_SEVERITY, 1.0, risk)
    return risk


class FieldModel:
    def __init__(self, snapshot: HazardSnapshot, profile: VesselProfile, thresholds: IceThresholds):
        self.snapshot = snapshot
        self.profile = profile
        self.thresholds = thresholds

    def sic_at(self, lon, lat) -> np.ndarray:
        s = self.snapshot
        return np.clip(_bilinear(s.sic, s.sea_ice_lat, s.sea_ice_lon, lat, lon), 0.0, 1.0)

    def berg_risk_at(self, lon, lat) -> np.ndarray:
        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)
        out = np.zeros(np.broadcast(lon, lat).shape)
        for b in self.snapshot.icebergs:
            d = haversine_km_array(lon, lat, b.lon, b.lat)
            r_ex = b.exclusion_radius_km
            halo = max(r_ex + BERG_HALO_MARGIN_KM, BERG_HALO_MIN_KM)
            decay = np.clip((halo - d) / max(halo - r_ex, 1e-6), 0.0, 1.0)
            level = np.where(d <= r_ex, 1.0, decay)
            out = np.maximum(out, level * BERG_RISK_FACTOR[b.risk_level])
        return out

    def evaluate(self, lon, lat) -> FieldSet:
        env = self.snapshot.env
        p = self.profile
        sic = self.sic_at(lon, lat)

        ice_risk = np.clip(np.interp(sic, _SIC_KNOTS, _ICE_RISK) * p.ice_risk_scale, 0.0, 1.0)
        ice_speed_loss = np.interp(sic, _SIC_KNOTS, _ICE_SPEED_LOSS) * p.ice_resistance_scale
        ice_fuel = np.interp(sic, _SIC_KNOTS, _ICE_FUEL) * p.ice_resistance_scale

        # Spatial weather: the background synoptic state (env) with the simulated
        # low-pressure systems superimposed. Reusing the snapshot's own `env` as
        # the background means the cost field A* optimises and the environmental
        # state the response reports are derived from the same forecast.
        wx = evaluate_weather(lon, lat, self.snapshot.horizon_hours, background=env)
        wave = wx.wave_m
        wind = wx.wind_kt
        visibility = wx.visibility_nm

        # One severity score, one threshold table, shared with hotspot detection
        # and the UI -- so a region the map calls SEVERE is the same region the
        # router paid a SEVERE penalty to cross.
        severity = weather_severity(wind, wave, visibility)
        wx_risk = np.clip(_weather_risk_from_severity(severity), 0.0, 1.0)
        wave_speed_factor = np.clip(1.0 - 0.06 * np.maximum(0.0, wave - 2.0), 0.6, 1.0)
        wave_fuel = 0.05 * np.maximum(0.0, wave - 1.0)

        berg_risk = self.berg_risk_at(lon, lat)
        risk = 1.0 - (1.0 - ice_risk) * (1.0 - berg_risk) * (1.0 - wx_risk)
        speed_factor = np.clip((1.0 - ice_speed_loss) * wave_speed_factor, 0.08, 1.0)
        return FieldSet(
            sic=sic,
            ice_risk=ice_risk,
            berg_risk=berg_risk,
            wx_risk=wx_risk,
            risk=risk,
            speed_factor=speed_factor,
            fuel_extra=ice_fuel + wave_fuel,
            wave_m=wave,
            wind_kt=wind,
            visibility_nm=visibility,
            pressure_hpa=wx.pressure_hpa,
            wx_severity=np.asarray(severity, dtype=float),
        )
