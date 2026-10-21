"""
Q-learning helpers: compact state encoding and macro action space.

This module does not change campaign/manual gameplay. Use via FastCompatibilityEnv
with state_mode='compact' and a training GameConfig (training_action_mode='macro').
"""

from __future__ import annotations

from typing import Any

from config import GameConfig
from env import (
    ACTION_CHOOSE_UPGRADE_OFFSET,
    ACTION_WAIT,
    GRID_COLS,
    GRID_ROWS,
    SUPPORTED_PLANT_TYPES,
    TowerDefenseEnv,
    action_dict_to_id,
)

TRAINING_COMPACT_STATE_VERSION = 1
TRAINING_COMPACT_GLOBAL_SIZE = 6
TRAINING_COMPACT_LANE_SIZE = 4
TRAINING_COMPACT_LANE_COUNT = GRID_ROWS
TRAINING_COMPACT_CARD_SIZE = 6
TRAINING_COMPACT_STATE_SIZE = (
    TRAINING_COMPACT_GLOBAL_SIZE
    + TRAINING_COMPACT_LANE_SIZE * TRAINING_COMPACT_LANE_COUNT
    + TRAINING_COMPACT_CARD_SIZE
)

MACRO_ACTION_WAIT = 0
MACRO_PLACE_PEA_ROW_OFFSET = 1
MACRO_PLACE_SUN_ROW_OFFSET = MACRO_PLACE_PEA_ROW_OFFSET + GRID_ROWS
MACRO_PLACE_WALL_ROW_OFFSET = MACRO_PLACE_SUN_ROW_OFFSET + GRID_ROWS
MACRO_CHOOSE_UPGRADE_OFFSET = MACRO_PLACE_WALL_ROW_OFFSET + GRID_ROWS
MACRO_ACTION_SIZE = MACRO_CHOOSE_UPGRADE_OFFSET + 3

MACRO_PLANT_BY_OFFSET = (
    ("pea_shooter", MACRO_PLACE_PEA_ROW_OFFSET),
    ("sunflower", MACRO_PLACE_SUN_ROW_OFFSET),
    ("wallnut", MACRO_PLACE_WALL_ROW_OFFSET),
)

ENEMY_KIND_NONE = 0
ENEMY_KIND_NORMAL = 1
ENEMY_KIND_POLE = 2
ENEMY_KIND_BUCKET = 3

_WAVE_PHASE_TO_ID = {
    "waiting": 0,
    "active": 1,
    "upgrade": 2,
    "waiting_clear": 3,
    "finished": 4,
}


def is_macro_training_config(config: GameConfig) -> bool:
    return str(getattr(config, "training_action_mode", "full")) == "macro"


