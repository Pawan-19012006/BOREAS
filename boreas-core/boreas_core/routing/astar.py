"""A* route search over a RiskGrid.

This is the "always-available, explainable baseline" from BOREAS design doc
§5.6: fast, deterministic, and correct without any learned component, so the
platform still functions if the RL re-planner (routing/env.py, train_ppo.py)
hasn't converged or isn't available.
"""

import heapq
from dataclasses import dataclass

from .grid import RiskGrid

Cell = tuple[int, int]

# 8-connected moves: (d_row, d_col)
NEIGHBOR_OFFSETS: list[Cell] = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
]


@dataclass
class RouteResult:
    path_cells: list[Cell]
    path_lonlat: list[tuple[float, float]]
    total_distance_km: float
    total_cost: float
    max_risk_on_path: float


def _edge_cost(grid: RiskGrid, a: Cell, b: Cell, *, risk_weight: float) -> float:
    distance_km = grid.haversine_km(a, b)
    # Average the risk of the two endpoints so cost is symmetric.
    risk = 0.5 * (grid.risk[a] + grid.risk[b])
    return distance_km * (1.0 + risk_weight * risk)


def astar_route(
    grid: RiskGrid,
    start: Cell,
    goal: Cell,
    *,
    risk_weight: float = 2.0,
    blocked_threshold: float = 0.95,
) -> RouteResult | None:
    """Standard A* with a haversine-distance heuristic.

    The heuristic (plain distance) never overestimates true edge cost
    (distance * (1 + risk_weight * risk) >= distance since risk_weight, risk >= 0),
    so the search remains admissible and the result is provably shortest
    under the chosen risk-weighted cost model.
    """
    if grid.is_blocked(*start, blocked_threshold=blocked_threshold):
        raise ValueError("start cell is blocked")
    if grid.is_blocked(*goal, blocked_threshold=blocked_threshold):
        raise ValueError("goal cell is blocked")

    open_heap: list[tuple[float, Cell]] = [(0.0, start)]
    came_from: dict[Cell, Cell] = {}
    g_score: dict[Cell, float] = {start: 0.0}
    visited: set[Cell] = set()

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current in visited:
            continue
        visited.add(current)

        if current == goal:
            return _reconstruct(grid, came_from, current, g_score[current], risk_weight)

        for d_row, d_col in NEIGHBOR_OFFSETS:
            neighbor = (current[0] + d_row, current[1] + d_col)
            if not grid.in_bounds(*neighbor) or grid.is_blocked(
                *neighbor, blocked_threshold=blocked_threshold
            ):
                continue
            tentative_g = g_score[current] + _edge_cost(
                grid, current, neighbor, risk_weight=risk_weight
            )
            if tentative_g < g_score.get(neighbor, float("inf")):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f_score = tentative_g + grid.haversine_km(neighbor, goal)
                heapq.heappush(open_heap, (f_score, neighbor))

    return None  # no path found (fully blocked)


def _reconstruct(
    grid: RiskGrid,
    came_from: dict[Cell, Cell],
    current: Cell,
    total_cost: float,
    risk_weight: float,
) -> RouteResult:
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()

    total_distance = sum(
        grid.haversine_km(path[i], path[i + 1]) for i in range(len(path) - 1)
    )
    max_risk = max(grid.risk[cell] for cell in path)
    return RouteResult(
        path_cells=path,
        path_lonlat=[grid.cell_center(*c) for c in path],
        total_distance_km=total_distance,
        total_cost=total_cost,
        max_risk_on_path=float(max_risk),
    )
