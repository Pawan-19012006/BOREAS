"""A Gymnasium environment for learning an incremental route re-planning policy
(BOREAS design doc §5.6).

The A* planner (astar.py) is the always-on baseline: fast, explainable, and
globally optimal for a *static* risk grid. What it can't do cheaply is
*incrementally* adjust a route as new hazard data streams in without a full
re-solve. This environment trains a policy to nudge the vessel's heading
in response to local risk, which is a fundamentally different (and much
cheaper, at inference time) problem than global search.
"""

from dataclasses import dataclass

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from .grid import RiskGrid

# 8-connected heading actions, matching astar.py's neighbor offsets so a
# trained policy's actions are directly comparable to A*'s.
HEADINGS: list[tuple[int, int]] = [
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1), (0, 1),
    (1, -1), (1, 0), (1, 1),
]

OBSERVATION_WINDOW = 5  # (2*w+1)^2 local risk patch


@dataclass
class RoutingEnvConfig:
    # This env models *incremental local re-planning* (AdaptiveRouter's
    # policy-based detour around a newly-invalidated stretch of an existing
    # A*-planned route, see routing/policy.py), not long-range global
    # navigation -- A* already solves that optimally and unboundedly.
    # goal_radius_cells bounds start/goal sampling accordingly, and
    # max_steps is sized so a direct 8-connected path always fits with room
    # to detour around hazards.
    max_steps: int = 40
    goal_radius_cells: int = 12
    # Risk must act as a soft tie-breaker between routes of similar length, not
    # an incentive strong enough to outweigh actually reaching the goal -- a
    # too-large risk_penalty_weight (tried 1.5-4.0) made the accumulated
    # per-step penalty over an episode exceed goal_bonus, and the learned
    # policy degenerated into fleeing toward the lowest-risk region regardless
    # of the goal. Empirically retuned so goal-directed progress dominates.
    risk_penalty_weight: float = 0.3
    fuel_cost_per_step: float = 0.02
    goal_bonus: float = 50.0
    collision_penalty: float = 3.0
    progress_reward_weight: float = 1.0


class IceRoutingEnv(gym.Env):
    """Observation: local risk window + normalised vector-to-goal.
    Action: one of 8 headings (discrete).
    Reward: -progress_cost - risk_penalty - fuel_cost, +goal_bonus on arrival.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        grid: RiskGrid,
        *,
        config: RoutingEnvConfig | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.grid = grid
        self.config = config or RoutingEnvConfig()
        self._rng = np.random.default_rng(seed)

        patch_dim = (2 * OBSERVATION_WINDOW + 1) ** 2
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(patch_dim + 2,), dtype=np.float32
        )
        self.action_space = spaces.Discrete(len(HEADINGS))

        self.position: tuple[int, int] = (0, 0)
        self.goal: tuple[int, int] = (0, 0)
        self.steps_taken = 0
        self._prev_distance = 0.0

    def _local_risk_patch(self) -> np.ndarray:
        h, w = self.grid.shape
        row, col = self.position
        patch = np.ones((2 * OBSERVATION_WINDOW + 1, 2 * OBSERVATION_WINDOW + 1), dtype=np.float32)
        for i, dr in enumerate(range(-OBSERVATION_WINDOW, OBSERVATION_WINDOW + 1)):
            for j, dc in enumerate(range(-OBSERVATION_WINDOW, OBSERVATION_WINDOW + 1)):
                r, c = row + dr, col + dc
                if 0 <= r < h and 0 <= c < w:
                    patch[i, j] = self.grid.risk[r, c]
        return patch.flatten()

    def _observation(self) -> np.ndarray:
        patch = self._local_risk_patch()
        h, w = self.grid.shape
        goal_vec = np.array(
            [
                (self.goal[0] - self.position[0]) / h,
                (self.goal[1] - self.position[1]) / w,
            ],
            dtype=np.float32,
        )
        return np.concatenate([patch * 2 - 1, np.clip(goal_vec, -1, 1)]).astype(np.float32)

    def _distance_to_goal(self) -> float:
        return float(np.hypot(self.position[0] - self.goal[0], self.position[1] - self.goal[1]))

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        h, w = self.grid.shape
        navigable = np.argwhere(self.grid.risk < 0.9)
        if len(navigable) < 2:
            raise RuntimeError("Grid has too few navigable cells to sample start/goal.")

        r = self.config.goal_radius_cells
        for _ in range(50):  # bounded retries; falls back to global sample below
            start_idx = navigable[self._rng.integers(len(navigable))]
            nearby_mask = (
                (np.abs(navigable[:, 0] - start_idx[0]) <= r)
                & (np.abs(navigable[:, 1] - start_idx[1]) <= r)
            )
            nearby = navigable[nearby_mask]
            if len(nearby) >= 2:
                goal_idx = nearby[self._rng.integers(len(nearby))]
                if tuple(goal_idx) != tuple(start_idx):
                    self.position = tuple(start_idx)
                    self.goal = tuple(goal_idx)
                    break
        else:
            idx = self._rng.choice(len(navigable), size=2, replace=False)
            self.position = tuple(navigable[idx[0]])
            self.goal = tuple(navigable[idx[1]])

        self.steps_taken = 0
        self._prev_distance = self._distance_to_goal()
        return self._observation(), {}

    def step(self, action: int):
        self.steps_taken += 1
        d_row, d_col = HEADINGS[action]
        h, w = self.grid.shape
        new_row = int(np.clip(self.position[0] + d_row, 0, h - 1))
        new_col = int(np.clip(self.position[1] + d_col, 0, w - 1))

        risk = float(self.grid.risk[new_row, new_col])
        collided = risk >= 0.95
        if not collided:
            self.position = (new_row, new_col)

        reached_goal = self.position == self.goal
        new_distance = self._distance_to_goal()
        progress = self._prev_distance - new_distance  # positive if we got closer
        self._prev_distance = new_distance

        reward = self.config.progress_reward_weight * progress
        reward -= self.config.fuel_cost_per_step
        reward -= self.config.risk_penalty_weight * risk
        if collided:
            reward -= self.config.collision_penalty
        if reached_goal:
            reward += self.config.goal_bonus

        terminated = reached_goal
        truncated = self.steps_taken >= self.config.max_steps
        return self._observation(), reward, terminated, truncated, {"collided": collided}
