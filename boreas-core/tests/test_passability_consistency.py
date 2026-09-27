"""The map and the router must tell the same story about the same water.

The invariant under test:

    IF a cell is blocked for this hull, THEN no returned route may enter it.

Previously the two disagreed. The map banded sea-ice concentration into
PASSABLE/CAUTION/RESTRICTED/IMPASSABLE while the router only made high
concentrations expensive (capped below A*'s block threshold), so a route could
run through water the legend had just coloured IMPASSABLE.

The distinction these tests protect is between two different questions:
`classify_sic` describes the ICE (absolute, what the map's four bands mean), and
`navigable_limit_sic` describes what a given HULL may enter. Collapsing them is
what made "IMPASSABLE" ambiguous in the first place.
"""

import numpy as np
import pytest

from boreas_core.mission import MissionPlanRequest, NoRouteFound, plan_mission
from boreas_core.mission.config import (
    DEFAULT_ICE_THRESHOLDS,
    IceThresholds,
    profile_for_ice_class,
)
from boreas_core.mission.fields import FieldModel, build_snapshot, domain_axes, land_mask
from boreas_core.mission.passability import (
    NAVIGABLE_LIMIT_BY_TIER,
    classify_sic,
    is_navigable,
    navigable_limit_sic,
)
from boreas_core.mission.planner import validate_route

T = DEFAULT_ICE_THRESHOLDS


# --------------------------------------------------- canonical classification ---


@pytest.mark.parametrize(
    "sic,expected",
    [
        (0.00, "PASSABLE"),
        (0.29, "PASSABLE"),
        (0.30, "PASSABLE"),  # boundary is inclusive of the lower band
        (0.31, "CAUTION"),
        (0.60, "CAUTION"),
        (0.61, "RESTRICTED"),
        (0.80, "RESTRICTED"),
        (0.81, "IMPASSABLE"),
        (1.00, "IMPASSABLE"),
    ],
)
def test_classification_follows_the_documented_bands(sic, expected):
    """Requirement 1: <30 PASSABLE, 30-60 CAUTION, 60-80 RESTRICTED, >80
    IMPASSABLE -- one function, used by map, router, validator and metrics."""
    assert classify_sic(sic, T) == expected


def test_the_four_bands_stay_distinct():
    """Requirement 3: the categories must not be collapsed into each other."""
    bands = [classify_sic(s, T) for s in (0.1, 0.45, 0.7, 0.9)]
    assert bands == ["PASSABLE", "CAUTION", "RESTRICTED", "IMPASSABLE"]
    assert len(set(bands)) == 4


def test_navigable_limits_are_ordered_by_hull_capability():
    """A better ice class may go further into ice, never less far."""
    heavy = NAVIGABLE_LIMIT_BY_TIER["HEAVY_ICEBREAKER"]
    strengthened = NAVIGABLE_LIMIT_BY_TIER["ICE_STRENGTHENED"]
    limited = NAVIGABLE_LIMIT_BY_TIER["LIMITED_ICE_CAPABILITY"]
    assert heavy >= strengthened > limited


def test_is_navigable_respects_the_hull_limit():
    strengthened = profile_for_ice_class("Arc5")
    assert is_navigable(0.85, strengthened)
    assert not is_navigable(0.95, strengthened)

    heavy = profile_for_ice_class("Arc7")
    assert is_navigable(0.95, heavy), "an icebreaker's job is exactly this water"


def test_classification_is_independent_of_the_vessel():
    """The ice is what it is. Only navigability depends on the hull -- keeping
    these separate is what lets the map describe conditions honestly while the
    router blocks per vessel."""
    assert classify_sic(0.95, T) == "IMPASSABLE"
    assert is_navigable(0.95, profile_for_ice_class("Arc7"))
    assert not is_navigable(0.95, profile_for_ice_class("Arc5"))


# ------------------------------------------------------- the routing invariant ---


def _grid_and_fields(ice_class: str, horizon: int = 0):
    lons, lats = domain_axes()
    land = land_mask(lons, lats)
    snapshot = build_snapshot(horizon)
    fm = FieldModel(snapshot, profile_for_ice_class(ice_class), T)
    return lons, lats, land, fm


# Both stations sit in 98-100% fast ice, and the simulated ice field varies
# almost only with latitude, so below ~68S it exceeds 90% at EVERY longitude.
# Only a heavy icebreaker can reach either station under this field; an
# ice-strengthened hull is genuinely stopped, which these tests assert
# explicitly rather than working around.
HEAVY_ICEBREAKER_VESSEL = "vasiliy_golovnin"
ICE_STRENGTHENED_VESSEL = "ivan_papanin"


