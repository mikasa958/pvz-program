from __future__ import annotations

import math
import pickle
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

from config import CONFIG, GameConfig
from env import (
    ACTION_SPACE_SIZE,
    STATE_ENEMY_MASK_START,
    STATE_RESOURCE_BUCKET_INDEX,
    STATE_TOWER_MASK_START,
    STATE_VECTOR_SIZE,
)


def _popcount(x: int) -> int:
    """Count set bits (Python 3.10+ has int.bit_count; 3.8 needs bin().count)."""
    i = int(x)
    bc = getattr(i, "bit_count", None)
    if callable(bc):
        return int(bc())
    return bin(i).count("1")


class BaseAgent:
    def choose_action(self, state: tuple[int, ...], valid_actions: list[int] | None = None) -> int:
        raise NotImplementedError


class RuleBasedAgent(BaseAgent):
    """
    Interpretable baseline policy for the concrete tower-defense environment.

    Policy:
    1. Find the row with the highest enemy pressure.
    2. If resources are enough and that row still has an empty cell,
       place the tower at the leftmost empty cell in that row.
    3. Otherwise wait.
    """

    def __init__(self, config: GameConfig | None = None) -> None:
        self.config = config or CONFIG
        self.required_resource_bucket = max(
            1,
            math.ceil(self.config.tower_cost / self.config.state_resource_bucket_size),
        )

    def choose_action(self, state: tuple[int, ...], valid_actions: list[int] | None = None) -> int:
        if len(state) != STATE_VECTOR_SIZE:
            return 0

        legal = set(valid_actions) if valid_actions is not None else None
        resource_bucket = int(state[STATE_RESOURCE_BUCKET_INDEX])
        if resource_bucket < self.required_resource_bucket:
            return 0

        tower_masks = state[STATE_TOWER_MASK_START : STATE_TOWER_MASK_START + self.config.grid_rows]
        enemy_masks = state[STATE_ENEMY_MASK_START : STATE_ENEMY_MASK_START + self.config.grid_rows]
        enemy_pressure = [_popcount(mask) for mask in enemy_masks]

        max_pressure = max(enemy_pressure, default=0)
        if max_pressure <= 0:
            return 0

        target_row = max(range(self.config.grid_rows), key=lambda row: enemy_pressure[row])
        occupied_mask = int(tower_masks[target_row]) | int(enemy_masks[target_row])

        for col in range(self.config.grid_cols):
            action_id = 1 + target_row * self.config.grid_cols + col
            if ((occupied_mask >> col) & 1) == 0 and (legal is None or action_id in legal):
                return action_id

        return 0


class ModelAgent(BaseAgent):
    """
    Greedy inference wrapper for the Q-table trained by auto_PVZ_v1/pvzlib.

    Accepted model file formats:
    - {"q_table": {(state_tuple, action_id): q_value}, "q_init": 0.0}
    - raw q_table dict: {(state_tuple, action_id): q_value}
    """

    def __init__(
        self,
        policy: dict[tuple[int, ...], int] | Callable[..., int] | None = None,
        default_action: int = 0,
        q_table: dict[tuple[tuple[int, ...], int], float] | None = None,
        q_init: float = 0.0,
        seed: int = 42,
    ) -> None:
        self.policy = policy
        self.default_action = int(default_action)
        self.q_table = q_table or {}
        self.q_init = float(q_init)
        self.random = random.Random(seed)

    @classmethod
    def from_pickle(cls, path: str | Path, default_action: int = 0) -> "ModelAgent":
        model_path = Path(path)
        if not model_path.exists():
            return cls(default_action=default_action)
        with model_path.open("rb") as f:
            payload = pickle.load(f)
        if isinstance(payload, dict) and "q_table" in payload:
            return cls(
                default_action=default_action,
                q_table=payload.get("q_table") or {},
                q_init=float(payload.get("q_init", 0.0)),
                seed=int(payload.get("seed", 42)),
            )
        if isinstance(payload, dict):
            return cls(default_action=default_action, q_table=payload)
        raise ValueError(f"Unsupported model payload in {model_path}")

    def _choose_from_q_table(self, state: tuple[int, ...], valid_actions: list[int] | None) -> int:
        if valid_actions is None:
            valid_actions = list(range(ACTION_SPACE_SIZE))
        if not valid_actions:
            return self.default_action
        s = tuple(state)
        scored = [(int(a), float(self.q_table.get((s, int(a)), self.q_init))) for a in valid_actions]
        max_q = max(q for _, q in scored)
        best = [a for a, q in scored if q == max_q]
        return self.random.choice(best)

    def choose_action(self, state: tuple[int, ...], valid_actions: list[int] | None = None) -> int:
        if callable(self.policy):
            try:
                return int(self.policy(state, valid_actions))
            except TypeError:
                return int(self.policy(state))
        if isinstance(self.policy, dict):
            return int(self.policy.get(tuple(state), self.default_action))
        if self.q_table:
            return self._choose_from_q_table(tuple(state), valid_actions)
        return self.default_action
