"""Shore<->ship coordination: in-memory active-route/vessel-state/route-update
stores, following the same process-lifetime-singleton style as
`api/state.py` (no SQL database anywhere in boreas-core; this is more of the
same, not new infrastructure).

Communication with the Ship application is deliberately simple-REST-and-poll,
per the prototype's own constraints -- no message broker, no websockets.
"""

import uuid
from datetime import datetime, timezone

from boreas_core.mission.config import MISSIONS
from boreas_core.mission.models import RoutePlan
from boreas_core.mission.planner import resolve_vessel

from .geo import KM_PER_NM, LonLat, haversine_km, position_at_distance
from .models import ActiveRoute, MissionInfo, RouteUpdate, RouteUpdateCreate, RouteUpdateStatus, VesselState


class MissionNotFound(KeyError):
    pass


def get_mission_info(mission_id: str) -> MissionInfo:
    """Static mission descriptor for the Ship app -- reuses the same
    `MISSIONS` registry `/mission/plan` itself resolves against; no
    duplicate mission definitions."""
    mission = MISSIONS.get(mission_id)
    if mission is None:
        raise MissionNotFound(mission_id)
    return MissionInfo(
        mission_id=mission.mission_id,
        label=mission.label,
        origin_name=mission.origin_name,
        origin=list(mission.origin),
        destination_name=mission.destination_name,
        destination=list(mission.destination),
    )

# Sim-hours advanced per real second at 1x. Deliberately SLOW: at 1x a vessel
# should creep, so position changes read as gradual and ETA/progress do not
# lurch between polls. A ~325 h Cape Town -> Bharati passage takes roughly 54
# real minutes at 1x and about 4.5 minutes at 12x, which is the point of the
# multiplier -- 1x is for realism, 12x is for demonstrating a long voyage
# quickly. This lives on the backend, so Shore and Ship cannot disagree about
# how fast time is passing.
TIME_ACCELERATION_HOURS_PER_SECOND = 0.1

# Offered demo accelerations. 1x first, because it is the default and the
# honest one.
SPEED_MULTIPLIERS = (1.0, 2.0, 4.0, 8.0, 12.0)

PAUSE_AWAITING_DECISION = "AWAITING_ROUTE_DECISION"

_active_routes: dict[str, ActiveRoute] = {}
_route_updates: dict[str, RouteUpdate] = {}


class RouteUpdateNotFound(KeyError):
    pass


class RouteUpdateAlreadyResolved(ValueError):
    pass


def activate_route(
    *,
    mission_id: str,
    vessel_id: str,
    route: RoutePlan,
    horizon_hours: int,
    supersedes_update_id: str | None = None,
    distance_travelled_before_km: float = 0.0,
    start_offset_km: float | None = None,
    speed_multiplier: float = 1.0,
    under_way: bool = True,
) -> ActiveRoute:
    """Sets (or REPLACES) the vessel's active route and resets the simulated
    voyage clock to now. When this follows an accepted RouteUpdate, `route`
    is that update's `new_route` -- whose own coordinates[0] is the position
    the vessel actually held at proposal time, so resetting the clock here
    produces a continuous handoff with no jump: the ship "continues" rather
    than restarting.

    There is exactly ONE active route per vessel: this assignment replaces the
    previous one outright, and `_active_routes` is the single canonical answer
    to "what is this vessel following". Nothing keeps the superseded route
    alive as a second active route.

    `distance_travelled_before_km` carries the voyage's history across the
    replacement so mission progress is continuous; the new route's own
    along-track distance restarts at zero because the route itself begins where
    the vessel now is.
    """
    # Fails fast and loudly here (VesselNotFound -> 404) rather than letting an
    # invalid vessel_id sit silently in the store until a later replan (which
    # calls plan_mission, and *that* validates the vessel) fails confusingly.
    resolve_vessel(vessel_id)

    active = ActiveRoute(
        mission_id=mission_id,
        vessel_id=vessel_id,
        route=route,
        horizon_hours=horizon_hours,
        activated_at=datetime.now(timezone.utc).isoformat(),
        supersedes_update_id=supersedes_update_id,
        distance_travelled_before_km=round(max(0.0, distance_travelled_before_km), 2),
        start_offset_km=start_offset_km,
        speed_multiplier=speed_multiplier,
        elapsed_sim_hours=0.0,
        running_since=datetime.now(timezone.utc).isoformat() if under_way else None,
        paused_reason=None if under_way else PAUSE_AWAITING_DECISION,
    )
    _active_routes[vessel_id] = active
    return active



