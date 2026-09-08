"""Second, independently-published routing engine: `polar-route`
(github.com/antarctica/PolarRoute) + `meshiphi`, run against our own real
trained sea-ice ensemble forecast and the request's real iceberg hazard
positions.

Verified this session by reading the installed library source directly
(not guessed): `MeshBuilder`/`VesselPerformanceModeller`/`RoutePlanner` all
accept plain Python dicts (and `RoutePlanner.compute_routes` a plain
DataFrame) via their own `json_str`/`pandas_dataframe_str` normalisers --
the CLI's file-path-only usage is a CLI convenience, not a library
requirement. The *one* genuine on-disk file needed is the SIC CSV, because
`ScalarCSVDataLoader.import_data` calls `pd.read_csv` on a real path with
no dict-passthrough option.

Vessel performance uses PolarRoute's own bundled "SDA" vessel class, which
models the real RRS Sir David Attenborough (a British Antarctic Survey
polar research vessel -- also a roster entry, see
boreas_core/vessels/roster.py). This is an ice-class-*typical* performance
profile applied uniformly to whichever roster vessel the request is really
for, since none of the other roster vessels' actual ice-resistance/powering
curves are publicly documented -- only the SDA's is (PolarRoute's own
published example config, examples/vessel_config/SDA.config.json in
github.com/antarctica/PolarRoute, fetched and reproduced verbatim below).
"""

import csv
import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

EARTH_RADIUS_KM = 6371.0

SDA_VESSEL_CONFIG = {
    "vessel_type": "SDA",
    "max_speed": 26.5,
    "unit": "km/hr",
    "beam": 24.0,
    "hull_type": "slender",
    "force_limit": 96634.5,
    "max_ice_conc": 80,
    "min_depth": 10,
}

# time_unit deliberately "days", not the schema-allowed "hours"/"seconds":
# reading polar_route/utils.py's unit_time() shows it only implements
# "days"/"hr"/"min"/"s" -- "hours" and "seconds" (the route_schema.py enum
# values) don't match any branch and would silently return None. "days" is
# the one value guaranteed correct in both the schema and the converter, so
# hours are computed here instead (total_traveltime * 24.0).
ROUTE_CONFIG = {
    "objective_function": "traveltime",
    "path_variables": ["fuel", "traveltime"],
    "vector_names": ["uC", "vC"],
    "zero_currents": True,
    "time_unit": "days",
    "adjust_waypoints": True,
}


@dataclass
class PolarRouteResult:
    available: bool
    path_lonlat: list[tuple[float, float]]
    total_distance_km: float
    total_traveltime_hours: float
    total_fuel_tons: float
    note: str


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _write_sic_csv(
    path: str,
    *,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    sample_step_deg: float,
    ice_lat,
    ice_lon,
    ice_mean,
    hazard_lon,
    hazard_lat,
    hazard_radius_km,
) -> None:
    """Write a `lat,long,SIC` CSV covering the mesh region at `sample_step_deg`
    resolution, bilinearly resampled from the real 32x32 ensemble grid.

    Writing only the native 32x32 nodes (~11 degree spacing) leaves most
    cells of a fine mesh with zero raw datapoints -> a `None` aggregated SIC
    -> a crash deep in PolarRoute's own route-smoothing code
    (`crossing_smoothing.blocked_ice` subtracts two SIC values assuming
    both are numbers). Resampling first is a standard, honest way to fix
    that: it's real interpolated values from the real trained forecast, not
    fabricated data, and it's exactly what a finer operational product
    would look like at this resolution.
    """
    import numpy as np
    from scipy.interpolate import RegularGridInterpolator

    ice_lat_arr = np.asarray(ice_lat, dtype=float)
    ice_lon_arr = np.asarray(ice_lon, dtype=float)
    ice_mean_arr = np.asarray(ice_mean, dtype=float)
    interpolator = RegularGridInterpolator(
        (ice_lat_arr, ice_lon_arr), ice_mean_arr, bounds_error=False, fill_value=None
    )

    sample_lats = np.arange(lat_min, lat_max + 1e-9, sample_step_deg)
    sample_lons = np.arange(lon_min, lon_max + 1e-9, sample_step_deg)
    grid_lat, grid_lon = np.meshgrid(sample_lats, sample_lons, indexing="ij")
    points = np.stack([grid_lat.ravel(), grid_lon.ravel()], axis=-1)
    values = np.clip(interpolator(points), 0.0, 1.0)

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["lat", "long", "SIC"])
        for (lat, lon), value in zip(points, values, strict=True):
            writer.writerow([float(lat), float(lon), float(value) * 100.0])

        # Iceberg exclusion: inject an explicit SIC=100 point directly at
        # each hazard's own lon/lat too, so the mesh cell containing it is
        # pulled toward "impassable" even though the interpolated forecast
        # alone wouldn't know about it.
        for lon, lat, _radius_km in zip(hazard_lon, hazard_lat, hazard_radius_km, strict=True):
            writer.writerow([float(lat), float(lon), 100.0])


