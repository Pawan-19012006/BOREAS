"""Great-circle geodesy for advancing a vessel's simulated position.

This is a deliberate, function-for-function port of
`frontend/src/lib/geo.ts` (haversine, initial bearing, great-circle slerp,
cumulative distance, position-at-distance): the same geometry the Shore
frontend already uses for its own navigation HUD. Porting it here -- rather
than inventing a different formula -- means the backend's canonical vessel
position (what both Shore and Ship poll) agrees with the frontend's own
math, and it is exactly that: geometry over the real route coordinates
`/mission/plan` returned, not a new prediction model.
"""

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0
KM_PER_NM = 1.852  # exact, by definition

LonLat = tuple[float, float]


def haversine_km(a: LonLat, b: LonLat) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    h = math.sin(d_phi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, h)))


def initial_bearing_deg(a: LonLat, b: LonLat) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)
    y = math.sin(d_lambda) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(d_lambda)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def interpolate_great_circle(a: LonLat, b: LonLat, fraction: float) -> LonLat:
    """Point at `fraction` (0-1) along the great circle from a to b (slerp)."""
    lon1, lat1 = a
    lon2, lat2 = b
    p1, l1 = math.radians(lat1), math.radians(lon1)
    p2, l2 = math.radians(lat2), math.radians(lon2)

    d = haversine_km(a, b) / EARTH_RADIUS_KM
    if d < 1e-9:
        return (lon1, lat1)

    A = math.sin((1 - fraction) * d) / math.sin(d)
    B = math.sin(fraction * d) / math.sin(d)
    x = A * math.cos(p1) * math.cos(l1) + B * math.cos(p2) * math.cos(l2)
    y = A * math.cos(p1) * math.sin(l1) + B * math.cos(p2) * math.sin(l2)
    z = A * math.sin(p1) + B * math.sin(p2)
    return (math.degrees(math.atan2(y, x)), math.degrees(math.atan2(z, math.hypot(x, y))))


def cumulative_distances_km(path: list[LonLat]) -> list[float]:
    out = [0.0]
    for i in range(1, len(path)):
        out.append(out[i - 1] + haversine_km(path[i - 1], path[i]))
    return out


@dataclass(frozen=True)
class PositionOnRoute:
    position: LonLat
    leg_index: int
    next_waypoint_index: int
    distance_travelled_km: float
    distance_remaining_km: float
    distance_to_next_waypoint_km: float
    bearing_deg: float | None
    progress_fraction: float
    is_complete: bool


def position_at_distance(path: list[LonLat], travelled_km: float) -> PositionOnRoute:
    """Resolves a distance-along-route into a geographic position plus
    navigation state, by walking the route's own vertices -- the same
    approach as `frontend/src/lib/geo.ts::positionAtDistance`.
    """
    if len(path) < 2:
        p = path[0] if path else (0.0, 0.0)
        return PositionOnRoute(p, 0, 0, 0.0, 0.0, 0.0, None, 1.0, True)

    cumulative = cumulative_distances_km(path)
    total_km = cumulative[-1]
    clamped = max(0.0, min(travelled_km, total_km))

    leg = 0
    while leg < len(cumulative) - 2 and cumulative[leg + 1] <= clamped:
        leg += 1

    leg_start_km = cumulative[leg]
    leg_length_km = cumulative[leg + 1] - leg_start_km
    leg_fraction = (clamped - leg_start_km) / leg_length_km if leg_length_km > 1e-9 else 0.0
    position = interpolate_great_circle(path[leg], path[leg + 1], leg_fraction)

    is_complete = clamped >= total_km - 1e-6
    next_waypoint_index = min(leg + 1, len(path) - 1)

    return PositionOnRoute(
        position=position,
        leg_index=leg,
        next_waypoint_index=next_waypoint_index,
        distance_travelled_km=clamped,
        distance_remaining_km=total_km - clamped,
        distance_to_next_waypoint_km=cumulative[next_waypoint_index] - clamped,
        bearing_deg=None if is_complete else initial_bearing_deg(position, path[next_waypoint_index]),
        progress_fraction=(clamped / total_km) if total_km > 0 else 1.0,
        is_complete=is_complete,
    )
