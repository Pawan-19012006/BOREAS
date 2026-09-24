"""Mission route planner: three A* routes over a coarse Cape Town -> Antarctic
navigation domain, judged on the forecast hazard state at a chosen horizon.

Reuses `routing.astar.astar_route` unchanged. A* cost is
`distance x (1 + RISK_WEIGHT_SCALE x penalty)`, where the per-cell `penalty`
mixes the risk, fuel and ETA penalty fields by the route's weights. Route
metrics are then computed from the final polyline with the same `FieldModel`.

PROTOTYPE: deterministic, not scientifically validated; the hazard state is a
single snapshot at T+horizon applied to the whole transit.
"""

import math
from datetime import datetime, timezone

import numpy as np
from scipy.ndimage import binary_dilation

from boreas_core.observe.service import get_observed_vessels
from boreas_core.routing.astar import astar_route

from .config import (
    DEFAULT_ICE_THRESHOLDS,
    DEVIATION_MAX_CAUSE_DISTANCE_KM,
    DEVIATION_MIN_PENALTY,
    DOMAIN_LAT_RANGE,
    DOMAIN_LON_RANGE,
    DOMAIN_RESOLUTION_DEG,
    MISSIONS,
    PASSABILITY_LEVELS,
    RISK_ACCEPTANCE_BAND,
    ROUTE_STRATEGIES,
    SIMPLIFY_TOLERANCE,
    IceThresholds,
    profile_for_ice_class,
)
from .fields import (
    FUEL_EXTRA_NORM,
    FieldModel,
    HazardSnapshot,
    NavGrid,
    build_snapshot,
    domain_axes,
    haversine_km_array,
    in_domain,
    land_mask,
)
from .models import (
    DomainSummary,
    FuelEstimate,
    IceThresholdsIn,
    IcebergExposure,
    MissionPlanRequest,
    MissionPlanResponse,
    RelevantIceberg,
    RiskAcceptability,
    RouteDeviation,
    RoutePlan,
    RouteTradeoff,
    RouteWeights,
    SeaIceExposure,
    VesselSummary,
    WeatherExposure,
)

RISK_WEIGHT_SCALE = 10.0  # A* cost multiplier for a fully-penalised cell
MAX_PENALTY = 0.94  # keep every navigable cell below astar's 0.95 block threshold
SAMPLE_SPACING_KM = 10.0
NEARBY_CORRIDOR_KM = 100.0  # beyond exclusion radius
ALT_PENALTIES = (0.25, 0.6, 1.0)  # corridor penalties for k-alternative search
MAX_POOL = 9
MIN_SEPARATION_KM = 40.0  # mean lateral separation below which two routes count as "the same"
HIGH_SEA_STATE_M = 4.0

# Candidate pool: one A* search per weight vector (risk, fuel, eta). These are
# an internal search-diversification device for generating a spread of distinct
# candidates -- they are NOT operator preferences, and are never surfaced as
# such. Strategies (recommended / low-risk / fuel-efficient) are assigned
# afterwards from the *measured* route metrics under a risk constraint, never
# from the weight vector that happened to produce a candidate.
POOL_WEIGHTS = [
    (1.0, 0.0, 0.0),
    (0.8, 0.1, 0.1),
    (0.5, 0.25, 0.25),
    (1 / 3, 1 / 3, 1 / 3),
    (0.2, 0.4, 0.4),
    (0.1, 0.45, 0.45),
    (0.0, 0.5, 0.5),
    (0.0, 1.0, 0.0),
    (0.0, 0.0, 1.0),
]
DRIVER_NAMES = {
    "sea_ice": "SEA_ICE_CONCENTRATION",
    "iceberg": "ICEBERG_EXPOSURE",
    "weather": "WEATHER_WAVE_CONDITIONS",
}


class VesselNotFound(KeyError):
    pass


class NoRouteFound(ValueError):
    pass


def risk_level(score: float) -> str:
    if score < 0.10:
        return "VERY LOW"
    if score < 0.25:
        return "LOW"
    if score < 0.45:
        return "MEDIUM"
    if score < 0.65:
        return "HIGH"
    return "CRITICAL"


def _cell_penalty(fields, weights: RouteWeights) -> np.ndarray:
    pen_time = 1.0 - fields.speed_factor
    pen_fuel = np.clip(fields.fuel_extra / FUEL_EXTRA_NORM, 0.0, 1.0)
    return weights.risk * fields.risk + weights.fuel * pen_fuel + weights.eta * pen_time


