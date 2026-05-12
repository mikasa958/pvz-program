from __future__ import annotations

import copy
from typing import Any

from env import ACTION_WAIT, TowerDefenseEnv


class FastCompatibilityEnv:
    """
    Lightweight adapter that exposes TowerDefenseEnv with a training-friendly step speed.
    """

    def __init__(
        self,
        base_env: TowerDefenseEnv | None = None,
        seed: int | None = None,
        step_dt: float = 1.0,
    ) -> None:
        self.base_env = base_env or TowerDefenseEnv()
        self.seed = self.base_env.config.random_seed if seed is None else seed
        self.step_dt = float(step_dt)

    @property
    def done(self) -> bool:
        return self.base_env.done

    def reset(self, seed: int | None = None) -> tuple[int, ...]:
        if seed is None:
            seed = self.seed
        return self.base_env.reset(seed=seed)

    def valid_actions(self) -> list[int]:
        return self.base_env.valid_actions()

    def step(self, action_id: int | None = 0) -> tuple[tuple[int, ...], float, bool, dict[str, Any]]:
        action_success = self.base_env.apply_action(action_id)
        reward = self.base_env.advance_world(dt=self.step_dt)

        try:
            safe_action_id = ACTION_WAIT if action_id is None else int(action_id)
        except Exception:
            safe_action_id = ACTION_WAIT

        action_reason = self.base_env.last_action_info.get("reason", "UNKNOWN")
        info = {
            "action_id": safe_action_id,
            "action_success": action_success,
            "action_reason": action_reason,
            "invalid_action": not action_success and action_reason not in {"WAIT", "GAME_OVER"},
            "kills": self.base_env.last_step_kills,
            "breaches": self.base_env.last_step_breaches,
            "resources": self.base_env.resources,
            "base_hp": self.base_env.base_hp,
            "score": self.base_env.score,
            "game_time": round(self.base_env.game_time, 2),
            "victory": self.base_env.victory,
            "done": self.base_env.done,
            "reward_breakdown": copy.deepcopy(self.base_env.last_reward_breakdown),
            "state_dict": self.base_env.get_render_state(),
            "step_dt": self.step_dt,
        }
        return self.base_env.get_state(), reward, self.base_env.done, info

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base_env, name)

