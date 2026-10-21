from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from config import CONFIG, GameConfig
from env import (
    STATE_ENEMY_MASK_START,
    STATE_OBSTACLE_MASK_START,
    STATE_RESOURCE_BUCKET_INDEX,
    STATE_TOWER_MASK_START,
    STATE_WAVE_STATE_ID_INDEX,
    action_dict_to_id,
)


class BaseAgent:
    def choose_action(self, state: tuple[int, ...]) -> int:
        raise NotImplementedError


class RuleBasedAgent(BaseAgent):
    """
    A stable gameplay baseline for demos and fallback automation.

    The richer policy reads `state_dict` when available so it can react to
    upgrades, card cooldowns, map effects, and enemy variants. The legacy
    tuple-only path stays intact for compatibility with older integrations.
    """

    UPGRADE_PRIORITIES: dict[str, int] = {
        "damage_up": 100,
        "sun_up": 90,
        "cost_down": 88,
        "cooldown_down": 86,
        "attack_speed_up": 82,
        "kill_sun_bonus": 76,
        "wallnut_hp_up": 70,
        "hp_up": 68,
    }
    PEA_COLUMN_ORDER = (2, 3, 1, 4, 0, 5, 6, 7, 8)
    SUNFLOWER_COLUMN_ORDER = (0, 1, 2, 3, 4, 5, 6, 7, 8)
    WALLNUT_COLUMN_ORDER = (6, 5, 7, 4, 8, 3, 2, 1, 0)

    def __init__(self, config: GameConfig | None = None) -> None:
        self.config = config or CONFIG
        self.required_resource_bucket = max(
            1,
            math.ceil(self.config.tower_cost / self.config.state_resource_bucket_size),
        )

    def choose_action(self, state: tuple[int, ...]) -> int:
        if len(state) > STATE_WAVE_STATE_ID_INDEX and int(state[STATE_WAVE_STATE_ID_INDEX]) == 2:
            return action_dict_to_id({"action_type": "choose_upgrade", "option_index": 0})

        min_state_len = STATE_ENEMY_MASK_START + self.config.grid_rows
        if len(state) < min_state_len:
            return 0

        resource_bucket = int(state[STATE_RESOURCE_BUCKET_INDEX])
        if resource_bucket < self.required_resource_bucket:
            return 0

        tower_masks = state[STATE_TOWER_MASK_START : STATE_TOWER_MASK_START + self.config.grid_rows]
        enemy_masks = state[STATE_ENEMY_MASK_START : STATE_ENEMY_MASK_START + self.config.grid_rows]
        if len(state) >= STATE_OBSTACLE_MASK_START + self.config.grid_rows:
            obstacle_masks = state[STATE_OBSTACLE_MASK_START : STATE_OBSTACLE_MASK_START + self.config.grid_rows]
        else:
            obstacle_masks = [0] * self.config.grid_rows
        enemy_pressure = [int(mask).bit_count() for mask in enemy_masks]

        max_pressure = max(enemy_pressure, default=0)
        if max_pressure <= 0:
            return 0

        target_row = max(range(self.config.grid_rows), key=lambda row: enemy_pressure[row])
        occupied_mask = int(tower_masks[target_row]) | int(obstacle_masks[target_row])

        for col in self.PEA_COLUMN_ORDER:
            if col >= self.config.grid_cols:
                continue
            if not ((occupied_mask >> col) & 1):
                return action_dict_to_id(
                    {
                        "action_type": "place_tower",
                        "plant_type": "pea_shooter",
                        "row": target_row,
                        "col": col,
                    }
                )

        return 0

    def choose_action_from_state_dict(self, state_dict: dict[str, Any], valid_actions: list[int]) -> int:
        valid_action_set = {int(action_id) for action_id in valid_actions}
        if not valid_action_set:
            return 0

        wave_state = str(state_dict.get("wave_state", "active"))
        pending_options = list(state_dict.get("pending_upgrade_options", []))
        if wave_state == "upgrade" or pending_options:
            return self._choose_upgrade_action(pending_options, valid_action_set)

        resources = int(state_dict.get("resources", state_dict.get("sun", 0)))
        plant_costs = state_dict.get("plant_costs", {})
        cheapest_cost = min((int(value) for value in plant_costs.values()), default=self.config.tower_cost)
        if resources < cheapest_cost:
            return 0

        available_cards = {
            plant_type: bool(state_dict.get("available_cards", {}).get(plant_type, False))
            for plant_type in ("pea_shooter", "sunflower", "wallnut")
        }
        if not any(available_cards.values()):
            return 0

        grid_rows = int(state_dict.get("map", {}).get("rows", self.config.grid_rows))
        grid_cols = int(state_dict.get("map", {}).get("cols", self.config.grid_cols))
        towers = list(state_dict.get("towers", []))
        enemies = list(state_dict.get("enemies", []))
        map_effect_lookup = self._map_effect_lookup(state_dict)
        row_stats = self._build_row_stats(enemies, grid_rows)
        plant_candidates = {
            plant_type: self._candidate_actions_for_plant(plant_type, valid_action_set, grid_rows, grid_cols)
            for plant_type in ("pea_shooter", "sunflower", "wallnut")
        }

        total_sunflowers = sum(1 for tower in towers if self._tower_plant_type(tower) == "sunflower")
        wave_id = max(1, int(state_dict.get("wave_id", 1)))
        if self._should_build_sunflower(
            available_cards=available_cards,
            row_stats=row_stats,
            towers=towers,
            wave_id=wave_id,
            total_sunflowers=total_sunflowers,
        ):
            action_id = self._choose_sunflower_action(
                plant_candidates["sunflower"],
                towers,
                row_stats,
                map_effect_lookup,
            )
            if action_id is not None:
                return action_id

        action_id = self._choose_wallnut_action(
            plant_candidates["wallnut"],
            towers,
            row_stats,
        )
        if action_id is not None:
            return action_id

        action_id = self._choose_pea_action(
            plant_candidates["pea_shooter"],
            row_stats,
            map_effect_lookup,
        )
        if action_id is not None:
            return action_id

        if available_cards["sunflower"]:
            action_id = self._choose_sunflower_action(
                plant_candidates["sunflower"],
                towers,
                row_stats,
                map_effect_lookup,
                force=True,
            )
            if action_id is not None:
                return action_id

        return 0

    def _choose_upgrade_action(self, pending_options: list[dict[str, Any]], valid_action_set: set[int]) -> int:
        ranked_options = sorted(
            enumerate(pending_options),
            key=lambda item: (
                -self.UPGRADE_PRIORITIES.get(str(item[1].get("id", "")), 0),
                int(item[1].get("index", item[0])),
            ),
        )
        for list_index, option in ranked_options:
            option_index = int(option.get("index", list_index))
            action_id = action_dict_to_id(
                {
                    "action_type": "choose_upgrade",
                    "option_index": option_index,
                }
            )
            if action_id in valid_action_set:
                return action_id
        return 0

    def _should_build_sunflower(
        self,
        *,
        available_cards: dict[str, bool],
        row_stats: list[dict[str, float]],
        towers: list[dict[str, Any]],
        wave_id: int,
        total_sunflowers: int,
    ) -> bool:
        if not available_cards.get("sunflower", False):
            return False

        desired_sunflowers = min(3, max(1, wave_id))
        if total_sunflowers >= desired_sunflowers:
            return False

        total_pea_shooters = sum(1 for tower in towers if self._tower_plant_type(tower) == "pea_shooter")
        total_enemies = int(sum(row["enemy_count"] for row in row_stats))
        max_pressure = max((float(row["pressure"]) for row in row_stats), default=0.0)

        if total_enemies == 0:
            return True
        if wave_id <= 2:
            return max_pressure <= 1.6 or total_pea_shooters >= 1
        if total_sunflowers == 0 and max_pressure <= 1.8:
            return True
        if total_sunflowers < 2 and total_enemies <= 2 and total_pea_shooters >= 1:
            return True
        return False

    def _choose_sunflower_action(
        self,
        candidates: list[tuple[int, int, int]],
        towers: list[dict[str, Any]],
        row_stats: list[dict[str, float]],
        map_effect_lookup: dict[tuple[int, int], str],
        *,
        force: bool = False,
    ) -> int | None:
        sunflower_rows = {int(tower.get("row", -1)) for tower in towers if self._tower_plant_type(tower) == "sunflower"}
        best_action: int | None = None
        best_score: float | None = None

        for row, col, action_id in candidates:
            if row in sunflower_rows:
                continue
            row_pressure = float(row_stats[row]["pressure"])
            if not force and row_pressure > 1.9 and row_stats[row]["enemy_count"] > 0:
                continue

            effect_id = map_effect_lookup.get((row, col), "")
            score = 0.0
            if effect_id == "fertile_land":
                score += 60.0
            score -= row_pressure * 28.0
            score -= float(row_stats[row]["enemy_count"]) * 8.0
            score -= float(row_stats[row]["tank_count"]) * 20.0
            score -= self._column_rank(col, self.SUNFLOWER_COLUMN_ORDER)

            if best_score is None or score > best_score:
                best_score = score
                best_action = action_id

        return best_action

    def _choose_wallnut_action(
        self,
        candidates: list[tuple[int, int, int]],
        towers: list[dict[str, Any]],
        row_stats: list[dict[str, float]],
    ) -> int | None:
        wallnut_rows = {int(tower.get("row", -1)) for tower in towers if self._tower_plant_type(tower) == "wallnut"}
        best_action: int | None = None
        best_score: float | None = None

        for row, col, action_id in candidates:
            tank_count = float(row_stats[row]["tank_count"])
            if tank_count <= 0:
                continue
            if row in wallnut_rows:
                continue

            score = 0.0
            score += tank_count * 100.0
            score += float(row_stats[row]["pressure"]) * 18.0
            score -= self._column_rank(col, self.WALLNUT_COLUMN_ORDER)

            if best_score is None or score > best_score:
                best_score = score
                best_action = action_id

        return best_action

    def _choose_pea_action(
        self,
        candidates: list[tuple[int, int, int]],
        row_stats: list[dict[str, float]],
        map_effect_lookup: dict[tuple[int, int], str],
    ) -> int | None:
        best_action: int | None = None
        best_score: float | None = None

        for row, col, action_id in candidates:
            enemy_count = float(row_stats[row]["enemy_count"])
            if enemy_count <= 0:
                continue

            effect_id = map_effect_lookup.get((row, col), "")
            score = 0.0
            score += enemy_count * 90.0
            score += float(row_stats[row]["pressure"]) * 20.0
            if effect_id == "attack_highland":
                score += 45.0
            score -= self._column_rank(col, self.PEA_COLUMN_ORDER)

            if best_score is None or score > best_score:
                best_score = score
                best_action = action_id

        return best_action

    def _candidate_actions_for_plant(
        self,
        plant_type: str,
        valid_action_set: set[int],
        grid_rows: int,
        grid_cols: int,
    ) -> list[tuple[int, int, int]]:
        candidates: list[tuple[int, int, int]] = []
        for row in range(grid_rows):
            for col in range(grid_cols):
                action_id = action_dict_to_id(
                    {
                        "action_type": "place_tower",
                        "plant_type": plant_type,
                        "row": row,
                        "col": col,
                    }
                )
                if action_id in valid_action_set:
                    candidates.append((row, col, action_id))
        return candidates

    def _build_row_stats(self, enemies: list[dict[str, Any]], grid_rows: int) -> list[dict[str, float]]:
        row_stats = [
            {
                "enemy_count": 0.0,
                "tank_count": 0.0,
                "pressure": 0.0,
            }
            for _ in range(grid_rows)
        ]
        grid_width = max(1, self.config.grid_cols * self.config.cell_size)

        for enemy in enemies:
            row = int(enemy.get("row", -1))
            if not (0 <= row < grid_rows):
                continue

            enemy_type = str(enemy.get("canonical_type", enemy.get("type", enemy.get("enemy_type", "normal"))))
            if enemy_type == "fast":
                enemy_type = "pole_vaulting"
            elif enemy_type == "tank":
                enemy_type = "buckethead"
            enemy_x = float(enemy.get("x", self.config.grid_origin_x + grid_width))
            progress = 1.0 - ((enemy_x - self.config.grid_origin_x) / float(grid_width))
            progress = max(0.0, min(1.0, progress))

            pressure = 1.0 + progress
            if enemy_type == "pole_vaulting":
                pressure += 0.35
            elif enemy_type == "buckethead":
                pressure += 1.0

            row_stats[row]["enemy_count"] += 1.0
            row_stats[row]["pressure"] += pressure
            if enemy_type == "buckethead":
                row_stats[row]["tank_count"] += 1.0

        return row_stats

    def _map_effect_lookup(self, state_dict: dict[str, Any]) -> dict[tuple[int, int], str]:
        lookup: dict[tuple[int, int], str] = {}
        for item in state_dict.get("map_effects", []):
            row = int(item.get("row", -1))
            col = int(item.get("col", -1))
            effect_id = str(item.get("effect", {}).get("id", ""))
            if row >= 0 and col >= 0 and effect_id:
                lookup[(row, col)] = effect_id
        return lookup

    @staticmethod
    def _tower_plant_type(tower_payload: dict[str, Any]) -> str:
        plant_type = tower_payload.get("plant_type", tower_payload.get("type", "pea_shooter"))
        if plant_type == "basic":
            return "pea_shooter"
        return str(plant_type)

    @staticmethod
    def _column_rank(col: int, preferred_order: tuple[int, ...]) -> int:
        if col in preferred_order:
            return preferred_order.index(col)
        return len(preferred_order) + int(col)


class ModelAgent(BaseAgent):
    """
    Placeholder model policy.
    It can wrap a dict lookup or a callable policy function later.
    """

    def __init__(
        self,
        policy: dict[tuple[int, ...], int] | Callable[[tuple[int, ...]], int] | None = None,
        default_action: int = 0,
    ) -> None:
        self.policy = policy
        self.default_action = default_action

    def choose_action(self, state: tuple[int, ...]) -> int:
        if callable(self.policy):
            return int(self.policy(state))
        if isinstance(self.policy, dict):
            return int(self.policy.get(tuple(state), self.default_action))
        return self.default_action
