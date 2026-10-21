from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace
from typing import Any


PLANT_CONFIG: dict[str, dict[str, Any]] = {
    "pea_shooter": {
        "name": "Pea Shooter",
        "name_en": "Pea Shooter",
        "name_cn": "豌豆射手",
        "role": "attack",
        "type": "attack",
        "cost": 100,
        "damage": 20,
        "ice_pea_chance": 0.15,
        "ice_pea_slow_duration": 8.0,
        "ice_pea_slow_ratio": 0.5,
        "range_cells": 9,
        # Legacy compatibility: `cooldown` continues to mean attack interval.
        "cooldown": 1.5,
        "attack_interval": 1.5,
        "card_cooldown": 7.5,
        "max_hp": 350.0,
        "produce_interval": 0.0,
        "sun_produce": 0,
    },
    "sunflower": {
        "name": "Sunflower",
        "name_en": "Sunflower",
        "name_cn": "向日葵",
        "role": "economy",
        "type": "economy",
        "cost": 50,
        "damage": 0,
        "range_cells": 0,
        "cooldown": 0.0,
        "attack_interval": 0.0,
        "card_cooldown": 7.5,
        "max_hp": 350.0,
        "produce_interval": 20.0,
        "sun_produce": 25,
    },
    "wallnut": {
        "name": "Wall-nut",
        "name_en": "Wall-nut",
        "name_cn": "坚果",
        "role": "defense",
        "type": "defense",
        "cost": 50,
        "damage": 0,
        "range_cells": 0,
        "cooldown": 0.0,
        "attack_interval": 0.0,
        "card_cooldown": 20.0,
        "max_hp": 4000.0,
        "produce_interval": 0.0,
        "sun_produce": 0,
    },
}

ENEMY_TYPE_ALIASES: dict[str, str] = {
    "fast": "pole_vaulting",
    "tank": "buckethead",
}

ENEMY_CONFIG: dict[str, dict[str, Any]] = {
    "normal": {
        "name": "Normal Zombie",
        "name_en": "Normal Zombie",
        "name_cn": "普通僵尸",
        "hp": 270.0,
        "speed": 16.0,
        "damage": 100.0,
        "reward": 20,
        "armor": 0.0,
        "attack_cooldown": 1.0,
    },
    "buckethead": {
        "name": "Buckethead Zombie",
        "name_en": "Buckethead Zombie",
        "name_cn": "铁桶僵尸",
        "hp": 1370.0,
        "speed": 16.0,
        "damage": 100.0,
        "reward": 30,
        "armor": 0.0,
        "attack_cooldown": 1.0,
    },
    "pole_vaulting": {
        "name": "Pole Vaulting Zombie",
        "name_en": "Pole Vaulting Zombie",
        "name_cn": "撑杆跳僵尸",
        "hp": 290.0,
        "speed": 32.0,
        "speed_fast": 32.0,
        "speed_normal": 16.0,
        "damage": 100.0,
        "reward": 25,
        "armor": 0.0,
        "attack_cooldown": 1.0,
        "can_jump_first_plant": True,
    },
    # Backward-compatible aliases retained for older callers/tests.
    "fast": {
        "name": "Pole Vaulting Zombie",
        "name_en": "Pole Vaulting Zombie",
        "name_cn": "撑杆跳僵尸",
        "hp": 290.0,
        "speed": 32.0,
        "speed_fast": 32.0,
        "speed_normal": 16.0,
        "damage": 100.0,
        "reward": 25,
        "armor": 0.0,
        "attack_cooldown": 1.0,
        "can_jump_first_plant": True,
        "alias_of": "pole_vaulting",
    },
    "tank": {
        "name": "Buckethead Zombie",
        "name_en": "Buckethead Zombie",
        "name_cn": "铁桶僵尸",
        "hp": 1370.0,
        "speed": 16.0,
        "damage": 100.0,
        "reward": 30,
        "armor": 0.0,
        "attack_cooldown": 1.0,
        "alias_of": "buckethead",
    },
}

SUN_SYSTEM: dict[str, Any] = {
    "sky_sun_amount": 25,
    "sky_sun_interval_min": 7.5,
    "sky_sun_interval_max": 10.0,
    "enable_sky_sun": True,
}