# ------------------------------------------------------------ voyage clock ---


def _elapsed_sim_hours(active: ActiveRoute, *, now: datetime | None = None) -> float:
    """Simulated voyage hours for this active route.

    Banked hours plus, when the clock is running, the current interval scaled by
    the speed multiplier. While `running_since` is None the vessel is frozen and
    this returns exactly the banked figure -- which is what makes a replan
    deterministic: the position cannot drift while the Captain is deciding.
    """
    total = active.elapsed_sim_hours
    if active.running_since is not None:
        now = now or datetime.now(timezone.utc)
        running_for_s = max(0.0, (now - datetime.fromisoformat(active.running_since)).total_seconds())
        total += running_for_s * TIME_ACCELERATION_HOURS_PER_SECOND * active.speed_multiplier
    return total


def _bank_elapsed(active: ActiveRoute, *, running: bool, reason: str | None = None) -> ActiveRoute:
    """Folds the current interval into `elapsed_sim_hours` and restarts (or
    stops) the clock. Used by pause, resume and speed changes alike, so a
    multiplier change never retroactively rescales hours already sailed."""
    now = datetime.now(timezone.utc)
    return active.model_copy(
        update={
            "elapsed_sim_hours": _elapsed_sim_hours(active, now=now),
            "running_since": now.isoformat() if running else None,
            "paused_reason": None if running else reason,
        }
    )


def pause_vessel(vessel_id: str, *, reason: str = PAUSE_AWAITING_DECISION) -> ActiveRoute | None:
    """Freezes simulated movement, banking the hours sailed so far."""
    active = _active_routes.get(vessel_id)
    if active is None or active.running_since is None:
        return active
    _active_routes[vessel_id] = _bank_elapsed(active, running=False, reason=reason)
    return _active_routes[vessel_id]


def resume_vessel(vessel_id: str) -> ActiveRoute | None:
    """Restarts simulated movement from exactly where it was frozen."""
    active = _active_routes.get(vessel_id)
    if active is None or active.running_since is not None:
        return active
    _active_routes[vessel_id] = _bank_elapsed(active, running=True)
    return _active_routes[vessel_id]


def set_speed_multiplier(vessel_id: str, multiplier: float) -> ActiveRoute | None:
    """Changes the demo acceleration without disturbing distance already sailed,
    and without resuming a frozen vessel."""
    active = _active_routes.get(vessel_id)
    if active is None:
        return None
    was_running = active.running_since is not None
    banked = _bank_elapsed(active, running=was_running, reason=active.paused_reason)
    _active_routes[vessel_id] = banked.model_copy(update={"speed_multiplier": float(multiplier)})
    return _active_routes[vessel_id]


def get_active_route(vessel_id: str) -> ActiveRoute | None:
    return _active_routes.get(vessel_id)


