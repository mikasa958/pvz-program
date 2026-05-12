from __future__ import annotations

import copy
import random
from typing import Any

from pygame_compat import pygame

from config import CONFIG, GameConfig
from enemy import Enemy
from tower import Tower

GRID_ROWS = 5
GRID_COLS = 9
ACTION_WAIT = 0
ACTION_PLACE_OFFSET = 1
ACTION_SPACE_SIZE = 1 + GRID_ROWS * GRID_COLS

STATE_RESOURCE_BUCKET_INDEX = 0
STATE_BASE_HP_INDEX = 1
STATE_TIME_BUCKET_INDEX = 2
STATE_SPAWN_BUCKET_INDEX = 3
STATE_TOWER_COUNT_INDEX = 4
STATE_ENEMY_COUNT_INDEX = 5
STATE_TOWER_MASK_START = 6
STATE_ENEMY_MASK_START = STATE_TOWER_MASK_START + GRID_ROWS
STATE_VECTOR_SIZE = STATE_ENEMY_MASK_START + GRID_ROWS


class DiscreteActionSpace:
    def __init__(self, n: int, rng: random.Random) -> None:
        self.n = n
        self._rng = rng

    def sample(self) -> int:
        return self._rng.randrange(self.n)

    def contains(self, item: Any) -> bool:
        return isinstance(item, int) and 0 <= item < self.n


def action_id_to_dict(action_id: int) -> dict[str, Any]:
    action_id = int(action_id)
    if action_id == ACTION_WAIT:
        return {"action_type": "wait"}
    if 1 <= action_id < ACTION_SPACE_SIZE:
        offset = action_id - ACTION_PLACE_OFFSET
        row = offset // GRID_COLS
        col = offset % GRID_COLS
        return {
            "action_type": "place_tower",
            "tower_type": "basic",
            "row": row,
            "col": col,
        }
    raise ValueError(f"invalid action_id: {action_id}")


def action_dict_to_id(action_dict: dict[str, Any]) -> int:
    action_type = str(action_dict.get("action_type", "wait"))
    if action_type == "wait":
        return ACTION_WAIT
    if action_type != "place_tower":
        raise ValueError(f"unsupported action_type: {action_type}")

    tower_type = str(action_dict.get("tower_type", "basic"))
    if tower_type != "basic":
        raise ValueError(f"unsupported tower_type: {tower_type}")

    row = int(action_dict["row"])
    col = int(action_dict["col"])
    if not (0 <= row < GRID_ROWS and 0 <= col < GRID_COLS):
        raise ValueError(f"out of range row/col: ({row}, {col})")
    return ACTION_PLACE_OFFSET + row * GRID_COLS + col


def _count_bucket(value: int, cap: int = 9) -> int:
    return min(int(value), cap)


