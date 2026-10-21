from __future__ import annotations

import copy

import pygame

from config import ENEMY_CONFIG, canonical_enemy_type


# Compatibility layer: keep this name, but source defaults from config.py.
ENEMY_PROFILES: dict[str, dict[str, object]] = copy.deepcopy(ENEMY_CONFIG)


class Enemy:
    def __init__(
        self,
        uid: str,
        row: int,
        x: float,
        y: float,
        hp: float,
        max_hp: float,
        speed: float,
        width: int,
        height: int,
        reward_score: int,
        enemy_type: str = "normal",
        display_name: str | None = None,
        attack_damage: float | None = None,
        attack_cooldown: float = 0.9,
        attack_cooldown_left: float = 0.0,
        modifier_ids: tuple[str, ...] = (),
        *,
        damage: float | None = None,
        armor: float | None = None,
        slow_timer: float = 0.0,
        speed_multiplier: float | None = None,
        speed_fast: float | None = None,
        speed_normal: float | None = None,
        can_jump_first_plant: bool | None = None,
        has_used_jump: bool = False,
        spawn_wave_id: int = 0,
    ) -> None:
        self.uid = uid
        self.row = int(row)
        self.x = float(x)
        self.y = float(y)
        self.hp = float(hp)
        self.max_hp = float(max_hp)
        self.width = int(width)
        self.height = int(height)
        self.reward_score = int(reward_score)

        self.enemy_type = self._normalize_enemy_type(enemy_type)
        self.canonical_enemy_type = canonical_enemy_type(self.enemy_type)
        profile = self._profile_for(self.enemy_type)
        self.speed_fast = float(profile.get("speed_fast", speed) if speed_fast is None else speed_fast)
        self.speed_normal = float(profile.get("speed_normal", profile.get("speed", speed)) if speed_normal is None else speed_normal)
        default_jump_ready = bool(profile.get("can_jump_first_plant", False))
        self.can_jump_first_plant = bool(default_jump_ready if can_jump_first_plant is None else can_jump_first_plant)
        self.has_used_jump = bool(has_used_jump)
        if self.canonical_enemy_type == "pole_vaulting":
            if self.can_jump_first_plant and not self.has_used_jump:
                self.speed = float(self.speed_fast)
            else:
                self.speed = float(self.speed_normal)
        else:
            self.speed = float(speed)

        self.display_name = str(profile["name"] if display_name is None else display_name)
        if damage is None:
            damage = attack_damage
        if damage is None:
            damage = profile["damage"]
        self.damage = float(damage)

        if armor is None:
            armor = profile.get("armor", 0.0)
        self.armor = float(armor)


        if speed_multiplier is None:
            speed_multiplier = 1.0
        self.speed_multiplier = float(speed_multiplier)
        self.slow_timer = float(slow_timer)
        self._slow_ratio = 1.0

        if attack_cooldown == 0.9 and "attack_cooldown" in profile:
            attack_cooldown = float(profile["attack_cooldown"])
        self.attack_cooldown = float(attack_cooldown)
        self.attack_cooldown_left = float(attack_cooldown_left)
        self.modifier_ids = tuple(modifier_ids)
        self.spawn_wave_id = int(spawn_wave_id)

    @staticmethod
    def _normalize_enemy_type(value: str) -> str:
        normalized = str(value or "normal")
        if normalized in ENEMY_CONFIG:
            return normalized
        if normalized in ENEMY_PROFILES:
            return normalized
        return "normal"

    @staticmethod
    def _profile_for(enemy_type: str) -> dict[str, object]:
        if enemy_type in ENEMY_CONFIG:
            return ENEMY_CONFIG[enemy_type]
        return ENEMY_PROFILES.get(enemy_type, ENEMY_PROFILES["normal"])

    @property
    def attack_damage(self) -> float:
        return self.damage

    @attack_damage.setter
    def attack_damage(self, value: float) -> None:
        self.damage = float(value)

    def tick(self, dt: float) -> None:
        dt = float(dt)
        slow_ratio = self._slow_ratio if self.slow_timer > 0.0 else 1.0
        self.attack_cooldown_left = max(0.0, self.attack_cooldown_left - dt * slow_ratio)
        if self.slow_timer > 0.0:
            self.slow_timer = max(0.0, self.slow_timer - dt)
            if self.slow_timer == 0.0:
                self._slow_ratio = 1.0

    def update(self, dt: float) -> None:
        self.x -= self.get_current_speed() * float(dt)

    @property
    def ready_to_attack(self) -> bool:
        return self.attack_cooldown_left <= 0.0

    def trigger_attack(self) -> None:
        self.attack_cooldown_left = self.attack_cooldown

    def has_jump_available(self) -> bool:
        return self.canonical_enemy_type == "pole_vaulting" and self.can_jump_first_plant and not self.has_used_jump

    def consume_jump(self) -> bool:
        if not self.has_jump_available():
            return False
        self.can_jump_first_plant = False
        self.has_used_jump = True
        self.speed = float(self.speed_normal)
        return True

    @property
    def centerx(self) -> float:
        return self.x + self.width / 2

    @property
    def centery(self) -> float:
        return self.y + self.height / 2

    def apply_slow(self, duration: float, ratio: float) -> None:
        self.slow_timer = max(self.slow_timer, float(duration))
        ratio = max(0.0, min(1.0, float(ratio)))
        self._slow_ratio = min(self._slow_ratio, ratio) if self.slow_timer > 0.0 else ratio

    def get_current_speed(self) -> float:
        slow_ratio = self._slow_ratio if self.slow_timer > 0.0 else 1.0
        return max(0.0, self.speed * self.speed_multiplier * slow_ratio)

    @property
    def is_slowed(self) -> bool:
        return self.slow_timer > 0.0

    def take_damage(self, damage: float) -> bool:
        self.hp -= float(damage)
        return self.hp <= 0

    def is_dead(self) -> bool:
        return self.hp <= 0

    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)

    def to_dict(self) -> dict[str, object]:
        return {
            "uid": self.uid,
            "type": self.enemy_type,
            "enemy_type": self.enemy_type,
            "canonical_type": self.canonical_enemy_type,
            "name": self.display_name,
            "row": self.row,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "hp": round(self.hp, 2),
            "max_hp": round(self.max_hp, 2),
            "speed": round(self.speed, 2),
            "speed_fast": round(self.speed_fast, 2),
            "speed_normal": round(self.speed_normal, 2),
            "current_speed": round(self.get_current_speed(), 2),
            "width": self.width,
            "height": self.height,
            "reward_score": self.reward_score,
            "damage": round(self.damage, 2),
            "attack_damage": round(self.attack_damage, 2),
            "armor": round(self.armor, 2),
            "slow_timer": round(self.slow_timer, 2),
            "slowed": self.is_slowed,
            "speed_multiplier": round(self.speed_multiplier, 2),
            "attack_cooldown": round(self.attack_cooldown, 2),
            "attack_cooldown_left": round(self.attack_cooldown_left, 2),
            "can_jump_first_plant": self.can_jump_first_plant,
            "has_used_jump": self.has_used_jump,
            "modifier_ids": list(self.modifier_ids),
        }
