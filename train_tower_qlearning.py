from __future__ import annotations

import argparse
import os
import pickle
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOWER_DIR = PROJECT_ROOT / "tower_defense_ai"
PVZ_COURSE_DIR = PROJECT_ROOT / "auto_PVZ_v1" / "pvz_ai_course"
MODEL_DIR = TOWER_DIR / "models"
MODEL_PATH = MODEL_DIR / "tower_q_table.pkl"

# 训练不需要打开窗口；有 pygame 时也走 dummy，方便服务器/命令行运行。
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

for p in (str(TOWER_DIR), str(PVZ_COURSE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from env import TowerDefenseEnv  # noqa: E402
from training_adapter import FastCompatibilityEnv  # noqa: E402
from pvzlib.agents import QLearningAgent, QLearningConfig  # noqa: E402
from pvzlib.train import evaluate_q, tail_mean, train_q_learning  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train auto_PVZ Q-learning agent on tower_defense_ai environment.")
    parser.add_argument("--episodes", type=int, default=2000, help="training episodes")
    parser.add_argument("--eval-episodes", type=int, default=200, help="greedy evaluation episodes")
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    parser.add_argument("--step-dt", type=float, default=1.0, help="seconds advanced per env.step")
    parser.add_argument("--alpha", type=float, default=0.12, help="Q-learning learning rate")
    parser.add_argument("--gamma", type=float, default=0.96, help="discount factor")
    parser.add_argument("--epsilon-decay", type=float, default=0.999, help="epsilon decay per episode")
    parser.add_argument("--q-init", type=float, default=0.0, help="default Q value for unseen (state, action)")
    parser.add_argument("--model-path", type=Path, default=MODEL_PATH, help="output pickle path")
    return parser.parse_args()


def build_env(seed: int, step_dt: float) -> FastCompatibilityEnv:
    return FastCompatibilityEnv(TowerDefenseEnv(), seed=seed, step_dt=step_dt)


def main() -> None:
    args = parse_args()
    env = build_env(seed=args.seed, step_dt=args.step_dt)
    q_cfg = QLearningConfig(
        alpha=args.alpha,
        gamma=args.gamma,
        epsilon=1.0,
        epsilon_min=0.05,
        epsilon_decay=args.epsilon_decay,
        seed=args.seed,
        q_init=args.q_init,
    )
    agent = QLearningAgent(q_cfg)

    print("=== Tower Q-learning Training ===")
    print(f"env_state_len={len(env.reset(seed=args.seed))}, action_space={env.action_space_size}, step_dt={args.step_dt}")
    print(f"episodes={args.episodes}, eval_episodes={args.eval_episodes}, seed={args.seed}")

    curve = train_q_learning(env, agent, episodes=args.episodes)
    eval_result = evaluate_q(env, agent, episodes=args.eval_episodes)
    if isinstance(eval_result, tuple):
        eval_mean, eval_std = eval_result
    else:
        eval_mean, eval_std = float(eval_result), 0.0

    args.model_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "q_table": agent.q_table,
        "q_init": agent.cfg.q_init,
        "seed": args.seed,
        "episodes": args.episodes,
        "eval_mean": eval_mean,
        "eval_std": eval_std,
        "tail_mean_200": tail_mean(curve, n=200),
        "state_len": len(env.reset(seed=args.seed)),
        "action_space_size": env.action_space_size,
        "note": "Trained with auto_PVZ_v1/pvzlib QLearningAgent on tower_defense_ai.FastCompatibilityEnv",
    }
    with args.model_path.open("wb") as f:
        pickle.dump(payload, f)

    print("\n=== Result ===")
    print(f"tail_mean_200={payload['tail_mean_200']:.3f}")
    print(f"eval_mean={eval_mean:.3f}, eval_std={eval_std:.3f}")
    print(f"q_table_size={len(agent.q_table)}")
    print(f"saved_model={args.model_path}")
    print("\nNext: run `python tower_defense_ai/main.py`, press 3 to switch to MODEL AI.")


if __name__ == "__main__":
    main()
