"""Weather hotspot detection: contiguous regions where forecast severity is a
navigation concern.

The severity field from `weather_severity` is thresholded and then grouped with
a connected-component labelling pass, so neighbouring severe cells become ONE
region rather than one marker per grid cell. Each region reports its own
area-weighted centre, its worst cell, and the variable actually driving it.

Takes the grid axes as arguments rather than importing the mission domain, which
keeps `forecast` free of any dependency on `mission` (the dependency runs the
other way).
"""

import numpy as np
from scipy.ndimage import label

from .models import WeatherHotspot
from .weather_field import WEATHER_PROVENANCE, evaluate_weather
from .weather_severity import (
    HOTSPOT_MIN_SEVERITY,
    primary_weather_driver,
    severity_category,
    weather_severity,
)

# A single 1-degree cell over open ocean is ~100 x 60 km. Requiring more than one
# cell stops a marginal, one-cell numerical speck from being promoted to an
# operational hazard region.
MIN_HOTSPOT_CELLS = 3

# 4-connectivity: diagonal-only touching cells are separate systems, not one
# region. This is what keeps two nearby lows from being merged across a corner.
_CONNECTIVITY = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=bool)


def _cell_area_km2(lat: np.ndarray, resolution_deg: float) -> np.ndarray:
    """Area of a resolution x resolution cell at each latitude."""
    km_per_deg = 111.32
    return (km_per_deg * resolution_deg) ** 2 * np.cos(np.radians(lat))


_CACHE: dict[tuple, list[WeatherHotspot]] = {}


def _clear_cache_for_tests() -> None:
    _CACHE.clear()


def detect_hotspots_cached(
    lons: np.ndarray,
    lats: np.ndarray,
    horizon_hours: int,
    **kwargs,
) -> list[WeatherHotspot]:
    """`detect_hotspots` memoised on the grid and horizon.

    The field is deterministic for a given horizon, so repeated detection within
    one request (route metrics, deviation attribution, the map endpoint) returns
    the identical region set -- which is the point: every consumer must see the
    same hotspots. Keyed on the grid extent so a different domain is not served a
    stale answer. Process-lifetime, like the other prototype caches here.
    """
    key = (
        int(horizon_hours),
        float(lons[0]),
        float(lons[-1]),
        len(lons),
        float(lats[0]),
        float(lats[-1]),
        len(lats),
        tuple(sorted(kwargs.items())),
    )
    if key not in _CACHE:
        _CACHE[key] = detect_hotspots(lons, lats, horizon_hours, **kwargs)
    return _CACHE[key]


def detect_hotspots(
    lons: np.ndarray,
    lats: np.ndarray,
    horizon_hours: int,
    *,
    resolution_deg: float = 1.0,
    min_severity: float = HOTSPOT_MIN_SEVERITY,
    base_time=None,
) -> list[WeatherHotspot]:
    """Find weather hotspot regions on the (lats x lons) grid at T+horizon.

    Returns an empty list when no region reaches `min_severity` -- normal weather
    produces no hotspots, and none are invented to fill the map.
    """
    lon_g, lat_g = np.meshgrid(np.asarray(lons, dtype=float), np.asarray(lats, dtype=float))
    field = evaluate_weather(lon_g, lat_g, horizon_hours, base_time=base_time)
    severity = weather_severity(field.wind_kt, field.wave_m, field.visibility_nm)

    labels, count = label(severity >= min_severity, structure=_CONNECTIVITY)
    if count == 0:
        return []

    areas = _cell_area_km2(lat_g, resolution_deg)
    valid_time = field.background.timestamp
    out: list[WeatherHotspot] = []

    for idx in range(1, count + 1):
        mask = labels == idx
        n_cells = int(mask.sum())
        if n_cells < MIN_HOTSPOT_CELLS:
            continue

        sev = severity[mask]
        # Weight the centre by severity as well as area so the reported centre
        # sits in the teeth of the system, not at the centroid of a long tail.
        weights = areas[mask] * sev
        if weights.sum() <= 0:
            continue
        centre_lon = float(np.average(lon_g[mask], weights=weights))
        centre_lat = float(np.average(lat_g[mask], weights=weights))

        # The worst cell is what sets the region's category -- an operator plans
        # for the worst weather inside the region, not its average.
        worst = int(np.argmax(sev))
        peak_severity = float(sev[worst])
        wind = float(field.wind_kt[mask][worst])
        wave = float(field.wave_m[mask][worst])
        vis = float(field.visibility_nm[mask][worst])
        pressure = float(field.pressure_hpa[mask][worst])

        area_km2 = float(areas[mask].sum())
        # Radius of the equivalent circle: one honest number for "how big",
        # reported alongside the true area rather than instead of it.
        radius_km = float(np.sqrt(area_km2 / np.pi))

        out.append(
            WeatherHotspot(
                hotspot_id=f"WX-{horizon_hours:03d}-{idx:02d}",
                longitude=centre_lon,
                latitude=centre_lat,
                radius_km=round(radius_km, 1),
                area_km2=round(area_km2, 1),
                severity=severity_category(peak_severity),
                severity_score=round(peak_severity, 3),
                mean_severity_score=round(float(sev.mean()), 3),
                forecast_horizon_hours=horizon_hours,
                valid_time=valid_time,
                wind_speed_kt=round(wind, 1),
                wave_height_m=round(wave, 1),
                visibility_nm=round(vis, 1),
                pressure_hpa=round(pressure, 1),
                primary_driver=primary_weather_driver(wind, wave, vis),
                confidence=field.background.confidence,
                cell_count=n_cells,
                source="SIMULATED",
                mode="DEMO",
                provenance=WEATHER_PROVENANCE,
            )
        )

    # Worst first: the region an operator must deal with leads the list.
    out.sort(key=lambda h: h.severity_score, reverse=True)
    return out