WAVE_MODIFIER_CONFIG: dict[str, dict[str, Any]] = {
    "steady": {
        "name": "Steady Push",
        "description": "Baseline wave with no extra modifier.",
        "enemy_speed_multiplier": 1.0,
        "enemy_hp_multiplier": 1.0,
        "enemy_count_multiplier": 1.0,
        "spawn_interval_multiplier": 1.0,
        "lane_mode": "spread",
    },
    "fast_attack": {
        "name": "Fast Attack",
        "description": "Enemies move 20% faster this wave.",
        "enemy_speed_multiplier": 1.2,
        "enemy_hp_multiplier": 1.0,
        "enemy_count_multiplier": 1.0,
        "spawn_interval_multiplier": 1.0,
        "lane_mode": "spread",
    },
    "thick_armor": {
        "name": "Thick Armor",
        "description": "Enemies gain 30% more health this wave.",
        "enemy_speed_multiplier": 1.0,
        "enemy_hp_multiplier": 1.3,
        "enemy_count_multiplier": 1.0,
        "spawn_interval_multiplier": 1.0,
        "lane_mode": "spread",
    },
    "number_pressure": {
        "name": "Number Pressure",
        "description": "This wave spawns 30% more enemies.",
        "enemy_speed_multiplier": 1.0,
        "enemy_hp_multiplier": 1.0,
        "enemy_count_multiplier": 1.3,
        "spawn_interval_multiplier": 1.0,
        "lane_mode": "spread",
    },
    "single_lane": {
        "name": "Single Lane",
        "description": "Enemies focus into one random lane this wave.",
        "enemy_speed_multiplier": 1.0,
        "enemy_hp_multiplier": 1.0,
        "enemy_count_multiplier": 1.0,
        "spawn_interval_multiplier": 1.0,
        "lane_mode": "single_lane",
    },
}

UPGRADE_POOL: dict[str, dict[str, Any]] = {
    "damage_up": {
        "name": "Damage Up",
        "description": "All offensive plants deal 20% more damage.",
        "kind": "attack",
        "damage_multiplier_add": 0.2,
        "priority": 60,
    },
    "attack_speed_up": {
        "name": "Attack Speed Up",
        "description": "Plant attack interval reduced by 15%.",
        "kind": "attack",
        "attack_interval_multiplier_factor": 0.85,
        "cooldown_multiplier_factor": 0.85,
        "priority": 62,
    },
    "hp_up": {
        "name": "Plant HP Up",
        "description": "All plants gain 20% more health.",
        "kind": "defense",
        "hp_multiplier_add": 0.2,
        "priority": 44,
    },
    "wallnut_hp_up": {
        "name": "Wall-nut HP Up",
        "description": "Wall-nuts gain 40% more health.",
        "kind": "defense",
        "wallnut_hp_multiplier_add": 0.4,
        "priority": 52,
    },
    "sun_up": {
        "name": "Sun Output Up",
        "description": "Sun-producing plants generate 20% more sun.",
        "kind": "economy",
        "sun_produce_multiplier_add": 0.2,
        "priority": 50,
    },
    "kill_sun_bonus": {
        "name": "Kill Sun Bonus",
        "description": "Each kill grants 5 bonus sun.",
        "kind": "economy",
        "kill_sun_bonus_add": 5,
        "priority": 56,
    },
    "cost_down": {
        "name": "Cost Down",
        "description": "Plant costs reduced by 10%.",
        "kind": "economy",
        "plant_cost_multiplier_factor": 0.9,
        "priority": 58,
    },
    "cooldown_down": {
        "name": "Cooldown Down",
        "description": "Card cooldowns reduced by 15%.",
        "kind": "economy",
        "card_cooldown_multiplier_factor": 0.85,
        "priority": 54,
    },
}

MAP_EFFECT_CONFIG: dict[str, dict[str, Any]] = {
    "normal": {
        "name": "Normal Ground",
        "description": "Standard tile with no extra effect.",
        "damage_multiplier": 1.0,
        "hp_multiplier": 1.0,
        "sun_produce_multiplier": 1.0,
        "resource_bonus_per_second": 0.0,
        "is_obstacle": False,
        "fill_color": (90, 100, 120),
        "border_color": (190, 210, 230),
    },
    "obstacle": {
        "name": "Obstacle",
        "description": "Cannot place plants on this tile.",
        "damage_multiplier": 1.0,
        "hp_multiplier": 1.0,
        "sun_produce_multiplier": 1.0,
        "resource_bonus_per_second": 0.0,
        "is_obstacle": True,
        "fill_color": (56, 60, 68),
        "border_color": (120, 126, 138),
    },
    "attack_highland": {
        "name": "Attack Highland",
        "description": "Attack plants deal 15% more damage here.",
        "damage_multiplier": 1.15,
        "hp_multiplier": 1.0,
        "sun_produce_multiplier": 1.0,
        "resource_bonus_per_second": 0.0,
        "is_obstacle": False,
        "fill_color": (132, 72, 46),
        "border_color": (238, 160, 94),
    },
    "fertile_land": {
        "name": "Fertile Land",
        "description": "Sunflowers produce 20% more sun here.",
        "damage_multiplier": 1.0,
        "hp_multiplier": 1.0,
        "sun_produce_multiplier": 1.2,
        "resource_bonus_per_second": 0.0,
        "is_obstacle": False,
        "fill_color": (118, 132, 54),
        "border_color": (210, 228, 120),
    },
}


