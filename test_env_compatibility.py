from __future__ import annotations

import os
import random
import sys
from pathlib import Path
from statistics import mean


SEED = 7
TRAIN_EPISODES = 200
EVAL_EPISODES = 50
TAIL_WINDOW = 200
STEP_DT = 1.0


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_PVZLIB_COURSE_DIR = PROJECT_DIR.parent / "auto_PVZ_v1" / "pvz_ai_course"

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from env import TowerDefenseEnv  # noqa: E402
from training_adapter import FastCompatibilityEnv  # noqa: E402


def _normalize_pvzlib_course_dir(path_str: str | None) -> Path | None:
    if not path_str:
        return None

    candidate = Path(path_str).expanduser()
    if candidate.name == "pvzlib" and (candidate / "__init__.py").exists():
        return candidate.parent
    if (candidate / "pvzlib").exists():
        return candidate
    return None


def resolve_pvzlib_course_dir() -> Path | None:
    env_candidate = _normalize_pvzlib_course_dir(os.getenv("PVZLIB_COURSE_DIR"))
    if env_candidate is not None:
        return env_candidate

    default_candidate = _normalize_pvzlib_course_dir(str(DEFAULT_PVZLIB_COURSE_DIR))
    if default_candidate is not None:
        return default_candidate

    return None


def load_pvzlib():
    course_dir = resolve_pvzlib_course_dir()
    if course_dir is None:
        return None

    if str(course_dir) not in sys.path:
        sys.path.insert(0, str(course_dir))

    try:
        from pvzlib.agents import QLearningAgent, QLearningConfig
        from pvzlib.train import evaluate_q, tail_mean, train_q_learning
    except Exception:
        return None

    return {
        "QLearningAgent": QLearningAgent,
        "QLearningConfig": QLearningConfig,
        "evaluate_q": evaluate_q,
        "tail_mean": tail_mean,
        "train_q_learning": train_q_learning,
    }


def build_env() -> FastCompatibilityEnv:
    return FastCompatibilityEnv(TowerDefenseEnv(), seed=SEED, step_dt=STEP_DT)


def smoke_test(env: FastCompatibilityEnv) -> None:
    state = env.reset(seed=SEED)
    assert isinstance(state, tuple), "reset() must return a tuple state"
    assert len(state) > 0, "state tuple must not be empty"

    valid_actions = env.valid_actions()
    assert 0 in valid_actions, "wait action must always be valid"

    print(f"[smoke] state_type={type(state).__name__}, state_len={len(state)}")
    print(f"[smoke] valid_actions={len(valid_actions)}")

    _, _, _, invalid_info = env.step(999)
    assert invalid_info.get("action_success") is False, "invalid action should fail"
    print(
        "[smoke] invalid_action -> "
        f"reason={invalid_info.get('action_reason')}, success={invalid_info.get('action_success')}"
    )

    env.reset(seed=SEED)
    legal_action = next((action for action in env.valid_actions() if action != 0), 0)
    assert legal_action != 0, "there should be at least one legal non-wait action at reset"

    _, _, _, legal_info = env.step(legal_action)
    assert legal_info.get("action_success") is True, "legal tower placement should succeed"
    print(
        "[smoke] valid_action -> "
        f"action={legal_action}, reason={legal_info.get('action_reason')}, success={legal_info.get('action_success')}"
    )

    env.reset(seed=SEED)
    start_time = env.game_time
    _, _, _, wait_info = env.step(0)
    assert abs(env.game_time - (start_time + STEP_DT)) < 1e-9, "step_dt should advance game time by 1 second"
    assert wait_info.get("action_success") is True, "wait action should succeed"

    for _ in range(3):
        _, _, _, loop_info = env.step(0)
        assert loop_info.get("action_reason") in {"WAIT", "GAME_OVER"}, "wait loop should not fail unexpectedly"

    print(f"[smoke] step_dt={env.step_dt}, time_after_wait={env.game_time:.2f}")


def run_external_qlearning_test(env: FastCompatibilityEnv, pvzlib_symbols: dict[str, object]) -> None:
    QLearningAgent = pvzlib_symbols["QLearningAgent"]
    QLearningConfig = pvzlib_symbols["QLearningConfig"]
    evaluate_q = pvzlib_symbols["evaluate_q"]
    tail_mean = pvzlib_symbols["tail_mean"]
    train_q_learning = pvzlib_symbols["train_q_learning"]

    agent = QLearningAgent(QLearningConfig(seed=SEED))

    print(f"Training Q-learning for {TRAIN_EPISODES} episodes...")
    train_curve = train_q_learning(env, agent, episodes=TRAIN_EPISODES)
    train_tail_avg = tail_mean(train_curve, n=TAIL_WINDOW)

    print(f"Evaluating greedy policy for {EVAL_EPISODES} episodes...")
    greedy_eval_result = evaluate_q(env, agent, episodes=EVAL_EPISODES)
    if isinstance(greedy_eval_result, tuple):
        greedy_eval_avg, greedy_eval_std = greedy_eval_result
    else:
        greedy_eval_avg, greedy_eval_std = float(greedy_eval_result), 0.0

    print("\n=== Compatibility Report ===")
    print(f"Seed: {SEED}")
    print(f"Training episodes: {TRAIN_EPISODES}")
    print(f"Evaluation episodes: {EVAL_EPISODES}")
    print(f"Training tail average reward (last {min(TAIL_WINDOW, len(train_curve))} episodes): {train_tail_avg:.3f}")
    print(f"Greedy evaluation average reward: {greedy_eval_avg:.3f} ± {greedy_eval_std:.3f}")
    print(f"Final epsilon: {agent.epsilon:.4f}")
    print(f"Reward mean across all training episodes: {mean(train_curve):.3f}")


def main() -> None:
    random.seed(SEED)

    env = build_env()
    print("Running compatibility smoke test...")
    smoke_test(env)

    pvzlib_symbols = load_pvzlib()
    if pvzlib_symbols is None:
        print("pvzlib not found, skipped external Q-learning compatibility test.")
        return

    env.reset(seed=SEED)
    run_external_qlearning_test(env, pvzlib_symbols)


if __name__ == "__main__":
    main()