def plan_polar_route(
    *,
    start_lonlat: tuple[float, float],
    goal_lonlat: tuple[float, float],
    ice_lat,
    ice_lon,
    ice_mean,
    hazard_lon: list[float] = (),
    hazard_lat: list[float] = (),
    hazard_radius_km: list[float] = (),
    cell_size_deg: float = 1.5,
    padding_deg: float = 3.0,
) -> PolarRouteResult:
    """Plan a route with PolarRoute. Never raises -- any failure in the
    mesh/vessel/routing pipeline (bad mesh, no route found, library
    internals) degrades to `available=False` with an explanatory `note`,
    so /route/plan can always fall back to the AI-only routes.
    """
    try:
        return _plan_polar_route_inner(
            start_lonlat=start_lonlat,
            goal_lonlat=goal_lonlat,
            ice_lat=ice_lat,
            ice_lon=ice_lon,
            ice_mean=ice_mean,
            hazard_lon=list(hazard_lon),
            hazard_lat=list(hazard_lat),
            hazard_radius_km=list(hazard_radius_km),
            cell_size_deg=cell_size_deg,
            padding_deg=padding_deg,
        )
    except Exception as exc:  # noqa: BLE001 -- PolarRoute is a heavy third-party
        # pipeline (mesh construction, vessel performance modelling, Dijkstra
        # + smoothing) with many possible failure modes (NoRouteFoundError,
        # InvalidMeshError, ValueError, KeyError, ...its own internals);
        # /route/plan must degrade to the AI-only routes rather than crash
        # for any of them, so every exception is caught here, not a curated
        # subset.
        return PolarRouteResult(
            available=False,
            path_lonlat=[],
            total_distance_km=0.0,
            total_traveltime_hours=0.0,
            total_fuel_tons=0.0,
            note=f"PolarRoute unavailable: {exc}",
        )


