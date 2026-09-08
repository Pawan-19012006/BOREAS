"""Turn-by-turn directions from an A*-planned route (BOREAS design doc §5.6/5.7).

`astar_route` runs 8-connected search on a 1-degree grid, so its raw
`path_cells` is a "staircase" of alternating headings whenever the true
bearing to the goal isn't a multiple of 45 degrees. Converting that directly
into a bearing-per-segment list would produce dozens of spurious tiny legs
instead of the handful of natural turns a human (or a Google-Maps-style UI)
expects. This module first simplifies the path geometrically (Ramer-Douglas-
Peucker, in a local equirectangular projection so distances are physically
meaningful), then computes real great-circle bearings between the simplified
vertices, then does a second bearing-threshold merge as cleanup.
"""

import math
from dataclasses import dataclass

from .astar import RouteResult

EARTH_RADIUS_KM = 6371.0


def great_circle_bearing_deg(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Initial bearing (forward azimuth) from point 1 to point 2, in degrees, [0, 360).

    Standard spherical bearing formula. A planar `atan2(dlat, dlon)` would be
    systematically wrong here: at latitude -70, a degree of longitude is only
    cos(70 deg) ~= 0.34x the length of a degree of latitude, and `RiskGrid`
    already treats the grid as spherical (see `haversine_km`), so bearing
    must be computed consistently with that, not in raw degree-space.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    bearing = math.degrees(math.atan2(x, y))
    return bearing % 360.0


_COMPASS_POINTS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def bearing_to_compass(bearing_deg: float) -> str:
    """8-point compass label (N/NE/E/SE/S/SW/W/NW) for a bearing in degrees."""
    index = round(bearing_deg / 45.0) % 8
    return _COMPASS_POINTS[index]


def _project_km(lon: float, lat: float, ref_lat: float) -> tuple[float, float]:
    """Local equirectangular projection (kilometres), centered on ref_lat.

    Only used internally for RDP's perpendicular-distance test, where what
    matters is a locally-consistent physical distance -- the same
    cos(lat)-scaling trick `RiskGrid.stamp_circular_hazard` already uses.
    """
    lat_scale = math.radians(1.0) * EARTH_RADIUS_KM
    lon_scale = lat_scale * math.cos(math.radians(ref_lat))
    return lon * lon_scale, lat * lat_scale


def _perpendicular_distance_km(
    point: tuple[float, float], line_start: tuple[float, float], line_end: tuple[float, float]
) -> float:
    (px, py), (ax, ay), (bx, by) = point, line_start, line_end
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    proj_x, proj_y = ax + t * dx, ay + t * dy
    return math.hypot(px - proj_x, py - proj_y)


def simplify_path_rdp(
    path_lonlat: list[tuple[float, float]], *, epsilon_km: float = 20.0
) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker simplification, returning original lon/lat vertices.

    Collapses the 8-connected-grid "staircase" into straight-ish segments
    wherever consecutive points deviate from a chord by less than
    `epsilon_km`, so the subsequent bearing computation sees a handful of
    real turns instead of a zig-zag.
    """
    if len(path_lonlat) < 3:
        return list(path_lonlat)

    ref_lat = sum(lat for _, lat in path_lonlat) / len(path_lonlat)
    projected = [_project_km(lon, lat, ref_lat) for lon, lat in path_lonlat]

    keep = [False] * len(path_lonlat)
    keep[0] = keep[-1] = True

    def _recurse(start: int, end: int) -> None:
        if end <= start + 1:
            return
        max_dist, max_index = -1.0, -1
        for i in range(start + 1, end):
            dist = _perpendicular_distance_km(projected[i], projected[start], projected[end])
            if dist > max_dist:
                max_dist, max_index = dist, i
        if max_dist > epsilon_km:
            keep[max_index] = True
            _recurse(start, max_index)
            _recurse(max_index, end)

    _recurse(0, len(path_lonlat) - 1)
    return [pt for pt, k in zip(path_lonlat, keep, strict=True) if k]


@dataclass
class RouteLeg:
    start_lonlat: tuple[float, float]
    end_lonlat: tuple[float, float]
    bearing_deg: float | None  # None for the final "arrival" leg
    compass_label: str | None
    distance_km: float


def _segment_distances_km(path_lonlat: list[tuple[float, float]]) -> list[float]:
    """Haversine distance between each consecutive pair in the original path."""
    distances = []
    for (lon1, lat1), (lon2, lat2) in zip(path_lonlat[:-1], path_lonlat[1:], strict=True):
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        distances.append(2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a)))
    return distances


def build_route_legs(
    route: RouteResult,
    *,
    epsilon_km: float = 20.0,
    merge_bearing_threshold_deg: float = 15.0,
    min_leg_km: float = 15.0,
) -> list[RouteLeg]:
    """Convert a raw A* path into a small number of real navigational legs.

    Each leg's `distance_km` sums the *original* (pre-simplification)
    segment lengths it spans, so `sum(leg.distance_km for leg in legs)`
    equals `route.total_distance_km` to floating-point tolerance -- the
    vessel still physically follows the original path; RDP only decides
    where the "turns" are for display purposes.
    """
    path = route.path_lonlat
    if len(path) < 2:
        return []

    original_distances = _segment_distances_km(path)
    simplified = simplify_path_rdp(path, epsilon_km=epsilon_km)

    # Map each simplified vertex back to its index in the original path so we
    # can sum the original segment distances spanned by each simplified leg.
    original_index = {point: i for i, point in enumerate(path)}
    simplified_indices = [original_index[pt] for pt in simplified]

    raw_legs: list[RouteLeg] = []
    for (start_idx, end_idx), start_pt, end_pt in zip(
        zip(simplified_indices[:-1], simplified_indices[1:], strict=True),
        simplified[:-1],
        simplified[1:],
        strict=True,
    ):
        distance = sum(original_distances[start_idx:end_idx])
        bearing = great_circle_bearing_deg(start_pt[0], start_pt[1], end_pt[0], end_pt[1])
        raw_legs.append(
            RouteLeg(
                start_lonlat=start_pt,
                end_lonlat=end_pt,
                bearing_deg=bearing,
                compass_label=bearing_to_compass(bearing),
                distance_km=distance,
            )
        )

    merged = _merge_similar_bearings(raw_legs, threshold_deg=merge_bearing_threshold_deg)
    merged = _fold_short_legs(merged, min_leg_km=min_leg_km)

    merged.append(
        RouteLeg(
            start_lonlat=merged[-1].end_lonlat if merged else path[-1],
            end_lonlat=path[-1],
            bearing_deg=None,
            compass_label=None,
            distance_km=0.0,
        )
    )
    return merged


def _merge_similar_bearings(legs: list[RouteLeg], *, threshold_deg: float) -> list[RouteLeg]:
    if not legs:
        return []
    merged = [legs[0]]
    for leg in legs[1:]:
        prev = merged[-1]
        if _bearing_diff(prev.bearing_deg, leg.bearing_deg) < threshold_deg:
            total_distance = prev.distance_km + leg.distance_km
            # Weighted-average bearing to avoid biasing toward whichever leg is longer.
            avg_bearing = _average_bearing(prev.bearing_deg, prev.distance_km, leg.bearing_deg, leg.distance_km)
            merged[-1] = RouteLeg(
                start_lonlat=prev.start_lonlat,
                end_lonlat=leg.end_lonlat,
                bearing_deg=avg_bearing,
                compass_label=bearing_to_compass(avg_bearing),
                distance_km=total_distance,
            )
        else:
            merged.append(leg)
    return merged


def _fold_short_legs(legs: list[RouteLeg], *, min_leg_km: float) -> list[RouteLeg]:
    if len(legs) <= 1:
        return legs
    folded: list[RouteLeg] = []
    for leg in legs:
        if folded and leg.distance_km < min_leg_km:
            prev = folded[-1]
            folded[-1] = RouteLeg(
                start_lonlat=prev.start_lonlat,
                end_lonlat=leg.end_lonlat,
                bearing_deg=prev.bearing_deg,
                compass_label=prev.compass_label,
                distance_km=prev.distance_km + leg.distance_km,
            )
        else:
            folded.append(leg)
    return folded


def _bearing_diff(a: float, b: float) -> float:
    diff = abs(a - b) % 360.0
    return min(diff, 360.0 - diff)


def _average_bearing(b1: float, w1: float, b2: float, w2: float) -> float:
    """Weighted circular mean of two bearings (handles the 0/360 wraparound)."""
    total_weight = w1 + w2 if (w1 + w2) > 0 else 1.0
    x = w1 * math.cos(math.radians(b1)) + w2 * math.cos(math.radians(b2))
    y = w1 * math.sin(math.radians(b1)) + w2 * math.sin(math.radians(b2))
    return math.degrees(math.atan2(y, x)) % 360.0 if (x or y) else b1
