from __future__ import annotations

import copy

import pygame

from config import GameConfig, PLANT_CONFIG


# Compatibility layer: keep this name, but source defaults from config.py.
PLANT_PROFILES: dict[str, dict[str, object]] = copy.deepcopy(PLANT_CONFIG)


class Tower:
    def __init__(
        self,
        uid: str,
        row: int,
        col: int,
        damage: int | None = None,
        range_cells: int | None = None,
        cooldown: float | None = None,
        width: int = 0,
        height: int = 0,
        tower_type: str = "basic",
        *,
        attack_interval: float | None = None,
        max_hp: float | None = None,
        hp: float | None = None,
        plant_type: str | None = None,
        role: str | None = None,
        produce_interval: float | None = None,
        produce_timer: float = 0.0,
        sun_produce: int | None = None,
        card_cooldown: float | None = None,
        level: int = 1,
        cooldown_left: float = 0.0,
        local_damage_multiplier: float = 1.0,
        local_cooldown_multiplier: float = 1.0,
        local_hp_multiplier: float = 1.0,
        local_resource_bonus_per_second: float = 0.0,
        local_range_bonus_cells: int = 0,
        cell_effect_id: str | None = None,
        cell_effect_name: str | None = None,
        base_damage: int | None = None,
        base_cooldown: float | None = None,
        base_hp: float | None = None,
    ) -> None:
        self.uid = uid
        self.row = int(row)
        self.col = int(col)
        self.width = int(width)
        self.height = int(height)
        self.tower_type = str(tower_type)
        self.level = int(level)

        self.plant_type = self._normalize_plant_type(plant_type or self.tower_type)
        profile = self._profile_for(self.plant_type)

        resolved_damage = profile["damage"] if damage is None and base_damage is None else damage
        if resolved_damage is None:
            resolved_damage = base_damage
        self.damage = int(profile["damage"] if resolved_damage is None else resolved_damage)

        resolved_range = profile["range_cells"] if range_cells is None else range_cells
        self.range_cells = int(profile["range_cells"] if resolved_range is None else resolved_range)

        default_attack_interval = profile.get("attack_interval", profile.get("cooldown", 0.0))
        if attack_interval is None:
            attack_interval = cooldown
        resolved_cooldown = default_attack_interval if attack_interval is None and base_cooldown is None else attack_interval
        if resolved_cooldown is None:
            resolved_cooldown = base_cooldown
        self.cooldown = float(default_attack_interval if resolved_cooldown is None else resolved_cooldown)
        self.card_cooldown = float(profile.get("card_cooldown", self.cooldown) if card_cooldown is None else card_cooldown)

        base_hp_value = profile["max_hp"] if base_hp is None else base_hp
        if max_hp is None:
            max_hp = base_hp_value
        if hp is None:
            hp = max_hp
        self._base_hp = float(base_hp_value)
        self.max_hp = float(max_hp)
        self.hp = float(hp)

        self.role = str(profile.get("role", profile.get("type", "attack")) if role is None else role)
        self.produce_interval = float(profile["produce_interval"] if produce_interval is None else produce_interval)
        self.produce_timer = float(produce_timer)
        self.sun_produce = int(profile["sun_produce"] if sun_produce is None else sun_produce)

        self.cooldown_left = float(cooldown_left)
        self.local_damage_multiplier = float(local_damage_multiplier)
        self.local_cooldown_multiplier = float(local_cooldown_multiplier)
        self.local_hp_multiplier = float(local_hp_multiplier)
        self.local_resource_bonus_per_second = float(local_resource_bonus_per_second)
        self.local_range_bonus_cells = int(local_range_bonus_cells)
        self.cell_effect_id = cell_effect_id
        self.cell_effect_name = cell_effect_name

    @staticmethod
    def _normalize_plant_type(value: str) -> str:
        normalized = str(value or "basic")
        if normalized == "basic":
            return "pea_shooter"
        if normalized in PLANT_CONFIG:
            return normalized
        if normalized in PLANT_PROFILES:
            return normalized
        return "pea_shooter"

    @staticmethod
    def _profile_for(plant_type: str) -> dict[str, object]:
        if plant_type in PLANT_CONFIG:
            return PLANT_CONFIG[plant_type]
        return PLANT_PROFILES.get(plant_type, PLANT_PROFILES["pea_shooter"])

    @property
    def base_damage(self) -> int:
        return self.damage

    @base_damage.setter
    def base_damage(self, value: int) -> None:
        self.damage = int(value)

    @property
    def base_cooldown(self) -> float:
        return self.cooldown

    @base_cooldown.setter
    def base_cooldown(self, value: float) -> None:
        self.cooldown = float(value)

    @property
    def attack_interval(self) -> float:
        return self.cooldown

    @attack_interval.setter
    def attack_interval(self, value: float) -> None:
        self.cooldown = float(value)

    @property
    def base_attack_interval(self) -> float:
        return self.base_cooldown

    @base_attack_interval.setter
    def base_attack_interval(self, value: float) -> None:
        self.base_cooldown = float(value)

    @property
    def base_hp(self) -> float:
        return self._base_hp

    @base_hp.setter
    def base_hp(self, value: float) -> None:
        self._base_hp = float(value)

    def tick(self, dt: float) -> None:
        dt = float(dt)
        self.cooldown_left = max(0.0, self.cooldown_left - dt)
        if self.is_alive() and self.produce_interval > 0.0 and self.sun_produce > 0:
            self.produce_timer += dt

    @property
    def ready(self) -> bool:
        return self.cooldown_left <= 0.0

    def trigger(self, cooldown_seconds: float | None = None) -> None:
        if cooldown_seconds is None:
            cooldown_seconds = self.cooldown
        self.cooldown_left = max(0.0, float(cooldown_seconds))

    def is_alive(self) -> bool:
        return self.hp > 0.0

    def take_damage(self, amount: float) -> bool:
        self.hp = max(0.0, self.hp - float(amount))
        return not self.is_alive()

    def can_produce_sun(self) -> bool:
        return (
            self.is_alive()
            and self.role == "economy"
            and self.sun_produce > 0
            and self.produce_interval > 0.0
            and self.produce_timer >= self.produce_interval
        )

    def produce_sun(self) -> int:
        if not self.can_produce_sun():
            return 0

        cycles = max(1, int(self.produce_timer // self.produce_interval))
        self.produce_timer = max(0.0, self.produce_timer - cycles * self.produce_interval)
        return cycles * self.sun_produce

    def center(self, config: GameConfig) -> tuple[float, float]:
        cx = config.grid_origin_x + self.col * config.cell_size + config.cell_size / 2
        cy = config.grid_origin_y + self.row * config.cell_size + config.cell_size / 2
        return cx, cy

    def rect(self, config: GameConfig) -> pygame.Rect:
        rect = pygame.Rect(0, 0, self.width, self.height)
        rect.center = (
            int(config.grid_origin_x + self.col * config.cell_size + config.cell_size / 2),
            int(config.grid_origin_y + self.row * config.cell_size + config.cell_size / 2),
        )
        return rect

    def attack_range_px(self, config: GameConfig, total_range_cells: int | None = None) -> float:
        if total_range_cells is None:
            total_range_cells = self.range_cells
        return float(total_range_cells) * config.cell_size

    def to_dict(self) -> dict[str, object]:
        return {
            "uid": self.uid,
            "type": self.tower_type,
            "tower_type": self.tower_type,
            "plant_type": self.plant_type,
            "role": self.role,
            "row": self.row,
            "col": self.col,
            "level": self.level,
            "damage": self.damage,
            "base_damage": self.base_damage,
            "range_cells": self.range_cells,
            "cooldown": self.cooldown,
            "attack_interval": self.attack_interval,
            "base_cooldown": self.base_cooldown,
            "base_attack_interval": self.base_attack_interval,
            "card_cooldown": round(self.card_cooldown, 2),
            "cooldown_left": round(self.cooldown_left, 2),
            "base_hp": round(self.base_hp, 2),
            "hp": round(self.hp, 2),
            "max_hp": round(self.max_hp, 2),
            "produce_interval": round(self.produce_interval, 2),
            "produce_timer": round(self.produce_timer, 2),
            "sun_produce": self.sun_produce,
            "cell_effect_id": self.cell_effect_id,
            "cell_effect_name": self.cell_effect_name,
            "local_damage_multiplier": round(self.local_damage_multiplier, 2),
            "local_cooldown_multiplier": round(self.local_cooldown_multiplier, 2),
            "local_hp_multiplier": round(self.local_hp_multiplier, 2),
            "local_resource_bonus_per_second": round(self.local_resource_bonus_per_second, 2),
            "local_range_bonus_cells": self.local_range_bonus_cells,
        }
