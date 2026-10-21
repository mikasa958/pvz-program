from __future__ import annotations

import copy
from dataclasses import dataclass, field
import random
from typing import Any

from config import GameConfig


DEFAULT_GAME_MODIFIERS: dict[str, float | int] = {
    "plant_damage_multiplier": 1.0,
    "plant_hp_multiplier": 1.0,
    "wallnut_hp_multiplier": 1.0,
    "sun_produce_multiplier": 1.0,
    "plant_cost_multiplier": 1.0,
    "attack_interval_multiplier": 1.0,
    "card_cooldown_multiplier": 1.0,
    "cooldown_multiplier": 1.0,
    "enemy_speed_multiplier": 1.0,
    "enemy_hp_multiplier": 1.0,
    "kill_sun_bonus": 0,
    # Compatibility keys still used by the current env/training path.
    "tower_damage_multiplier": 1.0,
    "tower_cooldown_multiplier": 1.0,
    "tower_hp_multiplier": 1.0,
    "tower_cost_multiplier": 1.0,
    "tower_range_bonus_cells": 0,
    "resource_income_multiplier": 1.0,
    "kill_resource_bonus": 0,
}


@dataclass(frozen=True)
class UpgradeDefinition:
    id: str
    name: str
    description: str
    kind: str
    additive_modifiers: dict[str, float | int] = field(default_factory=dict)
    multiplicative_modifiers: dict[str, float] = field(default_factory=dict)
    base_hp_bonus: int = 0
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.kind,
            "desc": self.description,
            "description": self.description,
            "kind": self.kind,
            "priority": self.priority,
        }


UPGRADE_LIBRARY: dict[str, UpgradeDefinition] = {
    "damage_up": UpgradeDefinition(
        id="damage_up",
        name="Damage Up",
        description="All offensive plants deal 20% more damage.",
        kind="attack",
        additive_modifiers={"plant_damage_multiplier": 0.2},
        priority=60,
    ),
    "attack_speed_up": UpgradeDefinition(
        id="attack_speed_up",
        name="Attack Speed Up",
        description="Plant attack interval reduced by 15%.",
        kind="attack",
        multiplicative_modifiers={"attack_interval_multiplier": 0.85},
        priority=62,
    ),
    "hp_up": UpgradeDefinition(
        id="hp_up",
        name="Plant HP Up",
        description="All plants gain 20% more health.",
        kind="defense",
        additive_modifiers={"plant_hp_multiplier": 0.2},
        priority=44,
    ),
    "wallnut_hp_up": UpgradeDefinition(
        id="wallnut_hp_up",
        name="Wall-nut HP Up",
        description="Wall-nuts gain 40% more health.",
        kind="defense",
        additive_modifiers={"wallnut_hp_multiplier": 0.4},
        priority=52,
    ),
    "sun_up": UpgradeDefinition(
        id="sun_up",
        name="Sun Output Up",
        description="Sun-producing plants generate 20% more sun.",
        kind="economy",
        additive_modifiers={"sun_produce_multiplier": 0.2},
        priority=50,
    ),
    "kill_sun_bonus": UpgradeDefinition(
        id="kill_sun_bonus",
        name="Kill Sun Bonus",
        description="Each kill grants 5 bonus sun.",
        kind="economy",
        additive_modifiers={"kill_sun_bonus": 5},
        priority=56,
    ),
    "cost_down": UpgradeDefinition(
        id="cost_down",
        name="Cost Down",
        description="Plant costs reduced by 10%.",
        kind="economy",
        multiplicative_modifiers={"plant_cost_multiplier": 0.9},
        priority=58,
    ),
    "cooldown_down": UpgradeDefinition(
        id="cooldown_down",
        name="Cooldown Down",
        description="Card cooldowns reduced by 15%.",
        kind="economy",
        multiplicative_modifiers={"card_cooldown_multiplier": 0.85},
        priority=54,
    ),
}


def _copy_modifiers() -> dict[str, float | int]:
    return copy.deepcopy(DEFAULT_GAME_MODIFIERS)


def _sync_compatibility_modifiers(modifiers: dict[str, float | int]) -> dict[str, float | int]:
    synced = dict(modifiers)

    synced["plant_damage_multiplier"] = float(synced.get("plant_damage_multiplier", synced.get("tower_damage_multiplier", 1.0)))
    synced["plant_hp_multiplier"] = float(synced.get("plant_hp_multiplier", synced.get("tower_hp_multiplier", 1.0)))
    synced["wallnut_hp_multiplier"] = float(synced.get("wallnut_hp_multiplier", 1.0))
    synced["sun_produce_multiplier"] = float(synced.get("sun_produce_multiplier", 1.0))
    synced["plant_cost_multiplier"] = float(synced.get("plant_cost_multiplier", synced.get("tower_cost_multiplier", 1.0)))
    synced["attack_interval_multiplier"] = float(
        synced.get(
            "attack_interval_multiplier",
            synced.get("cooldown_multiplier", synced.get("tower_cooldown_multiplier", 1.0)),
        )
    )
    synced["card_cooldown_multiplier"] = float(
        synced.get("card_cooldown_multiplier", synced.get("cooldown_multiplier", 1.0))
    )
    # Legacy key continues to represent attack interval scaling.
    synced["cooldown_multiplier"] = synced["attack_interval_multiplier"]
    synced["enemy_speed_multiplier"] = float(synced.get("enemy_speed_multiplier", 1.0))
    synced["enemy_hp_multiplier"] = float(synced.get("enemy_hp_multiplier", 1.0))
    synced["kill_sun_bonus"] = int(synced.get("kill_sun_bonus", synced.get("kill_resource_bonus", 0)))

    synced["tower_damage_multiplier"] = synced["plant_damage_multiplier"]
    synced["tower_hp_multiplier"] = synced["plant_hp_multiplier"]
    synced["tower_cost_multiplier"] = synced["plant_cost_multiplier"]
    synced["tower_cooldown_multiplier"] = synced["attack_interval_multiplier"]
    synced["kill_resource_bonus"] = synced["kill_sun_bonus"]
    synced.setdefault("tower_range_bonus_cells", 0)
    synced.setdefault("resource_income_multiplier", 1.0)
    return synced


