from __future__ import annotations

import random

import pygame

from agents import ModelAgent, RuleBasedAgent
from config import CONFIG, build_campaign_v5_config
from database import GameDatabase
from env import TowerDefenseEnv, action_dict_to_id
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

PLANT_KEY_BINDINGS = {
    pygame.K_q: "pea_shooter",
    pygame.K_w: "sunflower",
    pygame.K_e: "wallnut",
}

PLANT_KEY_LABELS = {
    "pea_shooter": "Q",
    "sunflower": "W",
    "wallnut": "E",
}

PLANT_LABELS = {
    "pea_shooter": "Pea Shooter",
    "sunflower": "Sunflower",
    "wallnut": "Wall-nut",
}

TOOL_PLANT = "plant"
TOOL_SHOVEL = "shovel"
SHOVEL_HOTKEY = "S"
PAUSE_HOTKEY = "P"


def draw_mode_badge(screen: pygame.Surface, font: pygame.font.Font, mode: int) -> None:
    label = f"MODE: {MODE_LABELS.get(mode, 'UNKNOWN')}"
    text = font.render(label, True, CONFIG.text_color)
    padding_x = 14
    padding_y = 8
    box = text.get_rect(topleft=(24, 94))
    bg = box.inflate(padding_x * 2, padding_y * 2)
    pygame.draw.rect(screen, (22, 28, 40), bg, border_radius=10)
    pygame.draw.rect(screen, CONFIG.hud_accent_color, bg, width=1, border_radius=10)
    screen.blit(text, box)


