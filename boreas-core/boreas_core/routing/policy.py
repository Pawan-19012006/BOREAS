"""AdaptiveRouter: A* baseline + optional PPO incremental re-planner.

Implements the two-tier routing behaviour from BOREAS design doc §5.6: A*
always provides a fast, explainable, globally-optimal route over the current
risk grid. When new hazard data invalidates part of an existing route, a
full A* re-solve is correct but comparatively expensive; the (optional)
learned policy nudges the path locally instead. If no trained policy is
available, or the platform wants zero model risk, the router transparently
falls back to a full A* re-solve -- it never depends on the RL component.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from .astar import Cell, RouteResult, astar_route
from .grid import RiskGrid

if TYPE_CHECKING:
    from stable_baselines3 import PPO


@dataclass
class RouteDecision:
    result: RouteResult
    replanned: bool
    replan_reason: str | None
    used_policy: bool


class AdaptiveRouter:
    def __init__(self, *, risk_change_threshold: float = 0.25) -> None:
        self._policy: "PPO | None" = None
        self.risk_change_threshold = risk_change_threshold

    def load_policy(self, model_path: Path) -> None:
        from stable_baselines3 import PPO  # local import: optional heavy dependency

        self._policy = PPO.load(model_path)

    @property
    def has_policy(self) -> bool:
        return self._policy is not None

    def plan(self, grid: RiskGrid, start: Cell, goal: Cell) -> RouteDecision:
        result = astar_route(grid, start, goal)
        if result is None:
            raise ValueError("No viable route exists on the current risk grid.")
        return RouteDecision(result=result, replanned=False, replan_reason=None, used_policy=False)

    def replan_if_needed(
        self,
        *,
        grid: RiskGrid,
        previous_route: RouteResult,
        updated_grid: RiskGrid,
        current_position: Cell,
        goal: Cell,
    ) -> RouteDecision:
        """Called when new hazard data arrives. Only re-plans if the risk along
        the existing route actually changed materially -- this is what makes
        the policy "incremental" rather than a full re-solve on every tick.
        """
        risk_delta = self._max_risk_delta_along_path(grid, updated_grid, previous_route.path_cells)

        if risk_delta < self.risk_change_threshold:
            return RouteDecision(
                result=previous_route, replanned=False, replan_reason=None, used_policy=False
            )

        reason = f"risk along route increased by {risk_delta:.2f} (threshold {self.risk_change_threshold})"

        if self._policy is not None:
            local_path = self._policy_local_detour(updated_grid, current_position, goal)
            if local_path is not None:
                return RouteDecision(
                    result=local_path, replanned=True, replan_reason=reason, used_policy=True
                )

        # Fall back to a full, always-correct A* re-solve.
        result = astar_route(updated_grid, current_position, goal)
        if result is None:
            raise ValueError("No viable route exists on the updated risk grid.")
        return RouteDecision(result=result, replanned=True, replan_reason=reason, used_policy=False)

    @staticmethod
    def _max_risk_delta_along_path(
        grid: RiskGrid, updated_grid: RiskGrid, path_cells: list[Cell]
    ) -> float:
        deltas = [
            abs(float(updated_grid.risk[cell]) - float(grid.risk[cell])) for cell in path_cells
        ]
        return max(deltas) if deltas else 0.0

    def _policy_local_detour(
        self, grid: RiskGrid, position: Cell, goal: Cell, *, max_steps: int = 60
    ) -> RouteResult | None:
        from .env import HEADINGS, IceRoutingEnv, RoutingEnvConfig

        env = IceRoutingEnv(grid, config=RoutingEnvConfig(max_steps=max_steps))
        env.position = position
        env.goal = goal
        env.steps_taken = 0
        env._prev_distance = env._distance_to_goal()
        obs = env._observation()

        path = [position]
        for _ in range(max_steps):
            action, _ = self._policy.predict(obs, deterministic=True)
            obs, _reward, terminated, truncated, info = env.step(int(action))
            if not info.get("collided", False):
                path.append(env.position)
            if terminated:
                break
            if truncated:
                return None  # policy failed to reach the goal within budget

        total_distance = sum(
            grid.haversine_km(path[i], path[i + 1]) for i in range(len(path) - 1)
        )
        max_risk = max(float(grid.risk[c]) for c in path)
        return RouteResult(
            path_cells=path,
            path_lonlat=[grid.cell_center(*c) for c in path],
            total_distance_km=total_distance,
            total_cost=total_distance,
            max_risk_on_path=max_risk,
        )