def default_game_modifiers() -> dict[str, float | int]:
    return _sync_compatibility_modifiers(_copy_modifiers())


def upgrade_definitions_from_config(config: GameConfig) -> dict[str, UpgradeDefinition]:
    # Keep the config argument for compatibility; current step uses the built-in upgrade library.
    _ = config
    return copy.deepcopy(UPGRADE_LIBRARY)


def build_upgrade_offer(
    config: GameConfig,
    rng: random.Random,
    count: int | None = None,
) -> list[UpgradeDefinition]:
    definitions = list(upgrade_definitions_from_config(config).values())
    if not definitions:
        return []

    offer_size = min(count or config.upgrade_offer_size, len(definitions))
    return rng.sample(definitions, offer_size)


def apply_upgrade(modifiers: dict[str, float | int], upgrade: UpgradeDefinition) -> dict[str, int]:
    modifiers.update(_sync_compatibility_modifiers(modifiers))

    for key, delta in upgrade.additive_modifiers.items():
        current_value = modifiers.get(key, DEFAULT_GAME_MODIFIERS.get(key, 0))
        modifiers[key] = type(current_value)(current_value + delta) if isinstance(current_value, int) and isinstance(delta, int) else float(current_value) + float(delta)

    for key, factor in upgrade.multiplicative_modifiers.items():
        current_value = float(modifiers.get(key, DEFAULT_GAME_MODIFIERS.get(key, 1.0)))
        modifiers[key] = current_value * float(factor)

    modifiers.update(_sync_compatibility_modifiers(modifiers))
    return {"base_hp_bonus": upgrade.base_hp_bonus}


def recommend_upgrade(offer: list[UpgradeDefinition], *, resources: int, tower_cost: int, base_hp: int) -> int:
    best_index = 0
    best_score: float | None = None

    for index, upgrade in enumerate(offer):
        score = float(upgrade.priority)

        if base_hp <= 3 and upgrade.id in {"hp_up", "wallnut_hp_up"}:
            score += 35.0
        if resources < tower_cost * 2:
            if upgrade.id == "cost_down":
                score += 20.0
            if upgrade.id in {"sun_up", "kill_sun_bonus"}:
                score += 12.0

        if best_score is None or score > best_score:
            best_score = score
            best_index = index
    return best_index


class UpgradeManager:
    def __init__(self, config: GameConfig | None = None) -> None:
        self.config = config
        self._rng = random.Random()
        self._modifiers = default_game_modifiers()
        self._active_upgrades: list[dict[str, Any]] = []

    def reset(self, seed: int) -> None:
        self._rng.seed(seed)
        self._modifiers = default_game_modifiers()
        self._active_upgrades = []

    def roll_options(self, count: int = 3) -> list[UpgradeDefinition]:
        definitions = list(UPGRADE_LIBRARY.values())
        if not definitions:
            return []
        return self._rng.sample(definitions, min(max(1, int(count)), len(definitions)))

    def apply_upgrade(self, upgrade_id: str, env: Any) -> UpgradeDefinition:
        if upgrade_id not in UPGRADE_LIBRARY:
            raise ValueError(f"unknown upgrade_id: {upgrade_id}")

        upgrade = copy.deepcopy(UPGRADE_LIBRARY[upgrade_id])
        apply_upgrade(self._modifiers, upgrade)
        record = upgrade.to_dict()
        record["stack"] = 1 + sum(1 for item in self._active_upgrades if item["id"] == upgrade.id)
        self._active_upgrades.append(record)

        if env is not None and hasattr(env, "game_modifiers"):
            env.game_modifiers.clear()
            env.game_modifiers.update(self.get_modifiers())
            if hasattr(env, "_recalculate_tower_stats"):
                env._recalculate_tower_stats()
            if hasattr(env, "_recalculate_card_cooldowns"):
                env._recalculate_card_cooldowns()

        return upgrade

    def get_active_upgrades(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._active_upgrades)

    def get_modifiers(self) -> dict[str, float | int]:
        return copy.deepcopy(_sync_compatibility_modifiers(self._modifiers))