def compute_vessel_state(vessel_id: str) -> VesselState | None:
    """The one canonical current position for this vessel, advanced from its
    active route's own real distance/ETA -- SIMULATED, not live AIS."""
    active = _active_routes.get(vessel_id)
    if active is None:
        return None

    route = active.route
    path: list[LonLat] = [(c[0], c[1]) for c in route.coordinates]
    km_per_hour = route.distance_km / route.eta_hours if route.eta_hours > 0 else 0.0

    now = datetime.now(timezone.utc)
    elapsed_sim_hours = _elapsed_sim_hours(active, now=now)
    travelled_km = elapsed_sim_hours * km_per_hour

    on_route = position_at_distance(path, travelled_km)
    is_under_way = active.running_since is not None
    # A frozen vessel is making no way; reporting its cruise speed while it sits
    # still would be the panel contradicting the position it is showing.
    speed_kt = 0.0 if (on_route.is_complete or not is_under_way) else km_per_hour / KM_PER_NM

    # Mission-level progress, not progress along this particular route. After a
    # replan the new route starts where the vessel is, so its own along-track
    # distance is zero -- without this carry-forward the voyage would appear to
    # restart at 0% every time the Captain accepts an update.
    travelled_total_km = active.distance_travelled_before_km + on_route.distance_travelled_km
    remaining_km = on_route.distance_remaining_km
    mission_total_km = travelled_total_km + remaining_km
    progress = travelled_total_km / mission_total_km if mission_total_km > 0 else 0.0

    return VesselState(
        vessel_id=vessel_id,
        mission_id=active.mission_id,
        route_id=route.route_id,
        longitude=round(on_route.position[0], 5),
        latitude=round(on_route.position[1], 5),
        heading_deg=round(on_route.bearing_deg, 1) if on_route.bearing_deg is not None else None,
        speed_kt=round(speed_kt, 2),
        distance_travelled_km=round(travelled_total_km, 2),
        distance_remaining_km=round(remaining_km, 2),
        distance_to_next_waypoint_km=round(on_route.distance_to_next_waypoint_km, 2),
        next_waypoint_index=on_route.next_waypoint_index,
        progress_fraction=round(min(1.0, max(0.0, progress)), 4),
        is_complete=on_route.is_complete,
        activated_at=active.activated_at,
        updated_at=now.isoformat(),
        is_under_way=is_under_way,
        paused_reason=active.paused_reason,
        speed_multiplier=active.speed_multiplier,
    )


def create_route_update(payload: RouteUpdateCreate) -> RouteUpdate:
    old, new = payload.old_route, payload.new_route
    update = RouteUpdate(
        update_id=f"upd_{uuid.uuid4().hex[:10]}",
        mission_id=payload.mission_id,
        vessel_id=payload.vessel_id,
        old_route_id=old.route_id,
        new_route_id=new.route_id,
        reason=payload.reason,
        created_at=datetime.now(timezone.utc).isoformat(),
        current_position=payload.current_position,
        origin_snapshot=payload.origin_snapshot,
        old_route=old,
        new_route=new,
        distance_delta=round(new.distance_km - old.distance_km, 1),
        eta_delta=round(new.eta_hours - old.eta_hours, 1),
        fuel_delta=round(new.estimated_fuel.tonnes - old.estimated_fuel.tonnes, 1),
        risk_delta=round(new.risk_score - old.risk_score, 3),
        status="PENDING",
    )
    _route_updates[update.update_id] = update
    return update


def list_route_updates(
    *, vessel_id: str | None = None, status: RouteUpdateStatus | None = None
) -> list[RouteUpdate]:
    updates = list(_route_updates.values())
    if vessel_id is not None:
        updates = [u for u in updates if u.vessel_id == vessel_id]
    if status is not None:
        updates = [u for u in updates if u.status == status]
    return sorted(updates, key=lambda u: u.created_at, reverse=True)


def get_route_update(update_id: str) -> RouteUpdate | None:
    return _route_updates.get(update_id)