def _deepcopy_config(raw: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return copy.deepcopy(raw)


def _default_plant_config() -> dict[str, dict[str, Any]]:
    return _deepcopy_config(PLANT_CONFIG)


def _default_enemy_config() -> dict[str, dict[str, Any]]:
    return _deepcopy_config(ENEMY_CONFIG)


def _default_enemy_archetypes() -> dict[str, dict[str, Any]]:
    normal = ENEMY_CONFIG["normal"]
    normal_hp = float(normal["hp"])
    normal_speed = float(normal["speed"])
    normal_reward = int(normal["reward"])
    normal_damage = float(normal["damage"])

    archetypes: dict[str, dict[str, Any]] = {}
    for enemy_id, raw in ENEMY_CONFIG.items():
        reference_speed = float(raw.get("speed_normal", raw.get("speed", normal_speed)))
        archetypes[enemy_id] = {
            "name": str(raw["name"]),
            "hp_multiplier": float(raw["hp"]) / normal_hp,
            "speed_multiplier": reference_speed / normal_speed,
            "reward_multiplier": int(raw["reward"]) / normal_reward,
            "attack_damage_multiplier": float(raw["damage"]) / normal_damage,
            "armor": float(raw.get("armor", 0.0)),
        }
    return archetypes


def _default_wave_modifier_pool() -> dict[str, dict[str, Any]]:
    return _deepcopy_config(WAVE_MODIFIER_CONFIG)


def _default_upgrade_pool() -> dict[str, dict[str, Any]]:
    return _deepcopy_config(UPGRADE_POOL)


def _default_map_effect_pool() -> dict[str, dict[str, Any]]:
    return _deepcopy_config(MAP_EFFECT_CONFIG)


def canonical_enemy_type(enemy_type: str | None) -> str:
    normalized = str(enemy_type or "normal")
    return ENEMY_TYPE_ALIASES.get(normalized, normalized if normalized in ENEMY_CONFIG else "normal")


@dataclass(frozen=True)
class GameConfig:
    window_width: int = 800
    window_height: int = 600

    grid_rows: int = 5
    grid_cols: int = 9
    cell_size: int = 80
    grid_origin_x: int = 40
    grid_origin_y: int = 100

    fps: int = 60
    # Seconds until forced defeat; <= 0 disables the time limit.
    game_duration: float = 180.0
    random_seed: int = 42

    initial_resources: int = 100
    resource_income_per_second: int = 0

    tower_cost: int = int(PLANT_CONFIG["pea_shooter"]["cost"])
    tower_damage: int = int(PLANT_CONFIG["pea_shooter"]["damage"])
    tower_base_hp: int = int(PLANT_CONFIG["pea_shooter"]["max_hp"])
    tower_range_cells: int = int(PLANT_CONFIG["pea_shooter"]["range_cells"])
    tower_cooldown: float = float(PLANT_CONFIG["pea_shooter"]["cooldown"])
    tower_card_cooldown: float = float(PLANT_CONFIG["pea_shooter"]["card_cooldown"])
    tower_width: int = 52
    tower_height: int = 52

    enemy_hp: int = int(ENEMY_CONFIG["normal"]["hp"])
    enemy_speed: float = float(ENEMY_CONFIG["normal"]["speed"])
    enemy_spawn_interval: float = 3.0
    enemy_reward_score: int = int(ENEMY_CONFIG["normal"]["reward"])
    enemy_width: int = 44
    enemy_height: int = 44
    enemy_attack_damage: int = int(ENEMY_CONFIG["normal"]["damage"])
    enemy_attack_cooldown: float = float(ENEMY_CONFIG["normal"]["attack_cooldown"])

    sky_sun_amount: int = int(SUN_SYSTEM["sky_sun_amount"])
    sky_sun_interval_min: float = float(SUN_SYSTEM["sky_sun_interval_min"])
    sky_sun_interval_max: float = float(SUN_SYSTEM["sky_sun_interval_max"])
    enable_sky_sun: bool = bool(SUN_SYSTEM["enable_sky_sun"])

    base_hp: int = 5
    base_damage: int = 1

    total_waves: int = 5
    wave_base_enemy_count: int = 4
    wave_enemy_count_step: int = 2
    wave_spawn_interval_decay: float = 0.12
    wave_clear_bonus_resources: int = 20
    wave_intermission_seconds: float = 0.0
    # Campaign: advance when this fraction of the wave's total HP has been dealt as damage.
    wave_hp_damage_threshold_min: float = 0.35
    wave_hp_damage_threshold_max: float = 0.50
    wave_advance_delay_seconds: float = 3.0
    # When no zombies remain after the HP threshold, use this shorter delay instead.
    wave_advance_empty_field_delay_seconds: float = 0.5
    wave_plan_id: str = "legacy_random"
    opening_grace_seconds: float = 0.0
    wallnut_roll_damage: int = 100
    wallnut_roll_seconds_per_cell: float = 0.35
    campaign_initial_resources: int = 100
    opening_bonus_sky_sun_count: int = 0
    lane_threat_weights: dict[str, float] = field(
        default_factory=lambda: {
            "normal": 1.0,
            "pole_vaulting": 1.5,
            "buckethead": 2.5,
        }
    )

    projectile_speed_px_per_second: float = 360.0
    projectile_radius_px: int = 7
    sun_drop_idle_seconds: float = 10.0
    sun_drop_auto_collect_delay: float = 0.75
    sun_drop_collect_speed_px_per_second: float = 520.0
    opening_bonus_sky_sun_delay: float = 5.0

    shovel_cooldown_seconds: float = 0.35
    # When False, skip SQLite/CSV/JSON session logs under logs/ (saves a lot of disk space).
    enable_battle_logging: bool = False

    upgrade_offer_size: int = 3
    auto_select_upgrades: bool = True
    map_bonus_tile_count: int = 5
    reward_preset: str = "default"
    max_episode_steps: int | None = None
    # RL-only knobs (defaults keep campaign/manual behavior unchanged).
    training_action_mode: str = "full"
    reward_clamp_terminal_separately: bool = False
    reward_valid_placement_front_bonus: float = 0.0
    reward_valid_placement_front_max_col: int = 7
    reward_delta_sun_per_unit: float = 0.0
    reward_delta_sun_step_cap: float = 2.0

    # Reward design for Q-learning.
    reward_kill: float = 10.0
    reward_breach: float = -10.0
    reward_invalid_action: float = -1.0
    reward_valid_placement: float = 0.0
    reward_survive_per_step: float = 0.1
    reward_win: float = 100.0
    reward_lose: float = -100.0
    reward_wave_clear: float = 8.0

    # State encoding buckets.
    state_resource_bucket_size: int = 25
    state_resource_bucket_max: int = 40
    state_time_bucket_size: float = 5.0
    state_time_bucket_max: int = 36
    state_spawn_bucket_max: int = 10

    plant_config: dict[str, dict[str, Any]] = field(default_factory=_default_plant_config)
    enemy_config: dict[str, dict[str, Any]] = field(default_factory=_default_enemy_config)
    enemy_archetypes: dict[str, dict[str, Any]] = field(default_factory=_default_enemy_archetypes)
    wave_modifier_pool: dict[str, dict[str, Any]] = field(default_factory=_default_wave_modifier_pool)
    upgrade_pool: dict[str, dict[str, Any]] = field(default_factory=_default_upgrade_pool)
    map_effect_pool: dict[str, dict[str, Any]] = field(default_factory=_default_map_effect_pool)

    background_color: tuple[int, int, int] = (18, 22, 34)
    grid_bg_color: tuple[int, int, int] = (34, 42, 58)
    cell_light_color: tuple[int, int, int] = (45, 54, 74)
    cell_dark_color: tuple[int, int, int] = (39, 48, 66)
    grid_line_color: tuple[int, int, int] = (85, 98, 128)
    grid_border_color: tuple[int, int, int] = (120, 138, 170)

    tower_fill_color: tuple[int, int, int] = (68, 156, 106)
    tower_shadow_color: tuple[int, int, int] = (28, 72, 52)
    tower_border_color: tuple[int, int, int] = (201, 244, 218)

    enemy_fill_color: tuple[int, int, int] = (229, 86, 80)
    enemy_shadow_color: tuple[int, int, int] = (112, 34, 31)
    enemy_border_color: tuple[int, int, int] = (255, 210, 205)

    hud_panel_color: tuple[int, int, int] = (14, 18, 26)
    hud_accent_color: tuple[int, int, int] = (96, 166, 255)
    text_color: tuple[int, int, int] = (245, 247, 250)
    muted_text_color: tuple[int, int, int] = (180, 188, 200)
    success_color: tuple[int, int, int] = (94, 204, 124)
    error_color: tuple[int, int, int] = (245, 111, 111)
    info_color: tuple[int, int, int] = (111, 184, 245)
    warning_color: tuple[int, int, int] = (251, 191, 36)

    overlay_color: tuple[int, int, int, int] = (0, 0, 0, 150)

    @property
    def grid_width(self) -> int:
        return self.grid_cols * self.cell_size

    @property
    def grid_height(self) -> int:
        return self.grid_rows * self.cell_size

    @property
    def grid_right(self) -> int:
        return self.grid_origin_x + self.grid_width

    @property
    def grid_bottom(self) -> int:
        return self.grid_origin_y + self.grid_height


CONFIG = GameConfig()


def apply_training_reward_preset(config: GameConfig) -> GameConfig:
    return replace(
        config,
        reward_preset="training",
        reward_kill=10.0,
        reward_breach=-10.0,
        reward_invalid_action=-1.0,
        reward_valid_placement=1.0,
        reward_survive_per_step=0.0,
        reward_win=100.0,
        reward_lose=-100.0,
        reward_wave_clear=8.0,
        reward_clamp_terminal_separately=True,
        reward_valid_placement_front_bonus=0.5,
        reward_valid_placement_front_max_col=7,
        reward_delta_sun_per_unit=0.02,
        reward_delta_sun_step_cap=2.0,
    )


def _scale_enemy_hp(config: GameConfig, scale: float) -> dict[str, dict[str, Any]]:
    scaled = copy.deepcopy(config.enemy_config)
    factor = max(0.1, float(scale))
    for profile in scaled.values():
        profile["hp"] = float(profile["hp"]) * factor
    return scaled


def _training_stage_base(seed: int, *, total_waves: int, wave_base_enemy_count: int, enemy_hp_scale: float) -> GameConfig:
    base = replace(
        CONFIG,
        random_seed=seed,
        wave_plan_id="legacy_random",
        total_waves=int(total_waves),
        wave_base_enemy_count=int(wave_base_enemy_count),
        wave_enemy_count_step=1,
        enemy_spawn_interval=1.2,
        initial_resources=150,
        campaign_initial_resources=150,
        tower_range_cells=9,
        tower_cooldown=0.5,
        tower_card_cooldown=1.0,
        resource_income_per_second=0,
        sky_sun_interval_min=4.0,
        sky_sun_interval_max=5.0,
        game_duration=180.0,
        auto_select_upgrades=True,
        map_bonus_tile_count=0,
        max_episode_steps=800,
        sun_drop_auto_collect_delay=2.0,
        training_action_mode="macro",
        enemy_config=_scale_enemy_hp(CONFIG, enemy_hp_scale),
    )
    return apply_training_reward_preset(base)


def build_training_stage_0_config(seed: int = 42) -> GameConfig:
    return _training_stage_base(seed, total_waves=2, wave_base_enemy_count=2, enemy_hp_scale=0.5)


def build_training_stage_1_config(seed: int = 42) -> GameConfig:
    return _training_stage_base(seed, total_waves=5, wave_base_enemy_count=3, enemy_hp_scale=1.0)


def build_training_stage_2_config(seed: int = 42) -> GameConfig:
    return _training_stage_base(seed, total_waves=8, wave_base_enemy_count=4, enemy_hp_scale=0.85)


def build_training_easy_config(seed: int = 42) -> GameConfig:
    return replace(
        build_training_stage_0_config(seed=seed),
        max_episode_steps=1000,
        training_action_mode="full",
    )


def build_campaign_v4_config(seed: int = 42) -> GameConfig:
    return replace(
        CONFIG,
        random_seed=seed,
        initial_resources=150,
        total_waves=20,
        wave_plan_id="campaign_v4",
        opening_grace_seconds=15.0,
        campaign_initial_resources=150,
        opening_bonus_sky_sun_count=1,
        opening_bonus_sky_sun_delay=5.0,
        auto_select_upgrades=False,
        game_duration=0.0,
        sun_drop_auto_collect_delay=11.0,
    )


def build_campaign_v5_config(seed: int = 42) -> GameConfig:
    return replace(
        CONFIG,
        random_seed=seed,
        initial_resources=150,
        total_waves=15,
        wave_plan_id="campaign_v5",
        opening_grace_seconds=15.0,
        campaign_initial_resources=150,
        opening_bonus_sky_sun_count=1,
        opening_bonus_sky_sun_delay=5.0,
        auto_select_upgrades=False,
        game_duration=0.0,
        sun_drop_auto_collect_delay=2.0,
        base_hp=6,
    )
