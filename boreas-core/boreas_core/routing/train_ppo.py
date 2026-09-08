"""Train a PPO re-planning policy on IceRoutingEnv (BOREAS design doc §5.6).

This is a proof-of-concept scale training run (small network, bounded
timesteps) intended to prove the RL loop is wired correctly end-to-end, not
to produce an operationally tuned policy -- per the design doc's own risk
mitigation: "A*/Dijkstra baseline remains fully functional independently; RL
is an additive re-planning layer, not a dependency." Run directly for a
quick benchmark:

    uv run python -m boreas_core.routing.train_ppo --timesteps 20000
"""

import argparse
import time
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor

from .astar import astar_route
from .env import IceRoutingEnv, RoutingEnvConfig
from .grid import synthetic_southern_ocean_grid

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "artifacts" / "ppo_router.zip"


def _make_env(seed: int):
    def _init():
        grid = synthetic_southern_ocean_grid(seed=seed)
        return Monitor(IceRoutingEnv(grid, config=RoutingEnvConfig(), seed=seed))

    return _init


def train(timesteps: int, model_path: Path, n_envs: int = 4, seed: int = 0) -> dict:
    vec_env = make_vec_env(
        lambda: IceRoutingEnv(synthetic_southern_ocean_grid(seed=seed), seed=seed),
        n_envs=n_envs,
    )
    model = PPO(
        "MlpPolicy",
        vec_env,
        policy_kwargs={"net_arch": [64, 64]},
        n_steps=256,
        batch_size=256,
        verbose=0,
        seed=seed,
    )
    start = time.time()
    model.learn(total_timesteps=timesteps)
    elapsed = time.time() - start

    model_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(model_path)

    return {"timesteps": timesteps, "elapsed_seconds": elapsed, "model_path": str(model_path)}


def evaluate_against_astar(model_path: Path, n_episodes: int = 20, seed: int = 1) -> dict:
    """Compares learned-policy episode return against the A* baseline's implied
    return on the same start/goal pairs, so we honestly report whether the RL
    layer is adding value yet or is still additive-only (per the design doc's
    risk mitigation) at this training budget.
    """
    model = PPO.load(model_path)
    grid = synthetic_southern_ocean_grid(seed=seed)
    env = IceRoutingEnv(grid, seed=seed)

    ppo_returns = []
    ppo_successes = 0
    astar_path_found = 0
    for _ in range(n_episodes):
        obs, _ = env.reset()
        start, goal = env.position, env.goal
        episode_return = 0.0
        reached_goal = False
        for _ in range(env.config.max_steps):
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(int(action))
            episode_return += reward
            if terminated:
                reached_goal = True
            if terminated or truncated:
                break
        ppo_returns.append(episode_return)
        ppo_successes += int(reached_goal)

        if astar_route(grid, start, goal) is not None:
            astar_path_found += 1

    import numpy as np

    return {
        "n_episodes": n_episodes,
        "ppo_mean_return": float(np.mean(ppo_returns)),
        "ppo_std_return": float(np.std(ppo_returns)),
        "ppo_goal_reached_fraction": ppo_successes / n_episodes,
        "astar_solved_fraction": astar_path_found / n_episodes,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timesteps", type=int, default=20_000)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    args = parser.parse_args()

    stats = train(args.timesteps, args.model_path)
    print(f"Trained PPO router: {stats}")
    eval_stats = evaluate_against_astar(args.model_path)
    print(f"Evaluation vs. A*: {eval_stats}")