def respond_to_update(update_id: str, status: RouteUpdateStatus) -> RouteUpdate:
    """Records the Captain's decision. Accepting also activates the new
    route immediately -- the one state transition the whole workflow exists
    to demonstrate."""
    update = _route_updates.get(update_id)
    if update is None:
        raise RouteUpdateNotFound(update_id)
    if update.status != "PENDING":
        raise RouteUpdateAlreadyResolved(f"route update {update_id} was already {update.status}")

    resolved = update.model_copy(
        update={"status": status, "responded_at": datetime.now(timezone.utc).isoformat()}
    )
    _route_updates[update_id] = resolved

    previous = _active_routes.get(resolved.vessel_id)

    if status == "ACCEPTED":
        # Read the canonical position BEFORE replacing the active route -- once
        # the new route is in place, compute_vessel_state answers against it and
        # the voyage history would be lost. The vessel has been frozen since the
        # environment change was triggered, so this is exactly the snapshot the
        # proposed route was planned from.
        current = compute_vessel_state(resolved.vessel_id)
        travelled_before = current.distance_travelled_km if current else 0.0

        # How far the accepted route's first coordinate sits from where the
        # vessel actually is. A replan from current position should be ~0; a
        # large value means Shore and Ship have desynchronised, and it is
        # recorded rather than silently accepted so the UI can warn.
        # Measured against the frozen snapshot the route was planned from when
        # there is one, else against the live position.
        reference = None
        if resolved.origin_snapshot is not None:
            reference = (resolved.origin_snapshot.longitude, resolved.origin_snapshot.latitude)
        elif current is not None:
            reference = (current.longitude, current.latitude)

        start_offset_km = None
        if reference and resolved.new_route.coordinates:
            first = resolved.new_route.coordinates[0]
            start_offset_km = round(
                haversine_km(reference, (float(first[0]), float(first[1]))), 2
            )

        activate_route(
            mission_id=resolved.mission_id,
            vessel_id=resolved.vessel_id,
            route=resolved.new_route,
            horizon_hours=resolved.new_route.iceberg_exposure.horizon_hours,
            supersedes_update_id=update_id,
            distance_travelled_before_km=travelled_before,
            start_offset_km=start_offset_km,
            # Carry the operator's chosen demo speed across the swap, and start
            # moving again immediately: the freeze exists only to hold the
            # position still while the decision was outstanding.
            speed_multiplier=previous.speed_multiplier if previous else 1.0,
            under_way=True,
        )
    else:
        # A DECLINED update changes nothing about WHICH route is active -- the
        # existing one stays canonical -- but the vessel was frozen for the
        # decision and must now carry on along it from where it stopped.
        resume_vessel(resolved.vessel_id)

    return resolved


def describe_route_change(old: RoutePlan, new: RoutePlan, old_horizon: int, new_horizon: int) -> str:
    """Honest, backend-numbers-only description of what changed between two
    real RoutePlan objects -- the same 'compare the two real outputs' idea
    already used by `mission.planner._explain`, not a new hazard model."""
    old_when = "NOW" if old_horizon == 0 else f"T+{old_horizon}h"
    new_when = "NOW" if new_horizon == 0 else f"T+{new_horizon}h"

    candidates = [
        (
            abs(new.sea_ice_exposure.mean_sic_pct - old.sea_ice_exposure.mean_sic_pct),
            f"sea-ice concentration along the corridor moved from {old.sea_ice_exposure.mean_sic_pct:.0f}% to "
            f"{new.sea_ice_exposure.mean_sic_pct:.0f}% mean SIC",
        ),
        (
            abs(
                (new.iceberg_exposure.intersecting_count + new.iceberg_exposure.potential_count)
                - (old.iceberg_exposure.intersecting_count + old.iceberg_exposure.potential_count)
            )
            * 20.0,  # weighted so a changed berg count competes fairly with a percentage-point SIC change
            f"tracked icebergs able to intersect the corridor changed from "
            f"{old.iceberg_exposure.intersecting_count + old.iceberg_exposure.potential_count} to "
            f"{new.iceberg_exposure.intersecting_count + new.iceberg_exposure.potential_count}",
        ),
        (
            abs(new.weather_exposure.max_wave_m - old.weather_exposure.max_wave_m) * 10.0,
            f"peak wave height moved from {old.weather_exposure.max_wave_m:.1f} m to "
            f"{new.weather_exposure.max_wave_m:.1f} m",
        ),
    ]
    _, headline = max(candidates, key=lambda c: c[0])

    return (
        f"Forecast advanced from {old_when} to {new_when}: {headline} (real backend forecast). "
        f"Route recalculated from the vessel's current position."
    )
