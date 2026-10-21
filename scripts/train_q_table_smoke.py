from __future__ import annotations

from collections import defaultdict
import os
from pathlib import Path
import random
from statistics import mean
import sys
from typing import DefaultDict


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config import build_training_stage_0_config
from env import TowerDefenseEnv
from rl_training import MACRO_ACTION_WAIT
from training_adapter import FastCompatibilityEnv


BENCHMARK_SEEDS = [1, 7, 42, 100, 256]
EPISODES = int(os.getenv("TD_SMOKE_EPISODES", "20"))
BASE_SEED = int(os.getenv("TD_SMOKE_BASE_SEED", "42"))
ALPHA = float(os.getenv("TD_SMOKE_ALPHA", "0.2"))
GAMMA = float(os.getenv("TD_SMOKE_GAMMA", "0.95"))
EPSILON = float(os.getenv("TD_SMOKE_EPSILON", "0.20"))


QTable = DefaultDict[tuple[int, ...], dict[int, float]]


def pick_action(
    state: tuple[int, ...],
    valid_actions: list[int],
    q_table: QTable,
    rng: random.Random,
    epsilon: float,
) -> int:
    if not valid_actions:
        return MACRO_ACTION_WAIT
    if rng.random() < epsilon:
        return rng.choice(valid_actions)

    state_values = q_table[state]
    best_value = None
    best_actions: list[int] = []
    for action in valid_actions:
        value = float(state_values.get(action, 0.0))
        if best_value is None or value > best_value:
            best_value = value
            best_actions = [action]
        elif value == best_value:
            best_actions.append(action)
    return rng.choice(best_actions or valid_actions)


def run_episode(
    seed: int,
    q_table: QTable,
    rng: random.Random,
    epsilon: float,
) -> dict[str, object]:
    config = build_training_stage_0_config(seed=seed)
    base_env = TowerDefenseEnv(config)
    env = FastCompatibilityEnv(
        base_env,
        seed=seed,
        step_dt=1.0,
        state_mode="compact",
        use_state_hash=True,
    )
    state = env.reset(seed=seed)

    done = False
    total_reward = 0.0
    steps = 0
    invalid_count = 0
    info: dict[str, object] = {}

    while not done:
        valid_actions = env.valid_actions()
        action = pick_action(state, valid_actions, q_table, rng, epsilon)
        next_state, reward, done, info = env.step(action)

        total_reward += float(reward)
        steps += 1
        if info.get("invalid_action"):
            invalid_count += 1

        next_valid_actions = env.valid_actions() if not done else [MACRO_ACTION_WAIT]
        next_max = max((q_table[next_state].get(next_action, 0.0) for next_action in next_valid_actions), default=0.0)
        old_value = float(q_table[state].get(action, 0.0))
        target = float(reward) + (0.0 if done else GAMMA * next_max)
        q_table[state][action] = old_value + ALPHA * (target - old_value)
        state = next_state

    termination_reason = str(info.get("termination_reason") or "unknown")
    truncated = bool(info.get("episode_truncated", False))
    win = bool(info.get("victory", False)) and termination_reason == "win"
    lose = (not win) and (not truncated)
    return {
        "seed": seed,
        "reward": round(total_reward, 2),
        "steps": steps,
        "win": win,
        "lose": lose,
        "truncated": truncated,
        "termination_reason": termination_reason,
        "invalid_count": invalid_count,
    }


def main() -> None:
    rng = random.Random(BASE_SEED)
    q_table: QTable = defaultdict(dict)
    results: list[dict[str, object]] = []

    for episode_idx in range(EPISODES):
        seed = BENCHMARK_SEEDS[episode_idx % len(BENCHMARK_SEEDS)] + BASE_SEED + episode_idx
        result = run_episode(seed=seed, q_table=q_table, rng=rng, epsilon=EPSILON)
        results.append(result)

        outcome = "truncated" if result["truncated"] else ("win" if result["win"] else "lose")
        print(
            f"episode={episode_idx:02d} "
            f"seed={result['seed']} "
            f"reward={result['reward']:.2f} "
            f"steps={result['steps']} "
            f"outcome={outcome} "
            f"termination_reason={result['termination_reason']} "
            f"invalid_action_count={result['invalid_count']}"
        )

    rewards = [float(item["reward"]) for item in results]
    steps = [int(item["steps"]) for item in results]
    win_rate = sum(1 for item in results if item["win"]) / max(1, len(results))

    print()
    print(f"episodes={len(results)}")
    print(f"average_reward={mean(rewards):.2f}")
    print(f"average_steps={mean(steps):.2f}")
    print(f"win_rate={win_rate:.2%}")


if __name__ == "__main__":
    main()
