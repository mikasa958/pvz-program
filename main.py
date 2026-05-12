from __future__ import annotations

from pathlib import Path

import pygame

from agents import ModelAgent, RuleBasedAgent
from config import CONFIG
from database import GameDatabase
from env import TowerDefenseEnv, action_dict_to_id
from font_loader import load_ui_font
from logger import GameLogger
from renderer import GameRenderer

MODE_MANUAL = 0
MODE_RULE = 1
MODE_MODEL = 2

MODE_LABELS = {
    MODE_MANUAL: "MANUAL",
    MODE_RULE: "RULE AI",
    MODE_MODEL: "MODEL AI",
}

MODE_LOG_NAMES = {
    MODE_MANUAL: "manual",
    MODE_RULE: "rule_ai",
    MODE_MODEL: "model_ai",
}


def draw_mode_badge(screen: pygame.Surface, font: pygame.font.Font, mode: int) -> None:
    label = f"MODE: {MODE_LABELS.get(mode, 'UNKNOWN')}"
    text = font.render(label, True, CONFIG.text_color)
    padding_x = 14
    padding_y = 8
    box = text.get_rect(topleft=(24, 82))
    bg = box.inflate(padding_x * 2, padding_y * 2)
    pygame.draw.rect(screen, (22, 28, 40), bg, border_radius=10)
    pygame.draw.rect(screen, CONFIG.hud_accent_color, bg, width=1, border_radius=10)
    screen.blit(text, box)


def episode_result(env: TowerDefenseEnv) -> str:
    if env.victory:
        return "victory"
    if env.base_hp <= 0:
        return "defeat"
    return "aborted"


def start_session(db: GameDatabase, mode: int) -> tuple[int, GameLogger]:
    mode_name = MODE_LOG_NAMES.get(mode, "unknown")
    session_id = db.create_session(mode_name)
    return session_id, GameLogger(mode=mode_name, session_id=session_id)


def finalize_session(
    db: GameDatabase,
    logger: GameLogger | None,
    session_id: int | None,
    env: TowerDefenseEnv,
) -> None:
    if logger is None or session_id is None:
        return

    result = episode_result(env)
    score = env.score
    survived_time = env.game_time
    rows = logger.to_rows()
    logger.save_csv()
    logger.save_json()
    db.record_session(session_id, result, score, survived_time, rows)


def main() -> None:
    pygame.init()
    pygame.font.init()
    pygame.display.set_caption("Tower Defense RL Environment")

    screen = pygame.display.set_mode((CONFIG.window_width, CONFIG.window_height))
    clock = pygame.time.Clock()

    env = TowerDefenseEnv(CONFIG)
    renderer = GameRenderer(CONFIG)
    rule_agent = RuleBasedAgent(CONFIG)
    model_path = Path(__file__).resolve().parent / "models" / "tower_q_table.pkl"
    model_agent = ModelAgent.from_pickle(model_path)
    database = GameDatabase()
    overlay_font = load_ui_font(20)

    current_mode = MODE_MANUAL
    pending_manual_action = 0
    state = env.reset(seed=CONFIG.random_seed)
    session_id, logger = start_session(database, current_mode)
    session_finalized = False

    def switch_mode(new_mode: int) -> None:
        nonlocal current_mode, pending_manual_action, session_id, logger, session_finalized

        if new_mode == current_mode:
            return

        if not session_finalized:
            finalize_session(database, logger, session_id, env)

        current_mode = new_mode
        pending_manual_action = 0
        session_id, logger = start_session(database, current_mode)
        session_finalized = False

    running = True
    while running:
        clock.tick(CONFIG.fps)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_r:
                    if not session_finalized:
                        finalize_session(database, logger, session_id, env)
                    session_id, logger = start_session(database, current_mode)
                    session_finalized = False
                    state = env.reset(seed=CONFIG.random_seed)
                    pending_manual_action = 0
                elif event.key == pygame.K_1:
                    switch_mode(MODE_MANUAL)
                elif event.key == pygame.K_2:
                    switch_mode(MODE_RULE)
                elif event.key == pygame.K_3:
                    switch_mode(MODE_MODEL)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if current_mode == MODE_MANUAL and not env.is_done():
                    cell = env.point_to_cell(event.pos)
                    if cell is not None:
                        row, col = cell
                        pending_manual_action = action_dict_to_id(
                            {
                                "action_type": "place_tower",
                                "tower_type": "basic",
                                "row": row,
                                "col": col,
                            }
                        )

        action_id = 0
        if not env.is_done():
            current_state = env.get_state()
            if current_mode == MODE_MANUAL:
                action_id = pending_manual_action
                pending_manual_action = 0
            elif current_mode == MODE_RULE:
                action_id = rule_agent.choose_action(current_state, env.valid_actions())
            elif current_mode == MODE_MODEL:
                action_id = model_agent.choose_action(current_state, env.valid_actions())

            state, reward, done, info = env.step(action_id)
            render_state = env.get_render_state()
            logger.log_step(
                tick=render_state["tick"],
                time=render_state["time"],
                resources=render_state["resources"],
                base_hp=render_state["base_hp"],
                action_id=action_id,
                reward=reward,
                done=done,
                valid=bool(info.get("action_success", True)),
                state=render_state,
            )
            if done and not session_finalized:
                finalize_session(database, logger, session_id, env)
                session_finalized = True
        else:
            reward = 0.0
            done = True
            info = {
                "action_id": 0,
                "action_success": False,
                "action_reason": "GAME_OVER",
                "reward_breakdown": {},
            }

        render_state = env.get_render_state()
        renderer.draw(screen, render_state)
        draw_mode_badge(screen, overlay_font, current_mode)

        if done:
            end_text = "Press R to restart or ESC to quit"
            end_surface = overlay_font.render(end_text, True, CONFIG.text_color)
            end_rect = end_surface.get_rect(center=(CONFIG.window_width // 2, 84))
            shadow_rect = end_rect.inflate(20, 12)
            pygame.draw.rect(screen, (22, 28, 40), shadow_rect, border_radius=8)
            pygame.draw.rect(screen, CONFIG.hud_accent_color, shadow_rect, width=1, border_radius=8)
            screen.blit(end_surface, end_rect)

        pygame.display.flip()

    if not session_finalized:
        finalize_session(database, logger, session_id, env)

    database.close()
    pygame.quit()


if __name__ == "__main__":
    main()
