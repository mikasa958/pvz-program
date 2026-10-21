from __future__ import annotations

import copy
from typing import Any

from config import GameConfig
from env import ACTION_WAIT, TRAINING_STATE_VECTOR_SIZE, TRAINING_STATE_VERSION, TowerDefenseEnv
from rl_training import (
    TRAINING_COMPACT_STATE_SIZE,
    TRAINING_COMPACT_STATE_VERSION,
    MACRO_ACTION_SIZE,
    compact_state_hash_key,
    describe_macro_action,
    encode_training_state_compact,
    is_macro_training_config,
    macro_to_legacy_action_id,
    macro_valid_actions,
)


def _safe_action_id(action_id: int | None) -> int:
    try:
        return ACTION_WAIT if action_id is None else int(action_id)
    except Exception:
        return ACTION_WAIT


class FastCompatibilityEnv:
    """
    Lightweight adapter that exposes TowerDefenseEnv with a training-friendly step speed.

    Gameplay is unchanged unless the wrapped GameConfig enables training-only options
    (training_action_mode='macro', training reward preset, etc.).
    """

    def __init__(
        self,
        base_env: TowerDefenseEnv | None = None,
        seed: int | None = None,
        step_dt: float = 1.0,
        state_mode: str = "default",
        *,
        use_state_hash: bool = False,
    ) -> None:
        self.base_env = base_env or TowerDefenseEnv()
        self.seed = self.base_env.config.random_seed if seed is None else seed
        self.step_dt = max(0.0, float(step_dt))
        if state_mode not in {"default", "training", "compact"}:
            raise ValueError("state_mode must be 'default', 'training', or 'compact'")
        self.state_mode = state_mode
        self.use_state_hash = bool(use_state_hash)
        self._last_macro_action_id: int | None = None

    @property
    def config(self) -> GameConfig:
        return self.base_env.config

    @property
    def done(self) -> bool:
        return self.base_env.done

    def _uses_macro_actions(self) -> bool:
        return is_macro_training_config(self.base_env.config)

    def _select_state(self) -> tuple[int, ...]:
        if self.state_mode == "compact":
            state = encode_training_state_compact(self.base_env)
            if self.use_state_hash:
                return compact_state_hash_key(state)
            return state
        if self.state_mode == "training":
            return self.base_env.get_training_state()
        return self.base_env.get_state()

    def reset(self, seed: int | None = None) -> tuple[int, ...]:
        if seed is None:
            seed = self.seed
        self.base_env.reset(seed=seed)
        self._last_macro_action_id = None
        return self._select_state()

    def valid_actions(self) -> list[int]:
        if self._uses_macro_actions():
            return macro_valid_actions(self.base_env)
        return self.base_env.valid_actions()

    def _resolve_legacy_action(self, action_id: int | None) -> tuple[int | None, int | None]:
        macro_id = _safe_action_id(action_id)
        if not self._uses_macro_actions():
            return macro_id, None
        legacy_id = macro_to_legacy_action_id(self.base_env, macro_id)
        return legacy_id, macro_id

    def step(self, action_id: int | None = 0) -> tuple[tuple[int, ...], float, bool, dict[str, Any]]:
        legacy_action_id, macro_action_id = self._resolve_legacy_action(action_id)
        self._last_macro_action_id = macro_action_id

        if self._uses_macro_actions() and macro_action_id is not None and legacy_action_id is None:
            was_done = self.base_env.done
            if not self.base_env.done:
                self.base_env._record_pending_reward("invalid_action", self.base_env.config.reward_invalid_action)
            self.base_env.last_action_info = {
                "action_id": int(macro_action_id),
                "action_dict": describe_macro_action(macro_action_id),
                "success": False,
                "reason": "INVALID_MACRO_ACTION",
                "message": "Macro action is not legal in the current state",
            }
            if not was_done:
                self.base_env.episode_steps += 1
            reward = self.base_env._advance_world(self.step_dt)
            info = self._build_step_info(macro_action_id, legacy_action_id, action_success=False)
            return self._select_state(), reward, self.base_env.done, info

        if self._uses_macro_actions() and legacy_action_id is None:
            legacy_action_id = ACTION_WAIT

        _state, reward, done, info = self.base_env.step(legacy_action_id, dt=self.step_dt)
        info = self._build_step_info(
            macro_action_id if macro_action_id is not None else _safe_action_id(action_id),
            legacy_action_id,
            action_success=bool(info.get("action_success", True)),
            base_info=info,
        )
        return self._select_state(), reward, done, info

    def _build_step_info(
        self,
        reported_action_id: int,
        legacy_action_id: int | None,
        *,
        action_success: bool,
        base_info: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if base_info is None:
            valid_actions = self.valid_actions()
            info: dict[str, Any] = {
                "action_success": action_success,
                "invalid_action": not action_success,
                "done": self.base_env.done,
                "victory": self.base_env.victory,
                "termination_reason": self.base_env.termination_reason,
                "episode_truncated": self.base_env.episode_truncated,
                "reward_breakdown": copy.deepcopy(self.base_env.last_reward_breakdown),
            }
        else:
            info = copy.deepcopy(base_info)
            valid_actions = self.valid_actions()

        info.update(
            {
                "action_id": int(reported_action_id),
                "legacy_action_id": legacy_action_id,
                "macro_action_id": reported_action_id if self._uses_macro_actions() else None,
                "macro_action": describe_macro_action(reported_action_id) if self._uses_macro_actions() else None,
                "state_mode": self.state_mode,
                "training_state_size": (
                    TRAINING_COMPACT_STATE_SIZE
                    if self.state_mode == "compact"
                    else TRAINING_STATE_VECTOR_SIZE
                ),
                "training_state_version": (
                    TRAINING_COMPACT_STATE_VERSION
                    if self.state_mode == "compact"
                    else TRAINING_STATE_VERSION
                ),
                "training_action_mode": str(self.base_env.config.training_action_mode),
                "valid_actions": valid_actions,
                "valid_actions_count": len(valid_actions),
                "macro_action_space_size": MACRO_ACTION_SIZE if self._uses_macro_actions() else None,
                "step_dt": self.step_dt,
                "use_state_hash": self.use_state_hash,
            }
        )
        return info

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base_env, name)