def _plan_polar_route_inner(
    *,
    start_lonlat: tuple[float, float],
    goal_lonlat: tuple[float, float],
    ice_lat,
    ice_lon,
    ice_mean,
    hazard_lon: list[float],
    hazard_lat: list[float],
    hazard_radius_km: list[float],
    cell_size_deg: float,
    padding_deg: float,
) -> PolarRouteResult:
    # Imported lazily so a missing/broken polar-route install only breaks
    # this function's call path (caught above), not every import of this
    # module (e.g. from server.py at startup).
    from meshiphi.mesh_generation.mesh_builder import MeshBuilder
    from polar_route.route_planner.route_planner import RoutePlanner
    from polar_route.vessel_performance.vessel_performance_modeller import (
        VesselPerformanceModeller,
    )

    start_lon, start_lat = start_lonlat
    goal_lon, goal_lat = goal_lonlat

    # MeshiPhi requires the region span to divide evenly by cell_width/
    # cell_height -- snap outward to the nearest cell_size_deg multiple
    # (floor/ceil) rather than using the raw padded bounds directly. 90 and
    # 180 are themselves exact multiples of every cell size used here, so
    # clipping to the poles/antimeridian afterward preserves divisibility.
    def _snap(lo: float, hi: float) -> tuple[float, float]:
        return (
            math.floor(lo / cell_size_deg) * cell_size_deg,
            math.ceil(hi / cell_size_deg) * cell_size_deg,
        )

    lat_min, lat_max = _snap(
        min(start_lat, goal_lat) - padding_deg, max(start_lat, goal_lat) + padding_deg
    )
    lon_min, lon_max = _snap(
        min(start_lon, goal_lon) - padding_deg, max(start_lon, goal_lon) + padding_deg
    )
    lat_min, lat_max = max(lat_min, -90.0), min(lat_max, 90.0)
    lon_min, lon_max = max(lon_min, -180.0), min(lon_max, 180.0)

    with tempfile.TemporaryDirectory(prefix="boreas_polarroute_") as tmpdir:
        sic_csv_path = str(Path(tmpdir) / "sic.csv")
        _write_sic_csv(
            sic_csv_path,
            lat_min=lat_min,
            lat_max=lat_max,
            lon_min=lon_min,
            lon_max=lon_max,
            sample_step_deg=cell_size_deg / 3.0,
            ice_lat=ice_lat,
            ice_lon=ice_lon,
            ice_mean=ice_mean,
            hazard_lon=hazard_lon,
            hazard_lat=hazard_lat,
            hazard_radius_km=hazard_radius_km,
        )

        mesh_config = {
            "region": {
                "lat_min": lat_min,
                "lat_max": lat_max,
                "long_min": lon_min,
                "long_max": lon_max,
                "start_time": "TODAY",
                "end_time": "TODAY + 1",
                "cell_width": cell_size_deg,
                "cell_height": cell_size_deg,
            },
            "data_sources": [
                {"loader": "scalar_csv", "params": {"files": [sic_csv_path], "data_name": "SIC"}},
                {"loader": "thickness", "params": {}},
                {"loader": "density", "params": {}},
            ],
            "splitting": {"split_depth": 0, "minimum_datapoints": 1},
        }

        env_mesh = MeshBuilder(mesh_config).build_environmental_mesh()
        mesh_json = env_mesh.to_json()

        vp = VesselPerformanceModeller(mesh_json, dict(SDA_VESSEL_CONFIG))
        vp.model_accessibility()
        vp.model_performance()
        vessel_mesh_json = vp.to_json()

        waypoints_df = pd.DataFrame(
            {
                "Name": ["Start", "Goal"],
                "Lat": [start_lat, goal_lat],
                "Long": [start_lon, goal_lon],
                "Source": ["X", None],
                "Destination": [None, "X"],
            }
        )

        route_planner = RoutePlanner(vessel_mesh_json, dict(ROUTE_CONFIG))
        route_planner.compute_routes(waypoints_df)
        smoothed = route_planner.compute_smoothed_routes()

    features = smoothed.get("features", [])
    if not features:
        return PolarRouteResult(
            available=False,
            path_lonlat=[],
            total_distance_km=0.0,
            total_traveltime_hours=0.0,
            total_fuel_tons=0.0,
            note="PolarRoute produced no route for this start/goal pair",
        )

    feature = features[0]
    coords = feature["geometry"]["coordinates"]
    path_lonlat = [(float(lon), float(lat)) for lon, lat in coords]

    total_distance_km = sum(
        _haversine_km(*path_lonlat[i], *path_lonlat[i + 1]) for i in range(len(path_lonlat) - 1)
    )
    props = feature.get("properties", {})
    total_traveltime_days = float(props.get("total_traveltime", 0.0))
    total_fuel_tons = float(props.get("total_fuel", 0.0))

    return PolarRouteResult(
        available=True,
        path_lonlat=path_lonlat,
        total_distance_km=total_distance_km,
        total_traveltime_hours=total_traveltime_days * 24.0,
        total_fuel_tons=total_fuel_tons,
        note="PolarRoute: MeshiPhi mesh + SDA-class ice-resistance vessel performance model",
    )
