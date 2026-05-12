from __future__ import annotations

import pygame

from config import GameConfig
from font_loader import load_ui_font


class GameRenderer:
    def __init__(self, config: GameConfig) -> None:
        self.config = config
        self.title_font = self._make_font(28)
        self.body_font = self._make_font(22)
        self.small_font = self._make_font(18)
        self.huge_font = self._make_font(44)

    def _make_font(self, size: int) -> pygame.font.Font:
        return load_ui_font(size)

    def draw(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        screen.fill(self.config.background_color)
        self._draw_board(screen)
        self._draw_towers(screen, state)
        self._draw_enemies(screen, state)
        self._draw_hud(screen, state)
        self._draw_footer(screen, state)
        if state.get("done"):
            self._draw_overlay(screen, state)

    def _draw_board(self, screen: pygame.Surface) -> None:
        board_rect = pygame.Rect(
            self.config.grid_origin_x,
            self.config.grid_origin_y,
            self.config.grid_width,
            self.config.grid_height,
        )
        pygame.draw.rect(screen, self.config.grid_bg_color, board_rect, border_radius=10)

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
                pygame.draw.rect(screen, self.config.grid_line_color, rect, width=1)

        pygame.draw.rect(screen, self.config.grid_border_color, board_rect, width=2, border_radius=10)

    def _draw_towers(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        for tower in state.get("towers", []):
            row = int(tower["row"])
            col = int(tower["col"])
            rect = pygame.Rect(
                self.config.grid_origin_x + col * self.config.cell_size + 12,
                self.config.grid_origin_y + row * self.config.cell_size + 12,
                self.config.cell_size - 24,
                self.config.cell_size - 24,
            )

            shadow = rect.copy()
            shadow.move_ip(4, 5)
            pygame.draw.ellipse(screen, self.config.tower_shadow_color, shadow)
            pygame.draw.ellipse(screen, self.config.tower_fill_color, rect)
            pygame.draw.ellipse(screen, self.config.tower_border_color, rect, width=2)

            barrel_rect = pygame.Rect(0, 0, rect.width * 0.25, rect.height * 0.65)
            barrel_rect.center = rect.center
            pygame.draw.rect(screen, (220, 245, 228), barrel_rect, border_radius=6)

    def _draw_enemies(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        for enemy in state.get("enemies", []):
            x = int(enemy["x"])
            y = int(enemy["y"])
            width = int(enemy.get("width", self.config.enemy_width))
            height = int(enemy.get("height", self.config.enemy_height))
            rect = pygame.Rect(x, y, width, height)

            shadow = rect.copy()
            shadow.move_ip(4, 4)
            pygame.draw.rect(screen, self.config.enemy_shadow_color, shadow, border_radius=8)
            pygame.draw.rect(screen, self.config.enemy_fill_color, rect, border_radius=8)
            pygame.draw.rect(screen, self.config.enemy_border_color, rect, width=2, border_radius=8)

            hp = int(enemy["hp"])
            max_hp = max(1, int(enemy.get("max_hp", 1)))
            bar_width = rect.width
            bar_height = 6
            bar_x = rect.left
            bar_y = rect.top - 10
            pygame.draw.rect(screen, (52, 58, 72), (bar_x, bar_y, bar_width, bar_height), border_radius=3)
            fill_width = int(bar_width * max(0.0, min(1.0, hp / max_hp)))
            pygame.draw.rect(screen, (93, 220, 120), (bar_x, bar_y, fill_width, bar_height), border_radius=3)

    def _draw_hud(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        panel_rect = pygame.Rect(18, 12, self.config.window_width - 36, 74)
        pygame.draw.rect(screen, self.config.hud_panel_color, panel_rect, border_radius=12)
        pygame.draw.rect(screen, self.config.hud_accent_color, panel_rect, width=1, border_radius=12)

        title = self.title_font.render("简化塔防原型", True, self.config.text_color)
        screen.blit(title, (32, 22))

        stats = (
            f"资源 {state.get('resources', 0)}   "
            f"基地血量 {state.get('base_hp', 0)}   "
            f"得分 {state.get('score', 0)}   "
            f"时间 {state.get('time', 0):.1f}s   "
            f"敌人 {state.get('enemy_count', 0)}   "
            f"防御塔 {state.get('tower_count', 0)}"
        )
        stats_surface = self.body_font.render(stats, True, self.config.text_color)
        screen.blit(stats_surface, (32, 52))

        hint = "左键放塔(50) | R 重开 | ESC 退出"
        hint_surface = self.small_font.render(hint, True, self.config.muted_text_color)
        hint_rect = hint_surface.get_rect(topright=(self.config.window_width - 32, 28))
        screen.blit(hint_surface, hint_rect)

    def _draw_footer(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        footer_rect = pygame.Rect(18, 516, self.config.window_width - 36, 66)
        pygame.draw.rect(screen, (11, 15, 22), footer_rect, border_radius=12)
        pygame.draw.rect(screen, self.config.grid_border_color, footer_rect, width=1, border_radius=12)

        message = str(state.get("message", ""))
        if message:
            color = self._message_color(str(state.get("message_kind", "info")))
            message_surface = self.body_font.render(message, True, color)
            screen.blit(message_surface, (32, 532))
        else:
            message_surface = self.body_font.render("提示：把塔放在敌人将经过的同一行，才能拦截更有效。", True, self.config.muted_text_color)
            screen.blit(message_surface, (32, 532))

        sub = f"下一只敌人 {state.get('next_spawn_in', 0):.1f}s 后出现   逻辑奖励 {state.get('last_reward', 0):.2f}"
        sub_surface = self.small_font.render(sub, True, self.config.muted_text_color)
        screen.blit(sub_surface, (32, 560))

    def _draw_overlay(self, screen: pygame.Surface, state: dict[str, object]) -> None:
        overlay = pygame.Surface((self.config.window_width, self.config.window_height), pygame.SRCALPHA)
        overlay.fill(self.config.overlay_color)
        screen.blit(overlay, (0, 0))

        text = "胜利" if state.get("victory") else "失败"
        color = self.config.success_color if state.get("victory") else self.config.error_color
        title = self.huge_font.render(text, True, color)
        title_rect = title.get_rect(center=(self.config.window_width // 2, 240))
        screen.blit(title, title_rect)

        subtitle_text = "已成功坚持 180 秒" if state.get("victory") else "基地血量已归零"
        subtitle = self.title_font.render(subtitle_text, True, self.config.text_color)
        subtitle_rect = subtitle.get_rect(center=(self.config.window_width // 2, 300))
        screen.blit(subtitle, subtitle_rect)

        tip = self.body_font.render("按 R 重新开始，按 ESC 退出", True, self.config.text_color)
        tip_rect = tip.get_rect(center=(self.config.window_width // 2, 350))
        screen.blit(tip, tip_rect)

    def _message_color(self, kind: str) -> tuple[int, int, int]:
        if kind == "success":
            return self.config.success_color
        if kind == "error":
            return self.config.error_color
        if kind == "warning":
            return self.config.warning_color
        return self.config.info_color

