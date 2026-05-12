from __future__ import annotations

from dataclasses import dataclass


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
    game_duration: float = 180.0
    random_seed: int = 42

    initial_resources: int = 100
    resource_income_per_second: int = 5

    tower_cost: int = 50
    tower_damage: int = 20
    tower_range_cells: int = 3
    tower_cooldown: float = 1.0
    tower_width: int = 52
    tower_height: int = 52

    enemy_hp: int = 60
    enemy_speed: float = 40.0
    enemy_spawn_interval: float = 3.0
    enemy_reward_score: int = 20
    enemy_width: int = 44
    enemy_height: int = 44

    base_hp: int = 10
    base_damage: int = 1

    # Reward design for Q-learning.
    reward_kill: float = 10.0
    reward_breach: float = -10.0
    reward_invalid_action: float = -1.0
    reward_survive_per_step: float = 0.1
    reward_win: float = 100.0
    reward_lose: float = -100.0

    # State encoding buckets.
    state_resource_bucket_size: int = 25
    state_resource_bucket_max: int = 40
    state_time_bucket_size: float = 5.0
    state_time_bucket_max: int = 36
    state_spawn_bucket_max: int = 10

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