class TowerDefenseEnv:
    action_space_size: int = ACTION_SPACE_SIZE
    state_space_size: int = STATE_VECTOR_SIZE
    grid_shape: tuple[int, int] = (GRID_ROWS, GRID_COLS)

    def __init__(self, config: GameConfig | None = None) -> None:
        self.config = config or CONFIG
        self.random = random.Random()
        self.action_space = DiscreteActionSpace(self.action_space_size, self.random)
        self.observation_space = type("ObservationSpace", (), {"shape": (STATE_VECTOR_SIZE,)})()
        self.reset(seed=self.config.random_seed)

    def reset(self, seed: int = 42) -> tuple[int, ...]:
        self.random.seed(seed)

        self.resources = self.config.initial_resources
        self.base_hp = self.config.base_hp
        self.score = 0
        self.kills = 0
        self.damage_taken = 0
        self.game_time = 0.0
        self.frame_count = 0
        self.spawn_timer = 0.0
        self.resource_accumulator = 0.0
        self.pending_reward = 0.0
        self.last_reward = 0.0
        self.total_reward = 0.0

        self.done = False
        self.victory = False

        self.towers: list[Tower] = []
        self.enemies: list[Enemy] = []

        self.tower_seq = 1
        self.enemy_seq = 1

        self.message = "Ready. Click an empty cell to place a tower."
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
        self._last_reward_breakdown: dict[str, float] = {
            "invalid_action": 0.0,
            "survive": 0.0,
            "kills": 0.0,
            "breaches": 0.0,
            "terminal": 0.0,
        }

        return self.get_state()

    def get_state(self) -> tuple[int, ...]:
        return self._encode_state()

    def get_render_state(self) -> dict[str, Any]:
        return {
            "time": round(self.game_time, 2),
            "tick": self.frame_count,
            "resources": self.resources,
            "base_hp": self.base_hp,
            "score": self.score,
            "kills": self.kills,
            "damage_taken": self.damage_taken,
            "enemy_count": len(self.enemies),
            "tower_count": len(self.towers),
            "done": self.done,
            "victory": self.victory,
            "last_reward": round(self.last_reward, 2),
            "total_reward": round(self.total_reward, 2),
            "next_spawn_in": round(max(0.0, self.config.enemy_spawn_interval - self.spawn_timer), 2),
            "map": {
                "rows": self.config.grid_rows,
                "cols": self.config.grid_cols,
                "cell_size": self.config.cell_size,
                "origin_x": self.config.grid_origin_x,
                "origin_y": self.config.grid_origin_y,
            },
            "towers": [tower.to_dict() for tower in self.towers],
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

    def is_cell_occupied(self, row: int, col: int) -> bool:
        if any(tower.row == row and tower.col == col for tower in self.towers):
            return True
        cell_rect = self.cell_rect(row, col)
        return any(enemy.rect().colliderect(cell_rect) for enemy in self.enemies)

    def valid_actions(self) -> list[int]:
        """
        Return all currently legal discrete actions.

        This keeps the environment compatible with the training loop used by
        the sibling pvzlib package.
        """
        if self.done:
            return [ACTION_WAIT]

        valid = [ACTION_WAIT]
        if self.resources < self.config.tower_cost:
            return valid

        for row in range(self.config.grid_rows):
            for col in range(self.config.grid_cols):
                if not self.is_cell_occupied(row, col):
                    valid.append(ACTION_PLACE_OFFSET + row * self.config.grid_cols + col)
        return valid

    def apply_action(self, action_id: int | None) -> bool:
        if action_id is None:
            action_id = ACTION_WAIT

        try:
            action_dict = action_id_to_dict(action_id)
        except Exception as exc:
            if not self.done:
                self.pending_reward += self.config.reward_invalid_action
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

        row = int(action_dict["row"])
        col = int(action_dict["col"])
        if not (0 <= row < self.config.grid_rows and 0 <= col < self.config.grid_cols):
            self.pending_reward += self.config.reward_invalid_action
            self._set_last_action_failure(action_id, action_dict, "OUT_OF_RANGE", "Out of range")
            return False

        if self.resources < self.config.tower_cost:
            self.pending_reward += self.config.reward_invalid_action
            self._set_last_action_failure(action_id, action_dict, "RESOURCE_NOT_ENOUGH", "Not enough resources")
            return False

        if self.is_cell_occupied(row, col):
            self.pending_reward += self.config.reward_invalid_action
            self._set_last_action_failure(action_id, action_dict, "CELL_OCCUPIED", "Cell occupied")
            return False

        tower = Tower(
            uid=f"tower_{self.tower_seq:03d}",
            row=row,
            col=col,
            damage=self.config.tower_damage,
            range_cells=self.config.tower_range_cells,
            cooldown=self.config.tower_cooldown,
            width=self.config.tower_width,
            height=self.config.tower_height,
            tower_type="basic",
        )
        self.tower_seq += 1
        self.towers.append(tower)
        self.resources -= self.config.tower_cost
        self.last_action_info = {
            "action_id": int(action_id),
            "action_dict": action_dict,
            "success": True,
            "reason": "TOWER_PLACED",
            "message": "Tower placed",
            "cost": self.config.tower_cost,
            "resources_left": self.resources,
            "tower_uid": tower.uid,
        }
        self.message = f"Placed tower at ({row}, {col})"
        self.message_kind = "success"
        self.message_timer = 2.0
        return True

    def step(self, action_id: int | None = 0) -> tuple[tuple[int, ...], float, bool, dict[str, Any]]:
        action_success = self.apply_action(action_id)
        reward = self._advance_world()
        try:
            safe_action_id = ACTION_WAIT if action_id is None else int(action_id)
        except Exception:
            safe_action_id = ACTION_WAIT
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

    def _advance_world(self, dt: float | None = None) -> float:
        if dt is None:
            dt = 1.0 / self.config.fps

        self._last_step_kills = 0
        self._last_step_breaches = 0
        self._last_reward_breakdown = {
            "invalid_action": 0.0,
            "survive": 0.0,
            "kills": 0.0,
            "breaches": 0.0,
            "terminal": 0.0,
        }

        if self.done:
            self.last_reward = 0.0
            return 0.0

        # reward = invalid_action + survive + kills + breaches + terminal
        reward = self.pending_reward
        self._last_reward_breakdown["invalid_action"] = self.pending_reward
        self.pending_reward = 0.0

        self.frame_count += 1
        self.game_time += dt

        self.resource_accumulator += self.config.resource_income_per_second * dt
        while self.resource_accumulator >= 1.0:
            self.resources += 1
            self.resource_accumulator -= 1.0

        self.spawn_timer += dt
        while self.spawn_timer >= self.config.enemy_spawn_interval:
            self.spawn_timer -= self.config.enemy_spawn_interval
            self._spawn_enemy()

        for tower in self.towers:
            tower.tick(dt)

        for enemy in self.enemies:
            enemy.update(dt)

        breaches = self._resolve_base_breach()
        if breaches:
            self._last_step_breaches = breaches
            self.base_hp = max(0, self.base_hp - breaches * self.config.base_damage)
            self.damage_taken += breaches * self.config.base_damage
            breach_reward = breaches * self.config.reward_breach
            reward += breach_reward
            self._last_reward_breakdown["breaches"] = breach_reward

        kills = self._resolve_tower_attacks()
        if kills:
            self._last_step_kills = kills
            self.kills += kills
            self.score += kills * self.config.enemy_reward_score
            kill_reward = kills * self.config.reward_kill
            reward += kill_reward
            self._last_reward_breakdown["kills"] = kill_reward

        survive_reward = self.config.reward_survive_per_step
        reward += survive_reward
        self._last_reward_breakdown["survive"] = survive_reward

        if self.base_hp <= 0:
            self.done = True
            self.victory = False
            self.message = "Defeat: base hp reached zero"
            self.message_kind = "error"
            self.message_timer = 9999.0
            reward += self.config.reward_lose
            self._last_reward_breakdown["terminal"] = self.config.reward_lose
        elif self.game_time >= self.config.game_duration:
            self.done = True
            self.victory = True
            self.game_time = self.config.game_duration
            self.message = "Victory: survived for 180 seconds"
            self.message_kind = "success"
            self.message_timer = 9999.0
            reward += self.config.reward_win
            self._last_reward_breakdown["terminal"] = self.config.reward_win
        else:
            self._tick_message(dt)

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

    def _spawn_enemy(self) -> None:
        row = self.random.randrange(self.config.grid_rows)
        x = self.config.grid_right - self.config.enemy_width
        y = self.config.grid_origin_y + row * self.config.cell_size + (self.config.cell_size - self.config.enemy_height) / 2
        enemy = Enemy(
            uid=f"enemy_{self.enemy_seq:03d}",
            row=row,
            x=float(x),
            y=float(y),
            hp=self.config.enemy_hp,
            max_hp=self.config.enemy_hp,
            speed=self.config.enemy_speed,
            width=self.config.enemy_width,
            height=self.config.enemy_height,
            reward_score=self.config.enemy_reward_score,
            enemy_type="normal",
        )
        self.enemy_seq += 1
        self.enemies.append(enemy)

    def _resolve_tower_attacks(self) -> int:
        kills = 0
        for tower in self.towers:
            if not tower.ready:
                continue
            target = self._find_target_for_tower(tower)
            if target is None:
                continue
            dead = target.take_damage(tower.damage)
            tower.trigger()
            if dead:
                kills += 1

        if kills:
            self.enemies = [enemy for enemy in self.enemies if not enemy.is_dead()]
        return kills

    def _find_target_for_tower(self, tower: Tower) -> Enemy | None:
        tower_center_x, _ = tower.center(self.config)
        attack_range = tower.attack_range_px(self.config)
        candidates = [
            enemy
            for enemy in self.enemies
            if enemy.row == tower.row and enemy.hp > 0 and abs(enemy.centerx - tower_center_x) <= attack_range
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

    def _encode_state(self) -> tuple[int, ...]:
        resource_bucket = min(
            self.resources // self.config.state_resource_bucket_size,
            self.config.state_resource_bucket_max,
        )
        time_bucket = min(
            int(self.game_time // self.config.state_time_bucket_size),
            self.config.state_time_bucket_max,
        )
        if self.config.enemy_spawn_interval > 0:
            spawn_progress = self.spawn_timer / self.config.enemy_spawn_interval
        else:
            spawn_progress = 0.0
        spawn_bucket = min(int(spawn_progress * 10), self.config.state_spawn_bucket_max)
        tower_count_bucket = _count_bucket(len(self.towers))
        enemy_count_bucket = _count_bucket(len(self.enemies))

        tower_masks = [0 for _ in range(self.config.grid_rows)]
        for tower in self.towers:
            tower_masks[tower.row] |= 1 << tower.col

        enemy_masks = [0 for _ in range(self.config.grid_rows)]
        for enemy in self.enemies:
            col = int((enemy.centerx - self.config.grid_origin_x) // self.config.cell_size)
            col = max(0, min(self.config.grid_cols - 1, col))
            enemy_masks[enemy.row] |= 1 << col

        state = (
            int(resource_bucket),
            int(self.base_hp),
            int(time_bucket),
            int(spawn_bucket),
            int(tower_count_bucket),
            int(enemy_count_bucket),
            *tower_masks,
            *enemy_masks,
        )
        return state


SimplifiedPVZEnv = TowerDefenseEnv
