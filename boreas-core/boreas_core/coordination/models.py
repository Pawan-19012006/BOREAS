"""Shared shore<->ship coordination contracts.

These are the minimal, additive models for the prototype workflow: a vessel
is following an `ActiveRoute`; Shore may propose a `RouteUpdate` (a genuinely
different route from `POST /mission/plan`, not a fabricated one); the
Captain accepts or declines it; `VesselState` is the one canonical position
both Shore and Ship poll, so they never show two different "current
positions" for the same ship.

Nothing here is a second routing engine -- `RoutePlan` (the backend's real
A* output) is reused verbatim as the payload of both the active route and
the update proposal.
"""

from typing import Literal

from pydantic import BaseModel, Field

from boreas_core.mission.models import RoutePlan

RouteUpdateStatus = Literal["PENDING", "ACCEPTED", "DECLINED"]


class MissionInfo(BaseModel):
    """Static mission descriptor -- origin/destination naming, reused from
    `boreas_core.mission.config.MISSIONS` verbatim (no duplicate mission
    definitions)."""

    mission_id: str
    label: str
    origin_name: str
    origin: list[float] = Field(..., description="[lon, lat]")
    destination_name: str
    destination: list[float] = Field(..., description="[lon, lat]")


class ActiveRoute(BaseModel):
    """The route a vessel is currently following. Activated once when Shore
    starts monitoring, and replaced whenever a `RouteUpdate` is accepted."""

    mission_id: str
    vessel_id: str
    route: RoutePlan
    horizon_hours: int = Field(..., description="Forecast horizon this route was planned against")
    activated_at: str = Field(..., description="ISO 8601 UTC -- also the SIMULATED voyage clock's zero point")
    supersedes_update_id: str | None = Field(
        None, description="The RouteUpdate whose acceptance produced this activation, if any"
    )


class VesselState(BaseModel):
    """The single canonical current position for a vessel under an
    ActiveRoute. SIMULATED: advanced from the active route's own real
    distance/ETA and geometry, not live telemetry -- boreas-core has no
    operational AIS coverage in the Southern Ocean (see
    docs/architecture/KNOWN_LIMITATIONS.md sec 1.3)."""

    vessel_id: str
    mission_id: str
    route_id: str = Field(..., description="RoutePlan.route_id of the currently active route")
    longitude: float
    latitude: float
    heading_deg: float | None = Field(None, description="True course to the next waypoint; null on arrival")
    speed_kt: float
    distance_travelled_km: float
    distance_remaining_km: float
    distance_to_next_waypoint_km: float
    next_waypoint_index: int = Field(..., description="Index into route.coordinates of the waypoint being steered toward")
    progress_fraction: float = Field(..., ge=0.0, le=1.0)
    is_complete: bool
    activated_at: str
    updated_at: str
    provenance: str = "SIMULATED — advanced from the active route's real distance/ETA; not live AIS telemetry"


class RouteUpdateCreate(BaseModel):
    mission_id: str
    vessel_id: str
    reason: str
    current_position: list[float] = Field(..., description="[lon, lat] of the vessel when this update was proposed")
    old_route: RoutePlan
    new_route: RoutePlan


class RouteUpdate(BaseModel):
    update_id: str
    mission_id: str
    vessel_id: str
    old_route_id: str
    new_route_id: str
    reason: str
    created_at: str
    current_position: list[float] = Field(..., description="[lon, lat] of the vessel when this update was proposed")
    old_route: RoutePlan
    new_route: RoutePlan
    distance_delta: float = Field(..., description="new_route.distance_km - old_route.distance_km")
    eta_delta: float = Field(..., description="new_route.eta_hours - old_route.eta_hours")
    fuel_delta: float = Field(..., description="new_route.estimated_fuel.tonnes - old_route.estimated_fuel.tonnes")
    risk_delta: float = Field(..., description="new_route.risk_score - old_route.risk_score")
    status: RouteUpdateStatus = "PENDING"
    responded_at: str | None = None


class RouteUpdateRespond(BaseModel):
    status: Literal["ACCEPTED", "DECLINED"]


class ActivateRouteRequest(BaseModel):
    """Shore's 'Start monitoring' action: hands the backend the RoutePlan it
    already has from `/mission/plan` so both apps can poll one canonical
    active route and vessel position for it."""

    mission_id: str
    vessel_id: str
    route: RoutePlan


class SimulateChangeRequest(BaseModel):
    """Shore's 'SIMULATE ENVIRONMENT CHANGE' action. Only a vessel_id is
    needed: the vessel's current (simulated) position and active route are
    already known to the backend."""

    vessel_id: str
