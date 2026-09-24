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

from .geo import KM_PER_NM, LonLat, position_at_distance
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

# Sim-hours advanced per real second once a route is active -- mirrors
# frontend/src/simulation/voyageSimulation.ts's SIM_HOURS_PER_SECOND exactly,
# so a route with a multi-hundred-hour ETA still visibly moves within a short
# demo/poll window, and both apps' sense of "how fast time passes" agrees.
TIME_ACCELERATION_HOURS_PER_SECOND = 1.5

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
) -> ActiveRoute:
    """Sets (or replaces) the vessel's active route and resets the simulated
    voyage clock to now. When this follows an accepted RouteUpdate, `route`
    is that update's `new_route` -- whose own coordinates[0] is the position
    the vessel actually held at proposal time, so resetting the clock here
    produces a continuous handoff with no jump: the ship "continues" rather
    than restarting.
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
    )
    _active_routes[vessel_id] = active
    return active


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

    activated_at = datetime.fromisoformat(active.activated_at)
    now = datetime.now(timezone.utc)
    elapsed_sim_hours = max(0.0, (now - activated_at).total_seconds()) * TIME_ACCELERATION_HOURS_PER_SECOND
    travelled_km = elapsed_sim_hours * km_per_hour

    on_route = position_at_distance(path, travelled_km)
    speed_kt = 0.0 if on_route.is_complete else km_per_hour / KM_PER_NM

    return VesselState(
        vessel_id=vessel_id,
        mission_id=active.mission_id,
        route_id=route.route_id,
        longitude=round(on_route.position[0], 5),
        latitude=round(on_route.position[1], 5),
        heading_deg=round(on_route.bearing_deg, 1) if on_route.bearing_deg is not None else None,
        speed_kt=round(speed_kt, 2),
        distance_travelled_km=round(on_route.distance_travelled_km, 2),
        distance_remaining_km=round(on_route.distance_remaining_km, 2),
        distance_to_next_waypoint_km=round(on_route.distance_to_next_waypoint_km, 2),
        next_waypoint_index=on_route.next_waypoint_index,
        progress_fraction=round(on_route.progress_fraction, 4),
        is_complete=on_route.is_complete,
        activated_at=active.activated_at,
        updated_at=now.isoformat(),
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

    if status == "ACCEPTED":
        activate_route(
            mission_id=resolved.mission_id,
            vessel_id=resolved.vessel_id,
            route=resolved.new_route,
            horizon_hours=resolved.new_route.iceberg_exposure.horizon_hours,
            supersedes_update_id=update_id,
        )

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