def _separation_km(a: list, b: list) -> float:
    """Symmetric mean lateral separation between two vertex paths (lon, lat)."""
    pa, pb = np.asarray(a, dtype=float), np.asarray(b, dtype=float)

    def one_way(x, y) -> float:
        return float(np.mean([haversine_km_array(px, py, y[:, 0], y[:, 1]).min() for px, py in x]))

    return 0.5 * (one_way(pa, pb) + one_way(pb, pa))


def _search(lons, lats, penalty: np.ndarray, land: np.ndarray, start, goal):
    risk = np.clip(penalty, 0.0, MAX_PENALTY)
    risk[land] = 1.0
    risk[start] = min(risk[start], MAX_PENALTY)
    risk[goal] = min(risk[goal], MAX_PENALTY)
    grid = NavGrid(lons=lons, lats=lats, risk=risk)
    result = astar_route(grid, start, goal, risk_weight=RISK_WEIGHT_SCALE, blocked_threshold=0.95)
    if result is None:
        raise NoRouteFound("No navigable route exists between origin and destination in the domain.")
    return result


def _snap_km(lon, lat, lons, lats, cell) -> float:
    return float(haversine_km_array(lon, lat, lons[cell[1]], lats[cell[0]]))


# --------------------------------------------------------- geometry cleanup ---