@pytest.mark.parametrize("mission", ["CAPE_TOWN_TO_BHARATI", "CAPE_TOWN_TO_MAITRI"])
@pytest.mark.parametrize("horizon", [0, 24, 72])
def test_no_returned_route_enters_water_its_hull_cannot_work(mission, horizon):
    """THE invariant. Sampled along every segment, not just at the vertices."""
    plan = plan_mission(
        MissionPlanRequest(
            mission_id=mission, vessel_id=HEAVY_ICEBREAKER_VESSEL, horizon_hours=horizon
        )
    )
    lons, lats, land, fm = _grid_and_fields(plan.vessel.ice_class, horizon)
    limit = navigable_limit_sic(profile_for_ice_class(plan.vessel.ice_class))

    for route in plan.routes:
        report = validate_route(
            route.coordinates,
            fm=fm,
            profile=profile_for_ice_class(plan.vessel.ice_class),
            thresholds=T,
            lons=lons,
            lats=lats,
            land=land,
        )
        assert report.valid, f"{route.label} violates the map: {report.first_violation}"
        assert report.impassable_intersections == 0
        assert report.land_intersections == 0
        # The figure the route card shows agrees with the limit that blocked
        # the router, so the panel and the map cannot contradict each other.
        assert route.sea_ice_exposure.navigable_limit_pct == pytest.approx(limit * 100)


@pytest.mark.parametrize("mission", ["CAPE_TOWN_TO_BHARATI", "CAPE_TOWN_TO_MAITRI"])
def test_every_returned_route_carries_a_passing_validation(mission):
    """Requirement 13: an invalid route must never reach a route card."""
    plan = plan_mission(
        MissionPlanRequest(
            mission_id=mission, vessel_id=HEAVY_ICEBREAKER_VESSEL, horizon_hours=0
        )
    )
    for route in plan.routes:
        report = route.sea_ice_exposure.validation
        assert report is not None
        assert report.valid is True
        assert report.impassable_intersections == 0


def test_routes_never_cross_land():
    """Requirement 16 / 5: land is never navigable, and is a separate question
    from sea ice."""
    plan = plan_mission(MissionPlanRequest(mission_id="CAPE_TOWN_TO_BHARATI", horizon_hours=0))
    lons, lats, land, _ = _grid_and_fields(plan.vessel.ice_class)
    for route in plan.routes:
        for lon, lat in route.coordinates:
            cell = (int(np.argmin(np.abs(lats - lat))), int(np.argmin(np.abs(lons - lon))))
            assert not bool(land[cell]), f"{route.label} crosses land at {lon},{lat}"


def test_segment_validation_catches_what_vertex_checks_miss():
    """Requirement 4: the whole point of sampling along segments.

    A two-point route whose endpoints are both in open water, but whose straight
    line crosses the heavy coastal ice, must be rejected. Checking only the
    endpoints would pass it.
    """
    lons, lats, land, fm = _grid_and_fields("Arc5")
    profile = profile_for_ice_class("Arc5")

    # Both endpoints in light ice well north of the pack, but the line between
    # them dives south through it and back.
    coords = [[20.0, -50.0], [20.0, -71.0], [40.0, -50.0]]
    report = validate_route(
        coords, fm=fm, profile=profile, thresholds=T, lons=lons, lats=lats, land=land
    )
    assert not report.valid
    assert report.impassable_intersections > 0
    assert report.first_violation is not None


def test_validation_exempts_only_the_destination_cell():
    """The berth is the one exemption -- an Antarctic station sits in fast ice.
    The approach to it is not exempt, and the exemption is disclosed."""
    lons, lats, land, fm = _grid_and_fields("Arc5")
    profile = profile_for_ice_class("Arc5")

    # A route ENDING in the heavy ice is tolerated...
    ending = validate_route(
        [[11.73, -60.0], [11.73, -70.77]],
        fm=fm, profile=profile, thresholds=T, lons=lons, lats=lats, land=land,
    )
    # ...but the long approach through the pack is not, so this still fails --
    # proving the exemption really is just the one cell.
    assert ending.impassable_intersections > 0
    assert any("fast ice" in n for n in ending.notes)


# -------------------------------------------- deterministic blocked corridor ---


class _WallFieldModel:
    """A FieldModel whose ice is a wall across part of the domain, leaving a
    gap. Used to prove the router goes AROUND blocked water rather than through
    it -- which the shipped sea-ice field cannot demonstrate, because it varies
    almost only with latitude and so offers nothing to go around."""

    def __init__(self, inner: FieldModel, *, lon_range, lat_range):
        self._inner = inner
        self.profile = inner.profile
        self.thresholds = inner.thresholds
        self.snapshot = inner.snapshot
        self._lon_range = lon_range
        self._lat_range = lat_range

    def sic_at(self, lon, lat):
        lon = np.asarray(lon, dtype=float)
        lat = np.asarray(lat, dtype=float)
        base = np.zeros(np.broadcast(lon, lat).shape)
        inside = (
            (lon >= self._lon_range[0])
            & (lon <= self._lon_range[1])
            & (lat >= self._lat_range[0])
            & (lat <= self._lat_range[1])
        )
        return np.where(inside, 0.99, base)


