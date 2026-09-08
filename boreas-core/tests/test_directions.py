import pytest

from boreas_core.routing.astar import astar_route
from boreas_core.routing.directions import (
    bearing_to_compass,
    build_route_legs,
    great_circle_bearing_deg,
    simplify_path_rdp,
)
from boreas_core.routing.grid import synthetic_southern_ocean_grid


def test_bearing_due_north_is_zero():
    bearing = great_circle_bearing_deg(0.0, -70.0, 0.0, -60.0)
    assert bearing == pytest.approx(0.0, abs=1.0)


def test_bearing_due_east_is_ninety():
    # A short span so great-circle "bulge toward the pole" (a real effect --
    # the rhumb line along a parallel is not a geodesic) stays negligible;
    # see test_bearing_geodesic_bulges_toward_pole_at_high_latitude below for
    # that effect made explicit rather than accidentally failing this test.
    bearing = great_circle_bearing_deg(0.0, -70.0, 0.5, -70.0)
    assert bearing == pytest.approx(90.0, abs=1.0)


def test_bearing_geodesic_bulges_toward_pole_at_high_latitude():
    # Over a large longitude span at high southern latitude, the shortest
    # (great-circle) path between two points on the same parallel is not
    # along that parallel -- it initially heads slightly poleward (south).
    # A naive "due east" assumption over long distances would be wrong,
    # which is exactly why this module uses the real spherical formula
    # instead of a planar atan2(dlon, dlat).
    bearing = great_circle_bearing_deg(0.0, -70.0, 10.0, -70.0)
    assert bearing > 90.0


def test_bearing_due_south_is_180():
    bearing = great_circle_bearing_deg(0.0, -60.0, 0.0, -70.0)
    assert bearing == pytest.approx(180.0, abs=1.0)


@pytest.mark.parametrize(
    "bearing,expected",
    [(0, "N"), (44, "NE"), (90, "E"), (135, "SE"), (180, "S"), (225, "SW"), (270, "W"), (315, "NW"), (359, "N")],
)
def test_compass_bucketing(bearing, expected):
    assert bearing_to_compass(bearing) == expected


def test_rdp_collapses_staircase_to_two_vertices():
    # A classic 8-connected "staircase" approximating a straight diagonal line.
    staircase = [(0.0, 0.0), (0.1, 0.0), (0.1, 0.1), (0.2, 0.1), (0.2, 0.2), (0.3, 0.2), (0.3, 0.3)]
    simplified = simplify_path_rdp(staircase, epsilon_km=15.0)
    assert len(simplified) <= 2
    assert simplified[0] == staircase[0]
    assert simplified[-1] == staircase[-1]


def test_rdp_keeps_a_real_turn():
    # An L-shaped path: RDP should keep the corner since it's a real turn, not noise.
    path = [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0), (1.0, 2.0), (2.0, 2.0)]
    simplified = simplify_path_rdp(path, epsilon_km=5.0)
    assert (0.0, 2.0) in simplified


def test_build_route_legs_distances_sum_to_total():
    grid = synthetic_southern_ocean_grid(seed=0)
    navigable = [
        (r, c)
        for r in range(grid.shape[0])
        for c in range(grid.shape[1])
        if grid.risk[r, c] < 0.5
    ]
    start, goal = navigable[0], navigable[-1]
    route = astar_route(grid, start, goal)
    assert route is not None

    legs = build_route_legs(route)
    assert len(legs) >= 1
    # last leg is the zero-distance arrival marker
    assert legs[-1].bearing_deg is None
    assert legs[-1].distance_km == 0.0

    total_leg_distance = sum(leg.distance_km for leg in legs)
    assert total_leg_distance == pytest.approx(route.total_distance_km, rel=1e-6)


def test_build_route_legs_produces_far_fewer_legs_than_raw_cells():
    grid = synthetic_southern_ocean_grid(seed=1)
    navigable = [
        (r, c)
        for r in range(grid.shape[0])
        for c in range(grid.shape[1])
        if grid.risk[r, c] < 0.5
    ]
    start, goal = navigable[0], navigable[-1]
    route = astar_route(grid, start, goal)
    assert route is not None

    legs = build_route_legs(route)
    # The whole point of RDP+merge is collapsing a long staircase into a
    # handful of real turns -- there should be an order-of-magnitude fewer
    # legs than raw path cells whenever the path is more than a few cells.
    if len(route.path_cells) > 10:
        assert len(legs) < len(route.path_cells) / 2


def test_build_route_legs_handles_trivial_two_point_path():
    grid = synthetic_southern_ocean_grid(seed=2)
    navigable = [
        (r, c)
        for r in range(grid.shape[0])
        for c in range(grid.shape[1])
        if grid.risk[r, c] < 0.5
    ]
    start = navigable[0]
    goal = (start[0], start[1] + 1) if start[1] + 1 < grid.shape[1] else (start[0], start[1] - 1)
    route = astar_route(grid, start, goal)
    assert route is not None
    legs = build_route_legs(route)
    assert len(legs) >= 1
