from __future__ import annotations

import math

import pygame

from config import GameConfig


class GameRenderer:
    def __init__(self, config: GameConfig) -> None:
        self.config = config
        self.title_font = self._make_font(24)
        self.body_font = self._make_font(18)
        self.small_font = self._make_font(14)
        self.huge_font = self._make_font(44)

    def _make_font(self, size: int) -> pygame.font.Font:
        for name in ("Microsoft YaHei", "SimHei", "Arial Unicode MS", "Arial"):
            try:
                font = pygame.font.SysFont(name, size)
                if font is not None:
                    return font
            except Exception:
                continue
        return pygame.font.Font(None, size)

    @staticmethod
    def _as_dict(value: object) -> dict[str, object]:
        return value if isinstance(value, dict) else {}

    def draw(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        screen.fill(self.config.background_color)
        self._draw_board(screen, state)
        self._draw_shovel_highlights(screen, state)
        self._draw_towers(screen, state)
        self._draw_sun_drops(screen, state)
        self._draw_enemies(screen, state)
        self._draw_rolling_wallnuts(screen, state)
        self._draw_projectiles(screen, state)
        self._draw_hud(screen, state)
        self._draw_footer(screen, state)
        if str(state.get("wave_state", "")) == "upgrade" and self._pending_upgrades(state):
            self._draw_upgrade_overlay(screen, state)
        if state.get("done"):
            self._draw_overlay(screen, state)

    def upgrade_card_rects(self, count: int) -> list[pygame.Rect]:
        if count <= 0:
            return []
        card_width = 224
        card_height = 196
        gap = 20
        total_width = count * card_width + (count - 1) * gap
        start_x = (self.config.window_width - total_width) // 2
        top = 220
        return [
            pygame.Rect(start_x + index * (card_width + gap), top, card_width, card_height)
            for index in range(count)
        ]

    def _draw_board(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        board_rect = pygame.Rect(
            self.config.grid_origin_x,
            self.config.grid_origin_y,
            self.config.grid_width,
            self.config.grid_height,
        )
        pygame.draw.rect(screen, self.config.grid_bg_color, board_rect, border_radius=14)
        bonus_cells = self._map_effect_cells(state)

        for row in range(self.config.grid_rows):
            for col in range(self.config.grid_cols):
                rect = pygame.Rect(
                    self.config.grid_origin_x + col * self.config.cell_size,
                    self.config.grid_origin_y + row * self.config.cell_size,
                    self.config.cell_size,
                    self.config.cell_size,
                )
                fill_color = self.config.cell_light_color if (row + col) % 2 == 0 else self.config.cell_dark_color
                pygame.draw.rect(screen, fill_color, rect)
                effect = bonus_cells.get((row, col))
                if effect is not None:
                    self._draw_map_effect_tile(screen, rect, effect)
                pygame.draw.rect(screen, self.config.grid_line_color, rect, width=1)

        pygame.draw.rect(screen, self.config.grid_border_color, board_rect, width=2, border_radius=14)

    def _draw_map_effect_tile(self, screen: pygame.Surface, rect: pygame.Rect, effect: dict[str, object]) -> None:
        inset = rect.inflate(-8, -8)
        fill_color = tuple(effect.get("fill_color", (90, 100, 120)))
        border_color = tuple(effect.get("border_color", (190, 210, 230)))
        overlay = pygame.Surface((inset.width, inset.height), pygame.SRCALPHA)
        alpha = 150 if effect.get("is_obstacle") else 120
        overlay.fill((*fill_color, alpha))
        screen.blit(overlay, inset.topleft)
        pygame.draw.rect(screen, border_color, inset, width=3 if effect.get("is_obstacle") else 2, border_radius=10)

        effect_id = str(effect.get("id", ""))
        center = inset.center
        if effect_id == "obstacle":
            block = inset.inflate(-18, -18)
            pygame.draw.rect(screen, (68, 72, 82), block, border_radius=8)
            pygame.draw.line(screen, (190, 196, 208), block.topleft, block.bottomright, 3)
            pygame.draw.line(screen, (190, 196, 208), block.topright, block.bottomleft, 3)
        elif effect_id == "attack_highland":
            diamond = [
                (center[0], inset.top + 10),
                (inset.right - 12, center[1]),
                (center[0], inset.bottom - 10),
                (inset.left + 12, center[1]),
            ]
            pygame.draw.polygon(screen, (252, 185, 90), diamond)
            pygame.draw.polygon(screen, (255, 227, 182), diamond, width=2)
        elif effect_id == "fertile_land":
            pygame.draw.circle(screen, (247, 214, 86), center, 12)
            for angle in range(0, 360, 45):
                dx = int(math.cos(math.radians(angle)) * 18)
                dy = int(math.sin(math.radians(angle)) * 18)
                pygame.draw.circle(screen, (178, 220, 92), (center[0] + dx, center[1] + dy), 6)

    def _draw_shovel_highlights(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        if str(state.get("selected_tool", "plant")) != "shovel":
            return

        drag_cells = state.get("shovel_drag_cells") or []
        for item in drag_cells:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            rect = self._plant_cell_rect(int(item[0]), int(item[1]))
            overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            overlay.fill((255, 120, 72, 72))
            screen.blit(overlay, rect.topleft)
            pygame.draw.rect(screen, (255, 168, 96), rect, width=2, border_radius=8)

        mouse_cell = state.get("mouse_grid_cell")
        if isinstance(mouse_cell, (list, tuple)) and len(mouse_cell) == 2:
            row, col = int(mouse_cell[0]), int(mouse_cell[1])
            if (row, col) not in {(int(item[0]), int(item[1])) for item in drag_cells if isinstance(item, (list, tuple)) and len(item) == 2}:
                rect = self._plant_cell_rect(row, col)
                overlay = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                overlay.fill((255, 86, 86, 56))
                screen.blit(overlay, rect.topleft)
                pygame.draw.rect(screen, (255, 132, 132), rect, width=2, border_radius=8)

    def _plant_cell_rect(self, row: int, col: int) -> pygame.Rect:
        return pygame.Rect(
            self.config.grid_origin_x + col * self.config.cell_size + 4,
            self.config.grid_origin_y + row * self.config.cell_size + 4,
            self.config.cell_size - 8,
            self.config.cell_size - 8,
        )

    def _draw_towers(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        for tower in state.get("towers", []):
            row = int(tower["row"])
            col = int(tower["col"])
            rect = pygame.Rect(
                self.config.grid_origin_x + col * self.config.cell_size + 10,
                self.config.grid_origin_y + row * self.config.cell_size + 10,
                self.config.cell_size - 20,
                self.config.cell_size - 20,
            )
            plant_type = str(tower.get("plant_type", tower.get("type", "pea_shooter")))
            if plant_type == "basic":
                plant_type = "pea_shooter"

            if plant_type == "sunflower":
                self._draw_sunflower(screen, rect)
            elif plant_type == "wallnut":
                self._draw_wallnut(screen, rect, rotation=0.0)
            else:
                self._draw_pea_shooter(screen, rect)

            hp = float(tower.get("hp", 1.0))
            max_hp = max(1.0, float(tower.get("max_hp", 1.0)))
            self._draw_bar(screen, rect.left, rect.top - 10, rect.width, 5, hp / max_hp, (88, 216, 122), back_color=(44, 56, 42))

    def _draw_pea_shooter(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        center = rect.center
        stem_color = (68, 150, 94)
        head_color = (108, 204, 118)
        muzzle_color = (182, 255, 182)
        leaf_color = (78, 170, 110)

        shadow = rect.move(4, 6)
        pygame.draw.ellipse(screen, (26, 64, 42), shadow.inflate(-12, -22))
        pygame.draw.line(screen, stem_color, (center[0] - 6, rect.bottom - 10), (center[0] - 2, center[1] + 10), 7)
        pygame.draw.line(screen, stem_color, (center[0] + 4, rect.bottom - 10), (center[0] + 2, center[1] + 10), 7)
        pygame.draw.ellipse(screen, leaf_color, pygame.Rect(rect.left + 10, rect.bottom - 22, 18, 10))
        pygame.draw.ellipse(screen, leaf_color, pygame.Rect(rect.left + 24, rect.bottom - 18, 18, 10))
        pygame.draw.circle(screen, head_color, (center[0] - 2, center[1] - 6), 16)
        muzzle = pygame.Rect(center[0] + 8, center[1] - 11, 22, 16)
        pygame.draw.ellipse(screen, head_color, muzzle)
        pygame.draw.ellipse(screen, muzzle_color, muzzle.inflate(-10, -8))
        pygame.draw.circle(screen, (58, 110, 68), (center[0] - 10, center[1] - 10), 3)

    def _draw_sunflower(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        center = rect.center
        petal_color = (255, 209, 76)
        petal_edge = (255, 240, 182)
        face_color = (120, 82, 38)
        stem_color = (74, 162, 86)

        shadow = rect.move(4, 6)
        pygame.draw.ellipse(screen, (60, 74, 32), shadow.inflate(-14, -24))
        pygame.draw.line(screen, stem_color, (center[0], rect.bottom - 10), (center[0], center[1] + 8), 7)
        pygame.draw.ellipse(screen, (94, 190, 102), pygame.Rect(rect.left + 8, center[1] + 6, 16, 10))
        pygame.draw.ellipse(screen, (94, 190, 102), pygame.Rect(rect.right - 24, center[1] + 2, 16, 10))
        for angle in range(0, 360, 45):
            dx = int(math.cos(math.radians(angle)) * 18)
            dy = int(math.sin(math.radians(angle)) * 18)
            pygame.draw.circle(screen, petal_color, (center[0] + dx, center[1] - 6 + dy), 9)
            pygame.draw.circle(screen, petal_edge, (center[0] + dx, center[1] - 6 + dy), 9, 1)
        pygame.draw.circle(screen, face_color, (center[0], center[1] - 6), 15)
        pygame.draw.circle(screen, (255, 226, 120), (center[0], center[1] - 6), 10)
        pygame.draw.circle(screen, (84, 58, 28), (center[0] - 4, center[1] - 8), 2)
        pygame.draw.circle(screen, (84, 58, 28), (center[0] + 4, center[1] - 8), 2)
        pygame.draw.arc(screen, (84, 58, 28), pygame.Rect(center[0] - 6, center[1] - 6, 12, 8), 0.2, 2.9, 2)

    def _draw_wallnut(self, screen: pygame.Surface, rect: pygame.Rect, rotation: float = 0.0) -> None:
        if abs(rotation) < 0.001:
            self._paint_wallnut(screen, rect)
            return

        sprite_size = max(rect.width, rect.height) + 12
        sprite = pygame.Surface((sprite_size, sprite_size), pygame.SRCALPHA)
        inner = pygame.Rect(0, 0, rect.width, rect.height)
        inner.center = (sprite_size // 2, sprite_size // 2)
        self._paint_wallnut(sprite, inner)
        rotated = pygame.transform.rotate(sprite, -math.degrees(rotation))
        dest = rotated.get_rect(center=rect.center)
        screen.blit(rotated, dest)

    def _paint_wallnut(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        shell_rect = rect.inflate(-8, -6)
        shadow = shell_rect.move(4, 6)
        pygame.draw.ellipse(screen, (64, 34, 16), shadow)
        pygame.draw.ellipse(screen, (150, 98, 54), shell_rect)
        pygame.draw.ellipse(screen, (198, 146, 84), shell_rect, 2)
        cap_rect = pygame.Rect(shell_rect.x + 6, shell_rect.y + 8, shell_rect.width - 12, shell_rect.height - 12)
        pygame.draw.arc(screen, (118, 72, 40), cap_rect, 2.7, 0.5, 3)
        pygame.draw.arc(screen, (118, 72, 40), cap_rect.inflate(-6, -10), 2.7, 0.5, 2)
        eye_y = shell_rect.centery - 6
        pygame.draw.circle(screen, (52, 30, 18), (shell_rect.centerx - 8, eye_y), 2)
        pygame.draw.circle(screen, (52, 30, 18), (shell_rect.centerx + 8, eye_y), 2)
        pygame.draw.arc(screen, (52, 30, 18), pygame.Rect(shell_rect.centerx - 10, shell_rect.centery + 2, 20, 10), 0.2, 2.9, 2)

    def _draw_rolling_wallnuts(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        for item in state.get("rolling_wallnuts") or []:
            if not isinstance(item, dict):
                continue
            width = int(item.get("width", self.config.tower_width))
            height = int(item.get("height", self.config.tower_height))
            rect = pygame.Rect(0, 0, width, height)
            rect.center = (int(item.get("x", 0)), int(item.get("y", 0)))
            shadow = rect.move(4, 6).inflate(-8, -10)
            pygame.draw.ellipse(screen, (64, 34, 16, 140), shadow)
            rotation = float(item.get("rotation", 0.0))
            self._draw_wallnut(screen, rect, rotation=rotation)

    def _draw_enemies(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        for enemy in state.get("enemies", []):
            x = int(enemy["x"])
            y = int(enemy["y"])
            enemy_type = str(enemy.get("canonical_type", enemy.get("type", enemy.get("enemy_type", "normal"))))
            if enemy_type == "fast":
                enemy_type = "pole_vaulting"
            elif enemy_type == "tank":
                enemy_type = "buckethead"
            base_width = int(enemy.get("width", self.config.enemy_width))
            base_height = int(enemy.get("height", self.config.enemy_height))
            base_rect = pygame.Rect(x, y, base_width, base_height)

            frozen = bool(enemy.get("slowed")) or float(enemy.get("slow_timer", 0.0)) > 0.0

            if enemy_type == "pole_vaulting":
                rect = pygame.Rect(0, 0, max(22, int(base_width * 0.82)), max(24, int(base_height * 0.82)))
                rect.center = base_rect.center
                self._draw_pole_vaulting_enemy(screen, rect, frozen=frozen)
                bar_height = 5
            elif enemy_type == "buckethead":
                rect = pygame.Rect(0, 0, max(32, int(base_width * 1.18)), max(34, int(base_height * 1.18)))
                rect.center = base_rect.center
                self._draw_buckethead_enemy(screen, rect, frozen=frozen)
                bar_height = 8
            else:
                rect = base_rect
                self._draw_normal_enemy(screen, rect, frozen=frozen)
                bar_height = 5

            hp = float(enemy.get("hp", 1.0))
            max_hp = max(1.0, float(enemy.get("max_hp", 1.0)))
            if frozen:
                bar_color = (96, 188, 255)
                bar_back = (24, 52, 92)
            else:
                bar_color = (220, 90, 90)
                bar_back = (74, 28, 28)
            self._draw_bar(screen, rect.left, rect.top - 10, rect.width, bar_height, hp / max_hp, bar_color, back_color=bar_back)

    def _draw_normal_enemy(self, screen: pygame.Surface, rect: pygame.Rect, *, frozen: bool = False) -> None:
        if frozen:
            shadow = rect.move(4, 4)
            pygame.draw.rect(screen, (34, 72, 112), shadow, border_radius=9)
            pygame.draw.rect(screen, (96, 176, 238), rect, border_radius=9)
            pygame.draw.rect(screen, (210, 238, 255), rect, 2, border_radius=9)
            eye_color = (236, 248, 255)
            mouth_color = (214, 236, 255)
        else:
            shadow = rect.move(4, 4)
            pygame.draw.rect(screen, (112, 34, 31), shadow, border_radius=9)
            pygame.draw.rect(screen, (225, 84, 78), rect, border_radius=9)
            pygame.draw.rect(screen, (255, 204, 198), rect, 2, border_radius=9)
            eye_color = (255, 240, 240)
            mouth_color = (255, 226, 226)
        eye_y = rect.top + 12
        pygame.draw.circle(screen, eye_color, (rect.left + 12, eye_y), 3)
        pygame.draw.circle(screen, eye_color, (rect.right - 12, eye_y), 3)
        pygame.draw.line(screen, mouth_color, (rect.centerx - 8, rect.centery), (rect.centerx + 6, rect.centery + 8), 2)

    def _draw_pole_vaulting_enemy(self, screen: pygame.Surface, rect: pygame.Rect, *, frozen: bool = False) -> None:
        trail_color = (150, 210, 255) if frozen else (255, 140, 140)
        for offset in (8, 14, 20):
            pygame.draw.line(screen, trail_color, (rect.left - offset, rect.centery - 8), (rect.left - 4, rect.centery - 8), 2)
            pygame.draw.line(screen, trail_color, (rect.left - offset + 2, rect.centery), (rect.left - 4, rect.centery), 2)
        if frozen:
            shadow = rect.move(4, 3)
            pygame.draw.rect(screen, (42, 82, 126), shadow, border_radius=10)
            pygame.draw.rect(screen, (118, 196, 248), rect, border_radius=10)
            pygame.draw.rect(screen, (220, 242, 255), rect, 2, border_radius=10)
            eye_color = (236, 248, 255)
            pole_colors = ((176, 214, 238), (214, 236, 255))
        else:
            shadow = rect.move(4, 3)
            pygame.draw.rect(screen, (126, 44, 42), shadow, border_radius=10)
            pygame.draw.rect(screen, (255, 124, 116), rect, border_radius=10)
            pygame.draw.rect(screen, (255, 230, 225), rect, 2, border_radius=10)
            eye_color = (255, 244, 240)
            pole_colors = ((210, 172, 108), (238, 220, 170))
        pygame.draw.circle(screen, eye_color, (rect.left + 10, rect.top + 10), 2)
        pygame.draw.circle(screen, eye_color, (rect.right - 10, rect.top + 10), 2)
        pygame.draw.line(screen, pole_colors[0], (rect.left - 10, rect.top + 2), (rect.right + 8, rect.bottom - 4), 3)
        pygame.draw.line(screen, pole_colors[1], (rect.left - 10, rect.top + 2), (rect.right + 8, rect.bottom - 4), 1)

    def _draw_buckethead_enemy(self, screen: pygame.Surface, rect: pygame.Rect, *, frozen: bool = False) -> None:
        if frozen:
            shadow = rect.move(5, 5)
            pygame.draw.rect(screen, (28, 58, 96), shadow, border_radius=8)
            pygame.draw.rect(screen, (88, 156, 214), rect, border_radius=8)
            pygame.draw.rect(screen, (196, 228, 255), rect, 3, border_radius=8)
            bucket_fill = (132, 196, 246)
            bucket_edge = (220, 240, 255)
            eye_color = (236, 248, 255)
            plate_fill = (52, 98, 148)
            seam_color = (176, 220, 255)
            bucket_line = (96, 148, 198)
        else:
            shadow = rect.move(5, 5)
            pygame.draw.rect(screen, (72, 20, 18), shadow, border_radius=8)
            pygame.draw.rect(screen, (154, 56, 52), rect, border_radius=8)
            pygame.draw.rect(screen, (214, 166, 160), rect, 3, border_radius=8)
            bucket_fill = (196, 198, 206)
            bucket_edge = (244, 246, 252)
            eye_color = (255, 240, 240)
            plate_fill = (128, 42, 38)
            seam_color = (214, 166, 160)
            bucket_line = (122, 132, 140)
        plate = rect.inflate(-12, -10)
        pygame.draw.rect(screen, plate_fill, plate, border_radius=6)
        pygame.draw.line(screen, seam_color, (rect.left + 8, rect.top + 12), (rect.right - 8, rect.top + 12), 2)
        pygame.draw.circle(screen, eye_color, (rect.left + 14, rect.top + 18), 3)
        pygame.draw.circle(screen, eye_color, (rect.right - 14, rect.top + 18), 3)
        bucket = pygame.Rect(rect.centerx - 13, rect.top - 8, 26, 14)
        pygame.draw.rect(screen, bucket_fill, bucket, border_radius=4)
        pygame.draw.rect(screen, bucket_edge, bucket, 2, border_radius=4)
        pygame.draw.line(screen, bucket_line, (bucket.left + 5, bucket.top + 4), (bucket.right - 5, bucket.top + 4), 2)

    def _draw_fast_enemy(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_pole_vaulting_enemy(screen, rect)

    def _draw_tank_enemy(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        self._draw_buckethead_enemy(screen, rect)

    def _draw_sun_drops(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        for item in state.get("sun_drops") or []:
            if not isinstance(item, dict):
                continue
            x = int(item.get("x", 0))
            y = int(item.get("y", 0))
            glow = pygame.Surface((44, 44), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 220, 90, 70), (22, 22), 20)
            screen.blit(glow, (x - 22, y - 22))
            pygame.draw.circle(screen, (248, 214, 82), (x, y), 13)
            pygame.draw.circle(screen, (255, 245, 184), (x, y), 13, 2)
            amount = str(item.get("amount", ""))
            if amount:
                text = self.small_font.render(amount, True, (110, 72, 12))
                screen.blit(text, text.get_rect(center=(x, y)))

    def _draw_projectiles(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        radius = max(4, int(self.config.projectile_radius_px))
        for item in state.get("projectiles") or []:
            if not isinstance(item, dict):
                continue
            x = int(item.get("x", 0))
            y = int(item.get("y", 0))
            pea_type = str(item.get("pea_type", "normal"))
            is_ice = bool(item.get("is_ice")) or pea_type == "ice"
            if is_ice:
                outer_color = (72, 150, 240)
                inner_color = (196, 232, 255)
            else:
                outer_color = (140, 220, 100)
                inner_color = (215, 248, 188)
            pygame.draw.circle(screen, outer_color, (x, y), radius)
            pygame.draw.circle(screen, inner_color, (x, y), max(2, radius // 2))

    def _draw_hud(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        panel_rect = pygame.Rect(18, 12, self.config.window_width - 36, 80)
        pygame.draw.rect(screen, self.config.hud_panel_color, panel_rect, border_radius=14)
        pygame.draw.rect(screen, self.config.hud_accent_color, panel_rect, width=1, border_radius=14)

        title = self.title_font.render("PVZ Roguelike Defense", True, self.config.text_color)
        screen.blit(title, (30, 18))

        wave_id = int(state.get("wave_id", 0))
        total_waves = int(state.get("total_waves", 0))
        base_hp = int(state.get("base_hp", 0))
        base_max_hp = int(state.get("base_max_hp", 0))
        resources = int(state.get("resources", 0))
        sky_sun_timer = float(state.get("sky_sun_timer", 0.0))
        opening_grace_remaining = float(state.get("opening_grace_remaining", 0.0))
        active_upgrades = self._active_upgrades(state)
        mode_label = str(state.get("mode_label", "MANUAL"))
        wave_modifier = state.get("wave_modifier", state.get("current_wave_modifier", {}))

        line_one = f"Sun {resources}   Base {base_hp}/{base_max_hp}   Wave {wave_id}/{total_waves}   Upgrades {len(active_upgrades)}"
        screen.blit(self.body_font.render(line_one, True, self.config.text_color), (30, 45))

        state_label = self._wave_state_label(str(state.get("wave_state", "waiting")))
        sky_sun_text = "Sky Sun --" if sky_sun_timer <= 0.0 else f"Sky Sun {sky_sun_timer:.1f}s"
        prep_text = f"   Prep {opening_grace_remaining:.1f}s" if opening_grace_remaining > 0.0 else ""
        wave_info = state.get("wave", {})
        wave_threshold = float(wave_info.get("wave_damage_threshold", 0.0) or 0.0)
        wave_damage = float(wave_info.get("wave_damage_dealt", 0.0) or 0.0)
        wave_hp_text = ""
        if wave_threshold > 0.0:
            wave_hp_percent = int(round(float(wave_info.get("wave_hp_threshold_percent", 0.0) or 0.0)))
            progress = min(100, int(round(wave_damage / wave_threshold * 100.0)))
            wave_hp_text = f"   Wave DMG {progress}%/{wave_hp_percent}%"
        advance_countdown = float(wave_info.get("wave_advance_countdown", 0.0) or 0.0)
        advance_text = f"   Next wave {advance_countdown:.1f}s" if advance_countdown > 0.0 else ""
        line_two = (
            f"State: {state_label}{wave_hp_text}{advance_text}   {sky_sun_text}{prep_text}"
        )
        screen.blit(self.small_font.render(line_two, True, self.config.muted_text_color), (30, 68))

        self._draw_selected_plant_panel(screen, state, panel_rect, mode_label)

    def _draw_selected_plant_panel(
        self,
        screen: pygame.Surface,
        state: dict[str, object],
        panel_rect: pygame.Rect,
        mode_label: str,
    ) -> None:
        selected_rect = pygame.Rect(panel_rect.right - 252, panel_rect.top + 11, 228, 58)
        selected_tool = str(state.get("selected_tool", "plant"))
        ready = bool(state.get("selected_tool_ready", state.get("selected_plant_ready", False)))
        panel_border = (255, 148, 92) if selected_tool == "shovel" else self.config.grid_border_color
        pygame.draw.rect(screen, (22, 30, 44), selected_rect, border_radius=12)
        pygame.draw.rect(screen, panel_border, selected_rect, width=2 if selected_tool == "shovel" else 1, border_radius=12)

        icon_rect = pygame.Rect(selected_rect.right - 54, selected_rect.y + 10, 40, 40)
        if selected_tool == "shovel":
            self._draw_shovel_icon(screen, icon_rect)
        else:
            self._draw_tool_plant_icon(screen, icon_rect, str(state.get("selected_plant", "pea_shooter")))

        line_one = self.small_font.render(f"Mode {mode_label}", True, self.config.hud_accent_color)
        if selected_tool == "shovel":
            hotkey = str(state.get("shovel_hotkey", "S"))
            shovel_cooldown = float(state.get("shovel_cooldown", 0.0))
            line_two = self.small_font.render(f"Shovel [{hotkey}]", True, self.config.text_color)
            cooldown_text = "Ready" if shovel_cooldown <= 0.0 else f"{shovel_cooldown:.1f}s"
            line_three = self.small_font.render(f"Remove plants | CD {cooldown_text}", True, self.config.muted_text_color)
        else:
            plant_name = str(state.get("selected_plant_name", "Pea Shooter"))
            hotkey = str(state.get("selected_plant_hotkey", "Q"))
            cost = int(state.get("selected_plant_cost", 0))
            cooldown = float(state.get("selected_plant_cooldown", 0.0))
            line_two = self.small_font.render(f"Plant {plant_name} [{hotkey}]", True, self.config.text_color)
            cooldown_text = "Ready" if cooldown <= 0.0 else f"{cooldown:.1f}s"
            line_three = self.small_font.render(f"Cost {cost} | CD {cooldown_text}", True, self.config.muted_text_color)

        status = str(state.get("selected_tool_status", state.get("selected_plant_status", "Ready")))
        status_color = self.config.success_color if ready else self.config.warning_color
        status_surface = self.small_font.render(status, True, status_color)

        screen.blit(line_one, (selected_rect.x + 12, selected_rect.y + 8))
        screen.blit(line_two, (selected_rect.x + 12, selected_rect.y + 24))
        screen.blit(line_three, (selected_rect.x + 12, selected_rect.y + 40))
        status_rect = status_surface.get_rect(topright=(icon_rect.left - 8, selected_rect.y + 8))
        screen.blit(status_surface, status_rect)

    def _draw_shovel_icon(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        pygame.draw.rect(screen, (42, 48, 58), rect, border_radius=10)
        handle_top = (rect.centerx - 4, rect.bottom - 8)
        handle_bottom = (rect.centerx + 2, rect.top + 10)
        blade_top = (rect.centerx + 10, rect.top + 8)
        blade_bottom = (rect.right - 8, rect.top + 22)
        pygame.draw.line(screen, (126, 84, 48), handle_top, handle_bottom, 5)
        pygame.draw.polygon(
            screen,
            (168, 176, 188),
            [(blade_top[0], blade_top[1]), (rect.right - 6, rect.top + 16), blade_bottom, (rect.centerx + 2, rect.top + 20)],
        )
        pygame.draw.polygon(
            screen,
            (210, 218, 228),
            [(blade_top[0], blade_top[1]), (rect.right - 10, rect.top + 14), (rect.centerx + 8, rect.top + 18)],
        )

    def _draw_tool_plant_icon(self, screen: pygame.Surface, rect: pygame.Rect, plant_type: str) -> None:
        inner = rect.inflate(-8, -8)
        if plant_type == "sunflower":
            self._draw_sunflower(screen, inner)
        elif plant_type == "wallnut":
            self._draw_wallnut(screen, inner, rotation=0.0)
        else:
            self._draw_pea_shooter(screen, inner)

    def _draw_footer(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        footer_rect = pygame.Rect(18, 516, self.config.window_width - 36, 66)
        pygame.draw.rect(screen, (11, 15, 22), footer_rect, border_radius=12)
        pygame.draw.rect(screen, self.config.grid_border_color, footer_rect, width=1, border_radius=12)

        message = str(state.get("message", ""))
        if message:
            message_color = self._message_color(str(state.get("message_kind", "info")))
            screen.blit(self.body_font.render(message, True, message_color), (32, 526))
        else:
            screen.blit(
                self.body_font.render(
                    "Q/W/E plants | S shovel (click or drag) | Sun auto-collects in 2s",
                    True,
                    self.config.muted_text_color,
                ),
                (32, 526),
            )

        modifiers = self._as_dict(state.get("modifiers", {}))
        modifier_line = (
            f"DMG x{modifiers.get('plant_damage_multiplier', 1.0)}   "
            f"Sun x{modifiers.get('sun_produce_multiplier', 1.0)}   "
            f"Cost x{modifiers.get('plant_cost_multiplier', 1.0)}   "
            f"ATK CD x{modifiers.get('attack_interval_multiplier', modifiers.get('cooldown_multiplier', 1.0))}   "
            f"Card CD x{modifiers.get('card_cooldown_multiplier', 1.0)}   "
            f"Kill Sun +{modifiers.get('kill_sun_bonus', 0)}"
        )
        screen.blit(self.small_font.render(modifier_line, True, self.config.muted_text_color), (32, 554))

        hover_text = self._hovered_effect_text(state)
        if hover_text:
            hover_surface = self.small_font.render(hover_text, True, self.config.text_color)
            hover_rect = hover_surface.get_rect(midright=(self.config.window_width - 24, 554))
            screen.blit(hover_surface, hover_rect)

    def _draw_upgrade_overlay(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        pending = self._pending_upgrades(state)
        if not pending:
            return

        overlay = pygame.Surface((self.config.window_width, self.config.window_height), pygame.SRCALPHA)
        overlay.fill((4, 6, 12, 164))
        screen.blit(overlay, (0, 0))

        modal_rect = pygame.Rect(58, 108, self.config.window_width - 116, 354)
        pygame.draw.rect(screen, (18, 24, 36), modal_rect, border_radius=20)
        pygame.draw.rect(screen, self.config.hud_accent_color, modal_rect, width=2, border_radius=20)

        wave_id = int(state.get("wave_id", 0))
        header = self.title_font.render(f"Wave {wave_id} cleared - choose one upgrade", True, self.config.text_color)
        header_rect = header.get_rect(center=(self.config.window_width // 2, modal_rect.top + 38))
        screen.blit(header, header_rect)
        sub = self.small_font.render("Press 1 / 2 / 3 or click a card", True, self.config.muted_text_color)
        sub_rect = sub.get_rect(center=(self.config.window_width // 2, modal_rect.top + 64))
        screen.blit(sub, sub_rect)

        for rect, item in zip(self.upgrade_card_rects(len(pending)), pending):
            recommended = bool(item.get("recommended"))
            card_fill = (36, 44, 62)
            card_border = self.config.warning_color if recommended else self.config.grid_border_color
            pygame.draw.rect(screen, card_fill, rect, border_radius=14)
            pygame.draw.rect(screen, card_border, rect, width=3 if recommended else 2, border_radius=14)

            screen.blit(self.body_font.render(str(item.get("name", "Upgrade")), True, self.config.text_color), (rect.x + 14, rect.y + 14))
            type_label = str(item.get("type", item.get("kind", "unknown"))).replace("_", " ").title()
            screen.blit(self.small_font.render(f"Type: {type_label}", True, self.config.hud_accent_color), (rect.x + 14, rect.y + 44))

            desc_lines = self._wrap_text(str(item.get("desc", item.get("description", ""))), self.small_font, rect.width - 28)
            for index, line in enumerate(desc_lines[:5]):
                screen.blit(self.small_font.render(line, True, self.config.muted_text_color), (rect.x + 14, rect.y + 72 + index * 18))

            stack_text = f"Next stack: {item.get('stack_if_taken', 1)}"
            screen.blit(self.small_font.render(stack_text, True, self.config.text_color), (rect.x + 14, rect.bottom - 46))

            prompt = f"Press {int(item.get('index', 0)) + 1} to take"
            if recommended:
                prompt += " | Recommended"
            prompt_surface = self.small_font.render(prompt, True, card_border)
            screen.blit(prompt_surface, (rect.x + 14, rect.bottom - 24))

        active_panel = pygame.Rect(82, 468, self.config.window_width - 164, 70)
        pygame.draw.rect(screen, (16, 21, 31), active_panel, border_radius=16)
        pygame.draw.rect(screen, self.config.grid_border_color, active_panel, width=1, border_radius=16)
        screen.blit(self.body_font.render("Active upgrades", True, self.config.text_color), (active_panel.x + 16, active_panel.y + 12))
        active_names = [str(item.get("name", item.get("id", "Upgrade"))) for item in self._active_upgrades(state)]
        active_text = " | ".join(active_names) if active_names else "None yet"
        active_lines = self._wrap_text(active_text, self.small_font, active_panel.width - 32)
        for index, line in enumerate(active_lines[:2]):
            screen.blit(self.small_font.render(line, True, self.config.muted_text_color), (active_panel.x + 16, active_panel.y + 40 + index * 16))

    def _draw_overlay(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        overlay = pygame.Surface((self.config.window_width, self.config.window_height), pygame.SRCALPHA)
        overlay.fill(self.config.overlay_color)
        screen.blit(overlay, (0, 0))

        title_text = "Victory" if state.get("victory") else "Defeat"
        title_color = self.config.success_color if state.get("victory") else self.config.error_color
        title = self.huge_font.render(title_text, True, title_color)
        title_rect = title.get_rect(center=(self.config.window_width // 2, 240))
        screen.blit(title, title_rect)

        subtitle_text = (
            f"Cleared {state.get('wave', {}).get('total_waves', 0)} waves"
            if state.get("victory")
            else "The base could not hold"
        )
        subtitle = self.title_font.render(subtitle_text, True, self.config.text_color)
        subtitle_rect = subtitle.get_rect(center=(self.config.window_width // 2, 300))
        screen.blit(subtitle, subtitle_rect)

        tip = self.body_font.render("Press R to restart or ESC to quit", True, self.config.text_color)
        tip_rect = tip.get_rect(center=(self.config.window_width // 2, 350))
        screen.blit(tip, tip_rect)

    def _draw_bar(
        self,
        screen: pygame.Surface,
        x: int,
        y: int,
        width: int,
        height: int,
        ratio: float,
        fill_color: tuple[int, int, int],
        *,
        back_color: tuple[int, int, int] = (52, 58, 72),
    ) -> None:
        ratio = max(0.0, min(1.0, ratio))
        pygame.draw.rect(screen, back_color, (x, y, width, height), border_radius=3)
        fill_width = max(0, int(width * ratio))
        if fill_width > 0:
            pygame.draw.rect(screen, fill_color, (x, y, fill_width, height), border_radius=3)

    def _message_color(self, kind: str) -> tuple[int, int, int]:
        if kind == "success":
            return self.config.success_color
        if kind == "error":
            return self.config.error_color
        if kind == "warning":
            return self.config.warning_color
        return self.config.info_color

    def _wrap_text(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        words = text.split()
        if len(words) <= 1 and font.size(text)[0] > max_width:
            return self._wrap_text_chars(text, font, max_width)
        if not words:
            return [text]

        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _wrap_text_chars(self, text: str, font: pygame.font.Font, max_width: int) -> list[str]:
        if not text:
            return [text]
        lines: list[str] = []
        current = ""
        for char in text:
            candidate = f"{current}{char}"
            if current and font.size(candidate)[0] > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def _wave_state_label(self, wave_state: str) -> str:
        labels = {
            "waiting": "Waiting",
            "active": "Active",
            "waiting_clear": "Clear Field",
            "upgrade": "Upgrade",
            "finished": "Finished",
        }
        return labels.get(wave_state, wave_state.title())

    def _pending_upgrades(self, state: dict[str, object]) -> list[dict[str, object]]:
        pending = state.get("pending_upgrade_options")
        if isinstance(pending, list) and pending:
            return pending
        upgrades = self._as_dict(state.get("upgrades", {}))
        if upgrades:
            fallback = upgrades.get("pending", [])
            if isinstance(fallback, list):
                return fallback
        return []

    def _active_upgrades(self, state: dict[str, object]) -> list[dict[str, object]]:
        active = state.get("active_upgrades")
        if isinstance(active, list):
            return active
        upgrades = self._as_dict(state.get("upgrades", {}))
        if upgrades:
            fallback = upgrades.get("applied", [])
            if isinstance(fallback, list):
                return fallback
        return []

    def _map_effect_cells(self, state: dict[str, object]) -> dict[tuple[int, int], dict[str, object]]:
        payload: dict[tuple[int, int], dict[str, object]] = {}
        top_level = state.get("map_effects")
        if isinstance(top_level, list):
            for item in top_level:
                if isinstance(item, dict):
                    payload[(int(item["row"]), int(item["col"]))] = dict(item["effect"])
        if payload:
            return payload

        map_state = self._as_dict(state.get("map", {}))
        if map_state:
            for item in map_state.get("effects", map_state.get("bonus_cells", [])):
                if isinstance(item, dict):
                    payload[(int(item["row"]), int(item["col"]))] = dict(item["effect"])
        return payload

    def _hovered_effect_text(self, state: dict[str, object]) -> str:
        map_state = self._as_dict(state.get("map", {}))
        if not map_state:
            return ""

        mouse_x, mouse_y = pygame.mouse.get_pos()
        origin_x = int(map_state.get("origin_x", self.config.grid_origin_x))
        origin_y = int(map_state.get("origin_y", self.config.grid_origin_y))
        cell_size = int(map_state.get("cell_size", self.config.cell_size))
        rows = int(map_state.get("rows", self.config.grid_rows))
        cols = int(map_state.get("cols", self.config.grid_cols))
        rel_x = mouse_x - origin_x
        rel_y = mouse_y - origin_y
        if rel_x < 0 or rel_y < 0:
            return ""

        col = rel_x // cell_size
        row = rel_y // cell_size
        if row >= rows or col >= cols:
            return ""

        effect = self._map_effect_cells(state).get((int(row), int(col)))
        if effect is None:
            return f"Hover R{int(row) + 1}C{int(col) + 1}: Normal Ground"
        return f"Hover R{int(row) + 1}C{int(col) + 1}: {effect.get('name', 'Effect')}"

    def _wave_modifier_name(self, modifier_state: object) -> str:
        if isinstance(modifier_state, dict):
            return str(modifier_state.get("name", "None"))
        return "None"

    def _wave_modifier_effect(self, modifier_state: object) -> str:
        if not isinstance(modifier_state, dict):
            return "-"
        modifier_id = str(modifier_state.get("id", ""))
        if modifier_id == "fast_attack":
            return "Enemy speed +20%"
        if modifier_id == "thick_armor":
            return "Enemy HP +30%"
        if modifier_id == "number_pressure":
            return "Enemy count +30%"
        if modifier_id == "single_lane":
            target_row = modifier_state.get("target_row")
            if target_row is None:
                return "Single lane pressure"
            return f"Single lane R{int(target_row) + 1}"
        return str(modifier_state.get("description", "-"))