def _sun_bucket(resources: int, bucket_size: int = 25, cap: int = 15) -> int:
    return min(max(0, int(resources) // max(1, int(bucket_size))), int(cap))


def _wave_phase_id(wave_state: str) -> int:
    return int(_WAVE_PHASE_TO_ID.get(str(wave_state), 0))


def _enemy_kind_id(enemy_type: str) -> int:
    normalized = str(enemy_type or "normal")
    if normalized in {"pole_vaulting", "fast"}:
        return ENEMY_KIND_POLE
    if normalized in {"buckethead", "tank"}:
        return ENEMY_KIND_BUCKET
    return ENEMY_KIND_NORMAL


def _lane_enemy_features(env: TowerDefenseEnv, row: int) -> tuple[int, int]:
    """Return (min_col 0-9 or 9 if empty, enemy_kind_id)."""
    origin_x = env.config.grid_origin_x
    cell_size = env.config.cell_size
    best_col = 9
    best_kind = ENEMY_KIND_NONE

    for enemy in env.enemies:
        if int(enemy.row) != int(row) or float(enemy.hp) <= 0:
            continue
        col = int((enemy.centerx - origin_x) // cell_size)
        col = max(0, min(GRID_COLS - 1, col))
        if col < best_col:
            best_col = col
            best_kind = _enemy_kind_id(str(enemy.enemy_type))

    return best_col, best_kind


def lane_enemy_min_col(env: TowerDefenseEnv, row: int) -> int | None:
    col, kind = _lane_enemy_features(env, row)
    if kind == ENEMY_KIND_NONE:
        return None
    return col


def encode_training_state_compact(env: TowerDefenseEnv) -> tuple[int, ...]:
    config = env.config
    damage_mult = float(env.game_modifiers.get("plant_damage_multiplier", env.game_modifiers["tower_damage_multiplier"]))
    upgrade_power = min(9, int(round(damage_mult * 5)) - 5)

    if env.current_wave_spawn_interval > 0 and env.pending_wave_spawns:
        spawn_progress = env.spawn_timer / env.current_wave_spawn_interval
    else:
        spawn_progress = 0.0
    spawn_bucket = min(int(spawn_progress * 10), int(config.state_spawn_bucket_max))

    globals_part = (
        _sun_bucket(env.resources, config.state_resource_bucket_size, 15),
        min(int(env.base_hp), 15),
        min(max(0, int(env.wave_id)), 15),
        _wave_phase_id(env.wave_state),
        spawn_bucket,
        upgrade_power,
    )

    lane_part: list[int] = []
    for row in range(GRID_ROWS):
        enemy_col, enemy_kind = _lane_enemy_features(env, row)
        has_pea = 0
        has_wall = 0
        for tower in env.towers:
            if int(tower.row) != row or float(tower.hp) <= 0:
                continue
            if tower.plant_type == "pea_shooter":
                has_pea = 1
            elif tower.plant_type == "wallnut":
                has_wall = 1
        lane_part.extend((enemy_col, enemy_kind, has_pea, has_wall))

    available = env._available_card_state()
    card_part: list[int] = []
    for plant_type in SUPPORTED_PLANT_TYPES:
        card_part.append(1 if available[plant_type] else 0)
        card_part.append(env._card_cooldown_bucket(plant_type))

    state = tuple(int(value) for value in (*globals_part, *lane_part, *card_part))
    if len(state) != TRAINING_COMPACT_STATE_SIZE:
        raise RuntimeError(f"compact state size mismatch: expected {TRAINING_COMPACT_STATE_SIZE}, got {len(state)}")
    return state


def compact_state_hash_key(state: tuple[int, ...]) -> tuple[int, ...]:
    """Drop card cooldown buckets to reduce Q-table fragmentation."""
    if len(state) != TRAINING_COMPACT_STATE_SIZE:
        return state
    global_end = TRAINING_COMPACT_GLOBAL_SIZE
    lane_end = global_end + TRAINING_COMPACT_LANE_SIZE * TRAINING_COMPACT_LANE_COUNT
    lane = state[global_end:lane_end]
    cards = state[lane_end:]
    return (
        *state[:global_end],
        *lane,
        cards[0],
        cards[2],
        cards[4],
    )


def _leftmost_placeable_col(env: TowerDefenseEnv, plant_type: str, row: int) -> int | None:
    for col in range(GRID_COLS):
        failure_reason, _ = env._validate_placement(plant_type, row, col)
        if failure_reason is None:
            return col
    return None


def macro_place_action_id(env: TowerDefenseEnv, plant_type: str, row: int) -> int | None:
    col = _leftmost_placeable_col(env, plant_type, row)
    if col is None:
        return None
    return action_dict_to_id(
        {
            "action_type": "place_tower",
            "plant_type": plant_type,
            "row": int(row),
            "col": int(col),
        }
    )


def macro_to_legacy_action_id(env: TowerDefenseEnv, macro_id: int) -> int | None:
    macro_id = int(macro_id)
    if macro_id == MACRO_ACTION_WAIT:
        return ACTION_WAIT

    if MACRO_CHOOSE_UPGRADE_OFFSET <= macro_id < MACRO_ACTION_SIZE:
        option_index = macro_id - MACRO_CHOOSE_UPGRADE_OFFSET
        if not (0 <= option_index < 3):
            return None
        return ACTION_CHOOSE_UPGRADE_OFFSET + option_index

    for plant_type, offset in MACRO_PLANT_BY_OFFSET:
        if offset <= macro_id < offset + GRID_ROWS:
            row = macro_id - offset
            return macro_place_action_id(env, plant_type, row)
    return None


def macro_valid_actions(env: TowerDefenseEnv) -> list[int]:
    if env.done:
        return [MACRO_ACTION_WAIT]

    if env._placement_locked() and not env.done:
        valid = [MACRO_ACTION_WAIT]
        upgrade_count = min(3, len(env.pending_upgrade_options))
        valid.extend(MACRO_CHOOSE_UPGRADE_OFFSET + index for index in range(upgrade_count))
        return valid

    valid = [MACRO_ACTION_WAIT]
    for plant_type, offset in MACRO_PLANT_BY_OFFSET:
        if not env._can_afford_plant(plant_type):
            continue
        if not env._is_card_ready(plant_type):
            continue
        for row in range(GRID_ROWS):
            if _leftmost_placeable_col(env, plant_type, row) is not None:
                valid.append(offset + row)
    return valid


def describe_macro_action(macro_id: int) -> dict[str, Any]:
    macro_id = int(macro_id)
    if macro_id == MACRO_ACTION_WAIT:
        return {"macro_action_type": "wait"}
    if MACRO_CHOOSE_UPGRADE_OFFSET <= macro_id < MACRO_ACTION_SIZE:
        return {
            "macro_action_type": "choose_upgrade",
            "option_index": macro_id - MACRO_CHOOSE_UPGRADE_OFFSET,
        }
    for plant_type, offset in MACRO_PLANT_BY_OFFSET:
        if offset <= macro_id < offset + GRID_ROWS:
            return {
                "macro_action_type": "place_tower",
                "plant_type": plant_type,
                "row": macro_id - offset,
            }
    return {"macro_action_type": "invalid", "macro_id": macro_id}
