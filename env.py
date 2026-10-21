from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass
from typing import Any

import pygame

from config import CONFIG, GameConfig, UPGRADE_POOL
from enemy import Enemy
from map_effects import MapEffectDefinition, MapEffectManager, serialize_map_effects
from tower import Tower
from upgrades import UpgradeDefinition, UpgradeManager, recommend_upgrade
from waves import WaveConfig, WaveManager, WaveSpawn

GRID_ROWS = 5
GRID_COLS = 9
ACTION_WAIT = 0
ACTION_PLACE_OFFSET = 1
SUPPORTED_PLANT_TYPES = ("pea_shooter", "sunflower", "wallnut")
PLANT_ACTION_INDEX = {plant_type: index for index, plant_type in enumerate(SUPPORTED_PLANT_TYPES)}
ACTION_SLOTS_PER_PLANT = GRID_ROWS * GRID_COLS
ACTION_CHOOSE_UPGRADE_OFFSET = ACTION_PLACE_OFFSET + len(SUPPORTED_PLANT_TYPES) * ACTION_SLOTS_PER_PLANT
UPGRADE_CHOICE_COUNT = 3
ACTION_SPACE_SIZE = ACTION_CHOOSE_UPGRADE_OFFSET + UPGRADE_CHOICE_COUNT
SIMPLIFIED_ENEMY_BITE_INTERVAL = 1.0
PLANT_LOST_REWARD = -2.0

STATE_RESOURCE_BUCKET_INDEX = 0
STATE_BASE_HP_INDEX = 1
STATE_TIME_BUCKET_INDEX = 2
STATE_SPAWN_BUCKET_INDEX = 3
STATE_TOWER_COUNT_INDEX = 4
STATE_ENEMY_COUNT_INDEX = 5
STATE_WAVE_ID_INDEX = 6
STATE_WAVE_STATE_ID_INDEX = 7
STATE_UPGRADE_COUNT_INDEX = 8
STATE_DAMAGE_MULTIPLIER_BUCKET_INDEX = 9
STATE_COST_MULTIPLIER_BUCKET_INDEX = 10
STATE_SUN_MULTIPLIER_BUCKET_INDEX = 11
STATE_WAVE_MODIFIER_ID_INDEX = 12
STATE_TOWER_MASK_START = 13
STATE_ENEMY_MASK_START = STATE_TOWER_MASK_START + GRID_ROWS
STATE_OBSTACLE_MASK_START = STATE_ENEMY_MASK_START + GRID_ROWS
STATE_ATTACK_HIGHLAND_MASK_START = STATE_OBSTACLE_MASK_START + GRID_ROWS
STATE_FERTILE_LAND_MASK_START = STATE_ATTACK_HIGHLAND_MASK_START + GRID_ROWS
STATE_VECTOR_SIZE = STATE_FERTILE_LAND_MASK_START + GRID_ROWS

TRAINING_STATE_VERSION = 1
TRAINING_UPGRADE_IDS = tuple(sorted(UPGRADE_POOL.keys()))
TRAINING_UPGRADE_ID_TO_INDEX = {upgrade_id: index + 1 for index, upgrade_id in enumerate(TRAINING_UPGRADE_IDS)}
TRAINING_STATE_SCALAR_COUNT = 13
TRAINING_PEA_MASK_START = TRAINING_STATE_SCALAR_COUNT
TRAINING_SUNFLOWER_MASK_START = TRAINING_PEA_MASK_START + GRID_ROWS
TRAINING_WALLNUT_MASK_START = TRAINING_SUNFLOWER_MASK_START + GRID_ROWS
TRAINING_ENEMY_MASK_START = TRAINING_WALLNUT_MASK_START + GRID_ROWS
TRAINING_OBSTACLE_MASK_START = TRAINING_ENEMY_MASK_START + GRID_ROWS
TRAINING_ATTACK_HIGHLAND_MASK_START = TRAINING_OBSTACLE_MASK_START + GRID_ROWS
TRAINING_FERTILE_LAND_MASK_START = TRAINING_ATTACK_HIGHLAND_MASK_START + GRID_ROWS
TRAINING_AVAILABLE_CARD_START = TRAINING_FERTILE_LAND_MASK_START + GRID_ROWS
TRAINING_CARD_COOLDOWN_START = TRAINING_AVAILABLE_CARD_START + len(SUPPORTED_PLANT_TYPES)
TRAINING_PENDING_UPGRADE_START = TRAINING_CARD_COOLDOWN_START + len(SUPPORTED_PLANT_TYPES)
TRAINING_STATE_VECTOR_SIZE = TRAINING_PENDING_UPGRADE_START + UPGRADE_CHOICE_COUNT

WAVE_STATE_TO_ID = {
    "waiting": 0,
    "active": 1,
    "upgrade": 2,
    "finished": 3,
}

WAVE_MODIFIER_TO_ID = {
    "none": 0,
    "steady": 0,
    "fast_attack": 1,
    "thick_armor": 2,
    "number_pressure": 3,
    "single_lane": 4,
}


class DiscreteActionSpace:
    def __init__(self, n: int, rng: random.Random) -> None:
        self.n = n
        self._rng = rng

    def sample(self) -> int:
        return self._rng.randrange(self.n)

    def contains(self, item: Any) -> bool:
        return isinstance(item, int) and 0 <= item < self.n


def _normalize_plant_type(value: Any) -> str:
    normalized = str(value or "basic")
    if normalized == "basic":
        return "pea_shooter"
    if normalized in PLANT_ACTION_INDEX:
        return normalized
    raise ValueError(f"unsupported tower_type/plant_type: {value}")


def _legacy_tower_type(plant_type: str) -> str:
    return "basic" if plant_type == "pea_shooter" else plant_type


def _plant_action_id(plant_type: str, row: int, col: int) -> int:
    normalized = _normalize_plant_type(plant_type)
    plant_index = PLANT_ACTION_INDEX[normalized]
    return ACTION_PLACE_OFFSET + plant_index * ACTION_SLOTS_PER_PLANT + row * GRID_COLS + col


def _upgrade_action_id(option_index: int) -> int:
    if not (0 <= int(option_index) < UPGRADE_CHOICE_COUNT):
        raise ValueError(f"out of range option_index: {option_index}")
    return ACTION_CHOOSE_UPGRADE_OFFSET + int(option_index)


def action_id_to_dict(action_id: int) -> dict[str, Any]:
    action_id = int(action_id)
    if action_id == ACTION_WAIT:
        return {"action_type": "wait"}
    if ACTION_PLACE_OFFSET <= action_id < ACTION_CHOOSE_UPGRADE_OFFSET:
        offset = action_id - ACTION_PLACE_OFFSET
        plant_index = offset // ACTION_SLOTS_PER_PLANT
        cell_offset = offset % ACTION_SLOTS_PER_PLANT
        plant_type = SUPPORTED_PLANT_TYPES[plant_index]
        row = cell_offset // GRID_COLS
        col = cell_offset % GRID_COLS
        return {
            "action_type": "place_tower",
            "tower_type": _legacy_tower_type(plant_type),
            "plant_type": plant_type,
            "row": row,
            "col": col,
        }
    if ACTION_CHOOSE_UPGRADE_OFFSET <= action_id < ACTION_SPACE_SIZE:
        return {
            "action_type": "choose_upgrade",
            "option_index": action_id - ACTION_CHOOSE_UPGRADE_OFFSET,
        }
    raise ValueError(f"invalid action_id: {action_id}")


def action_dict_to_id(action_dict: dict[str, Any]) -> int:
    action_type = str(action_dict.get("action_type", "wait"))
    if action_type == "wait":
        return ACTION_WAIT
    if action_type == "choose_upgrade":
        return _upgrade_action_id(int(action_dict["option_index"]))
    if action_type != "place_tower":
        raise ValueError(f"unsupported action_type: {action_type}")

    plant_type = _normalize_plant_type(action_dict.get("plant_type", action_dict.get("tower_type", "basic")))

    row = int(action_dict["row"])
    col = int(action_dict["col"])
    if not (0 <= row < GRID_ROWS and 0 <= col < GRID_COLS):
        raise ValueError(f"out of range row/col: ({row}, {col})")
    return _plant_action_id(plant_type, row, col)


def _count_bucket(value: int, cap: int = 9) -> int:
    return min(int(value), cap)


def _multiplier_bucket(value: float) -> int:
    return max(0, int(round(float(value) * 100)))


def _blank_reward_breakdown() -> dict[str, float]:
    return {
        "invalid_action": 0.0,
        "valid_placement": 0.0,
        "economy": 0.0,
        "plant_lost": 0.0,
        "survive": 0.0,
        "kills": 0.0,
        "breaches": 0.0,
        "terminal": 0.0,
        "wave_clear": 0.0,
    }


@dataclass
class Projectile:
    uid: str
    row: int
    x: float
    y: float
    speed: float
    damage: int
    source_tower_id: str
    target_enemy_id: str | None = None
    pea_type: str = "normal"

    def to_dict(self) -> dict[str, Any]:
        pea_type = str(self.pea_type or "normal")
        return {
            "uid": self.uid,
            "row": int(self.row),
            "x": round(float(self.x), 2),
            "y": round(float(self.y), 2),
            "speed": round(float(self.speed), 2),
            "damage": int(self.damage),
            "source_tower_id": self.source_tower_id,
            "target_enemy_id": self.target_enemy_id,
            "pea_type": pea_type,
            "is_ice": pea_type == "ice",
        }


@dataclass
class RollingWallnut:
    uid: str
    row: int
    x: float
    y: float
    width: int
    height: int
    speed: float
    damage: int
    rotation: float = 0.0
    hit_enemy_ids: set[str] | None = None

    def __post_init__(self) -> None:
        if self.hit_enemy_ids is None:
            self.hit_enemy_ids = set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "row": int(self.row),
            "x": round(float(self.x), 2),
            "y": round(float(self.y), 2),
            "width": int(self.width),
            "height": int(self.height),
            "speed": round(float(self.speed), 2),
            "damage": int(self.damage),
            "rotation": round(float(self.rotation), 3),
        }


@dataclass
class SunDrop:
    uid: str
    x: float
    y: float
    amount: int
    age: float
    state: str = "idle"
    source: str = "plant"

    def to_dict(self) -> dict[str, Any]:
        return {
            "uid": self.uid,
            "x": round(float(self.x), 2),
            "y": round(float(self.y), 2),
            "amount": int(self.amount),
            "age": round(float(self.age), 2),
            "state": self.state,
            "source": self.source,
        }


def _safe_payload_dict(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, dict) else {}


