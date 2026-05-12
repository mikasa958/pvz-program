from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOWER_DIR = PROJECT_ROOT / "tower_defense_ai"
PVZ_COURSE_DIR = PROJECT_ROOT / "auto_PVZ_v1" / "pvz_ai_course"

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

for p in (str(TOWER_DIR), str(PVZ_COURSE_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from env import ACTION_SPACE_SIZE, STATE_VECTOR_SIZE, TowerDefenseEnv  # noqa: E402
from training_adapter import FastCompatibilityEnv  # noqa: E402
from pvzlib.agents import QLearningAgent, QLearningConfig  # noqa: E402
from pvzlib.train import evaluate_q, train_q_learning  # noqa: E402


def main() -> None:
    env = FastCompatibilityEnv(TowerDefenseEnv(), seed=7, step_dt=1.0)
    state = env.reset(seed=7)
    print(f"state={state}")
    print(f"state_len={len(state)} expected={STATE_VECTOR_SIZE}")
    print(f"action_space={ACTION_SPACE_SIZE}, valid_actions_at_reset={env.valid_actions()[:8]}...")
    assert isinstance(state, tuple)
    assert len(state) == STATE_VECTOR_SIZE
    assert 0 in env.valid_actions()

    agent = QLearningAgent(QLearningConfig(seed=7, epsilon_decay=0.99))
    curve = train_q_learning(env, agent, episodes=20)
    eval_result = evaluate_q(env, agent, episodes=5)
    if isinstance(eval_result, tuple):
        mean, std = eval_result
    else:
        mean, std = float(eval_result), 0.0
    print(f"train_episodes=20, last_reward={curve[-1]:.3f}, eval={mean:.3f}±{std:.3f}, q_size={len(agent.q_table)}")
    print("OK: auto_PVZ_v1 Q-learning can train tower_defense_ai environment.")


if __name__ == "__main__":
    main()
