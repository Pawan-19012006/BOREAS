import numpy as np
import pytest

from boreas_core.routing.astar import astar_route
from boreas_core.routing.grid import RiskGrid


def make_open_grid(size: int = 10) -> RiskGrid:
    lons = np.linspace(-10, 10, size)
    lats = np.linspace(-70, -60, size)
    risk = np.zeros((size, size))
    return RiskGrid(lons=lons, lats=lats, risk=risk)


def test_finds_direct_path_on_open_grid():
    grid = make_open_grid()
    result = astar_route(grid, (0, 0), (9, 9))
    assert result is not None
    assert result.path_cells[0] == (0, 0)
    assert result.path_cells[-1] == (9, 9)
    # 8-connected diagonal move should be the shortest path length in cells.
    assert len(result.path_cells) == 10


def test_route_avoids_blocked_wall():
    grid = make_open_grid(size=11)
    grid.risk[:, 5] = 1.0  # a solid wall down the middle
    grid.risk[8, 5] = 0.0  # one gap
    result = astar_route(grid, (0, 0), (0, 10))
    assert result is not None
    assert (8, 5) in result.path_cells
    assert result.max_risk_on_path < 1.0


def test_route_prefers_lower_risk_when_detour_is_cheap():
    grid = make_open_grid(size=11)
    grid.risk[5, :] = 0.8  # a risky band across the whole grid, but passable
    grid.risk[5, 10] = 0.0  # a free corridor at the edge
    result = astar_route(grid, (0, 0), (10, 0), risk_weight=20.0)
    assert result is not None
    assert result.max_risk_on_path < 0.8


def test_raises_when_start_or_goal_blocked():
    grid = make_open_grid()
    grid.risk[0, 0] = 1.0
    with pytest.raises(ValueError):
        astar_route(grid, (0, 0), (9, 9))


def test_returns_none_when_fully_partitioned():
    grid = make_open_grid(size=6)
    grid.risk[:, 3] = 1.0  # full wall, no gap
    result = astar_route(grid, (0, 0), (0, 5))
    assert result is None