class TowerDefenseEnv:
    action_space_size: int = ACTION_SPACE_SIZE
    state_space_size: int = STATE_VECTOR_SIZE
    training_state_space_size: int = TRAINING_STATE_VECTOR_SIZE
    training_state_version: int = TRAINING_STATE_VERSION
    grid_shape: tuple[int, int] = (GRID_ROWS, GRID_COLS)

    def __init__(self, config: GameConfig | None = None) -> None:
        self.config = config or CONFIG
        self.random = random.Random()
        self.action_space = DiscreteActionSpace(self.action_space_size, self.random)
        self.observation_space = type("ObservationSpace", (), {"shape": (STATE_VECTOR_SIZE,)})()
        self.manual_upgrade_selection = False
        self.reset(seed=self.config.random_seed)

    def reset(self, seed: int = 42) -> tuple[int, ...]:
        self.random.seed(seed)

        # Keep the legacy variable name for compatibility; gameplay/UI treat this as sun.
        if self._is_campaign_plan():
            self.resources = int(self.config.campaign_initial_resources)
        else:
            self.resources = self.config.initial_resources
        self.base_hp = self.config.base_hp
        self.base_max_hp = self.config.base_hp
        self.score = 0
        self.kills = 0
        self.damage_taken = 0
        self.game_time = 0.0
        self.frame_count = 0
        self.spawn_timer = 0.0
        self.next_spawn_in = 0.0
        self.current_wave_spawn_interval = self.config.enemy_spawn_interval
        self.resource_accumulator = 0.0
        self.sky_sun_timer = self._roll_sky_sun_interval()
        self.pending_reward = 0.0
        self.last_reward = 0.0
        self.total_reward = 0.0
        self.episode_steps = 0
        self.episode_truncated = False
        self.termination_reason: str | None = None
        self.last_auto_selected_upgrade: str | None = None

        self.done = False
        self.victory = False

        self.towers: list[Tower] = []
        self.enemies: list[Enemy] = []
        self.projectiles: list[Projectile] = []
        self.rolling_wallnuts: list[RollingWallnut] = []
        self.sun_drops: list[SunDrop] = []

        self.tower_seq = 1
        self.enemy_seq = 1
        self.projectile_seq = 1
        self.rolling_wallnut_seq = 1
        self.sun_drop_seq = 1
        self.opening_bonus_sky_sun_remaining = int(self.config.opening_bonus_sky_sun_count)
        self.shovel_cooldown_left = 0.0

        self.upgrade_manager = UpgradeManager(self.config)
        self.upgrade_manager.reset(seed)
        self.game_modifiers = self.upgrade_manager.get_modifiers()
        self.wave_manager = WaveManager(self.config)
        self.wave_manager.reset(seed)
        self.wave_definitions: list[WaveConfig] = list(self.wave_manager.waves)
        self.wave_index = -1
        self.waves_cleared = 0
        self.current_wave: WaveConfig | None = None
        self.pending_wave_spawns: list[WaveSpawn] = []
        self.wave_id = 0
        self.total_waves = self.wave_manager.total_waves
        self.wave_state = "waiting"
        self.current_wave_modifier: dict[str, Any] = {}
        self.pending_upgrade_options: list[UpgradeDefinition] = []
        self.applied_upgrades: list[dict[str, Any]] = self.upgrade_manager.get_active_upgrades()
        self.upgrade_counts: dict[str, int] = {}
        self.last_selected_upgrade: dict[str, Any] = {}
        self.map_effect_manager = MapEffectManager(self.config)
        self.map_effects: dict[tuple[int, int], MapEffectDefinition] = self.map_effect_manager.reset(seed)
        self.card_cooldowns: dict[str, float] = {plant_type: 0.0 for plant_type in SUPPORTED_PLANT_TYPES}

        self.message = "Ready. Place towers to survive the wave sequence."
        self.message_kind = "info"
        self.message_timer = 3.0

        self.last_action_info: dict[str, Any] = {
            "action_id": ACTION_WAIT,
            "action_dict": {"action_type": "wait"},
            "success": True,
            "reason": "RESET",
            "message": "Environment reset",
        }
        self._last_step_kills = 0
        self._last_step_breaches = 0
        self._pending_reward_breakdown: dict[str, float] = _blank_reward_breakdown()
        self._last_reward_breakdown: dict[str, float] = _blank_reward_breakdown()
        self.wave_total_hp = 0.0
        self.wave_hp_threshold_ratio = 0.0
        self.wave_damage_threshold = 0.0
        self.wave_damage_dealt = 0.0
        self.wave_advance_armed = False
        self.wave_advance_countdown = 0.0
        self.wave_spawn_locked = False
        self.campaign_waiting_clear_field = False

        self._start_next_wave()
        return self.get_state()

    def get_state(self) -> tuple[int, ...]:
        return self._encode_state()

    def get_training_state(self) -> tuple[int, ...]:
        return self._encode_training_state()

    def get_render_state(self) -> dict[str, Any]:
        wave_modifier_payload = self._current_wave_modifier_payload()
        pending_upgrade_payload = self._pending_upgrade_payload()
        active_upgrades_payload = copy.deepcopy(self.applied_upgrades)
        map_effect_payload = self._serialized_map_effects()
        return {
            "time": round(self.game_time, 2),
            "tick": self.frame_count,
            "resources": self.resources,
            "sun": self.resources,
            "sky_sun_timer": round(max(0.0, self.sky_sun_timer), 2) if self.config.enable_sky_sun else 0.0,
            "sun_system": {
                "enabled": bool(self.config.enable_sky_sun),
                "sky_sun_amount": int(self.config.sky_sun_amount),
                "sky_sun_interval_min": float(self.config.sky_sun_interval_min),
                "sky_sun_interval_max": float(self.config.sky_sun_interval_max),
            },
            "base_hp": self.base_hp,
            "base_max_hp": self.base_max_hp,
            "score": self.score,
            "kills": self.kills,
            "damage_taken": self.damage_taken,
            "enemy_count": len(self.enemies),
            "tower_count": len(self.towers),
            "done": self.done,
            "victory": self.victory,
            "last_reward": round(self.last_reward, 2),
            "total_reward": round(self.total_reward, 2),
            "next_spawn_in": round(max(0.0, self.next_spawn_in), 2),
            "wave_id": self.wave_id,
            "total_waves": self.total_waves,
            "wave_state": self.wave_state,
            "wave_remaining": self._wave_remaining(),
            "current_wave_modifier": wave_modifier_payload,
            "wave_modifier": copy.deepcopy(wave_modifier_payload),
            "opening_grace_remaining": round(self.opening_grace_remaining(), 2),
            "tower_cost": self.current_tower_cost(),
            "available_plants": list(SUPPORTED_PLANT_TYPES),
            "plant_costs": self._plant_cost_state(),
            "available_cards": self._available_card_state(),
            "card_cooldowns": self._card_cooldown_state(),
            "pending_upgrade_options": pending_upgrade_payload,
            "active_upgrades": active_upgrades_payload,
            "map_effects": map_effect_payload,
            "projectiles": [projectile.to_dict() for projectile in self.projectiles],
            "rolling_wallnuts": [roll.to_dict() for roll in self.rolling_wallnuts],
            "sun_drops": [sun_drop.to_dict() for sun_drop in self.sun_drops],
            "lane_pressure": self.lane_pressure_snapshot(),
            "shovel_cooldown": round(max(0.0, self.shovel_cooldown_left), 2),
            "shovel_ready": self.shovel_cooldown_left <= 0.0,
            "map": {
                "rows": self.config.grid_rows,
                "cols": self.config.grid_cols,
                "cell_size": self.config.cell_size,
                "origin_x": self.config.grid_origin_x,
                "origin_y": self.config.grid_origin_y,
                "bonus_cells": copy.deepcopy(map_effect_payload),
                "effects": copy.deepcopy(map_effect_payload),
            },
            "wave": self._wave_render_state(),
            "modifiers": self._modifier_render_state(),
            "placement_locked": self._placement_locked(),
            "pending_upgrade_count": len(self.pending_upgrade_options),
            "auto_selected_upgrade": self.last_auto_selected_upgrade,
            "episode_steps": self.episode_steps,
            "max_episode_steps": self.config.max_episode_steps,
            "episode_truncated": self.episode_truncated,
            "termination_reason": self.termination_reason,
            "upgrades": {
                "pending": copy.deepcopy(pending_upgrade_payload),
                "applied": copy.deepcopy(active_upgrades_payload),
                "last_selected": copy.deepcopy(self.last_selected_upgrade),
                "manual_selection": self.manual_upgrade_selection,
            },
            "towers": [self._tower_render_payload(tower) for tower in self.towers],
            "enemies": [enemy.to_dict() for enemy in self.enemies],
            "message": self.message,
            "message_kind": self.message_kind,
            "last_action": copy.deepcopy(self.last_action_info),
        }

    def get_state_dict(self) -> dict[str, Any]:
        return self.get_render_state()

    def is_done(self) -> bool:
        return self.done

    @property
    def last_step_kills(self) -> int:
        return self._last_step_kills

    @property
    def last_step_breaches(self) -> int:
        return self._last_step_breaches

    @property
    def last_reward_breakdown(self) -> dict[str, float]:
        return self._last_reward_breakdown

    @property
    def has_pending_upgrade(self) -> bool:
        return bool(self.pending_upgrade_options)

    def _is_campaign_plan(self) -> bool:
        return str(self.config.wave_plan_id) in {"campaign_v4", "campaign_v5"}

    def opening_grace_remaining(self) -> float:
        if not self._is_campaign_plan():
            return 0.0
        return max(0.0, float(self.config.opening_grace_seconds) - float(self.game_time))

    def lane_pressure_snapshot(self) -> list[dict[str, Any]]:
        return self.wave_manager.lane_pressure_snapshot(self.enemies)

    def _record_pending_reward(self, key: str, amount: float) -> None:
        amount = float(amount)
        if amount == 0.0:
            return
        self.pending_reward += amount
        self._pending_reward_breakdown[key] = self._pending_reward_breakdown.get(key, 0.0) + amount

    def point_to_cell(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        x, y = pos
        rel_x = x - self.config.grid_origin_x
        rel_y = y - self.config.grid_origin_y
        if rel_x < 0 or rel_y < 0:
            return None
        col = rel_x // self.config.cell_size
        row = rel_y // self.config.cell_size
        if row >= self.config.grid_rows or col >= self.config.grid_cols:
            return None
        return int(row), int(col)

    def try_collect_sun_drop(self, pos: tuple[int, int]) -> bool:
        x, y = pos
        for index, sun_drop in enumerate(self.sun_drops):
            if sun_drop.state != "idle":
                continue
            rect = pygame.Rect(int(sun_drop.x) - 18, int(sun_drop.y) - 18, 36, 36)
            if not rect.collidepoint(x, y):
                continue
            self.resources += int(sun_drop.amount)
            self.sun_drops.pop(index)
            self.message = f"Collected {int(sun_drop.amount)} sun"
            self.message_kind = "success"
            self.message_timer = 1.0
            return True
        return False

    def can_use_shovel(self) -> bool:
        return not self.done and self.wave_state == "active"

    def tower_at_cell(self, row: int, col: int) -> Tower | None:
        for tower in self.towers:
            if tower.row == row and tower.col == col and tower.is_alive():
                return tower
        return None

    def _remove_tower(self, tower: Tower) -> None:
        self.towers = [item for item in self.towers if item.uid != tower.uid]
        self.projectiles = [projectile for projectile in self.projectiles if projectile.source_tower_id != tower.uid]

    def remove_tower_at(self, row: int, col: int) -> bool:
        if not self.can_use_shovel():
            return False
        if self.shovel_cooldown_left > 0.0:
            return False

        tower = self.tower_at_cell(row, col)
        if tower is None:
            return False

        plant_profile = self._plant_profile(tower.plant_type)
        plant_name = str(plant_profile.get("name", tower.plant_type))
        self._remove_tower(tower)
        self.shovel_cooldown_left = max(0.0, float(self.config.shovel_cooldown_seconds))
        self.message = f"Shoveled {plant_name} at ({row}, {col})"
        self.message_kind = "info"
        self.message_timer = 1.4
        return True

    def try_shovel_at(self, pos: tuple[int, int]) -> bool:
        cell = self.point_to_cell(pos)
        if cell is None:
            return False
        row, col = cell
        return self.remove_tower_at(row, col)

    def cell_rect(self, row: int, col: int) -> pygame.Rect:
        return pygame.Rect(
            self.config.grid_origin_x + col * self.config.cell_size,
            self.config.grid_origin_y + row * self.config.cell_size,
            self.config.cell_size,
            self.config.cell_size,
        )

    def cell_center(self, row: int, col: int) -> tuple[float, float]:
        rect = self.cell_rect(row, col)
        return rect.centerx, rect.centery

    def has_tower_at_cell(self, row: int, col: int) -> bool:
        return self.tower_at_cell(row, col) is not None

    def is_cell_occupied(self, row: int, col: int) -> bool:
        """Placement uses plant occupancy only; zombies may share a cell."""
        return self.has_tower_at_cell(row, col)

    def is_cell_obstacle(self, row: int, col: int) -> bool:
        effect = self.map_effects.get((row, col))
        return bool(effect is not None and getattr(effect, "is_obstacle", False))

    def _placement_locked(self) -> bool:
        return self.done or self.wave_state == "upgrade" or self.has_pending_upgrade

    def _lane_enemy_min_col(self, row: int) -> int | None:
        origin_x = self.config.grid_origin_x
        cell_size = self.config.cell_size
        best_col: int | None = None
        for enemy in self.enemies:
            if int(enemy.row) != int(row) or float(enemy.hp) <= 0:
                continue
            col = int((enemy.centerx - origin_x) // cell_size)
            col = max(0, min(self.config.grid_cols - 1, col))
            if best_col is None or col < best_col:
                best_col = col
        return best_col

    def _placement_reward_amount(self, plant_type: str, row: int) -> float:
        amount = float(self.config.reward_valid_placement)
        bonus = float(self.config.reward_valid_placement_front_bonus)
        if bonus <= 0.0:
            return amount
        lane_col = self._lane_enemy_min_col(row)
        if lane_col is not None and lane_col < int(self.config.reward_valid_placement_front_max_col):
            return amount + bonus
        return amount

    def _should_auto_select_upgrades(self) -> bool:
        return bool(self.config.auto_select_upgrades and not self.manual_upgrade_selection)

    def _can_afford_plant(self, plant_type: str) -> bool:
        return self.resources >= self.current_tower_cost(plant_type)

    def _is_card_ready(self, plant_type: str) -> bool:
        return self.card_cooldowns.get(plant_type, 0.0) <= 0.0

    def current_tower_cost(self, plant_type: str = "basic") -> int:
        profile = self._plant_profile(plant_type)
        cost_multiplier = float(self.game_modifiers.get("plant_cost_multiplier", self.game_modifiers["tower_cost_multiplier"]))
        scaled_cost = int(profile["cost"]) * cost_multiplier
        return max(1, int(round(scaled_cost)))

    def current_card_cooldown(self, plant_type: str = "basic") -> float:
        profile = self._plant_profile(plant_type)
        cooldown_multiplier = float(self.game_modifiers.get("card_cooldown_multiplier", 1.0))
        base_card_cooldown = float(profile.get("card_cooldown", profile.get("cooldown", 0.0)))
        return max(0.0, base_card_cooldown * cooldown_multiplier)

    def _plant_profile(self, plant_type: str) -> dict[str, Any]:
        normalized = _normalize_plant_type(plant_type)
        profile = self.config.plant_config.get(normalized)
        if profile is None:
            raise ValueError(f"missing plant config for {normalized}")
        resolved_profile = dict(profile)
        if normalized == "pea_shooter":
            resolved_profile.update(
                {
                    "cost": self.config.tower_cost,
                    "damage": self.config.tower_damage,
                    "range_cells": self.config.tower_range_cells,
                    "cooldown": self.config.tower_cooldown,
                    "attack_interval": self.config.tower_cooldown,
                    "card_cooldown": self.config.tower_card_cooldown,
                    "max_hp": self.config.tower_base_hp,
                }
            )
        return resolved_profile

    def _placeable_cells(self) -> list[tuple[int, int]]:
        cells: list[tuple[int, int]] = []
        for row in range(self.config.grid_rows):
            for col in range(self.config.grid_cols):
                if self.is_cell_obstacle(row, col):
                    continue
                if self.is_cell_occupied(row, col):
                    continue
                cells.append((row, col))
        return cells

    def _serialized_map_effects(self) -> list[dict[str, Any]]:
        return serialize_map_effects(self.map_effects)

    def _plant_cost_state(self) -> dict[str, int]:
        return {plant_type: self.current_tower_cost(plant_type) for plant_type in SUPPORTED_PLANT_TYPES}

    def _current_wave_modifier_payload(self) -> dict[str, Any]:
        return _safe_payload_dict(self.current_wave_modifier)

    def _available_card_state(self) -> dict[str, bool]:
        placeable = bool(self._placeable_cells())
        placement_locked = self._placement_locked()
        payload: dict[str, bool] = {}
        for plant_type in SUPPORTED_PLANT_TYPES:
            payload[plant_type] = (
                not placement_locked
                and placeable
                and self._can_afford_plant(plant_type)
                and self._is_card_ready(plant_type)
            )
        return payload

    def _card_cooldown_state(self) -> dict[str, float]:
        return {plant_type: round(max(0.0, self.card_cooldowns.get(plant_type, 0.0)), 2) for plant_type in SUPPORTED_PLANT_TYPES}

    def _tick_card_cooldowns(self, dt: float) -> None:
        self.shovel_cooldown_left = max(0.0, self.shovel_cooldown_left - float(dt))
        for plant_type in SUPPORTED_PLANT_TYPES:
            self.card_cooldowns[plant_type] = max(0.0, self.card_cooldowns.get(plant_type, 0.0) - dt)

    def _recalculate_card_cooldowns(self) -> None:
        for plant_type in SUPPORTED_PLANT_TYPES:
            self.card_cooldowns[plant_type] = min(
                self.card_cooldowns.get(plant_type, 0.0),
                self.current_card_cooldown(plant_type),
            )

    def valid_actions(self) -> list[int]:
        """
        Return all currently legal discrete actions.

        This keeps the environment compatible with the training loop used by
        the sibling pvzlib package while treating resources as the sun pool.
        """
        if self.done:
            return [ACTION_WAIT]

        if self._placement_locked() and not self.done:
            return [ACTION_WAIT, *self._upgrade_action_ids()]

        valid = [ACTION_WAIT]
        placeable_cells = self._placeable_cells()
        if not placeable_cells:
            return valid

        for plant_type in SUPPORTED_PLANT_TYPES:
            if not self._can_afford_plant(plant_type):
                continue
            if not self._is_card_ready(plant_type):
                continue
            for row, col in placeable_cells:
                valid.append(_plant_action_id(plant_type, row, col))
        return valid

    def _validate_placement(self, plant_type: str, row: int, col: int) -> tuple[str | None, str | None]:
        if not (0 <= row < self.config.grid_rows and 0 <= col < self.config.grid_cols):
            return "OUT_OF_RANGE", "Out of range"
        if not self._can_afford_plant(plant_type):
            return "RESOURCE_NOT_ENOUGH", "Not enough sun"
        if self.is_cell_obstacle(row, col):
            return "CELL_BLOCKED", "Cell blocked by obstacle"
        if self.has_tower_at_cell(row, col):
            return "CELL_OCCUPIED", "Cell already has a plant"
        if not self._is_card_ready(plant_type):
            return "CARD_COOLDOWN", "Card cooling down"
        return None, None

    def apply_action(self, action_id: int | None) -> bool:
        if action_id is None:
            action_id = ACTION_WAIT

        try:
            action_dict = action_id_to_dict(action_id)
        except Exception as exc:
            if not self.done:
                self._record_pending_reward("invalid_action", self.config.reward_invalid_action)
            self.last_action_info = {
                "action_id": int(action_id) if isinstance(action_id, int) else action_id,
                "action_dict": None,
                "success": False,
                "reason": "INVALID_ACTION_ID",
                "message": str(exc),
            }
            self.message = "Invalid action id"
            self.message_kind = "error"
            self.message_timer = 2.0
            return False

        if self.done:
            self.last_action_info = {
                "action_id": int(action_id),
                "action_dict": action_dict,
                "success": False,
                "reason": "GAME_OVER",
                "message": "Episode already finished",
            }
            return False

        if self.wave_state == "upgrade" or self.has_pending_upgrade:
            if action_dict["action_type"] == "wait":
                self.last_action_info = {
                    "action_id": int(action_id),
                    "action_dict": action_dict,
                    "success": True,
                    "reason": "AWAITING_UPGRADE",
                    "message": "Select an upgrade to continue.",
                }
                return True
            if action_dict["action_type"] == "choose_upgrade":
                option_index = int(action_dict.get("option_index", -1))
                if not (0 <= option_index < len(self.pending_upgrade_options)):
                    self._record_pending_reward("invalid_action", self.config.reward_invalid_action)
                    self._set_last_action_failure(action_id, action_dict, "INVALID_UPGRADE_OPTION", "Invalid upgrade option")
                    return False
                if not self.select_upgrade(option_index=option_index):
                    self._record_pending_reward("invalid_action", self.config.reward_invalid_action)
                    self._set_last_action_failure(action_id, action_dict, "UPGRADE_APPLY_FAILED", "Failed to apply upgrade")
                    return False
                self.last_action_info = {
                    "action_id": int(action_id),
                    "action_dict": action_dict,
                    "success": True,
                    "reason": "UPGRADE_CHOSEN",
                    "message": "Upgrade selected",
                    "selected_upgrade": copy.deepcopy(self.last_selected_upgrade),
                }
                return True
            self._record_pending_reward("invalid_action", self.config.reward_invalid_action)
            self.last_action_info = {
                "action_id": int(action_id),
                "action_dict": action_dict,
                "success": False,
                "reason": "UPGRADE_SELECTION_PENDING",
                "message": "Upgrade selection pending",
            }
            return False

        action_type = action_dict["action_type"]
        if action_type == "wait":
            self.last_action_info = {
                "action_id": int(action_id),
                "action_dict": action_dict,
                "success": True,
                "reason": "WAIT",
                "message": "wait",
            }
            return True
        if action_type == "choose_upgrade":
            self._record_pending_reward("invalid_action", self.config.reward_invalid_action)
            self._set_last_action_failure(action_id, action_dict, "NO_UPGRADE_PENDING", "No upgrade choice is currently available")
            return False

        row = int(action_dict["row"])
        col = int(action_dict["col"])
        plant_type = _normalize_plant_type(action_dict.get("plant_type", action_dict.get("tower_type", "basic")))
        cost = self.current_tower_cost(plant_type)
        failure_reason, failure_message = self._validate_placement(plant_type, row, col)
        if failure_reason is not None and failure_message is not None:
            self._record_pending_reward("invalid_action", self.config.reward_invalid_action)
            self._set_last_action_failure(action_id, action_dict, failure_reason, failure_message)
            return False

        plant_profile = self._plant_profile(plant_type)
        tower_type = _legacy_tower_type(plant_type)
        map_effect = self.map_effects.get((row, col))
        plant_role = str(plant_profile.get("role", "attack"))
        local_damage_multiplier = 1.0
        if map_effect is not None and plant_role == "attack":
            local_damage_multiplier = float(map_effect.damage_multiplier)
        tower = Tower(
            uid=f"tower_{self.tower_seq:03d}",
            row=row,
            col=col,
            base_damage=int(plant_profile["damage"]),
            range_cells=int(plant_profile["range_cells"]),
            base_cooldown=float(plant_profile.get("attack_interval", plant_profile.get("cooldown", 0.0))),
            base_hp=float(plant_profile["max_hp"]),
            width=self.config.tower_width,
            height=self.config.tower_height,
            tower_type=tower_type,
            plant_type=plant_type,
            card_cooldown=float(plant_profile.get("card_cooldown", 0.0)),
            local_damage_multiplier=local_damage_multiplier,
            local_hp_multiplier=1.0,
            local_resource_bonus_per_second=0.0,
            cell_effect_id=map_effect.id if map_effect else None,
            cell_effect_name=map_effect.name if map_effect else None,
        )
        self._sync_tower_stats(tower, preserve_ratio=False)

        self.tower_seq += 1
        self.towers.append(tower)
        self.resources -= cost
        self.card_cooldowns[plant_type] = self.current_card_cooldown(plant_type)
        self._record_pending_reward("valid_placement", self._placement_reward_amount(plant_type, row))
        plant_name = str(plant_profile.get("name", plant_type))
        self.last_action_info = {
            "action_id": int(action_id),
            "action_dict": action_dict,
            "success": True,
            "reason": "TOWER_PLACED",
            "message": f"{plant_name} placed",
            "plant_type": plant_type,
            "cost": cost,
            "resources_left": self.resources,
            "sun_left": self.resources,
            "tower_uid": tower.uid,
            "map_effect_id": tower.cell_effect_id,
        }
        if map_effect is not None:
            self.message = f"Placed {plant_name} at ({row}, {col}) on {map_effect.name}"
        else:
            self.message = f"Placed {plant_name} at ({row}, {col})"
        self.message_kind = "success"
        self.message_timer = 2.0
        return True

    def step(self, action_id: int | None = 0, *, dt: float | None = None) -> tuple[tuple[int, ...], float, bool, dict[str, Any]]:
        was_done = self.done
        action_success = self.apply_action(action_id)
        if not was_done:
            self.episode_steps += 1
        reward = self._advance_world(dt)
        try:
            safe_action_id = ACTION_WAIT if action_id is None else int(action_id)
        except Exception:
            safe_action_id = ACTION_WAIT
        valid_actions = self.valid_actions()
        info = {
            "action_id": safe_action_id,
            "action_success": action_success,
            "action_result": copy.deepcopy(self.last_action_info),
            "action_reason": self.last_action_info.get("reason"),
            "invalid_action": not action_success and self.last_action_info.get("reason") not in {"WAIT", "GAME_OVER"},
            "kills": self._last_step_kills,
            "breaches": self._last_step_breaches,
            "resources": self.resources,
            "base_hp": self.base_hp,
            "score": self.score,
            "game_time": round(self.game_time, 2),
            "victory": self.victory,
            "done": self.done,
            "wave_state": self.wave_state,
            "placement_locked": self._placement_locked(),
            "pending_upgrade_count": len(self.pending_upgrade_options),
            "auto_selected_upgrade": self.last_auto_selected_upgrade,
            "episode_truncated": self.episode_truncated,
            "termination_reason": self.termination_reason,
            "valid_actions": valid_actions,
            "valid_actions_count": len(valid_actions),
            "reward_breakdown": copy.deepcopy(self._last_reward_breakdown),
            "state_dict": self.get_render_state(),
        }
        return self.get_state(), reward, self.done, info

    def update(self, dt: float | None = None) -> float:
        if dt is None:
            dt = 1.0 / self.config.fps
        return self._advance_world(dt)

    def advance_world(self, dt: float | None = None) -> float:
        return self._advance_world(dt)

    def select_upgrade(self, option_index: int | None = None, upgrade_id: str | None = None) -> bool:
        if not self.pending_upgrade_options:
            return False

        if upgrade_id is not None:
            matched_index = next(
                (index for index, upgrade in enumerate(self.pending_upgrade_options) if upgrade.id == upgrade_id),
                None,
            )
            if matched_index is None:
                return False
            option_index = matched_index

        if option_index is None:
            option_index = 0

        if not (0 <= option_index < len(self.pending_upgrade_options)):
            return False

        selected_upgrade = self.pending_upgrade_options[option_index]
        upgrade = self.upgrade_manager.apply_upgrade(selected_upgrade.id, self)
        base_hp_bonus = int(upgrade.base_hp_bonus)
        if base_hp_bonus:
            self.base_max_hp += base_hp_bonus
            self.base_hp = min(self.base_max_hp, self.base_hp + base_hp_bonus)

        self.upgrade_counts[upgrade.id] = self.upgrade_counts.get(upgrade.id, 0) + 1
        record = upgrade.to_dict()
        record["stack"] = self.upgrade_counts[upgrade.id]
        record["wave_after_clear"] = self.waves_cleared
        self.last_selected_upgrade = copy.deepcopy(record)
        self.applied_upgrades.append(record)
        self._set_pending_upgrade_options([])

        self.message = f"Upgrade applied: {upgrade.name}"
        self.message_kind = "success"
        self.message_timer = 2.5

        if self.wave_manager.is_wave_active():
            self.wave_state = "active"
        elif self.waves_cleared < self.config.total_waves and not self.wave_manager.is_wave_active():
            self._start_next_wave()
        return True

    def _auto_select_pending_upgrade(self) -> str | None:
        if not self.pending_upgrade_options:
            return None

        recommended_index = recommend_upgrade(
            self.pending_upgrade_options,
            resources=self.resources,
            tower_cost=self.current_tower_cost(),
            base_hp=self.base_hp,
        )
        recommended_index = max(0, min(int(recommended_index), len(self.pending_upgrade_options) - 1))
        selected_upgrade = self.pending_upgrade_options[recommended_index]
        if not self.select_upgrade(option_index=recommended_index):
            return None

        auto_selected = str(
            self.last_selected_upgrade.get("id")
            or self.last_selected_upgrade.get("name")
            or selected_upgrade.id
        )
        self.last_auto_selected_upgrade = auto_selected
        return auto_selected

    def _apply_episode_truncation_if_needed(self) -> None:
        max_episode_steps = self.config.max_episode_steps
        if self.done or max_episode_steps is None or int(max_episode_steps) <= 0:
            return
        if self.episode_steps < int(max_episode_steps):
            return

        self.done = True
        self.victory = False
        self.episode_truncated = True
        self.termination_reason = "max_episode_steps"
        self.message = f"Episode truncated at {int(max_episode_steps)} steps"
        self.message_kind = "warning"
        self.message_timer = 9999.0

    def _advance_world(self, dt: float | None = None) -> float:
        if dt is None:
            dt = 1.0 / self.config.fps

        self._last_step_kills = 0
        self._last_step_breaches = 0
        self._last_reward_breakdown = _blank_reward_breakdown()
        self.last_auto_selected_upgrade = None

        if self.done:
            self.last_reward = 0.0
            return 0.0

        sun_before = int(self.resources)
        reward = self.pending_reward
        for key, value in self._pending_reward_breakdown.items():
            self._last_reward_breakdown[key] = value
        self.pending_reward = 0.0
        self._pending_reward_breakdown = _blank_reward_breakdown()

        if self.wave_state == "upgrade" and self.pending_upgrade_options and self._should_auto_select_upgrades():
            self._auto_select_pending_upgrade()

        campaign_upgrade_with_active_wave = (
            self._is_campaign_plan()
            and self.wave_state == "upgrade"
            and self.wave_manager.is_wave_active()
        )
        if self.wave_state == "upgrade" and not campaign_upgrade_with_active_wave:
            self._apply_episode_truncation_if_needed()
            reward = max(-100.0, min(100.0, reward))
            self.last_reward = reward
            self.total_reward += reward
            return reward

        self.frame_count += 1
        self.game_time += dt

        self._tick_card_cooldowns(dt)
        self._grant_resources(dt)
        self._progress_wave_spawns(dt)
        projectile_kills = self._tick_projectiles(dt) if self._uses_visual_entities() else 0
        self._tick_sun_drops(dt)

        economy_reward = 0.0
        for tower in self.towers:
            tower.tick(dt)
            if tower.role != "economy":
                continue
            produced_sun, tower_economy_reward = self._resolve_economy_production(tower)
            if produced_sun > 0:
                if self._uses_visual_entities():
                    self._spawn_sun_drop(amount=produced_sun, x=tower.center(self.config)[0], y=tower.center(self.config)[1] - 14, source="plant")
                else:
                    self.resources += produced_sun
            economy_reward += tower_economy_reward
        if economy_reward:
            reward += economy_reward
            self._last_reward_breakdown["economy"] = economy_reward

        plants_lost = self._resolve_enemy_actions(dt)
        rolling_kills = self._tick_rolling_wallnuts(dt) if self._uses_visual_entities() else 0
        if plants_lost:
            plant_lost_reward = plants_lost * PLANT_LOST_REWARD
            reward += plant_lost_reward
            self._last_reward_breakdown["plant_lost"] = plant_lost_reward

        breaches = self._resolve_base_breach()
        if breaches:
            self._last_step_breaches = breaches
            self.base_hp = max(0, self.base_hp - breaches * self.config.base_damage)
            self.damage_taken += breaches * self.config.base_damage
            breach_reward = breaches * self.config.reward_breach
            reward += breach_reward
            self._last_reward_breakdown["breaches"] = breach_reward

        kills = projectile_kills + rolling_kills + self._resolve_tower_attacks()
        if kills:
            self._last_step_kills = kills
            self.kills += kills
            kill_reward = kills * self.config.reward_kill
            reward += kill_reward
            self._last_reward_breakdown["kills"] = kill_reward

            kill_sun_bonus = int(self.game_modifiers.get("kill_sun_bonus", self.game_modifiers["kill_resource_bonus"]))
            if kill_sun_bonus:
                self.resources += kills * kill_sun_bonus

        self._update_wave_advance_countdown(dt)
        if self._is_campaign_plan() and self.wave_advance_armed and self.wave_advance_countdown <= 0.0:
            self._sync_campaign_clear_field_wait()
        elif (
            self._is_campaign_plan()
            and self.wave_advance_armed
            and not self.enemies
            and (self.wave_state == "waiting_clear" or self.campaign_waiting_clear_field)
        ):
            self._sync_campaign_clear_field_wait()
        wave_clear_reward = self._resolve_wave_progression()
        if wave_clear_reward:
            reward += wave_clear_reward
            self._last_reward_breakdown["wave_clear"] = wave_clear_reward

        survive_reward = self.config.reward_survive_per_step
        reward += survive_reward
        self._last_reward_breakdown["survive"] = survive_reward

        delta_sun_rate = float(self.config.reward_delta_sun_per_unit)
        if delta_sun_rate > 0.0:
            delta_sun = int(self.resources) - sun_before
            if delta_sun > 0:
                economy_delta = min(float(self.config.reward_delta_sun_step_cap), delta_sun_rate * float(delta_sun))
                reward += economy_delta
                self._last_reward_breakdown["economy"] = self._last_reward_breakdown.get("economy", 0.0) + economy_delta

        terminal_reward = 0.0
        if self.base_hp <= 0:
            self.done = True
            self.victory = False
            self.episode_truncated = False
            self.termination_reason = "lose"
            self.message = "Defeat: base hp reached zero"
            self.message_kind = "error"
            self.message_timer = 9999.0
            terminal_reward += self.config.reward_lose
            self._last_reward_breakdown["terminal"] = self.config.reward_lose
        elif self.victory:
            self.done = True
            self.episode_truncated = False
            self.termination_reason = "win"
            terminal_reward += self.config.reward_win
            self._last_reward_breakdown["terminal"] = self.config.reward_win
            self.message_timer = 9999.0
        elif self.config.game_duration > 0.0 and self.game_time >= self.config.game_duration:
            self.done = True
            self.victory = False
            self.episode_truncated = False
            self.termination_reason = "lose"
            self.game_time = self.config.game_duration
            self.message = "Defeat: time limit reached"
            self.message_kind = "error"
            self.message_timer = 9999.0
            terminal_reward += self.config.reward_lose
            self._last_reward_breakdown["terminal"] = self.config.reward_lose
        else:
            self._tick_message(dt)

        self._apply_episode_truncation_if_needed()

        reward += terminal_reward
        if self.config.reward_clamp_terminal_separately:
            reward = max(-100.0, min(100.0, reward - terminal_reward)) + terminal_reward
        else:
            reward = max(-100.0, min(100.0, reward))
        self.last_reward = reward
        self.total_reward += reward
        return reward

    def _set_last_action_failure(self, action_id: int, action_dict: dict[str, Any], reason: str, message: str) -> None:
        self.last_action_info = {
            "action_id": int(action_id),
            "action_dict": action_dict,
            "success": False,
            "reason": reason,
            "message": message,
        }
        self.message = message
        self.message_kind = "error"
        self.message_timer = 2.0

    def _tick_message(self, dt: float) -> None:
        if self.message_timer <= 0:
            return
        self.message_timer = max(0.0, self.message_timer - dt)
        if self.message_timer == 0.0 and not self.done:
            self.message = ""
            self.message_kind = "info"

    def _uses_visual_entities(self) -> bool:
        return self._is_campaign_plan()

    def _sun_hud_target(self) -> tuple[float, float]:
        return float(self.config.grid_origin_x + 38), 48.0

    def _spawn_sun_drop(
        self,
        *,
        amount: int,
        x: float | None = None,
        y: float | None = None,
        source: str,
    ) -> None:
        if amount <= 0:
            return
        if x is None:
            x = self.random.uniform(self.config.grid_origin_x + 32, self.config.grid_right - 32)
        if y is None:
            y = self.random.uniform(self.config.grid_origin_y + 18, self.config.grid_origin_y + self.config.cell_size * 1.1)
        self.sun_drops.append(
            SunDrop(
                uid=f"sun_{self.sun_drop_seq:03d}",
                x=float(x),
                y=float(y),
                amount=int(amount),
                age=0.0,
                state="idle",
                source=source,
            )
        )
        self.sun_drop_seq += 1

    def _tick_sun_drops(self, dt: float) -> None:
        if not self.sun_drops:
            return
        target_x, target_y = self._sun_hud_target()
        remaining: list[SunDrop] = []
        for sun_drop in self.sun_drops:
            sun_drop.age += float(dt)
            if sun_drop.state == "idle":
                delay = float(self.config.sun_drop_auto_collect_delay)
                if sun_drop.age >= delay:
                    manual_mode = bool(self.manual_upgrade_selection)
                    idle_seconds = float(self.config.sun_drop_idle_seconds)
                    # Manual + long delay: click to collect (campaign v4). Short delay: auto (v5 / training).
                    if not (manual_mode and delay > idle_seconds):
                        sun_drop.state = "collecting"
            if sun_drop.state == "collecting":
                dx = target_x - sun_drop.x
                dy = target_y - sun_drop.y
                distance = math.hypot(dx, dy)
                max_step = float(self.config.sun_drop_collect_speed_px_per_second) * float(dt)
                if distance <= max_step or distance <= 1.0:
                    self.resources += int(sun_drop.amount)
                    continue
                if distance > 0:
                    sun_drop.x += dx / distance * max_step
                    sun_drop.y += dy / distance * max_step
            remaining.append(sun_drop)
        self.sun_drops = remaining

    def _roll_pea_type(self, tower: Tower) -> str:
        if tower.plant_type != "pea_shooter":
            return "normal"
        profile = self._plant_profile("pea_shooter")
        chance = float(profile.get("ice_pea_chance", 0.0))
        if chance <= 0.0:
            return "normal"
        return "ice" if self.random.random() < chance else "normal"

    def _ice_pea_slow_params(self) -> tuple[float, float]:
        profile = self._plant_profile("pea_shooter")
        duration = float(profile.get("ice_pea_slow_duration", 8.0))
        ratio = float(profile.get("ice_pea_slow_ratio", 0.5))
        return duration, ratio

    def _apply_ice_slow(self, enemy: Enemy) -> None:
        duration, ratio = self._ice_pea_slow_params()
        enemy.apply_slow(duration, ratio)

    def _apply_projectile_hit(self, target: Enemy, projectile: Projectile) -> bool:
        dead = self._apply_enemy_damage(target, projectile.damage)
        if projectile.pea_type == "ice":
            self._apply_ice_slow(target)
        return dead

    def _spawn_projectile(self, tower: Tower, target: Enemy) -> None:
        start_x, start_y = tower.center(self.config)
        self.projectiles.append(
            Projectile(
                uid=f"projectile_{self.projectile_seq:03d}",
                row=int(tower.row),
                x=float(start_x + tower.width * 0.22),
                y=float(start_y),
                speed=float(self.config.projectile_speed_px_per_second),
                damage=int(self._tower_damage(tower)),
                source_tower_id=tower.uid,
                target_enemy_id=target.uid,
                pea_type=self._roll_pea_type(tower),
            )
        )
        self.projectile_seq += 1

    def _tick_projectiles(self, dt: float) -> int:
        if not self.projectiles:
            return 0
        kills = 0
        survivors: list[Projectile] = []
        for projectile in self.projectiles:
            previous_x = float(projectile.x)
            projectile.x += float(projectile.speed) * float(dt)
            target = self._find_projectile_hit(projectile, previous_x)
            if target is not None:
                dead = self._apply_projectile_hit(target, projectile)
                if dead:
                    kills += 1
                    self.score += int(target.reward_score)
                continue
            if projectile.x > float(self.config.grid_right + self.config.projectile_radius_px * 2):
                continue
            survivors.append(projectile)
        if kills:
            self.enemies = [enemy for enemy in self.enemies if not enemy.is_dead()]
        self.projectiles = survivors
        return kills

    def _wallnut_roll_speed_px(self) -> float:
        seconds_per_cell = max(0.01, float(self.config.wallnut_roll_seconds_per_cell))
        return float(self.config.cell_size) / seconds_per_cell

    def _spawn_rolling_wallnut(self, tower: Tower) -> None:
        if not self._uses_visual_entities() or tower.plant_type != "wallnut":
            return

        center_x, center_y = tower.center(self.config)
        self.rolling_wallnuts.append(
            RollingWallnut(
                uid=f"wallnut_roll_{self.rolling_wallnut_seq:03d}",
                row=int(tower.row),
                x=float(center_x),
                y=float(center_y),
                width=int(tower.width),
                height=int(tower.height),
                speed=self._wallnut_roll_speed_px(),
                damage=int(self.config.wallnut_roll_damage),
            )
        )
        self.rolling_wallnut_seq += 1

    def _rolling_wallnut_rect(self, roll: RollingWallnut) -> pygame.Rect:
        rect = pygame.Rect(0, 0, int(roll.width), int(roll.height))
        rect.center = (int(roll.x), int(roll.y))
        return rect

    def _tick_rolling_wallnut_hits(self, roll: RollingWallnut, previous_x: float) -> int:
        kills = 0
        nut_rect = self._rolling_wallnut_rect(roll)
        sweep_rect = nut_rect.copy()
        sweep_rect.left = min(sweep_rect.left, int(previous_x - roll.width / 2))
        sweep_rect.right = max(sweep_rect.right, int(roll.x + roll.width / 2))
        hit_ids = roll.hit_enemy_ids if roll.hit_enemy_ids is not None else set()

        for enemy in self.enemies:
            if enemy.row != roll.row or enemy.hp <= 0 or enemy.uid in hit_ids:
                continue
            enemy_rect = enemy.rect()
            if not (nut_rect.colliderect(enemy_rect) or sweep_rect.colliderect(enemy_rect)):
                continue
            hit_ids.add(enemy.uid)
            dead = self._apply_enemy_damage(enemy, roll.damage)
            if dead:
                kills += 1
                self.score += int(enemy.reward_score)
        roll.hit_enemy_ids = hit_ids
        return kills

    def _tick_rolling_wallnuts(self, dt: float) -> int:
        if not self.rolling_wallnuts:
            return 0

        kills = 0
        survivors: list[RollingWallnut] = []
        roll_radius = max(8.0, float(self.config.tower_width) / 2.0)
        right_bound = float(self.config.grid_right)

        for roll in self.rolling_wallnuts:
            previous_x = float(roll.x)
            delta = float(roll.speed) * float(dt)
            roll.x += delta
            roll.rotation += delta / roll_radius
            kills += self._tick_rolling_wallnut_hits(roll, previous_x)

            if float(roll.x) - roll_radius >= right_bound:
                continue
            survivors.append(roll)

        if kills:
            self.enemies = [enemy for enemy in self.enemies if not enemy.is_dead()]
        self.rolling_wallnuts = survivors
        return kills

    def _find_projectile_hit(self, projectile: Projectile, previous_x: float) -> Enemy | None:
        candidates = [
            enemy
            for enemy in self.enemies
            if enemy.row == projectile.row
            and enemy.hp > 0
            and enemy.rect().top <= projectile.y <= enemy.rect().bottom
            and previous_x <= enemy.rect().right
            and projectile.x >= enemy.rect().left
        ]
        if not candidates:
            return None
        preferred = next((enemy for enemy in candidates if enemy.uid == projectile.target_enemy_id), None)
        if preferred is not None:
            return preferred
        return min(candidates, key=lambda enemy: enemy.centerx)

    def _roll_sky_sun_interval(self) -> float:
        if not self.config.enable_sky_sun:
            return 0.0

        interval_min = max(0.1, float(self.config.sky_sun_interval_min))
        interval_max = max(interval_min, float(self.config.sky_sun_interval_max))
        return self.random.uniform(interval_min, interval_max)

    def _grant_resources(self, dt: float) -> None:
        passive_income = self.config.resource_income_per_second * float(self.game_modifiers["resource_income_multiplier"])
        tile_bonus_income = sum(tower.local_resource_bonus_per_second for tower in self.towers if tower.hp > 0)
        self.resource_accumulator += (passive_income + tile_bonus_income) * dt
        while self.resource_accumulator >= 1.0:
            self.resources += 1
            self.resource_accumulator -= 1.0

        if self._uses_visual_entities():
            if self.opening_bonus_sky_sun_remaining > 0 and self.game_time >= float(self.config.opening_bonus_sky_sun_delay):
                self._spawn_sun_drop(amount=int(self.config.sky_sun_amount), source="sky")
                self.opening_bonus_sky_sun_remaining -= 1
            if self.opening_grace_remaining() > 0.0:
                return

        if not self.config.enable_sky_sun or self.config.sky_sun_amount <= 0:
            self.sky_sun_timer = 0.0
            return

        remaining_dt = max(0.0, float(dt))
        while remaining_dt > 0.0:
            if self.sky_sun_timer > remaining_dt:
                self.sky_sun_timer -= remaining_dt
                break

            remaining_dt -= self.sky_sun_timer
            if self._uses_visual_entities():
                self._spawn_sun_drop(amount=int(self.config.sky_sun_amount), source="sky")
            else:
                self.resources += int(self.config.sky_sun_amount)
            self.sky_sun_timer = self._roll_sky_sun_interval()

    def _resolve_economy_production(self, tower: Tower) -> tuple[int, float]:
        if tower.role != "economy" or not tower.is_alive():
            return 0, 0.0

        base_sun = tower.produce_sun()
        if base_sun <= 0:
            return 0, 0.0

        tile_sun_multiplier = 1.0
        map_effect = self.map_effects.get((tower.row, tower.col))
        if map_effect is not None and tower.plant_type == "sunflower":
            tile_sun_multiplier = float(getattr(map_effect, "sun_produce_multiplier", 1.0))
        sun_multiplier = max(0.0, float(self.game_modifiers.get("sun_produce_multiplier", 1.0)))
        produced_sun = max(0, int(round(base_sun * sun_multiplier * tile_sun_multiplier)))
        production_cycles = max(1, base_sun // max(1, tower.sun_produce))
        return produced_sun, 0.2 * production_cycles

    def _start_next_wave(self) -> None:
        next_wave = self.wave_manager.start_next_wave()
        if next_wave is None:
            self.wave_state = "finished"
            self._sync_wave_runtime_fields()
            return

        self.wave_index = self.wave_manager.current_wave_index
        self.current_wave = next_wave
        self.wave_state = "active"
        self.current_wave_spawn_interval = self.current_wave.spawn_interval
        self.wave_spawn_locked = False
        self.wave_advance_armed = False
        self.wave_advance_countdown = 0.0
        self.campaign_waiting_clear_field = False
        self._init_campaign_wave_hp_tracking()
        if self._is_campaign_plan():
            self.wave_manager.prime_spawns_for_immediate_start(0.0)
            if self.opening_grace_remaining() <= 0.0 or self.wave_manager.current_wave_index > 0:
                self._flush_pending_wave_spawns()
        self._sync_wave_runtime_fields()
        self.message = f"Wave {self.current_wave.index} started: {self.current_wave.modifier.name}"
        self.message_kind = "info"
        self.message_timer = 2.0

    def _should_run_wave_spawns(self) -> bool:
        if self.wave_state == "active":
            return True
        return (
            self._is_campaign_plan()
            and self.wave_state == "upgrade"
            and self.wave_manager.is_wave_active()
        )

    def _flush_pending_wave_spawns(self) -> None:
        if not self.wave_manager.is_wave_active():
            return
        while self.wave_manager.should_spawn():
            spawn = self.wave_manager.get_next_spawn()
            if spawn is None:
                break
            self._spawn_enemy(enemy_type=spawn.enemy_type_id, row=spawn.row)
        self._refresh_spawn_timer()

    def _progress_wave_spawns(self, dt: float) -> None:
        if not self._should_run_wave_spawns():
            self.next_spawn_in = 0.0
            self.spawn_timer = 0.0
            self._sync_wave_runtime_fields()
            return

        if (
            self._uses_visual_entities()
            and self.opening_grace_remaining() > 0.0
            and self.wave_manager.current_wave_index <= 0
        ):
            self.spawn_timer = 0.0
            self.next_spawn_in = self.opening_grace_remaining() + float(self.wave_manager.time_until_next_spawn)
            return

        if self.wave_spawn_locked:
            self.next_spawn_in = 0.0
            self.spawn_timer = 0.0
            self._sync_wave_runtime_fields()
            return

        self.wave_manager.update(dt)
        while self.wave_manager.should_spawn():
            spawn = self.wave_manager.get_next_spawn()
            if spawn is None:
                break
            self._spawn_enemy(enemy_type=spawn.enemy_type_id, row=spawn.row)

        self._refresh_spawn_timer()

    def _refresh_spawn_timer(self) -> None:
        if not self.wave_manager.is_wave_active() or self.current_wave_spawn_interval <= 0:
            self.spawn_timer = 0.0
            self.next_spawn_in = 0.0
            self._sync_wave_runtime_fields()
            return

        self.next_spawn_in = self.wave_manager.time_until_next_spawn
        remaining = min(self.next_spawn_in, self.current_wave_spawn_interval)
        self.spawn_timer = max(0.0, self.current_wave_spawn_interval - remaining)
        self._sync_wave_runtime_fields()

    def _spawn_enemy(
        self,
        enemy_type: str | WaveSpawn = "normal",
        row: int | None = None,
        modifiers: dict[str, Any] | Any | None = None,
    ) -> None:
        if isinstance(enemy_type, WaveSpawn):
            spawn = enemy_type
            enemy_type = spawn.enemy_type_id
            if row is None:
                row = spawn.row

        wave_modifier = self.current_wave.modifier if self.current_wave is not None else None
        if row is None:
            if wave_modifier is not None and getattr(wave_modifier, "lane_mode", "spread") == "single_lane" and getattr(wave_modifier, "target_row", None) is not None:
                row = int(getattr(wave_modifier, "target_row"))
        if row is None:
            row = self.random.randrange(self.config.grid_rows)
        row = max(0, min(self.config.grid_rows - 1, int(row)))

        enemy_type_id = str(enemy_type or "normal")
        profile = self.config.enemy_config.get(enemy_type_id, self.config.enemy_config["normal"])
        enemy_type_id = enemy_type_id if enemy_type_id in self.config.enemy_config else "normal"

        wave_hp_multiplier = wave_modifier.enemy_hp_multiplier if wave_modifier is not None else 1.0
        wave_speed_multiplier = wave_modifier.enemy_speed_multiplier if wave_modifier is not None else 1.0

        extra_hp_multiplier = 1.0
        extra_speed_multiplier = 1.0
        extra_modifier_id: str | None = None
        if modifiers is not None:
            if hasattr(modifiers, "enemy_hp_multiplier") and hasattr(modifiers, "enemy_speed_multiplier"):
                extra_hp_multiplier = float(getattr(modifiers, "enemy_hp_multiplier", 1.0))
                extra_speed_multiplier = float(getattr(modifiers, "enemy_speed_multiplier", 1.0))
                extra_modifier_id = getattr(modifiers, "id", None)
            elif isinstance(modifiers, dict):
                extra_hp_multiplier = float(modifiers.get("enemy_hp_multiplier", 1.0))
                extra_speed_multiplier = float(modifiers.get("enemy_speed_multiplier", 1.0))
                modifier_id = modifiers.get("id")
                extra_modifier_id = None if modifier_id is None else str(modifier_id)

        game_hp_multiplier = float(self.game_modifiers.get("enemy_hp_multiplier", 1.0))
        game_speed_multiplier = float(self.game_modifiers.get("enemy_speed_multiplier", 1.0))

        total_hp_multiplier = wave_hp_multiplier * game_hp_multiplier * extra_hp_multiplier
        total_speed_multiplier = wave_speed_multiplier * game_speed_multiplier * extra_speed_multiplier

        x = self.config.grid_right - self.config.enemy_width
        y = self.config.grid_origin_y + row * self.config.cell_size + (self.config.cell_size - self.config.enemy_height) / 2

        modifier_ids: list[str] = []
        if wave_modifier is not None:
            modifier_ids.append(wave_modifier.id)
        if extra_modifier_id and extra_modifier_id not in modifier_ids:
            modifier_ids.append(extra_modifier_id)

        enemy = Enemy(
            uid=f"enemy_{self.enemy_seq:03d}",
            row=row,
            x=float(x),
            y=float(y),
            hp=max(1.0, float(profile["hp"]) * total_hp_multiplier),
            max_hp=max(1.0, float(profile["hp"]) * total_hp_multiplier),
            speed=max(1.0, float(profile["speed"]) * total_speed_multiplier),
            speed_fast=max(1.0, float(profile.get("speed_fast", profile["speed"])) * total_speed_multiplier),
            speed_normal=max(1.0, float(profile.get("speed_normal", profile["speed"])) * total_speed_multiplier),
            width=self.config.enemy_width,
            height=self.config.enemy_height,
            reward_score=max(1, int(profile["reward"])),
            enemy_type=enemy_type_id,
            display_name=str(profile["name"]),
            attack_damage=max(1.0, float(profile["damage"])),
            attack_cooldown=float(profile.get("attack_cooldown", self.config.enemy_attack_cooldown)),
            armor=float(profile.get("armor", 0.0)),
            can_jump_first_plant=bool(profile.get("can_jump_first_plant", False)),
            modifier_ids=tuple(modifier_ids),
            spawn_wave_id=int(self.current_wave.wave_id) if self.current_wave is not None else 0,
        )
        self.enemy_seq += 1
        self.enemies.append(enemy)

    def _init_campaign_wave_hp_tracking(self) -> None:
        if not self._is_campaign_plan() or self.current_wave is None:
            self.wave_total_hp = 0.0
            self.wave_hp_threshold_ratio = 0.0
            self.wave_damage_threshold = 0.0
            self.wave_damage_dealt = 0.0
            return

        total_hp = 0.0
        for spawn in self.current_wave.spawns:
            total_hp += self._estimate_spawn_max_hp(spawn.enemy_type_id)
        self.wave_total_hp = max(1.0, total_hp)
        threshold_min = float(self.config.wave_hp_damage_threshold_min)
        threshold_max = float(self.config.wave_hp_damage_threshold_max)
        if threshold_min > threshold_max:
            threshold_min, threshold_max = threshold_max, threshold_min
        self.wave_hp_threshold_ratio = self.random.uniform(threshold_min, threshold_max)
        self.wave_damage_threshold = self.wave_total_hp * self.wave_hp_threshold_ratio
        self.wave_damage_dealt = 0.0

    def _estimate_spawn_max_hp(self, enemy_type_id: str) -> float:
        profile = self.config.enemy_config.get(enemy_type_id, self.config.enemy_config["normal"])
        wave_modifier = self.current_wave.modifier if self.current_wave is not None else None
        wave_hp_multiplier = wave_modifier.enemy_hp_multiplier if wave_modifier is not None else 1.0
        game_hp_multiplier = float(self.game_modifiers.get("enemy_hp_multiplier", 1.0))
        return max(1.0, float(profile["hp"]) * wave_hp_multiplier * game_hp_multiplier)

    def _apply_enemy_damage(self, enemy: Enemy, damage: float) -> bool:
        hp_before = max(0.0, float(enemy.hp))
        if hp_before <= 0.0:
            return True
        dealt = min(float(damage), hp_before)
        self._register_wave_damage(dealt, enemy)
        return enemy.take_damage(damage)

    def _register_wave_damage(self, amount: float, enemy: Enemy) -> None:
        if not self._is_campaign_plan() or self.current_wave is None:
            return
        if int(getattr(enemy, "spawn_wave_id", 0)) != int(self.current_wave.wave_id):
            return
        if self.wave_advance_armed:
            return

        self.wave_damage_dealt += max(0.0, float(amount))
        if self.wave_damage_threshold > 0.0 and self.wave_damage_dealt >= self.wave_damage_threshold:
            self._arm_wave_advance()

    def _wave_advance_countdown_when_field_clear(self) -> float:
        return max(0.0, float(self.config.wave_advance_empty_field_delay_seconds))

    def _apply_fast_wave_advance_if_field_clear(self) -> None:
        if not self.wave_advance_armed or self.enemies:
            return

        fast_delay = self._wave_advance_countdown_when_field_clear()
        if self.wave_advance_countdown > fast_delay:
            self.wave_advance_countdown = fast_delay

    def _arm_wave_advance(self) -> None:
        if self.current_wave is None or self.wave_advance_armed:
            return

        self.wave_advance_armed = True
        delay = float(self.config.wave_advance_delay_seconds)
        if not self.enemies:
            delay = min(delay, self._wave_advance_countdown_when_field_clear())
        self.wave_advance_countdown = delay
        self.wave_spawn_locked = True
        self.wave_manager.cancel_pending_spawns()
        percent = int(round(self.wave_hp_threshold_ratio * 100.0))
        delay = max(0.0, self.wave_advance_countdown)
        self.message = f"Wave {self.current_wave.index}: {percent}% HP damage reached. Next wave in {delay:.0f}s."
        self.message_kind = "warning"
        self.message_timer = max(2.0, delay + 0.5)
        self._sync_wave_runtime_fields()

    def _update_wave_advance_countdown(self, dt: float) -> None:
        if not self._is_campaign_plan() or not self.wave_advance_armed:
            return

        self._apply_fast_wave_advance_if_field_clear()

        if self.wave_advance_countdown <= 0.0:
            return

        self.wave_advance_countdown = max(0.0, self.wave_advance_countdown - float(dt))
        if self.wave_advance_countdown > 0.0:
            return

        self._sync_campaign_clear_field_wait()

    def _peek_next_wave_config(self) -> WaveConfig | None:
        next_index = self.wave_manager.current_wave_index + 1
        if next_index >= len(self.wave_manager.waves):
            return None
        return self.wave_manager.waves[next_index]

    def _sync_campaign_clear_field_wait(self) -> None:
        if not self._is_campaign_plan() or not self.wave_advance_armed or self.wave_advance_countdown > 0.0:
            self.campaign_waiting_clear_field = False
            if self.wave_state == "waiting_clear":
                self.wave_state = "active"
            return

        next_wave = self._peek_next_wave_config()
        requires_clear = bool(next_wave is not None and getattr(next_wave, "start_requires_clear_field", False))
        if requires_clear and self.enemies:
            self.campaign_waiting_clear_field = True
            if self.wave_state != "upgrade":
                self.wave_state = "waiting_clear"
            self.message = f"Clear the field before Wave {next_wave.index} begins."
            self.message_kind = "warning"
            self.message_timer = 2.0
            self._sync_wave_runtime_fields()
            return

        self.campaign_waiting_clear_field = False
        if self.wave_state == "waiting_clear":
            self.wave_state = "active"
        if self.wave_advance_armed:
            self.message = f"Wave {self.current_wave.index if self.current_wave is not None else self.wave_id} complete. Advancing..."
            self.message_kind = "success"
            self.message_timer = 1.5
        self._sync_wave_runtime_fields()

    def _resolve_enemy_actions(self, dt: float) -> int:
        towers_by_row = self._towers_by_row()
        destroyed_towers: list[Tower] = []

        for enemy in self.enemies:
            enemy.tick(dt)
            blocker = self._find_blocking_tower(enemy, towers_by_row, dt)
            if blocker is None:
                enemy.update(dt)
                continue

            if self._try_enemy_jump(enemy, blocker):
                continue

            blocker_rect = blocker.rect(self.config)
            # Zombies move left: pin on the east side of the plant for attack, never push east of it.
            attack_x = float(blocker_rect.right) - float(enemy.width)
            enemy.x = min(enemy.x, attack_x)
            if enemy.ready_to_attack:
                if blocker.take_damage(enemy.attack_damage):
                    destroyed_towers.append(blocker)
                enemy.trigger_attack()

        if destroyed_towers:
            destroyed_ids = {tower.uid for tower in destroyed_towers}
            for tower in destroyed_towers:
                self._spawn_rolling_wallnut(tower)
            self.towers = [tower for tower in self.towers if tower.uid not in destroyed_ids]
        return len(destroyed_towers)

    def _towers_by_row(self) -> dict[int, list[Tower]]:
        towers_by_row: dict[int, list[Tower]] = {row: [] for row in range(self.config.grid_rows)}
        for tower in self.towers:
            towers_by_row[tower.row].append(tower)
        for towers in towers_by_row.values():
            towers.sort(key=lambda tower: tower.col, reverse=True)
        return towers_by_row

    def _find_blocking_tower(self, enemy: Enemy, towers_by_row: dict[int, list[Tower]], dt: float) -> Tower | None:
        enemy_rect = enemy.rect()
        projected_rect = enemy_rect.move(-int(round(enemy.get_current_speed() * max(0.0, dt))), 0)
        blockers: list[Tower] = []
        for tower in towers_by_row.get(enemy.row, []):
            if tower.hp <= 0:
                continue
            tower_rect = tower.rect(self.config)
            if enemy_rect.colliderect(tower_rect) or projected_rect.colliderect(tower_rect):
                blockers.append(tower)
        if not blockers:
            return None
        # Approach from the right: the rightmost plant in the lane is encountered first.
        return max(blockers, key=lambda tower: tower.col)

    def _try_enemy_jump(self, enemy: Enemy, blocker: Tower) -> bool:
        if not enemy.has_jump_available():
            return False

        if not enemy.consume_jump():
            return False

        blocker_rect = blocker.rect(self.config)
        clear_gap = 4.0
        enemy.x = float(blocker_rect.left) - float(enemy.width) - clear_gap
        enemy.y = self.config.grid_origin_y + enemy.row * self.config.cell_size + (self.config.cell_size - enemy.height) / 2
        return True

    def _resolve_tower_attacks(self) -> int:
        kills = 0
        for tower in self.towers:
            if tower.hp <= 0 or not tower.ready:
                continue
            if self._tower_damage(tower) <= 0 or self._tower_range_cells(tower) <= 0:
                continue
            target = self._find_target_for_tower(tower)
            if target is None:
                continue
            tower.trigger(self._tower_cooldown(tower))
            if self._uses_visual_entities():
                self._spawn_projectile(tower, target)
                continue
            dead = self._apply_enemy_damage(target, self._tower_damage(tower))
            if self._roll_pea_type(tower) == "ice":
                self._apply_ice_slow(target)
            if dead:
                kills += 1

        if kills:
            gained_score = sum(enemy.reward_score for enemy in self.enemies if enemy.is_dead())
            self.score += gained_score
            self.enemies = [enemy for enemy in self.enemies if not enemy.is_dead()]
        return kills

    def _find_target_for_tower(self, tower: Tower) -> Enemy | None:
        tower_center_x, _ = tower.center(self.config)
        attack_range = tower.attack_range_px(self.config, self._tower_range_cells(tower))
        candidates = [
            enemy
            for enemy in self.enemies
            if enemy.row == tower.row
            and enemy.hp > 0
            and enemy.centerx >= tower_center_x
            and (enemy.centerx - tower_center_x) <= attack_range
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda enemy: enemy.centerx)

    def _resolve_base_breach(self) -> int:
        remaining: list[Enemy] = []
        breaches = 0
        for enemy in self.enemies:
            if enemy.x <= self.config.grid_origin_x:
                breaches += 1
            else:
                remaining.append(enemy)
        self.enemies = remaining
        return breaches

    def _is_final_campaign_wave(self) -> bool:
        return self._peek_next_wave_config() is None

    def _campaign_field_clear_required(self) -> bool:
        if not self._is_campaign_plan():
            return True
        if self.campaign_waiting_clear_field:
            return False
        if self._is_final_campaign_wave():
            return bool(self.wave_manager.are_spawns_complete() and not self.enemies)
        return True

    def _campaign_wave_progress_ready(self) -> bool:
        if self.campaign_waiting_clear_field:
            return False
        if self.wave_advance_armed:
            if self.wave_advance_countdown > 0.0:
                return False
            return self._campaign_field_clear_required()
        return bool(self.wave_manager.are_spawns_complete() and not self.enemies)

    def _wave_progress_ready(self) -> bool:
        if self.current_wave is None:
            return False

        if self._is_campaign_plan():
            return self._campaign_wave_progress_ready()

        if not self.wave_manager.are_spawns_complete():
            return False
        if not self.enemies:
            return True

        next_index = self.wave_manager.current_wave_index + 1
        if next_index >= len(self.wave_manager.waves):
            # Final waves cannot hand remaining enemies to another wave.
            return False

        next_wave = self.wave_manager.waves[next_index]
        return not bool(getattr(next_wave, "start_requires_clear_field", False))

    def _resolve_wave_progression(self) -> float:
        if not self._wave_progress_ready():
            return 0.0

        cleared_wave = self.current_wave
        self.waves_cleared += 1
        self.resources += self.config.wave_clear_bonus_resources
        self.wave_manager.finish_current_wave()
        self.wave_advance_armed = False
        self.wave_advance_countdown = 0.0
        self.wave_spawn_locked = False
        self.campaign_waiting_clear_field = False

        if self.waves_cleared >= self.total_waves and not self.enemies:
            self.victory = True
            self.wave_state = "finished"
            self.message = f"Victory: cleared all {self.total_waves} waves"
            self.message_kind = "success"
            self._sync_wave_runtime_fields()
            return self.config.reward_wave_clear

        is_checkpoint = bool(getattr(cleared_wave, "checkpoint_upgrade", True))
        if self._is_campaign_plan() and is_checkpoint:
            self._start_next_wave()

        if not is_checkpoint:
            self.message = f"Wave {cleared_wave.index} cleared. Next wave incoming."
            self.message_kind = "success"
            self.message_timer = 2.0
            self._start_next_wave()
            self._sync_wave_runtime_fields()
            return self.config.reward_wave_clear

        self.wave_state = "upgrade"
        self._set_pending_upgrade_options(self.upgrade_manager.roll_options(UPGRADE_CHOICE_COUNT))
        if not self.pending_upgrade_options:
            self.message = f"Wave {cleared_wave.index} cleared. No upgrades rolled."
            self.message_kind = "info"
            self.message_timer = 2.0
            if not self.wave_manager.is_wave_active():
                self._start_next_wave()
            self._sync_wave_runtime_fields()
            return self.config.reward_wave_clear

        if self._should_auto_select_upgrades():
            self._auto_select_pending_upgrade()
            self._sync_wave_runtime_fields()
            return self.config.reward_wave_clear

        self.message = f"Wave {cleared_wave.index} cleared. Choose an upgrade to continue."
        self.message_kind = "success"
        self.message_timer = 4.0
        self._sync_wave_runtime_fields()
        return self.config.reward_wave_clear

    def _sync_tower_stats(self, tower: Tower, *, preserve_ratio: bool) -> None:
        wallnut_hp_multiplier = 1.0
        if tower.plant_type == "wallnut":
            wallnut_hp_multiplier = float(self.game_modifiers.get("wallnut_hp_multiplier", 1.0))
        plant_hp_multiplier = float(self.game_modifiers.get("plant_hp_multiplier", self.game_modifiers["tower_hp_multiplier"]))
        new_max_hp = max(
            1.0,
            tower.base_hp
            * plant_hp_multiplier
            * wallnut_hp_multiplier
            * tower.local_hp_multiplier,
        )
        if preserve_ratio and tower.max_hp > 0:
            hp_ratio = tower.hp / tower.max_hp
            tower.max_hp = new_max_hp
            tower.hp = max(1.0, min(tower.max_hp, hp_ratio * tower.max_hp))
        else:
            tower.max_hp = new_max_hp
            tower.hp = new_max_hp
        tower.cooldown_left = min(tower.cooldown_left, self._tower_attack_interval(tower))

    def _recalculate_tower_stats(self) -> None:
        for tower in self.towers:
            self._sync_tower_stats(tower, preserve_ratio=True)

    def _tower_damage(self, tower: Tower) -> int:
        if tower.base_damage <= 0:
            return 0
        multiplier = float(self.game_modifiers.get("plant_damage_multiplier", self.game_modifiers["tower_damage_multiplier"])) * tower.local_damage_multiplier
        return max(1, int(round(tower.base_damage * multiplier)))

    def _tower_attack_interval(self, tower: Tower) -> float:
        attack_interval_multiplier = float(self.game_modifiers.get("attack_interval_multiplier", self.game_modifiers["tower_cooldown_multiplier"]))
        attack_interval = tower.base_cooldown * attack_interval_multiplier * tower.local_cooldown_multiplier
        return max(0.15, attack_interval) if tower.base_cooldown > 0.0 else 0.0

    def _tower_cooldown(self, tower: Tower) -> float:
        return self._tower_attack_interval(tower)

    def _tower_range_cells(self, tower: Tower) -> int:
        return max(0, tower.range_cells + int(self.game_modifiers["tower_range_bonus_cells"]) + tower.local_range_bonus_cells)

    def _tower_render_payload(self, tower: Tower) -> dict[str, Any]:
        payload = tower.to_dict()
        payload["damage"] = self._tower_damage(tower)
        payload["cooldown"] = round(self._tower_attack_interval(tower), 2)
        payload["attack_interval"] = round(self._tower_attack_interval(tower), 2)
        payload["card_cooldown"] = round(self.current_card_cooldown(tower.plant_type), 2)
        payload["effective_range_cells"] = self._tower_range_cells(tower)
        return payload

    def _wave_render_state(self) -> dict[str, Any]:
        current_wave = self.current_wave.to_dict() if self.current_wave is not None else {}
        return {
            "current_wave_index": self.wave_id,
            "wave_id": self.wave_id,
            "total_waves": self.total_waves,
            "wave_state": self.wave_state,
            "wave_remaining": self._wave_remaining(),
            "waves_cleared": self.waves_cleared,
            "remaining_spawns": self.wave_manager.remaining_spawns(),
            "next_spawn_in": round(self.next_spawn_in, 2),
            "modifier": self._current_wave_modifier_payload(),
            "current": current_wave,
            "wave_total_hp": round(self.wave_total_hp, 1),
            "wave_damage_dealt": round(self.wave_damage_dealt, 1),
            "wave_damage_threshold": round(self.wave_damage_threshold, 1),
            "wave_hp_threshold_percent": round(self.wave_hp_threshold_ratio * 100.0, 1),
            "wave_advance_countdown": round(self.wave_advance_countdown, 2),
            "wave_spawn_locked": bool(self.wave_spawn_locked),
            "campaign_waiting_clear_field": bool(self.campaign_waiting_clear_field),
        }

    def _sync_wave_runtime_fields(self) -> None:
        self.current_wave = self.wave_manager.current_wave
        self.wave_index = self.wave_manager.current_wave_index
        self.total_waves = self.wave_manager.total_waves
        self.wave_id = self.current_wave.wave_id if self.current_wave is not None else min(self.waves_cleared, self.total_waves)
        self.pending_wave_spawns = list(self.wave_manager.pending_spawns)
        self.next_spawn_in = self.wave_manager.time_until_next_spawn if self.wave_manager.is_wave_active() else 0.0
        if self.current_wave is not None:
            self.current_wave_spawn_interval = self.current_wave.spawn_interval
            self.current_wave_modifier = self.current_wave.modifier.to_dict()
        else:
            self.current_wave_spawn_interval = 0.0
            self.current_wave_modifier = {}

    def _wave_remaining(self) -> int:
        return self.wave_manager.remaining_spawns() + len(self.enemies)

    def _modifier_render_state(self) -> dict[str, float | int]:
        return {
            "plant_damage_multiplier": round(float(self.game_modifiers.get("plant_damage_multiplier", self.game_modifiers["tower_damage_multiplier"])), 2),
            "plant_hp_multiplier": round(float(self.game_modifiers.get("plant_hp_multiplier", self.game_modifiers["tower_hp_multiplier"])), 2),
            "wallnut_hp_multiplier": round(float(self.game_modifiers.get("wallnut_hp_multiplier", 1.0)), 2),
            "plant_cost_multiplier": round(float(self.game_modifiers.get("plant_cost_multiplier", self.game_modifiers["tower_cost_multiplier"])), 2),
            "attack_interval_multiplier": round(float(self.game_modifiers.get("attack_interval_multiplier", self.game_modifiers["tower_cooldown_multiplier"])), 2),
            "card_cooldown_multiplier": round(float(self.game_modifiers.get("card_cooldown_multiplier", 1.0)), 2),
            "cooldown_multiplier": round(float(self.game_modifiers.get("cooldown_multiplier", self.game_modifiers["tower_cooldown_multiplier"])), 2),
            "kill_sun_bonus": int(self.game_modifiers.get("kill_sun_bonus", self.game_modifiers["kill_resource_bonus"])),
            "tower_damage_multiplier": round(float(self.game_modifiers["tower_damage_multiplier"]), 2),
            "tower_cooldown_multiplier": round(float(self.game_modifiers["tower_cooldown_multiplier"]), 2),
            "tower_hp_multiplier": round(float(self.game_modifiers["tower_hp_multiplier"]), 2),
            "tower_cost_multiplier": round(float(self.game_modifiers["tower_cost_multiplier"]), 2),
            "tower_range_bonus_cells": int(self.game_modifiers["tower_range_bonus_cells"]),
            "enemy_hp_multiplier": round(float(self.game_modifiers.get("enemy_hp_multiplier", 1.0)), 2),
            "enemy_speed_multiplier": round(float(self.game_modifiers.get("enemy_speed_multiplier", 1.0)), 2),
            "resource_income_multiplier": round(float(self.game_modifiers["resource_income_multiplier"]), 2),
            "sun_produce_multiplier": round(float(self.game_modifiers["sun_produce_multiplier"]), 2),
            "kill_resource_bonus": int(self.game_modifiers["kill_resource_bonus"]),
        }

    def _pending_upgrade_payload(self) -> list[dict[str, Any]]:
        recommended_index = None
        if self.pending_upgrade_options:
            recommended_index = recommend_upgrade(
                self.pending_upgrade_options,
                resources=self.resources,
                tower_cost=self.current_tower_cost(),
                base_hp=self.base_hp,
            )

        payload: list[dict[str, Any]] = []
        for index, upgrade in enumerate(self.pending_upgrade_options):
            item = upgrade.to_dict()
            item["index"] = index
            item["stack_if_taken"] = self.upgrade_counts.get(upgrade.id, 0) + 1
            item["recommended"] = index == recommended_index
            payload.append(item)
        return payload

    def _upgrade_action_ids(self) -> list[int]:
        return [_upgrade_action_id(index) for index in range(min(UPGRADE_CHOICE_COUNT, len(self.pending_upgrade_options)))]

    def _set_pending_upgrade_options(self, options: list[UpgradeDefinition]) -> None:
        self.pending_upgrade_options = list(options)

    def _wave_state_id(self) -> int:
        return int(WAVE_STATE_TO_ID.get(self.wave_state, 0))

    def _current_wave_modifier_id(self) -> int:
        modifier_name = str(self.current_wave_modifier.get("id", "none")) if self.current_wave_modifier else "none"
        return int(WAVE_MODIFIER_TO_ID.get(modifier_name, 0))

    def _map_effect_mask_rows(self, effect_id: str) -> list[int]:
        masks = [0 for _ in range(self.config.grid_rows)]
        for (row, col), effect in self.map_effects.items():
            if effect.id == effect_id:
                masks[int(row)] |= 1 << int(col)
        return masks

    def _tower_mask_rows(self, plant_type: str | None = None) -> list[int]:
        masks = [0 for _ in range(self.config.grid_rows)]
        for tower in self.towers:
            if plant_type is not None and tower.plant_type != plant_type:
                continue
            masks[int(tower.row)] |= 1 << int(tower.col)
        return masks

    def _enemy_mask_rows(self) -> list[int]:
        masks = [0 for _ in range(self.config.grid_rows)]
        for enemy in self.enemies:
            col = int((enemy.centerx - self.config.grid_origin_x) // self.config.cell_size)
            col = max(0, min(self.config.grid_cols - 1, col))
            masks[int(enemy.row)] |= 1 << int(col)
        return masks

    def _card_cooldown_bucket(self, plant_type: str) -> int:
        remaining = max(0.0, float(self.card_cooldowns.get(plant_type, 0.0)))
        total = max(0.0, float(self.current_card_cooldown(plant_type)))
        if remaining <= 0.0 or total <= 0.0:
            return 0

        ratio = remaining / total
        if ratio > (2.0 / 3.0):
            return 3
        if ratio > (1.0 / 3.0):
            return 2
        return 1

    def _encode_upgrade_option(self, upgrade_id: str | None) -> int:
        if not upgrade_id:
            return 0
        return int(TRAINING_UPGRADE_ID_TO_INDEX.get(str(upgrade_id), 0))

    def _encoded_pending_upgrade_options(self) -> tuple[int, int, int]:
        encoded = [self._encode_upgrade_option(upgrade.id) for upgrade in self.pending_upgrade_options[:UPGRADE_CHOICE_COUNT]]
        while len(encoded) < UPGRADE_CHOICE_COUNT:
            encoded.append(0)
        return int(encoded[0]), int(encoded[1]), int(encoded[2])

    def _encode_state(self) -> tuple[int, ...]:
        resource_bucket = min(
            self.resources // self.config.state_resource_bucket_size,
            self.config.state_resource_bucket_max,
        )
        time_bucket = min(
            int(self.game_time // self.config.state_time_bucket_size),
            self.config.state_time_bucket_max,
        )
        if self.current_wave_spawn_interval > 0 and self.pending_wave_spawns:
            spawn_progress = self.spawn_timer / self.current_wave_spawn_interval
        else:
            spawn_progress = 0.0
        spawn_bucket = min(int(spawn_progress * 10), self.config.state_spawn_bucket_max)
        tower_count_bucket = _count_bucket(len(self.towers))
        enemy_count_bucket = _count_bucket(len(self.enemies))
        wave_id = max(0, int(self.wave_id))
        wave_state_id = self._wave_state_id()
        active_upgrade_count = max(0, int(len(self.applied_upgrades)))
        damage_multiplier_bucket = _multiplier_bucket(
            float(self.game_modifiers.get("plant_damage_multiplier", self.game_modifiers["tower_damage_multiplier"]))
        )
        cost_multiplier_bucket = _multiplier_bucket(
            float(self.game_modifiers.get("plant_cost_multiplier", self.game_modifiers["tower_cost_multiplier"]))
        )
        sun_multiplier_bucket = _multiplier_bucket(float(self.game_modifiers.get("sun_produce_multiplier", 1.0)))
        current_wave_modifier_id = self._current_wave_modifier_id()

        tower_masks = [0 for _ in range(self.config.grid_rows)]
        for tower in self.towers:
            tower_masks[tower.row] |= 1 << tower.col

        enemy_masks = [0 for _ in range(self.config.grid_rows)]
        for enemy in self.enemies:
            col = int((enemy.centerx - self.config.grid_origin_x) // self.config.cell_size)
            col = max(0, min(self.config.grid_cols - 1, col))
            enemy_masks[enemy.row] |= 1 << col

        obstacle_masks = self._map_effect_mask_rows("obstacle")
        attack_highland_masks = self._map_effect_mask_rows("attack_highland")
        fertile_land_masks = self._map_effect_mask_rows("fertile_land")

        state = (
            int(resource_bucket),
            int(self.base_hp),
            int(time_bucket),
            int(spawn_bucket),
            int(tower_count_bucket),
            int(enemy_count_bucket),
            int(wave_id),
            int(wave_state_id),
            int(active_upgrade_count),
            int(damage_multiplier_bucket),
            int(cost_multiplier_bucket),
            int(sun_multiplier_bucket),
            int(current_wave_modifier_id),
            *tower_masks,
            *enemy_masks,
            *obstacle_masks,
            *attack_highland_masks,
            *fertile_land_masks,
        )
        return state

    def _encode_training_state(self) -> tuple[int, ...]:
        base_scalars = list(self._encode_state()[:TRAINING_STATE_SCALAR_COUNT])
        pea_masks = self._tower_mask_rows("pea_shooter")
        sunflower_masks = self._tower_mask_rows("sunflower")
        wallnut_masks = self._tower_mask_rows("wallnut")
        enemy_masks = self._enemy_mask_rows()
        obstacle_masks = self._map_effect_mask_rows("obstacle")
        attack_highland_masks = self._map_effect_mask_rows("attack_highland")
        fertile_land_masks = self._map_effect_mask_rows("fertile_land")

        available_cards = self._available_card_state()
        available_card_values = [1 if available_cards[plant_type] else 0 for plant_type in SUPPORTED_PLANT_TYPES]
        cooldown_buckets = [self._card_cooldown_bucket(plant_type) for plant_type in SUPPORTED_PLANT_TYPES]
        pending_upgrade_options = self._encoded_pending_upgrade_options()

        state = tuple(
            int(value)
            for value in (
                *base_scalars,
                *pea_masks,
                *sunflower_masks,
                *wallnut_masks,
                *enemy_masks,
                *obstacle_masks,
                *attack_highland_masks,
                *fertile_land_masks,
                *available_card_values,
                *cooldown_buckets,
                *pending_upgrade_options,
            )
        )
        if len(state) != TRAINING_STATE_VECTOR_SIZE:
            raise RuntimeError(
                f"training state size mismatch: expected {TRAINING_STATE_VECTOR_SIZE}, got {len(state)}"
            )
        return state


SimplifiedPVZEnv = TowerDefenseEnv
