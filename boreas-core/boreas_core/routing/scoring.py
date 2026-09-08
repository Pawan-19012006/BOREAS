"""Time-aware forecast risk + combined scoring across route alternatives.

Every candidate route (both AI/A* variants and PolarRoute, if available) is
judged on the same basis: the real trained ensemble forecast's mean sea-ice
concentration, sampled at the *lead step the vessel will actually be at that
point in its voyage* rather than a single "today" snapshot -- so a leg the
vessel won't reach for several days is scored against the forecast for that
later day, not the current one.

Real, disclosed limitation: the exported ensemble
(`artifacts/ensemble_export.npz`, produced by
`icenet-mp/scripts/export_ensemble_predictions.py`) has shape `(..., T=2,
...)`, matching `icenet_mp`'s own `n_forecast_steps: 2` config, at a
confirmed 24-hour step spacing (the `..._24h_...` dataset configs). The
model only forecasts ~1-2 days ahead, while a real Cape-Town-to-Antarctica
voyage takes on the order of two weeks -- so in practice, every leg beyond
day 2 resolves to the same (last) lead step. The mechanism is still real
and still meaningfully different from scoring every leg against today's
snapshot (which is what happens without this module); the limitation is
surfaced in the API response's `warnings`, not hidden.
"""

from dataclasses import dataclass, replace

from .directions import RouteLeg

HOURS_PER_LEAD_STEP = 24.0
KM_PER_KNOT_HOUR = 1.852

# Score weights: risk weighted heaviest, deliberately -- BOREAS's core value
# proposition is safety over raw speed/distance, and this weighting is what
# actually encodes that in the one "recommended" pick.
WEIGHT_DISTANCE = 0.3
WEIGHT_DURATION = 0.3
WEIGHT_RISK = 0.4


def lead_step_for_eta_hours(eta_hours: float, *, max_lead_step: int, hours_per_step: float = HOURS_PER_LEAD_STEP) -> int:
    step = int(eta_hours // hours_per_step)
    return min(max(step, 0), max_lead_step)


def _nearest_cell_value(lat_grid, lon_grid, mean_grid, lon: float, lat: float) -> float:
    lat_list = list(lat_grid)
    lon_list = list(lon_grid)
    lat_idx = min(range(len(lat_list)), key=lambda i: abs(lat_list[i] - lat))
    lon_idx = min(range(len(lon_list)), key=lambda i: abs(lon_list[i] - lon))
    return float(mean_grid[lat_idx][lon_idx])


def time_aware_max_risk(
    legs: list[RouteLeg],
    *,
    vessel_speed_kt: float,
    ice_lat,
    ice_lon,
    ice_mean_by_lead_step: list,
) -> float:
    """Max forecast SIC (0-1) encountered along `legs`, each leg's endpoint
    sampled against the lead step it's actually reached at, given
    `vessel_speed_kt` and cumulative leg distance.
    """
    if not legs or vessel_speed_kt <= 0 or not ice_mean_by_lead_step:
        return 0.0

    max_lead_step = len(ice_mean_by_lead_step) - 1
    speed_km_per_hour = vessel_speed_kt * KM_PER_KNOT_HOUR
    cumulative_km = 0.0
    max_risk = 0.0
    for leg in legs:
        cumulative_km += leg.distance_km
        eta_hours = cumulative_km / speed_km_per_hour
        lead_step = lead_step_for_eta_hours(eta_hours, max_lead_step=max_lead_step)
        lon, lat = leg.end_lonlat
        risk = _nearest_cell_value(ice_lat, ice_lon, ice_mean_by_lead_step[lead_step], lon, lat)
        max_risk = max(max_risk, risk)
    return max_risk


@dataclass(frozen=True)
class ScoredCandidate:
    key: str
    label: str
    distance_km: float
    duration_hours: float
    risk: float
    recommended: bool = False


def rank_candidates(candidates: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Return `candidates` with exactly one marked `recommended=True` (the
    lowest combined score) and all others `False`. Distance/duration are
    min-max normalized across the candidate set (they're in different units
    and PolarRoute's ice-resistance-aware duration isn't directly comparable
    to the AI routes' constant-speed estimate otherwise); risk is already a
    0-1 fraction, so it's compared as-is once normalized alongside the rest.
    """
    if not candidates:
        return []
    if len(candidates) == 1:
        return [replace(candidates[0], recommended=True)]

    def _normalize(values: list[float]) -> list[float]:
        lo, hi = min(values), max(values)
        if hi - lo < 1e-9:
            return [0.0] * len(values)
        return [(v - lo) / (hi - lo) for v in values]

    norm_distance = _normalize([c.distance_km for c in candidates])
    norm_duration = _normalize([c.duration_hours for c in candidates])
    norm_risk = _normalize([c.risk for c in candidates])

    scores = [
        WEIGHT_DISTANCE * d + WEIGHT_DURATION * t + WEIGHT_RISK * r
        for d, t, r in zip(norm_distance, norm_duration, norm_risk, strict=True)
    ]
    best_index = min(range(len(candidates)), key=lambda i: scores[i])
    return [replace(c, recommended=(i == best_index)) for i, c in enumerate(candidates)]
