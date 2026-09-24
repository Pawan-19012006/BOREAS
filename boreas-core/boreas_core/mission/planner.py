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
    DOMAIN_LAT_RANGE,
    DOMAIN_LON_RANGE,
    DOMAIN_RESOLUTION_DEG,
    MISSIONS,
    PASSABILITY_LEVELS,
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
    RoutePlan,
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

# Candidate pool: one A* search per weight vector (risk, fuel, eta), plus the caller's
# own weights. Roles (recommended / low-risk / fast-fuel) are assigned afterwards
# from the *measured* route metrics, never from the weights that produced a route.
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
ROLE_LABELS = {
    "recommended": "RECOMMENDED",
    "low_risk": "LOW-RISK ALTERNATIVE",
    "fast_fuel": "FASTEST / FUEL-ORIENTED",
}
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


ROLE_SELECTION = {
    "low_risk": "the lowest measured risk score",
    "fast_fuel": "the lowest combined ETA and fuel",
}


def _explain(route: RoutePlan, peers: list[RoutePlan], horizon: int, weights: RouteWeights) -> list[str]:
    si, ib, wx = route.sea_ice_exposure, route.iceberg_exposure, route.weather_exposure
    n = route.candidates_evaluated
    when = "NOW" if horizon == 0 else f"T+{horizon}h"
    if route.route_id == "recommended":
        why = (
            f"Selected as the best trade-off under the requested weights (risk {weights.risk:.0%} / "
            f"fuel {weights.fuel:.0%} / ETA {weights.eta:.0%}) among {n} distinct A* candidates, "
            f"evaluated against hazards at {when}."
        )
    else:
        why = (
            f"Selected as the candidate with {ROLE_SELECTION[route.route_id]} among the {n - 1} not chosen "
            f"as RECOMMENDED, evaluated against hazards at {when}."
        )
    lines = [
        f"{route.distance_km:.0f} km, {route.eta_hours:.0f} h, {route.estimated_fuel.tonnes:.0f} t fuel "
        f"(PROTOTYPE ESTIMATE); risk {route.risk_score:.2f} ({route.risk_level}), confidence {route.confidence:.0%}.",
        why,
        f"Sea ice for {si.vessel_ice_class} (PROTOTYPE PASSABILITY MODEL): {si.passable_pct:.0f}% passable, "
        f"{si.caution_pct:.0f}% caution, {si.restricted_pct:.0f}% restricted, {si.impassable_pct:.0f}% impassable; "
        f"mean SIC {si.mean_sic_pct:.0f}%, max {si.max_sic_pct:.0f}% -> {si.assessment}.",
    ]
    hot = [r for r in ib.relevant_icebergs if r.classification in ("INTERSECTING", "POTENTIAL")]
    if hot:
        top = hot[0]
        lines.append(
            f"{len(hot)} iceberg(s) may intersect the corridor; closest {top.id} at {top.distance_km:.0f} km "
            f"(exclusion radius {top.exclusion_radius_km:.0f} km, {top.classification})."
        )
    elif ib.relevant_icebergs:
        top = ib.relevant_icebergs[0]
        lines.append(f"No projected iceberg intersection; nearest {top.id} at {top.distance_km:.0f} km.")
    else:
        lines.append(f"No tracked iceberg within {NEARBY_CORRIDOR_KM:.0f} km of its exclusion zone.")
    lines.append(
        f"Peak waves {wx.max_wave_m:.1f} m, peak wind {wx.max_wind_kt:.0f} kt; "
        f"{wx.high_sea_state_pct:.0f}% of the route in waves >= {HIGH_SEA_STATE_M:.0f} m."
    )
    share = route.risk_driver_shares.get(route.primary_risk_driver)
    lines.append(
        f"Primary risk driver: {route.primary_risk_driver}"
        + (f" ({share:.0%} of combined hazard)." if share is not None else ".")
    )
    for p in peers:
        dd, dt, df = p.distance_km - route.distance_km, p.eta_hours - route.eta_hours, p.estimated_fuel.tonnes - route.estimated_fuel.tonnes
        lines.append(
            f"Compared with {p.label}: this route is {-dd:+.0f} km, {-dt:+.0f} h, {-df:+.0f} t fuel, "
            f"risk {route.risk_score - p.risk_score:+.2f}."
        )
    if route.route_id == "recommended":
        fast = next((p for p in peers if p.route_id == "fast_fuel"), None)
        if fast and route.distance_km > fast.distance_km and route.risk_score < fast.risk_score:
            lines.append(
                f"Accepts +{route.distance_km - fast.distance_km:.0f} km over the fastest route to lower "
                f"risk score by {fast.risk_score - route.risk_score:.2f}."
            )
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
        lonlat = list(result.path_lonlat)
        if any(_separation_km(lonlat, c["lonlat"]) < MIN_SEPARATION_KM for c in candidates):
            return False
        coords = [list(origin)] + [[float(lo), float(la)] for lo, la in lonlat] + [list(mission.destination)]
        candidates.append(
            {
                "weights": w,
                "generation": generation,
                "lonlat": lonlat,
                "cells": result.path_cells,
                "coords": coords,
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
    balanced = RouteWeights(risk=1 / 3, fuel=1 / 3, eta=1 / 3)
    for extra in ALT_PENALTIES:
        for w in (weights, balanced):
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

    # -- role assignment from measured metrics
    def norm(key) -> list[float]:
        vals = [key(c["m"]) for c in candidates]
        lo, hi = min(vals), max(vals)
        return [0.0 if hi - lo < 1e-9 else (v - lo) / (hi - lo) for v in vals]

    n_risk, n_fuel, n_eta = norm(lambda m: m["risk_score"]), norm(lambda m: m["fuel"].tonnes), norm(lambda m: m["eta_hours"])
    remaining = list(range(len(candidates)))
    composite = lambda i: weights.risk * n_risk[i] + weights.fuel * n_fuel[i] + weights.eta * n_eta[i]  # noqa: E731
    picks: dict[str, int] = {}
    picks["recommended"] = min(remaining, key=lambda i: (composite(i), candidates[i]["m"]["distance_km"]))
    remaining.remove(picks["recommended"])
    if remaining:
        picks["low_risk"] = min(remaining, key=lambda i: (n_risk[i], candidates[i]["m"]["distance_km"]))
        remaining.remove(picks["low_risk"])
    if remaining:
        picks["fast_fuel"] = min(remaining, key=lambda i: (n_eta[i] + n_fuel[i], candidates[i]["m"]["distance_km"]))
    if len(picks) < 3:
        raise NoRouteFound(f"Could not generate three distinct routes in this domain ({len(candidates)} distinct candidate(s) found).")

    routes: list[RoutePlan] = []
    for route_id in ("recommended", "low_risk", "fast_fuel"):
        c = candidates[picks[route_id]]
        m = c["m"]
        routes.append(
            RoutePlan(
                route_id=route_id,
                label=ROLE_LABELS[route_id],
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
                    "route_optimization": "PROTOTYPE — A* OPTIMIZATION (coarse 1° navigation grid); role assigned from measured metrics",
                    "fuel": "PROTOTYPE ESTIMATE — distance x vessel consumption x environmental multiplier",
                    "passability": "PROTOTYPE PASSABILITY MODEL — configurable SIC thresholds, not validated",
                    "sea_ice": snapshot.sea_ice_provenance,
                    "icebergs": snapshot.iceberg_provenance,
                    "weather": snapshot.env.provenance,
                },
            )
        )

    for r in routes:
        r.explanation = _explain(r, [p for p in routes if p is not r], request.horizon_hours, weights)

    warnings: list[str] = []
    for r in routes:
        si = r.sea_ice_exposure
        if si.impassable_pct > 0:
            warnings.append(
                f"{r.label}: {si.impassable_pct:.0f}% of the route ({si.impassable_pct / 100 * r.distance_km:.0f} km) "
                f"is in IMPASSABLE ice (SIC > {thresholds.restricted_max:.0%}) for {si.vessel_ice_class}; "
                "impassable cells are penalised, not hard-blocked, so the station approach remains reachable."
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