def draw_pause_overlay(screen: pygame.Surface, font: pygame.font.Font) -> None:
    title = font.render("PAUSED", True, CONFIG.warning_color)
    hint = font.render(f"Press {PAUSE_HOTKEY} to resume", True, CONFIG.text_color)
    padding_x = 24
    padding_y = 16
    title_box = title.get_rect()
    hint_box = hint.get_rect()
    panel_width = max(title_box.width, hint_box.width) + padding_x * 2
    panel_height = title_box.height + hint_box.height + padding_y * 2 + 8
    panel = pygame.Rect(0, 0, panel_width, panel_height)
    panel.center = (CONFIG.window_width // 2, CONFIG.window_height // 2)
    pygame.draw.rect(screen, (22, 28, 40), panel, border_radius=12)
    pygame.draw.rect(screen, CONFIG.warning_color, panel, width=2, border_radius=12)
    title_rect = title.get_rect(centerx=panel.centerx, top=panel.top + padding_y)
    hint_rect = hint.get_rect(centerx=panel.centerx, top=title_rect.bottom + 8)
    screen.blit(title, title_rect)
    screen.blit(hint, hint_rect)


def episode_result(env: TowerDefenseEnv) -> str:
    if env.victory:
        return "victory"
    if env.base_hp <= 0:
        return "defeat"
    return "aborted"


def start_session(
    db: GameDatabase | None,
    mode: int,
    *,
    logging_enabled: bool,
) -> tuple[int | None, GameLogger | None]:
    if not logging_enabled or db is None:
        return None, None
    mode_name = MODE_LOG_NAMES.get(mode, "unknown")
    session_id = db.create_session(mode_name)
    return session_id, GameLogger(mode=mode_name, session_id=session_id)


def finalize_session(
    db: GameDatabase,
    logger: GameLogger | None,
    session_id: int | None,
    env: TowerDefenseEnv,
    *,
    seed: int | None = None,
) -> None:
    if logger is None or session_id is None:
        return

    result = episode_result(env)
    score = env.score
    survived_time = env.game_time
    rows = logger.to_rows()
    session_summary = logger.build_session_summary(
        result=result,
        state=env.get_render_state(),
        seed=seed,
    )
    logger.set_session_summary(session_summary)
    logger.save_csv()
    logger.save_json()
    db.record_session(session_id, result, score, survived_time, rows, session_summary=session_summary)


def generate_run_seed() -> int:
    return random.SystemRandom().randrange(1, 2**31)


def plant_label(plant_type: str) -> str:
    return PLANT_LABELS.get(plant_type, plant_type.replace("_", " ").title())


def push_shovel_message(env: TowerDefenseEnv) -> None:
    cooldown_left = max(0.0, float(env.shovel_cooldown_left))
    if cooldown_left > 0.0:
        status = f"Cooldown {cooldown_left:.1f}s"
        kind = "warning"
    elif not env.can_use_shovel():
        status = "Unavailable"
        kind = "warning"
    else:
        status = "Click or drag on plants"
        kind = "info"

    env.message = f"Shovel [{SHOVEL_HOTKEY}] | {status}"
    env.message_kind = kind
    env.message_timer = 2.2


def push_selected_plant_message(env: TowerDefenseEnv, plant_type: str) -> None:
    cost = env.current_tower_cost(plant_type)
    cooldown_left = max(0.0, float(env.card_cooldowns.get(plant_type, 0.0)))
    has_enough_sun = env.resources >= cost
    if cooldown_left > 0.0:
        status = f"Cooldown {cooldown_left:.1f}s"
        kind = "warning"
    elif not has_enough_sun:
        status = f"Need {cost} sun"
        kind = "warning"
    else:
        status = "Ready"
        kind = "info"

    env.message = f"Selected {plant_label(plant_type)} [{PLANT_KEY_LABELS[plant_type]}] | Cost {cost} | {status}"
    env.message_kind = kind
    env.message_timer = 2.2


def reset_run_state(
    env: TowerDefenseEnv,
    mode: int,
    seed: int,
    selected_plant: str,
    *,
    selected_tool: str = TOOL_PLANT,
) -> None:
    env.reset(seed=seed)
    env.manual_upgrade_selection = mode == MODE_MANUAL
    if selected_tool == TOOL_SHOVEL:
        push_shovel_message(env)
    else:
        push_selected_plant_message(env, selected_plant)


def apply_shovel_at(
    env: TowerDefenseEnv,
    pos: tuple[int, int],
    visited_cells: set[tuple[int, int]],
) -> bool:
    cell = env.point_to_cell(pos)
    if cell is None or cell in visited_cells:
        return False
    if env.remove_tower_at(cell[0], cell[1]):
        visited_cells.add(cell)
        return True
    return False


def build_render_state(
    env: TowerDefenseEnv,
    mode: int,
    selected_plant: str,
    *,
    selected_tool: str = TOOL_PLANT,
    mouse_pos: tuple[int, int] | None = None,
    shovel_drag_cells: list[tuple[int, int]] | None = None,
    valid_actions_count: int | None = None,
) -> dict[str, object]:
    render_state = env.get_render_state()
    plant_costs = render_state.get("plant_costs")
    if not isinstance(plant_costs, dict):
        plant_costs = {}
    card_cooldowns = render_state.get("card_cooldowns")
    if not isinstance(card_cooldowns, dict):
        card_cooldowns = {}
    available_cards = render_state.get("available_cards")
    if not isinstance(available_cards, dict):
        available_cards = {}

    selected_cost = int(plant_costs.get(selected_plant, env.current_tower_cost(selected_plant)))
    selected_cooldown = float(card_cooldowns.get(selected_plant, env.card_cooldowns.get(selected_plant, 0.0)))
    has_enough_sun = int(render_state.get("resources", 0)) >= selected_cost
    selected_ready = bool(available_cards.get(selected_plant, False))
    if selected_cooldown > 0.0:
        selected_status = f"Cooldown {selected_cooldown:.1f}s"
    elif not has_enough_sun:
        selected_status = "Not enough sun"
    else:
        selected_status = "Ready"

    render_state["mode_label"] = MODE_LABELS.get(mode, "UNKNOWN")
    render_state["selected_plant"] = selected_plant
    render_state["selected_plant_name"] = plant_label(selected_plant)
    render_state["selected_plant_hotkey"] = PLANT_KEY_LABELS.get(selected_plant, "")
    render_state["selected_plant_cost"] = selected_cost
    render_state["selected_plant_cooldown"] = round(selected_cooldown, 2)
    render_state["selected_plant_ready"] = selected_ready
    render_state["selected_plant_status"] = selected_status
    render_state["selected_tool"] = selected_tool
    render_state["shovel_hotkey"] = SHOVEL_HOTKEY
    shovel_cooldown = float(render_state.get("shovel_cooldown", env.shovel_cooldown_left))
    render_state["shovel_cooldown"] = round(shovel_cooldown, 2)
    render_state["shovel_ready"] = bool(render_state.get("shovel_ready", shovel_cooldown <= 0.0))
    if selected_tool == TOOL_SHOVEL:
        if shovel_cooldown > 0.0:
            render_state["selected_tool_status"] = f"Cooldown {shovel_cooldown:.1f}s"
            render_state["selected_tool_ready"] = False
        elif not env.can_use_shovel():
            render_state["selected_tool_status"] = "Unavailable"
            render_state["selected_tool_ready"] = False
        else:
            render_state["selected_tool_status"] = "Click or drag"
            render_state["selected_tool_ready"] = True
    else:
        render_state["selected_tool_status"] = selected_status
        render_state["selected_tool_ready"] = selected_ready

    if mouse_pos is not None:
        render_state["mouse_grid_cell"] = env.point_to_cell(mouse_pos)
    else:
        render_state["mouse_grid_cell"] = None
    render_state["shovel_drag_cells"] = list(shovel_drag_cells or [])
    render_state["valid_actions_count"] = valid_actions_count
    return render_state


def main() -> None:
    pygame.init()
    pygame.font.init()
    pygame.display.set_caption("Tower Defense RL Environment")
    game_config = build_campaign_v5_config()

    screen = pygame.display.set_mode((game_config.window_width, game_config.window_height))
    clock = pygame.time.Clock()

    env = TowerDefenseEnv(game_config)
    renderer = GameRenderer(game_config)
    rule_agent = RuleBasedAgent(game_config)
    model_agent = ModelAgent()
    battle_logging_enabled = bool(game_config.enable_battle_logging)
    database = GameDatabase() if battle_logging_enabled else None
    try:
        overlay_font = pygame.font.SysFont("Arial", 20)
        if overlay_font is None:
            raise RuntimeError("SysFont returned None")
    except Exception:
        overlay_font = pygame.font.Font(None, 20)

    current_mode = MODE_MANUAL
    current_seed = generate_run_seed()
    selected_plant = "pea_shooter"
    selected_tool = TOOL_PLANT
    game_paused = False
    env.manual_upgrade_selection = True
    pending_manual_action = 0
    shovel_drag_active = False
    shovel_drag_cells: set[tuple[int, int]] = set()
    reset_run_state(env, current_mode, current_seed, selected_plant, selected_tool=selected_tool)
    session_id, logger = start_session(database, current_mode, logging_enabled=battle_logging_enabled)
    session_finalized = False

    def switch_mode(new_mode: int) -> None:
        nonlocal current_mode, pending_manual_action, session_id, logger, session_finalized, shovel_drag_active, shovel_drag_cells, game_paused

        if new_mode == current_mode:
            return

        if not session_finalized:
            finalize_session(database, logger, session_id, env, seed=current_seed)

        current_mode = new_mode
        game_paused = False
        env.manual_upgrade_selection = current_mode == MODE_MANUAL
        pending_manual_action = 0
        shovel_drag_active = False
        shovel_drag_cells = set()
        session_id, logger = start_session(database, current_mode, logging_enabled=battle_logging_enabled)
        session_finalized = False

    running = True
    while running:
        clock.tick(game_config.fps)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_p, pygame.K_PAUSE):
                    if not env.is_done():
                        game_paused = not game_paused
                        if game_paused:
                            pending_manual_action = 0
                            shovel_drag_active = False
                            shovel_drag_cells = set()
                elif event.key == pygame.K_r:
                    if not session_finalized:
                        finalize_session(database, logger, session_id, env, seed=current_seed)
                    session_id, logger = start_session(database, current_mode, logging_enabled=battle_logging_enabled)
                    session_finalized = False
                    current_seed = generate_run_seed()
                    selected_plant = "pea_shooter"
                    selected_tool = TOOL_PLANT
                    game_paused = False
                    pending_manual_action = 0
                    shovel_drag_active = False
                    shovel_drag_cells = set()
                    reset_run_state(env, current_mode, current_seed, selected_plant, selected_tool=selected_tool)
                elif event.key == pygame.K_s:
                    selected_tool = TOOL_SHOVEL
                    push_shovel_message(env)
                elif event.key in PLANT_KEY_BINDINGS:
                    selected_tool = TOOL_PLANT
                    selected_plant = PLANT_KEY_BINDINGS[event.key]
                    push_selected_plant_message(env, selected_plant)
                elif (
                    not game_paused
                    and env.wave_state == "upgrade"
                    and event.key in (pygame.K_1, pygame.K_2, pygame.K_3)
                ):
                    pending_manual_action = action_dict_to_id(
                        {
                            "action_type": "choose_upgrade",
                            "option_index": event.key - pygame.K_1,
                        }
                    )
                elif event.key == pygame.K_F1:
                    switch_mode(MODE_MANUAL)
                elif event.key == pygame.K_F2:
                    switch_mode(MODE_RULE)
                elif event.key == pygame.K_F3:
                    switch_mode(MODE_MODEL)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if game_paused or current_mode != MODE_MANUAL or env.is_done():
                    continue

                if env.has_pending_upgrade:
                    pending = env.get_render_state().get("upgrades", {}).get("pending", [])
                    for index, rect in enumerate(renderer.upgrade_card_rects(len(pending))):
                        if rect.collidepoint(event.pos):
                            pending_manual_action = action_dict_to_id(
                                {
                                    "action_type": "choose_upgrade",
                                    "option_index": index,
                                }
                            )
                            break
                    continue

                if env.try_collect_sun_drop(event.pos):
                    continue

                if selected_tool == TOOL_SHOVEL:
                    shovel_drag_active = True
                    shovel_drag_cells = set()
                    apply_shovel_at(env, event.pos, shovel_drag_cells)
                    continue

                cell = env.point_to_cell(event.pos)
                if cell is not None:
                    row, col = cell
                    pending_manual_action = action_dict_to_id(
                        {
                            "action_type": "place_tower",
                            "plant_type": selected_plant,
                            "row": row,
                            "col": col,
                        }
                    )
            elif event.type == pygame.MOUSEMOTION:
                if (
                    not game_paused
                    and current_mode == MODE_MANUAL
                    and not env.is_done()
                    and selected_tool == TOOL_SHOVEL
                    and shovel_drag_active
                    and pygame.mouse.get_pressed()[0]
                ):
                    apply_shovel_at(env, event.pos, shovel_drag_cells)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                shovel_drag_active = False
                shovel_drag_cells = set()

        action_id = 0
        reward = 0.0
        done = env.is_done()
        info = {
            "action_id": 0,
            "action_success": False,
            "action_reason": "IDLE",
            "reward_breakdown": {},
        }

        if not env.is_done() and not game_paused:
            env.manual_upgrade_selection = current_mode == MODE_MANUAL
            valid_actions_for_logging = env.valid_actions()

            current_state = env.get_state()
            current_state_dict = env.get_state_dict() if current_mode == MODE_RULE or env.wave_state == "upgrade" else None
            current_valid_actions = valid_actions_for_logging if current_mode == MODE_RULE else None
            if env.wave_state == "upgrade" and current_mode == MODE_RULE:
                action_id = rule_agent.choose_action_from_state_dict(
                    current_state_dict or {},
                    current_valid_actions or [0],
                )
            elif env.wave_state == "upgrade" and current_mode != MODE_MANUAL:
                pending_options = env.get_render_state().get("pending_upgrade_options", [])
                option_index = next(
                    (int(item.get("index", 0)) for item in pending_options if item.get("recommended")),
                    0,
                )
                action_id = action_dict_to_id(
                    {
                        "action_type": "choose_upgrade",
                        "option_index": option_index,
                    }
                )
            elif current_mode == MODE_MANUAL:
                action_id = pending_manual_action
                pending_manual_action = 0
            elif current_mode == MODE_RULE:
                action_id = rule_agent.choose_action_from_state_dict(
                    current_state_dict or {},
                    current_valid_actions or [0],
                )
            elif current_mode == MODE_MODEL:
                action_id = model_agent.choose_action(current_state)

            _, reward, done, info = env.step(action_id)
            render_state = build_render_state(
                env,
                current_mode,
                selected_plant,
                selected_tool=selected_tool,
                mouse_pos=pygame.mouse.get_pos(),
                shovel_drag_cells=list(shovel_drag_cells),
                valid_actions_count=len(valid_actions_for_logging),
            )
            if logger is not None:
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
                finalize_session(database, logger, session_id, env, seed=current_seed)
                session_finalized = True
        else:
            done = True
            info = {
                "action_id": 0,
                "action_success": False,
                "action_reason": "GAME_OVER",
                "reward_breakdown": {},
            }

        display_valid_actions_count = None if env.is_done() else len(env.valid_actions())
        render_state = build_render_state(
            env,
            current_mode,
            selected_plant,
            selected_tool=selected_tool,
            mouse_pos=pygame.mouse.get_pos(),
            shovel_drag_cells=list(shovel_drag_cells),
            valid_actions_count=display_valid_actions_count,
        )
        renderer.draw(screen, render_state)
        draw_mode_badge(screen, overlay_font, current_mode)
        if game_paused and not env.is_done():
            draw_pause_overlay(screen, overlay_font)

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
        finalize_session(database, logger, session_id, env, seed=current_seed)

    if database is not None:
        database.close()
    pygame.quit()


if __name__ == "__main__":
    main()
