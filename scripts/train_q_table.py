from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
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

from config import (
    build_training_stage_0_config,
    build_training_stage_1_config,
    build_training_stage_2_config,
)
from env import ACTION_WAIT, TowerDefenseEnv
from rl_training import MACRO_ACTION_WAIT
from training_adapter import FastCompatibilityEnv


STAGE_BUILDERS = {
    0: build_training_stage_0_config,
    1: build_training_stage_1_config,
    2: build_training_stage_2_config,
}

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
    *,
    seed: int,
    stage: int,
    q_table: QTable,
    rng: random.Random,
    epsilon: float,
    use_state_hash: bool,
    step_dt: float,
) -> dict[str, object]:
    builder = STAGE_BUILDERS[int(stage)]
    config = builder(seed=seed)
    env = FastCompatibilityEnv(
        TowerDefenseEnv(config),
        seed=seed,
        step_dt=float(step_dt),
        state_mode="compact",
        use_state_hash=use_state_hash,
    )
    state = env.reset(seed=seed)

    done = False
    total_reward = 0.0
    steps = 0
    invalid_count = 0
    visited_states: set[tuple[int, ...]] = set()
    info: dict[str, object] = {}

    while not done:
        visited_states.add(state)
        valid_actions = env.valid_actions()
        action = pick_action(state, valid_actions, q_table, rng, epsilon)
        next_state, reward, done, info = env.step(action)

        total_reward += float(reward)
        steps += 1
        if info.get("invalid_action"):
            invalid_count += 1

        next_valid = env.valid_actions() if not done else [MACRO_ACTION_WAIT]
        next_max = max((q_table[next_state].get(next_action, 0.0) for next_action in next_valid), default=0.0)
        old_value = float(q_table[state].get(action, 0.0))
        target = float(reward) + (0.0 if done else 0.95 * next_max)
        q_table[state][action] = old_value + 0.2 * (target - old_value)
        state = next_state

    termination_reason = str(info.get("termination_reason") or "unknown")
    truncated = bool(info.get("episode_truncated", False))
    win = bool(info.get("victory", False)) and termination_reason == "win"
    return {
        "seed": seed,
        "stage": stage,
        "reward": round(total_reward, 2),
        "steps": steps,
        "win": win,
        "truncated": truncated,
        "termination_reason": termination_reason,
        "invalid_count": invalid_count,
        "unique_states": len(visited_states),
    }


def save_q_table(path: Path, q_table: QTable) -> None:
    serializable = {
        ",".join(str(part) for part in state): {str(action): value for action, value in actions.items()}
        for state, actions in q_table.items()
    }
    path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a tabular Q agent with compact state + macro actions.")
    parser.add_argument("--episodes", type=int, default=int(os.getenv("TD_TRAIN_EPISODES", "100")))
    parser.add_argument("--stage", type=int, default=int(os.getenv("TD_TRAIN_STAGE", "0")))
    parser.add_argument("--base-seed", type=int, default=int(os.getenv("TD_TRAIN_BASE_SEED", "42")))
    parser.add_argument("--epsilon", type=float, default=float(os.getenv("TD_TRAIN_EPSILON", "0.2")))
    parser.add_argument("--step-dt", type=float, default=float(os.getenv("TD_TRAIN_STEP_DT", "1.0")))
    parser.add_argument("--state-hash", action="store_true", default=os.getenv("TD_TRAIN_STATE_HASH", "") == "1")
    parser.add_argument("--save", type=str, default=os.getenv("TD_TRAIN_SAVE", ""))
    args = parser.parse_args()

    if args.stage not in STAGE_BUILDERS:
        raise SystemExit(f"Unsupported stage {args.stage}; choose from {sorted(STAGE_BUILDERS)}")

    rng = random.Random(args.base_seed)
    q_table: QTable = defaultdict(dict)
    results: list[dict[str, object]] = []

    for episode_idx in range(int(args.episodes)):
        seed = args.base_seed + episode_idx
        result = run_episode(
            seed=seed,
            stage=int(args.stage),
            q_table=q_table,
            rng=rng,
            epsilon=float(args.epsilon),
            use_state_hash=bool(args.state_hash),
            step_dt=float(args.step_dt),
        )
        results.append(result)
        outcome = "truncated" if result["truncated"] else ("win" if result["win"] else "lose")
        print(
            f"episode={episode_idx:03d} seed={result['seed']} "
            f"reward={result['reward']:.2f} steps={result['steps']} outcome={outcome} "
            f"invalid={result['invalid_count']} unique_states={result['unique_states']}"
        )

    wins = sum(1 for item in results if item["win"])
    print()
    print(f"stage={args.stage} episodes={len(results)} win_rate={wins / max(1, len(results)):.2%}")
    print(f"average_reward={mean(float(item['reward']) for item in results):.2f}")
    print(f"average_steps={mean(int(item['steps']) for item in results):.2f}")
    print(f"q_table_states={len(q_table)}")

    if args.save:
        save_path = Path(args.save)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_q_table(save_path, q_table)
        print(f"saved_q_table={save_path}")


if __name__ == "__main__":
    main()