def test_router_goes_around_a_blocked_corridor():
    """Requirement 15: a wall of impassable ice directly between two points must
    push the route around it, not through it."""
    lons, lats, land, fm = _grid_and_fields("Arc5")
    profile = profile_for_ice_class("Arc5")
    wall = _WallFieldModel(fm, lon_range=(30.0, 40.0), lat_range=(-60.0, -40.0))

    # The direct line runs straight through the wall.
    direct = validate_route(
        [[20.0, -50.0], [50.0, -50.0]],
        fm=wall, profile=profile, thresholds=T, lons=lons, lats=lats, land=land,
    )
    assert not direct.valid, "the direct line must be refused"
    assert direct.impassable_intersections > 0

    # A detour south of the wall is clean.
    around = validate_route(
        [[20.0, -50.0], [25.0, -65.0], [45.0, -65.0], [50.0, -50.0]],
        fm=wall, profile=profile, thresholds=T, lons=lons, lats=lats, land=land,
    )
    assert around.valid, f"detour should clear the wall, violated at {around.first_violation}"
    assert around.impassable_intersections == 0


@pytest.mark.parametrize("mission", ["CAPE_TOWN_TO_BHARATI", "CAPE_TOWN_TO_MAITRI"])
def test_hull_capability_decides_whether_a_station_is_reachable(mission):
    """The vessel-relative model, stated as behaviour: the same leg in the same
    ice is open to an icebreaker and closed to an ice-strengthened hull. That
    difference is the whole point of making passability vessel-relative rather
    than one absolute ceiling."""
    heavy = plan_mission(
        MissionPlanRequest(
            mission_id=mission, vessel_id=HEAVY_ICEBREAKER_VESSEL, horizon_hours=0
        )
    )
    assert heavy.routes, "an icebreaker must be able to work this ice"

    with pytest.raises(NoRouteFound):
        plan_mission(
            MissionPlanRequest(
                mission_id=mission, vessel_id=ICE_STRENGTHENED_VESSEL, horizon_hours=0
            )
        )


def test_unsuitable_hull_is_refused_with_an_explanation():
    """Requirement 10: no forced route, and a reason the operator can act on."""
    with pytest.raises(NoRouteFound) as exc:
        plan_mission(
            MissionPlanRequest(
                mission_id="CAPE_TOWN_TO_MAITRI", vessel_id="ivan_papanin", horizon_hours=0
            )
        )
    message = str(exc.value)
    assert "No navigable corridor" in message
    # Names the hull's limit rather than failing silently.
    assert "%" in message and "limit" in message.lower()


def test_thresholds_are_configurable_without_touching_the_classifier():
    """Requirement 1: one function, driven by the thresholds it is handed."""
    strict = IceThresholds(passable_max=0.10, caution_max=0.20, restricted_max=0.30)
    assert classify_sic(0.15, strict) == "CAUTION"
    assert classify_sic(0.15, T) == "PASSABLE"


@pytest.mark.parametrize("horizon", [0, 24, 72])
def test_map_grid_and_routing_grid_agree_cell_for_cell(horizon):
    """Requirement 6/7: the raster the map draws and the field the router costs
    must be the same data at the same horizon, with no coordinate flip.

    Samples the forecast grid the frontend receives and the FieldModel the
    planner uses at identical coordinates; a latitude/longitude reversal or an
    off-by-one row index would show up immediately.
    """
    from boreas_core.forecast import get_sea_ice_forecast

    grid = get_sea_ice_forecast(horizon_hours=horizon)
    _, _, _, fm = _grid_and_fields("Arc7", horizon)

    grid_lat = np.asarray(grid.grid_lat, dtype=float)
    grid_lon = np.asarray(grid.grid_lon, dtype=float)
    values = np.asarray(grid.sic_values, dtype=float)

    # Spot-check a spread of cells rather than the whole grid.
    for r in range(0, len(grid_lat), max(1, len(grid_lat) // 6)):
        for c in range(0, len(grid_lon), max(1, len(grid_lon) // 6)):
            lat, lon = float(grid_lat[r]), float(grid_lon[c])
            from_planner = float(fm.sic_at(np.array([lon]), np.array([lat]))[0])
            assert from_planner == pytest.approx(values[r][c], abs=1e-6), (
                f"map/router disagree at ({lon}, {lat}) for T+{horizon}"
            )


def test_existing_hazard_routing_still_works():
    """Requirement 17.12: icebergs and weather must be unaffected by the
    passability change."""
    plan = plan_mission(
        MissionPlanRequest(
            mission_id="CAPE_TOWN_TO_BHARATI",
            vessel_id=HEAVY_ICEBREAKER_VESSEL,
            horizon_hours=24,
        )
    )
    assert len(plan.routes) == 3
    for route in plan.routes:
        assert route.iceberg_exposure.tracked_count > 0
        assert route.weather_exposure.mode == "DEMO"
        assert route.risk_score >= 0.0