def _line_cells(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    """Grid cells a straight segment from `a` to `b` passes through."""
    r0, c0 = a
    r1, c1 = b
    steps = max(abs(r1 - r0), abs(c1 - c0))
    if steps == 0:
        return [a]
    out = []
    for s in range(steps + 1):
        t = s / steps
        out.append((round(r0 + (r1 - r0) * t), round(c0 + (c1 - c0) * t)))
    return out


def _path_cost(cells: list[tuple[int, int]], risk_eff, lons, lats) -> float:
    """Cost of a cell polyline under the same rule A* itself used:
    `distance x (1 + RISK_WEIGHT_SCALE x mean endpoint risk)` per step. Using
    A*'s own cost is what makes the shortcut test meaningful -- a shortcut is
    only taken when the search would have preferred it too."""
    total = 0.0
    for a, b in zip(cells[:-1], cells[1:]):
        d = float(haversine_km_array(lons[a[1]], lats[a[0]], lons[b[1]], lats[b[0]]))
        total += d * (1.0 + RISK_WEIGHT_SCALE * 0.5 * (float(risk_eff[a]) + float(risk_eff[b])))
    return total


def _simplify_path(
    path_cells: list[tuple[int, int]],
    risk_eff,
    lons,
    lats,
    *,
    hazard_field=None,
    tolerance: float = SIMPLIFY_TOLERANCE,
    blocked_threshold: float = 0.95,
) -> tuple[list[tuple[int, int]], dict[tuple[int, int], tuple[int, int]]]:
    """Greedy string-pulling over the A* path, preserving A*'s own cost.

    A vertex is dropped when the straight line past it costs no more than the
    sub-path it replaces. In uniform open water the staircase is strictly
    longer than the straight line, so every such shortcut is cheaper and the
    lattice artefact collapses to a straight leg. Near ice or an iceberg
    exclusion zone the straight line crosses costlier cells, the shortcut is
    rejected, and the bend survives -- so every remaining bend is one the
    environment actually paid for.

    Comparing *path cost* rather than peak cell penalty matters: on an
    Antarctic approach the unavoidable station leg pins the peak near the
    blocked threshold for the whole route, which would make a peak-based test
    accept every shortcut and flatten the route into a straight line.

    Returns the simplified cells and, for each retained bend, the offending
    cell that blocked the shortcut -- the causal record behind
    `RoutePlan.deviations`.
    """
    if len(path_cells) <= 2:
        return list(path_cells), {}

    simplified = [path_cells[0]]
    causes: dict[tuple[int, int], tuple[int, int]] = {}
    i = 0
    last = len(path_cells) - 1

    while i < last:
        best_j = i + 1
        # Longest shortcut first, so we drop as many lattice artefacts as possible.
        for j in range(last, i + 1, -1):
            shortcut = _line_cells(path_cells[i], path_cells[j])
            # Never shortcut through a cell A* itself treats as impassable.
            if any(float(risk_eff[c]) >= blocked_threshold for c in shortcut):
                continue
            original = path_cells[i : j + 1]

            # Physical-hazard guard, independent of the search weighting.
            # Candidates are generated with varied weight vectors, and some of
            # them weight risk at zero -- without this, a shortcut would be
            # free to cut straight through an iceberg exclusion zone the
            # original path went around, because that berg contributes nothing
            # to *that candidate's* cost field. Hazards constrain the geometry
            # whatever the search was optimising for.
            if hazard_field is not None:
                if max(float(hazard_field[c]) for c in shortcut) > max(
                    float(hazard_field[c]) for c in original
                ) + tolerance:
                    continue

            short_cost = _path_cost(shortcut, risk_eff, lons, lats)
            orig_cost = _path_cost(original, risk_eff, lons, lats)
            if short_cost <= orig_cost * (1.0 + tolerance):
                best_j = j
                break

        if best_j < last:
            # We stopped short of the destination, so the vertex we stopped at
            # is a real turn. What made it one is whatever the next-longer
            # shortcut (i -> best_j+1) would have had to cross: record that
            # cell as the cause.
            rejected = _line_cells(path_cells[i], path_cells[best_j + 1])
            causes[path_cells[best_j]] = max(rejected, key=lambda c: float(risk_eff[c]))

        simplified.append(path_cells[best_j])
        i = best_j

    return simplified, causes


def _describe_deviations(
    simplified_cells: list[tuple[int, int]],
    causes: dict[tuple[int, int], tuple[int, int]],
    *,
    lons,
    lats,
    fields,
    land,
    snapshot: HazardSnapshot,
    thresholds: IceThresholds,
) -> list[RouteDeviation]:
    """Turns blocked shortcuts into operator-facing reasons, using only what is
    actually in the hazard fields at the offending cell. A bend whose cost is
    real but too small to attribute is reported as NAVIGATION_COST rather than
    being pinned on a hazard that isn't there."""
    out: list[RouteDeviation] = []
    for cell in simplified_cells:
        cause_cell = causes.get(cell)
        if cause_cell is None:
            continue

        cause_lon, cause_lat = float(lons[cause_cell[1]]), float(lats[cause_cell[0]])
        bend_lon, bend_lat = float(lons[cell[1]]), float(lats[cell[0]])

        # Only name a hazard the operator can actually see near this bend --
        # see DEVIATION_MAX_CAUSE_DISTANCE_KM.
        cause_distance_km = float(haversine_km_array(bend_lon, bend_lat, cause_lon, cause_lat))
        if cause_distance_km > DEVIATION_MAX_CAUSE_DISTANCE_KM:
            out.append(
                RouteDeviation(
                    longitude=bend_lon,
                    latitude=bend_lat,
                    cause_longitude=cause_lon,
                    cause_latitude=cause_lat,
                    cause="NAVIGATION_COST",
                    detail="Higher-cost water than the direct line",
                )
            )
            continue

        sic = float(fields.sic[cause_cell])
        berg_risk = float(fields.berg_risk[cause_cell])
        ice_risk = float(fields.ice_risk[cause_cell])

        if bool(land[cause_cell]):
            out.append(
                RouteDeviation(
                    longitude=float(lons[cell[1]]),
                    latitude=float(lats[cell[0]]),
                    cause_longitude=cause_lon,
                    cause_latitude=cause_lat,
                    cause="LAND",
                    detail="Landmass / non-navigable cell",
                )
            )
            continue

        # Nearest tracked berg to the offending cell -- reported only when that
        # berg is genuinely what makes the cell expensive.
        nearest_id, nearest_km = None, None
        if snapshot.icebergs:
            nearest = min(
                snapshot.icebergs,
                key=lambda b: float(haversine_km_array(cause_lon, cause_lat, b.lon, b.lat)),
            )
            nearest_km = float(haversine_km_array(cause_lon, cause_lat, nearest.lon, nearest.lat))
            nearest_id = nearest.id

        if berg_risk >= ice_risk and berg_risk >= DEVIATION_MIN_PENALTY and nearest_id is not None:
            out.append(
                RouteDeviation(
                    longitude=float(lons[cell[1]]),
                    latitude=float(lats[cell[0]]),
                    cause_longitude=cause_lon,
                    cause_latitude=cause_lat,
                    cause="ICEBERG",
                    detail=f"Iceberg {nearest_id} exclusion zone, {nearest_km:.0f} km",
                    iceberg_id=nearest_id,
                    iceberg_distance_km=round(nearest_km, 1),
                )
            )
        elif ice_risk >= DEVIATION_MIN_PENALTY and sic > thresholds.passable_max:
            out.append(
                RouteDeviation(
                    longitude=float(lons[cell[1]]),
                    latitude=float(lats[cell[0]]),
                    cause_longitude=cause_lon,
                    cause_latitude=cause_lat,
                    cause="SEA_ICE",
                    detail=f"Sea ice {sic * 100:.0f}% concentration",
                    sic_pct=round(sic * 100, 1),
                )
            )
        else:
            out.append(
                RouteDeviation(
                    longitude=float(lons[cell[1]]),
                    latitude=float(lats[cell[0]]),
                    cause_longitude=cause_lon,
                    cause_latitude=cause_lat,
                    cause="NAVIGATION_COST",
                    detail="Higher-cost water than the direct line",
                )
            )
    return out


def _evaluate_route(coords, fm: FieldModel, ice_class: str, thresholds: IceThresholds, snapshot: HazardSnapshot):
    """Metrics from the final polyline, sampled every ~SAMPLE_SPACING_KM."""
    pts = np.asarray(coords, dtype=float)
    mid_lon, mid_lat, seg_len = [], [], []
    for (lo1, la1), (lo2, la2) in zip(pts[:-1], pts[1:]):
        length = float(haversine_km_array(lo1, la1, lo2, la2))
        n = max(1, math.ceil(length / SAMPLE_SPACING_KM))
        t = (np.arange(n) + 0.5) / n
        mid_lon.extend(lo1 + (lo2 - lo1) * t)
        mid_lat.extend(la1 + (la2 - la1) * t)
        seg_len.extend([length / n] * n)
    mid_lon, mid_lat, seg_len = np.array(mid_lon), np.array(mid_lat), np.array(seg_len)
    dist = float(seg_len.sum())
    share = seg_len / dist

    f = fm.evaluate(mid_lon, mid_lat)
    profile = fm.profile
    seg_time = seg_len / (profile.cruise_speed_kt * f.speed_factor * 1.852)
    eta = float(seg_time.sum())
    fuel_mult = 1.0 + f.fuel_extra
    fuel_t = float((seg_len * profile.fuel_t_per_km * fuel_mult).sum())
    mean_mult = float((share * fuel_mult).sum())

    def wmean(x) -> float:
        return float((share * x).sum())

    # -- sea ice
    level = (f.sic > thresholds.passable_max).astype(int) + (f.sic > thresholds.caution_max) + (
        f.sic > thresholds.restricted_max
    )
    pct = [float(share[level == k].sum() * 100.0) for k in range(4)]
    assessment = "PASSABLE"
    for k in (3, 2, 1):
        if pct[k] >= 10.0:
            assessment = PASSABILITY_LEVELS[k]
            break
    sea_ice = SeaIceExposure(
        vessel_ice_class=ice_class,
        mean_sic_pct=round(wmean(f.sic) * 100, 1),
        max_sic_pct=round(float(f.sic.max()) * 100, 1),
        passable_pct=round(pct[0], 1),
        caution_pct=round(pct[1], 1),
        restricted_pct=round(pct[2], 1),
        impassable_pct=round(pct[3], 1),
        ice_exposure_km=round(float(seg_len[level >= 1].sum()), 1),
        assessment=assessment,
        max_level_encountered=PASSABILITY_LEVELS[int(level.max())],
    )

    # -- icebergs
    cum_time = np.cumsum(seg_time) - seg_time / 2.0
    relevant: list[RelevantIceberg] = []
    for b in snapshot.icebergs:
        d = haversine_km_array(mid_lon, mid_lat, b.lon, b.lat)
        k = int(np.argmin(d))
        dmin = float(d[k])
        r_ex = b.exclusion_radius_km
        if dmin <= b.physical_radius_km + 5.0:
            cls = "INTERSECTING"
        elif dmin <= r_ex:
            cls = "POTENTIAL"
        elif dmin <= r_ex + NEARBY_CORRIDOR_KM:
            cls = "NEARBY"
        else:
            continue
        relevant.append(
            RelevantIceberg(
                id=b.id,
                name=b.name,
                distance_km=round(dmin, 1),
                exclusion_radius_km=round(r_ex, 1),
                uncertainty_radius_km=round(b.uncertainty_radius_km, 1),
                classification=cls,
                risk_level=b.risk_level.upper(),
                confidence=b.confidence,
                closest_approach_eta_h=round(float(cum_time[k]), 1),
            )
        )
    relevant.sort(key=lambda r: r.distance_km)
    count = lambda c: sum(1 for r in relevant if r.classification == c)  # noqa: E731
    bergs = IcebergExposure(
        horizon_hours=snapshot.horizon_hours,
        tracked_count=len(snapshot.icebergs),
        intersecting_count=count("INTERSECTING"),
        potential_count=count("POTENTIAL"),
        nearby_count=count("NEARBY"),
        min_distance_km=relevant[0].distance_km if relevant else None,
        mean_risk=round(wmean(f.berg_risk), 3),
        max_risk=round(float(f.berg_risk.max()), 3),
        relevant_icebergs=relevant,
    )

    # -- weather
    env = snapshot.env
    weather = WeatherExposure(
        mean_wave_m=round(wmean(f.wave_m), 2),
        max_wave_m=round(float(f.wave_m.max()), 2),
        mean_wind_kt=round(wmean(f.wind_kt), 1),
        max_wind_kt=round(float(f.wind_kt.max()), 1),
        min_visibility_nm=env.visibility_nm,
        air_temp_c=env.air_temp_c,
        pressure_hpa=env.pressure_hpa,
        high_sea_state_pct=round(float(share[f.wave_m >= HIGH_SEA_STATE_M].sum() * 100), 1),
        mean_risk=round(wmean(f.wx_risk), 3),
        provenance=env.provenance + " (uniform state scaled by latitude band)",
    )

    # -- risk score, driver, confidence
    score = 0.7 * wmean(f.risk) + 0.3 * float(share[f.risk >= 0.6].sum())
    components = {"sea_ice": wmean(f.ice_risk), "iceberg": wmean(f.berg_risk), "weather": wmean(f.wx_risk)}
    total = sum(components.values())
    shares = {k: (v / total if total > 1e-9 else 0.0) for k, v in components.items()}
    driver = DRIVER_NAMES[max(components, key=components.get)] if max(components.values()) >= 0.02 else "NO_SIGNIFICANT_DRIVER"

    confs = [snapshot.sea_ice_confidence, env.confidence]
    near = [r.confidence for r in relevant]
    if near:
        confs.append(min(near))
    severe_share = (pct[2] + pct[3]) / 100.0
    confidence = round(max(0.0, min(1.0, float(np.mean(confs)) * (1.0 - 0.2 * severe_share))), 2)

    return {
        "distance_km": round(dist, 1),
        "eta_hours": round(eta, 1),
        "fuel": FuelEstimate(
            tonnes=round(fuel_t, 1),
            consumption_t_per_km=profile.fuel_t_per_km,
            environmental_multiplier=round(mean_mult, 3),
        ),
        "risk_score": round(float(np.clip(score, 0.0, 1.0)), 3),
        "confidence": confidence,
        "sea_ice": sea_ice,
        "bergs": bergs,
        "weather": weather,
        "driver": driver,
        "shares": {DRIVER_NAMES[k]: round(v, 3) for k, v in shares.items()},
    }


def _explain(route: RoutePlan, horizon: int) -> list[str]:
    """Three compact operational lines. Deliberately not a narrative: the
    Shore panel renders the structured fields, and anything the operator
    cannot act on (search internals, candidate counts, weight vectors) stays
    out of the operator-facing text entirely."""
    si, ib = route.sea_ice_exposure, route.iceberg_exposure
    when = "now" if horizon == 0 else f"T+{horizon}h"

    lines = [
        f"{route.distance_km:.0f} km, {route.eta_hours:.0f} h, {route.estimated_fuel.tonnes:.0f} t fuel "
        f"(prototype estimate); navigation risk {route.risk_level.lower()}.",
        route.selection_rationale,
    ]

    hot = [r for r in ib.relevant_icebergs if r.classification in ("INTERSECTING", "POTENTIAL")]
    ice_part = (
        f"Sea ice {si.assessment.lower()} for {si.vessel_ice_class} "
        f"({si.mean_sic_pct:.0f}% mean concentration)"
    )
    berg_part = (
        f"{len(hot)} iceberg(s) may reach the corridor" if hot else "no iceberg projected to reach the corridor"
    )
    lines.append(f"{ice_part}; {berg_part}, evaluated at {when}.")
    return lines


def resolve_vessel(vessel_id: str):
    for v in get_observed_vessels().vessels:
        if v.id == vessel_id:
            return v
    raise VesselNotFound(vessel_id)


def plan_mission(request: MissionPlanRequest, snapshot: HazardSnapshot | None = None) -> MissionPlanResponse:
    mission = MISSIONS[request.mission_id]
    vessel = resolve_vessel(request.vessel_id or mission.default_vessel_id)
    profile = profile_for_ice_class(vessel.ice_class)
    t_in = request.ice_thresholds
    thresholds = (
        IceThresholds(t_in.passable_max, t_in.caution_max, t_in.restricted_max) if t_in else DEFAULT_ICE_THRESHOLDS
    )
    weights = request.weights.normalized()
    snapshot = snapshot or build_snapshot(request.horizon_hours)

    # An underway replan starts from the vessel's actual current position rather
    # than the mission's fixed origin (e.g. Cape Town) -- same A* engine and
    # navigation domain, just a different start cell. See coordination/service.py
    # for the shore<->ship workflow that supplies this.
    origin_overridden = request.start_lon is not None and request.start_lat is not None
    origin = (request.start_lon, request.start_lat) if origin_overridden else mission.origin
    origin_name = (
        f"Current position ({request.start_lat:.2f}, {request.start_lon:.2f})"
        if origin_overridden
        else mission.origin_name
    )

    for name, (lon, lat) in (("origin", origin), ("destination", mission.destination)):
        if not in_domain(lon, lat):
            raise ValueError(f"{name} is outside the navigation domain")

    lons, lats = domain_axes()
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    land = land_mask(lons, lats)
    fm = FieldModel(snapshot, profile, thresholds)
    grid_fields = fm.evaluate(lon_grid, lat_grid)

    def cell_of(lon, lat):
        return int(np.argmin(np.abs(lats - lat))), int(np.argmin(np.abs(lons - lon)))

    start, goal = cell_of(*origin), cell_of(*mission.destination)

    # -- candidate pool
    candidates: list[dict] = []

    def add_candidate(result, w: RouteWeights, generation: str) -> bool:
        # The raw A* path is an 8-connected staircase; simplify it so the only
        # bends that survive are ones a real environmental cost forced. The
        # *unsimplified* cells are kept for the k-alternative corridor mask
        # below, which needs the full swept corridor to push later candidates
        # away properly.
        risk_eff = np.clip(_cell_penalty(grid_fields, w), 0.0, MAX_PENALTY)
        risk_eff[land] = 1.0
        simple_cells, causes = _simplify_path(
            result.path_cells, risk_eff, lons, lats, hazard_field=grid_fields.risk
        )
        simple_lonlat = [(float(lons[c[1]]), float(lats[c[0]])) for c in simple_cells]

        # Distinctness is judged on the geometry actually displayed and scored,
        # not on the pre-simplification staircase -- otherwise two candidates
        # that differ only in lattice noise would both be kept and then present
        # as identical routes to the operator.
        if any(_separation_km(simple_lonlat, c["lonlat"]) < MIN_SEPARATION_KM for c in candidates):
            return False
        lonlat = simple_lonlat

        coords = (
            [list(origin)] + [[lo, la] for lo, la in simple_lonlat] + [list(mission.destination)]
        )
        candidates.append(
            {
                "weights": w,
                "generation": generation,
                "lonlat": lonlat,
                "cells": result.path_cells,
                "coords": coords,
                "deviations": _describe_deviations(
                    simple_cells,
                    causes,
                    lons=lons,
                    lats=lats,
                    fields=grid_fields,
                    land=land,
                    snapshot=snapshot,
                    thresholds=thresholds,
                ),
                "m": _evaluate_route(coords, fm, vessel.ice_class, thresholds, snapshot),
            }
        )
        return True

    for wr, wf, we in [(weights.risk, weights.fuel, weights.eta)] + POOL_WEIGHTS:
        w = RouteWeights(risk=wr, fuel=wf, eta=we)
        result = _search(lons, lats, _cell_penalty(grid_fields, w), land, start, goal)
        add_candidate(result, w, f"A* with weights risk {wr:.2f} / fuel {wf:.2f} / ETA {we:.2f}")

    # k-alternatives: re-run A* with the corridors of ALL routes found so far penalised,
    # so each new route must avoid every earlier one. Real A* routes over the same
    # cost field, just forced away from duplicates.
    # Simplification collapses candidates that differed only in lattice noise
    # into the same geometry, so more rounds are needed than the raw searches
    # suggest to end up with three genuinely distinct corridors.
    balanced = RouteWeights(risk=1 / 3, fuel=1 / 3, eta=1 / 3)
    risk_led = RouteWeights(risk=0.7, fuel=0.15, eta=0.15)
    for extra in ALT_PENALTIES:
        for w in (weights, balanced, risk_led):
            if len(candidates) >= 6:
                break
            mask = np.zeros(land.shape, dtype=bool)
            for c in candidates:
                for cell in c["cells"]:
                    mask[cell] = True
            mask = binary_dilation(mask, iterations=2)
            mask[start] = mask[goal] = False
            result = _search(lons, lats, _cell_penalty(grid_fields, w) + extra * mask, land, start, goal)
            add_candidate(
                result,
                w,
                f"A* alternative: corridors of earlier routes penalised (+{extra:.2f}), "
                f"weights risk {w.risk:.2f} / fuel {w.fuel:.2f} / ETA {w.eta:.2f}",
            )

    # -- strategy assignment from measured metrics.
    #
    # Navigation risk is applied here as a CONSTRAINT, not as an operator
    # preference: the engine finds the safest candidate it can, then treats
    # everything within RISK_ACCEPTANCE_BAND of it as operationally
    # acceptable. RECOMMENDED and FUEL-EFFICIENT are only ever chosen from
    # that acceptable set, so neither can trade safety away for speed or fuel.
    def norm(key) -> list[float]:
        vals = [key(c["m"]) for c in candidates]
        lo, hi = min(vals), max(vals)
        return [0.0 if hi - lo < 1e-9 else (v - lo) / (hi - lo) for v in vals]

    n_risk = norm(lambda m: m["risk_score"])
    n_fuel, n_eta = norm(lambda m: m["fuel"].tonnes), norm(lambda m: m["eta_hours"])
    risk_of = lambda i: candidates[i]["m"]["risk_score"]  # noqa: E731
    fuel_of = lambda i: candidates[i]["m"]["fuel"].tonnes  # noqa: E731
    distance_of = lambda i: candidates[i]["m"]["distance_km"]  # noqa: E731

    all_indices = list(range(len(candidates)))
    safest_risk = min(risk_of(i) for i in all_indices)
    acceptance_ceiling = safest_risk + RISK_ACCEPTANCE_BAND
    acceptable = [i for i in all_indices if risk_of(i) <= acceptance_ceiling]

    picks: dict[str, int] = {}

    def take(role: str, pool: list[int], key) -> None:
        """Assigns the best candidate in `pool` to `role`.

        Falls back to the full candidate set when the risk-acceptable pool is
        exhausted. If every candidate is already claimed -- which happens when
        the environment genuinely offers fewer distinct corridors than there
        are strategies, e.g. a leg where the ice gradient is latitudinal and no
        lateral deviation helps -- the best track for this objective is reused
        and flagged, rather than manufacturing a detour with no cause.
        """
        available = [i for i in pool if i not in picks.values()]
        if not available:
            available = [i for i in all_indices if i not in picks.values()]
        if not available:
            available = pool or all_indices
        picks[role] = min(available, key=key)

    # The two single-objective strategies are assigned first, because each has
    # a hard definition that must actually hold: LOW-RISK really is the
    # lowest-risk track available, and FUEL-EFFICIENT really is the lowest-burn
    # one inside the risk constraint. Assigning RECOMMENDED first would let it
    # take the cheapest candidate and leave FUEL-EFFICIENT burning more fuel
    # than the route it is supposed to undercut.
    take("low_risk", all_indices, key=lambda i: (risk_of(i), distance_of(i)))
    take("fast_fuel", acceptable, key=lambda i: (fuel_of(i), distance_of(i)))
    # RECOMMENDED is the compromise: minimise the worst normalised regret
    # across risk, ETA and fuel (Chebyshev / compromise programming), which
    # lands on a genuinely middle track instead of an extreme. Risk enters
    # here only as regret *within the already risk-acceptable set* -- the
    # constraint decides what is allowed, this only balances what is left.
    take(
        "recommended",
        acceptable,
        key=lambda i: (max(n_risk[i], n_eta[i], n_fuel[i]), n_eta[i] + n_fuel[i], distance_of(i)),
    )

    # Which strategy first claimed each candidate, so a reused track can say
    # so. Iterated in assignment order, not display order.
    first_claim: dict[int, str] = {}
    for role in ("low_risk", "fast_fuel", "recommended"):
        first_claim.setdefault(picks[role], role)

    routes: list[RoutePlan] = []
    for route_id in ("recommended", "low_risk", "fast_fuel"):
        c = candidates[picks[route_id]]
        m = c["m"]
        strategy = ROUTE_STRATEGIES[route_id]
        routes.append(
            RoutePlan(
                route_id=route_id,
                label=strategy["label"],
                objective=strategy["objective"],
                selection_rationale=strategy["rationale"],
                risk_acceptability=RiskAcceptability(
                    risk_score=m["risk_score"],
                    safest_candidate_risk=round(safest_risk, 3),
                    band=RISK_ACCEPTANCE_BAND,
                    within_constraint=m["risk_score"] <= acceptance_ceiling + 1e-9,
                ),
                deviations=c["deviations"],
                shares_track_with=(
                    ROUTE_STRATEGIES[first_claim[picks[route_id]]]["label"]
                    if first_claim[picks[route_id]] != route_id
                    else None
                ),
                coordinates=c["coords"],
                search_weights=c["weights"],
                distance_km=m["distance_km"],
                eta_hours=m["eta_hours"],
                estimated_fuel=m["fuel"],
                risk_score=m["risk_score"],
                risk_level=risk_level(m["risk_score"]),
                confidence=m["confidence"],
                sea_ice_exposure=m["sea_ice"],
                iceberg_exposure=m["bergs"],
                weather_exposure=m["weather"],
                primary_risk_driver=m["driver"],
                risk_driver_shares=m["shares"],
                explanation=[],
                generation=c["generation"],
                candidates_evaluated=len(candidates),
                provenance={
                    "route_optimization": "PROTOTYPE — A* OPTIMIZATION (coarse 1° navigation grid); strategy assigned from measured metrics under a risk constraint",
                    "fuel": "PROTOTYPE ESTIMATE — distance x vessel consumption x environmental multiplier",
                    "passability": "PROTOTYPE PASSABILITY MODEL — configurable SIC thresholds, not validated",
                    "sea_ice": snapshot.sea_ice_provenance,
                    "icebergs": snapshot.iceberg_provenance,
                    "weather": snapshot.env.provenance,
                },
            )
        )

    # Trade-offs are measured against RECOMMENDED, so the operator compares
    # alternatives to the advised route rather than to each other.
    recommended_route = routes[0]
    for r in routes:
        if r.route_id != "recommended":
            r.tradeoff_vs_recommended = RouteTradeoff(
                distance_delta_km=round(r.distance_km - recommended_route.distance_km, 1),
                eta_delta_hours=round(r.eta_hours - recommended_route.eta_hours, 1),
                fuel_delta_t=round(r.estimated_fuel.tonnes - recommended_route.estimated_fuel.tonnes, 1),
                risk_delta=round(r.risk_score - recommended_route.risk_score, 3),
            )
        r.explanation = _explain(r, request.horizon_hours)

    warnings: list[str] = []
    for r in routes:
        si = r.sea_ice_exposure
        if si.impassable_pct > 0:
            warnings.append(
                f"{r.label}: {si.impassable_pct:.0f}% of the route ({si.impassable_pct / 100 * r.distance_km:.0f} km) "
                f"is in IMPASSABLE ice (SIC > {thresholds.restricted_max:.0%}) for {si.vessel_ice_class}; "
                "impassable cells are penalised, not hard-blocked, so the station approach remains reachable."
            )

    for r in routes:
        if r.shares_track_with:
            warnings.append(
                f"{r.label} follows the same track as {r.shares_track_with}: at this horizon the "
                "environment offers no distinct corridor that better serves this objective. The "
                "route is repeated rather than a detour being invented to make it look different."
            )

    rec, low, fast = routes
    if low.risk_score > rec.risk_score:
        warnings.append(
            f"LOW-RISK ALTERNATIVE (risk {low.risk_score:.2f}) is not lower risk than RECOMMENDED "
            f"({rec.risk_score:.2f}) under this hazard state; the forecast fields offer no lower-risk corridor."
        )
    if fast.eta_hours > rec.eta_hours:
        warnings.append(
            f"FASTEST / FUEL-ORIENTED ({fast.eta_hours:.0f} h) is not faster than RECOMMENDED "
            f"({rec.eta_hours:.0f} h) under this hazard state."
        )

    return MissionPlanResponse(
        mission_id=mission.mission_id,
        mission_label=mission.label,
        origin_name=origin_name,
        destination_name=mission.destination_name,
        vessel=VesselSummary(
            id=vessel.id,
            name=vessel.name,
            ice_class=vessel.ice_class,
            profile_tier=profile.tier,
            cruise_speed_kt=profile.cruise_speed_kt,
            fuel_t_per_km=profile.fuel_t_per_km,
        ),
        horizon_hours=request.horizon_hours,
        weights=weights,
        ice_thresholds=IceThresholdsIn(
            passable_max=thresholds.passable_max,
            caution_max=thresholds.caution_max,
            restricted_max=thresholds.restricted_max,
        ),
        domain=DomainSummary(
            lon_range=list(DOMAIN_LON_RANGE),
            lat_range=list(DOMAIN_LAT_RANGE),
            resolution_deg=DOMAIN_RESOLUTION_DEG,
            origin_snap_km=round(_snap_km(*origin, lons, lats, start), 1),
            destination_snap_km=round(_snap_km(*mission.destination, lons, lats, goal), 1),
            note=(
                "Coarse prototype domain with a crude southern-Africa land block; not a navigational chart. "
                "Hazards are one snapshot at the chosen horizon applied to the whole transit."
            ),
        ),
        routes=routes,
        warnings=warnings,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
