from __future__ import annotations

from dataclasses import dataclass

from pygame_compat import pygame

from config import GameConfig


@dataclass
class Tower:
    uid: str
    row: int
    col: int
    damage: int
    range_cells: int
    cooldown: float
    width: int
    height: int
    tower_type: str = "basic"
    level: int = 1
    cooldown_left: float = 0.0

    def tick(self, dt: float) -> None:
        self.cooldown_left = max(0.0, self.cooldown_left - dt)

    @property
    def ready(self) -> bool:
        return self.cooldown_left <= 0.0

    def trigger(self) -> None:
        self.cooldown_left = self.cooldown

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

    def attack_range_px(self, config: GameConfig) -> float:
        return self.range_cells * config.cell_size

    def to_dict(self) -> dict[str, object]:
        return {
            "uid": self.uid,
            "type": self.tower_type,
            "row": self.row,
            "col": self.col,
            "level": self.level,
            "damage": self.damage,
            "range_cells": self.range_cells,
            "cooldown": self.cooldown,
            "cooldown_left": round(self.cooldown_left, 2),
        }

