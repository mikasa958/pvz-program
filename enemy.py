from __future__ import annotations

from dataclasses import dataclass

from pygame_compat import pygame

from config import GameConfig


@dataclass
class Enemy:
    uid: str
    row: int
    x: float
    y: float
    hp: int
    max_hp: int
    speed: float
    width: int
    height: int
    reward_score: int
    enemy_type: str = "normal"

    def update(self, dt: float) -> None:
        self.x -= self.speed * dt

    @property
    def centerx(self) -> float:
        return self.x + self.width / 2

    @property
    def centery(self) -> float:
        return self.y + self.height / 2

    def take_damage(self, damage: int) -> bool:
        self.hp -= damage
        return self.hp <= 0

    def is_dead(self) -> bool:
        return self.hp <= 0

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)

    def to_dict(self) -> dict[str, object]:
        return {
            "uid": self.uid,
            "type": self.enemy_type,
            "row": self.row,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "hp": self.hp,
            "max_hp": self.max_hp,
            "speed": self.speed,
            "width": self.width,
            "height": self.height,
            "reward_score": self.reward_score,
        }

