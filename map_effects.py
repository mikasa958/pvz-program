from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any

from config import GameConfig


@dataclass(frozen=True)
class MapEffectDefinition:
    id: str
    name: str
    description: str
    damage_multiplier: float = 1.0
    sun_produce_multiplier: float = 1.0
    is_obstacle: bool = False
    fill_color: tuple[int, int, int] = (60, 72, 88)
    border_color: tuple[int, int, int] = (140, 156, 178)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "damage_multiplier": self.damage_multiplier,
            "sun_produce_multiplier": self.sun_produce_multiplier,
            "is_obstacle": self.is_obstacle,
            "fill_color": list(self.fill_color),
            "border_color": list(self.border_color),
        }


def map_effect_definitions() -> dict[str, MapEffectDefinition]:
    return {
        "obstacle": MapEffectDefinition(
            id="obstacle",
            name="Obstacle",
            description="Cannot place plants on this tile.",
            is_obstacle=True,
            fill_color=(56, 60, 68),
            border_color=(120, 126, 138),
        ),
        "attack_highland": MapEffectDefinition(
            id="attack_highland",
            name="Attack Highland",
            description="Attack plants deal 15% more damage here.",
            damage_multiplier=1.15,
            fill_color=(132, 72, 46),
            border_color=(238, 160, 94),
        ),
        "fertile_land": MapEffectDefinition(
            id="fertile_land",
            name="Fertile Land",
            description="Sunflowers produce 20% more sun here.",
            sun_produce_multiplier=1.2,
            fill_color=(118, 132, 54),
            border_color=(210, 228, 120),
        ),
    }


class MapEffectManager:
    OBSTACLE_COUNT = 2
    ATTACK_HIGHLAND_COUNT = 2
    FERTILE_LAND_COUNT = 2

    def __init__(self, config: GameConfig) -> None:
        self.config = config
        self._rng = random.Random()
        self._definitions = map_effect_definitions()
        self._effects: dict[tuple[int, int], MapEffectDefinition] = {}

    def reset(self, seed: int) -> dict[tuple[int, int], MapEffectDefinition]:
        self._rng.seed(seed)
        self._effects = self._generate_effects()
        return self.get_effects()

    def get_effects(self) -> dict[tuple[int, int], MapEffectDefinition]:
        return dict(self._effects)

    def serialize(self) -> list[dict[str, Any]]:
        return serialize_map_effects(self._effects)

    def _generate_effects(self) -> dict[tuple[int, int], MapEffectDefinition]:
        if int(getattr(self.config, "map_bonus_tile_count", 0)) <= 0:
            return {}

        effects: dict[tuple[int, int], MapEffectDefinition] = {}

        obstacle_candidates = [
            (row, col)
            for row in range(self.config.grid_rows)
            for col in range(1, max(1, self.config.grid_cols - 1))
        ]
        obstacle_cells = self._sample_cells(obstacle_candidates, self.OBSTACLE_COUNT)
        for cell in obstacle_cells:
            effects[cell] = self._definitions["obstacle"]

        remaining_cells = [
            (row, col)
            for row in range(self.config.grid_rows)
            for col in range(self.config.grid_cols)
            if (row, col) not in effects
        ]
        attack_cells = self._sample_cells(remaining_cells, self.ATTACK_HIGHLAND_COUNT)
        for cell in attack_cells:
            effects[cell] = self._definitions["attack_highland"]

        remaining_cells = [cell for cell in remaining_cells if cell not in attack_cells]
        fertile_cells = self._sample_cells(remaining_cells, self.FERTILE_LAND_COUNT)
        for cell in fertile_cells:
            effects[cell] = self._definitions["fertile_land"]

        return effects

    def _sample_cells(self, cells: list[tuple[int, int]], count: int) -> list[tuple[int, int]]:
        if not cells or count <= 0:
            return []
        return self._rng.sample(cells, min(count, len(cells)))


def serialize_map_effects(tiles: dict[tuple[int, int], MapEffectDefinition]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for (row, col), effect in sorted(tiles.items()):
        payload.append(
            {
                "row": row,
                "col": col,
                "effect": effect.to_dict(),
            }
        )
    return payload


def generate_bonus_tiles(
    config: GameConfig,
    rng: random.Random,
) -> dict[tuple[int, int], MapEffectDefinition]:
    manager = MapEffectManager(config)
    seed = rng.randrange(2**31)
    manager.reset(seed)
    return manager.get_effects()


def serialize_bonus_tiles(tiles: dict[tuple[int, int], MapEffectDefinition]) -> list[dict[str, Any]]:
    return serialize_map_effects(tiles)
