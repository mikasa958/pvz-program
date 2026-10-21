from __future__ import annotations

from collections.abc import Callable
import csv
from dataclasses import replace
import json
import os
import random
import sqlite3
import sys
import tempfile
from pathlib import Path
from statistics import mean


SEED = 7
TRAIN_EPISODES = 1000
EVAL_EPISODES = 200
TAIL_WINDOW = 200
STEP_DT = 1.0


PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PVZLIB_COURSE_DIR = PROJECT_DIR.parent / "auto_PVZ" / "pvz_ai_course"

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from agents import RuleBasedAgent  # noqa: E402
from config import CONFIG, ENEMY_CONFIG, PLANT_CONFIG, _scale_enemy_hp, build_training_easy_config  # noqa: E402
from database import GameDatabase  # noqa: E402
from enemy import Enemy  # noqa: E402
from env import (  # noqa: E402
    ACTION_CHOOSE_UPGRADE_OFFSET,
    ACTION_SPACE_SIZE,
    ACTION_WAIT,
    STATE_VECTOR_SIZE,
    TRAINING_STATE_VECTOR_SIZE,
    TRAINING_STATE_VERSION,
    TowerDefenseEnv,
    action_dict_to_id,
    action_id_to_dict,
)
from logger import GameLogger  # noqa: E402
from map_effects import MapEffectDefinition, MapEffectManager  # noqa: E402
from tower import Tower  # noqa: E402
from training_adapter import FastCompatibilityEnv  # noqa: E402
from upgrades import UpgradeManager, upgrade_definitions_from_config  # noqa: E402
from waves import WaveManager, WaveSpawn  # noqa: E402


def _normalize_pvzlib_course_dir(path_str: str | None) -> Path | None:
    if not path_str:
        return None

    candidate = Path(path_str).expanduser()
    if candidate.name == "pvzlib" and (candidate / "__init__.py").exists():
        return candidate.parent
    if (candidate / "pvzlib").exists():
        return candidate
    return None


def resolve_pvzlib_course_dir() -> Path | None:
    env_candidate = _normalize_pvzlib_course_dir(os.getenv("PVZLIB_COURSE_DIR"))
    if env_candidate is not None:
        return env_candidate

    default_candidate = _normalize_pvzlib_course_dir(str(DEFAULT_PVZLIB_COURSE_DIR))
    if default_candidate is not None:
        return default_candidate

    return None


def load_pvzlib():
    course_dir = resolve_pvzlib_course_dir()
    if course_dir is None:
        return None

    if str(course_dir) not in sys.path:
        sys.path.insert(0, str(course_dir))

    try:
        from pvzlib.agents import QLearningAgent, QLearningConfig
        from pvzlib.train import evaluate_q, tail_mean, train_q_learning
    except Exception:
        return None

    return {
        "QLearningAgent": QLearningAgent,
        "QLearningConfig": QLearningConfig,
        "evaluate_q": evaluate_q,
        "tail_mean": tail_mean,
        "train_q_learning": train_q_learning,
    }


def build_env() -> FastCompatibilityEnv:
    return FastCompatibilityEnv(TowerDefenseEnv(), seed=SEED, step_dt=STEP_DT)


def build_fast_wave_env(*, total_waves: int) -> FastCompatibilityEnv:
    steady_modifier_pool = {"steady": CONFIG.wave_modifier_pool["steady"]}
    custom_config = replace(
        CONFIG,
        auto_select_upgrades=False,
        total_waves=total_waves,
        wave_modifier_pool=steady_modifier_pool,
        wave_base_enemy_count=1,
        wave_enemy_count_step=0,
        tower_range_cells=9,
        tower_cooldown=0.25,
        enemy_hp=5,
        enemy_config=_scale_enemy_hp(CONFIG, 5.0 / float(ENEMY_CONFIG["normal"]["hp"])),
        enemy_speed=20.0,
        enemy_spawn_interval=0.2,
        resource_income_per_second=0,
        game_duration=60.0,
    )
    return FastCompatibilityEnv(TowerDefenseEnv(custom_config), seed=SEED, step_dt=0.5)


def build_training_env(*, seed: int = SEED) -> FastCompatibilityEnv:
    training_config = build_training_easy_config(seed=seed)
    return FastCompatibilityEnv(
        TowerDefenseEnv(training_config),
        seed=seed,
        step_dt=1.0,
        state_mode="training",
    )


def _first_open_cell(env: TowerDefenseEnv) -> tuple[int, int]:
    for row in range(env.config.grid_rows):
        for col in range(env.config.grid_cols):
            if env.is_cell_obstacle(row, col):
                continue
            if env.is_cell_occupied(row, col):
                continue
            return row, col
    raise AssertionError("expected at least one open cell")


def _first_obstacle_cell(env: TowerDefenseEnv) -> tuple[int, int]:
    for (row, col), effect in env.map_effects.items():
        if effect.is_obstacle:
            return int(row), int(col)
    raise AssertionError("expected generated map to include at least one obstacle")


def _pause_world(env: TowerDefenseEnv) -> None:
    env.wave_state = "waiting"
    env.current_wave = None
    env.pending_wave_spawns = []
    env.wave_manager.finish_current_wave()


def _clear_first_wave_to_upgrade(env: FastCompatibilityEnv) -> list[dict[str, object]]:
    render_state = env.get_render_state()
    preview_rows = render_state["wave"]["current"]["preview_rows"]
    target_row = int(preview_rows[0])
    placement_action = 1 + target_row * env.base_env.config.grid_cols
    env.step(placement_action)

    for _ in range(60):
        env.step(0)
        if env.base_env.wave_state == "upgrade":
            break

    assert env.base_env.wave_state == "upgrade", "first wave should be clearable into upgrade state"
    pending_options = env.get_render_state()["pending_upgrade_options"]
    assert len(pending_options) == 3, "wave clear should offer three upgrades"
    return pending_options


def headless_environment_test() -> str:
    assert os.environ.get("SDL_VIDEODRIVER") == "dummy", "SDL_VIDEODRIVER must stay on dummy for headless CI"
    assert os.environ.get("SDL_AUDIODRIVER") == "dummy", "SDL_AUDIODRIVER must stay on dummy for headless CI"
    return "SDL dummy drivers configured"


def reset_render_state_smoke_test() -> str:
    env = TowerDefenseEnv()
    state = env.reset(seed=SEED)
    render_state = env.get_render_state()

    assert isinstance(state, tuple), "reset() must return a tuple state"
    assert state, "state tuple should not be empty"
    assert all(isinstance(item, int) for item in state), "state tuple must stay integer-only"
    assert "wave_id" in render_state, "render_state must expose wave_id"
    assert "modifiers" in render_state, "render_state must expose modifiers"
    assert "map_effects" in render_state, "render_state must expose map_effects"
    assert "available_cards" in render_state, "render_state must expose available_cards"

    return (
        f"state_len={len(state)}, wave_id={render_state['wave_id']}, "
        f"map_effects={len(render_state['map_effects'])}, cards={len(render_state['available_cards'])}"
    )


def valid_actions_smoke_test() -> str:
    env = TowerDefenseEnv()
    env.reset(seed=SEED)

    valid_actions = env.valid_actions()
    assert 0 in valid_actions, "wait action must always remain legal"

    open_row, open_col = _first_open_cell(env)
    wallnut_action = action_dict_to_id(
        {
            "action_type": "place_tower",
            "plant_type": "wallnut",
            "row": open_row,
            "col": open_col,
        }
    )
    env.resources = max(0, env.current_tower_cost("wallnut") - 1)
    assert wallnut_action not in env.valid_actions(), "insufficient sun should block plant placement"

    obstacle_row, obstacle_col = _first_obstacle_cell(env)
    obstacle_action_ids = [
        action_dict_to_id(
            {
                "action_type": "place_tower",
                "plant_type": plant_type,
                "row": obstacle_row,
                "col": obstacle_col,
            }
        )
        for plant_type in ("pea_shooter", "sunflower", "wallnut")
    ]
    available_after_obstacle = env.valid_actions()
    assert all(action_id not in available_after_obstacle for action_id in obstacle_action_ids), "obstacle cells must remain unplaceable"

    return f"wait=yes, low_sun_blocks=wallnut@({open_row},{open_col}), obstacle=({obstacle_row},{obstacle_col})"


def plant_system_smoke_test() -> str:
    env = TowerDefenseEnv(replace(CONFIG, resource_income_per_second=0))
    env.reset(seed=SEED)
    _pause_world(env)

    pea = Tower(uid="pea_attack_test", row=0, col=0, plant_type="pea_shooter", tower_type="basic", width=52, height=52)
    enemy = Enemy(
        uid="enemy_pea_target",
        row=0,
        x=float(env.config.grid_origin_x + env.config.cell_size * 2),
        y=float(env.config.grid_origin_y + (env.config.cell_size - env.config.enemy_height) / 2),
        hp=20.0,
        max_hp=20.0,
        speed=0.0,
        width=env.config.enemy_width,
        height=env.config.enemy_height,
        reward_score=1,
        enemy_type="normal",
    )
    env.towers = [pea]
    env.enemies = [enemy]
    enemy_hp_before = env.enemies[0].hp
    env.advance_world(dt=0.1)
    enemy_hp_after = env.enemies[0].hp if env.enemies else 0.0
    assert enemy_hp_after < enemy_hp_before, "pea_shooter should actually damage enemies"
    pea_damage = enemy_hp_before - enemy_hp_after

    sunflower = Tower(
        uid="sunflower_test",
        row=1,
        col=0,
        plant_type="sunflower",
        tower_type="sunflower",
        width=52,
        height=52,
        produce_timer=float(PLANT_CONFIG["sunflower"]["produce_interval"]),
    )
    env.towers = [sunflower]
    env.enemies = []
    resources_before = env.resources
    env.advance_world(dt=0.0)
    assert env.resources > resources_before, "sunflower should generate sun into resources"
    sun_gain = env.resources - resources_before

    pea_profile = Tower(uid="pea_profile", row=0, col=0, plant_type="pea_shooter", tower_type="basic", width=52, height=52)
    wallnut_profile = Tower(uid="wallnut_profile", row=0, col=1, plant_type="wallnut", tower_type="wallnut", width=52, height=52)
    assert wallnut_profile.max_hp > pea_profile.max_hp, "wallnut should stay tankier than attack plants"

    return f"pea_damage={pea_damage:.1f}, sun_gain={sun_gain}, wallnut_hp={wallnut_profile.max_hp:.0f}"


def enemy_system_smoke_test() -> str:
    env = TowerDefenseEnv()
    env.reset(seed=SEED)
    env.enemies = []
    env.current_wave = None
    env.current_wave_modifier = None

    env._spawn_enemy(enemy_type="normal", row=0)
    env._spawn_enemy(enemy_type="fast", row=1)
    env._spawn_enemy(enemy_type="tank", row=2)

    spawned = {enemy.enemy_type: enemy for enemy in env.enemies[-3:]}
    assert {"normal", "fast", "tank"}.issubset(spawned.keys()), "all three enemy variants should spawn"
    assert spawned["fast"].speed > spawned["normal"].speed, "fast enemy speed should exceed normal"
    assert spawned["tank"].max_hp > spawned["normal"].max_hp, "tank enemy hp should exceed normal"

    return (
        f"normal_hp={spawned['normal'].max_hp:.0f}, fast_speed={spawned['fast'].speed:.0f}, "
        f"tank_hp={spawned['tank'].max_hp:.0f}"
    )


def wave_system_smoke_test() -> str:
    env = build_fast_wave_env(total_waves=2)
    state = env.reset(seed=SEED)
    _ = state
    render_state = env.get_render_state()
    assert render_state["wave_id"] == 1, "game should automatically begin at wave 1"
    assert render_state["wave_state"] == "active", "wave 1 should start active"
    pending_options = _clear_first_wave_to_upgrade(env)
    assert env.base_env.wave_state == "upgrade", "clearing the current wave should enter upgrade state"
    return f"wave_start={render_state['wave_id']}, pending_upgrades={len(pending_options)}"


def upgrade_system_smoke_test() -> str:
    manager = UpgradeManager(CONFIG)
    manager.reset(SEED)
    options = manager.roll_options(3)
    assert len(options) == 3, "roll_options should return exactly 3 upgrades"

    env = build_fast_wave_env(total_waves=2)
    env.reset(seed=SEED)
    pending_options = _clear_first_wave_to_upgrade(env)
    selected_upgrade_id = str(pending_options[0]["id"])
    before_modifiers = dict(env.base_env.game_modifiers)
    choose_action = action_dict_to_id({"action_type": "choose_upgrade", "option_index": 0})
    _, _, _, choose_info = env.step(choose_action)
    assert choose_info["action_success"] is True, "choose_upgrade should succeed in upgrade state"
    assert env.base_env.wave_state == "active", "choosing an upgrade should start the next wave"
    assert env.get_render_state()["wave_id"] == 2, "wave index should advance after upgrade selection"
    assert dict(env.base_env.game_modifiers) != before_modifiers, "choosing an upgrade should modify combat modifiers"

    return f"rolled={len(options)}, chosen={selected_upgrade_id}, next_wave={env.get_render_state()['wave_id']}"


def training_adapter_smoke_test() -> str:
    env = build_env()
    state = env.reset(seed=SEED)
    assert isinstance(state, tuple), "FastCompatibilityEnv.reset() should return a tuple"

    valid_actions = env.valid_actions()
    assert isinstance(valid_actions, list) and valid_actions, "FastCompatibilityEnv.valid_actions() should return available actions"

    next_state, reward, done, info = env.step(0)
    assert isinstance(next_state, tuple), "FastCompatibilityEnv.step() should return a tuple next_state"
    assert isinstance(reward, float), "FastCompatibilityEnv.step() should return float reward"
    assert isinstance(done, bool), "FastCompatibilityEnv.step() should return bool done"
    assert isinstance(info, dict), "FastCompatibilityEnv.step() should return an info dict"
    assert "state_dict" in info and isinstance(info["state_dict"], dict), "FastCompatibilityEnv info must expose state_dict"

    return f"valid_actions={len(valid_actions)}, reward={reward:.2f}, done={done}"


def training_state_smoke_test() -> str:
    env = build_training_env(seed=SEED)
    state = env.reset(seed=SEED)
    assert isinstance(state, tuple), "training state mode should still return tuple observations"
    assert len(state) == TRAINING_STATE_VECTOR_SIZE, "training state length should match TRAINING_STATE_VECTOR_SIZE"

    next_state, _, _, info = env.step(ACTION_WAIT)
    assert len(next_state) == TRAINING_STATE_VECTOR_SIZE, "training state mode should keep a fixed tuple size"
    assert info["state_mode"] == "training", "training adapter should report training state_mode"
    assert info["training_state_size"] == TRAINING_STATE_VECTOR_SIZE, "info should expose training_state_size"
    assert info["training_state_version"] == TRAINING_STATE_VERSION, "info should expose training state version"
    return f"training_state_len={len(state)}, version={TRAINING_STATE_VERSION}"


def auto_select_upgrade_smoke_test() -> str:
    steady_modifier_pool = {"steady": CONFIG.wave_modifier_pool["steady"]}
    auto_config = replace(
        CONFIG,
        auto_select_upgrades=True,
        total_waves=2,
        wave_modifier_pool=steady_modifier_pool,
        wave_base_enemy_count=1,
        wave_enemy_count_step=0,
        tower_range_cells=9,
        tower_cooldown=0.25,
        enemy_hp=5,
        enemy_config=_scale_enemy_hp(CONFIG, 5.0 / float(ENEMY_CONFIG["normal"]["hp"])),
        enemy_speed=20.0,
        enemy_spawn_interval=0.2,
        resource_income_per_second=0,
        game_duration=60.0,
    )
    env = FastCompatibilityEnv(TowerDefenseEnv(auto_config), seed=SEED, step_dt=0.5)
    env.reset(seed=SEED)

    preview_rows = env.get_render_state()["wave"]["current"]["preview_rows"]
    target_row = int(preview_rows[0])
    placement_action = 1 + target_row * env.base_env.config.grid_cols
    _, _, _, placement_info = env.step(placement_action)

    # A short wave can finish during placement, before the first wait action.
    auto_selected_upgrade = placement_info.get("auto_selected_upgrade")
    for _ in range(80):
        _, _, done, info = env.step(ACTION_WAIT)
        if info.get("auto_selected_upgrade") is not None:
            auto_selected_upgrade = str(info["auto_selected_upgrade"])
        if done or env.get_render_state()["wave_id"] >= 2:
            break

    assert auto_selected_upgrade is not None, "auto_select_upgrades=True should report the selected upgrade in info"
    assert env.base_env.wave_state != "upgrade", "auto-selected upgrade flow should not stay on the upgrade screen"
    assert not env.base_env.pending_upgrade_options, "pending upgrades should clear after auto selection"
    return f"auto_selected={auto_selected_upgrade}, wave_state={env.base_env.wave_state}"


def truncation_smoke_test() -> str:
    config = replace(build_training_easy_config(seed=SEED), max_episode_steps=3)
    env = FastCompatibilityEnv(TowerDefenseEnv(config), seed=SEED, step_dt=0.0, state_mode="training")
    env.reset(seed=SEED)

    info: dict[str, object] = {}
    done = False
    steps = 0
    while not done and steps < 10:
        _, _, done, info = env.step(ACTION_WAIT)
        steps += 1

    assert done is True, "max_episode_steps should terminate the episode"
    assert info.get("episode_truncated") is True, "truncation should be marked in info"
    assert info.get("termination_reason") == "max_episode_steps", "truncation reason should be max_episode_steps"
    return f"steps={steps}, termination={info.get('termination_reason')}"


def run_compatibility_smoke_report() -> None:
    report_cases: list[tuple[str, Callable[[], str]]] = [
        ("Headless", headless_environment_test),
        ("Reset/State", reset_render_state_smoke_test),
        ("Valid Actions", valid_actions_smoke_test),
        ("Plants", plant_system_smoke_test),
        ("Enemies", enemy_system_smoke_test),
        ("Waves", wave_system_smoke_test),
        ("Upgrades", upgrade_system_smoke_test),
        ("Training Adapter", training_adapter_smoke_test),
        ("Training State", training_state_smoke_test),
        ("Auto Upgrade", auto_select_upgrade_smoke_test),
        ("Truncation", truncation_smoke_test),
    ]
    results: list[tuple[str, str]] = []

    for label, fn in report_cases:
        detail = fn()
        results.append((label, detail))

    print("\n=== Compatibility Smoke Report ===")
    for label, detail in results:
        print(f"[PASS] {label:<16} {detail}")


def smoke_test(env: FastCompatibilityEnv) -> None:
    state = env.reset(seed=SEED)
    assert isinstance(state, tuple), "reset() must return a tuple state"
    assert state, "state tuple should not be empty"
    assert all(isinstance(item, int) for item in state), "state tuple must stay hashable and integer-only"
    assert len(state) == STATE_VECTOR_SIZE, "STATE_VECTOR_SIZE should match the encoded tuple length"

    render_state = env.get_render_state()
    assert "wave" in render_state, "render state should expose wave metadata"
    assert "upgrades" in render_state, "render state should expose upgrade metadata"
    assert "map" in render_state, "render state should expose map metadata"
    assert "map_effects" in render_state, "render state should expose generated map effects"
    assert "modifiers" in render_state, "render state should expose modifier metadata"
    assert "wave_modifier" in render_state, "render state should expose the active wave modifier"
    assert "current_wave_modifier" in render_state, "render state should expose current_wave_modifier"
    assert "available_cards" in render_state, "render state should expose available card state"
    assert "card_cooldowns" in render_state, "render state should expose card cooldown state"
    assert "available_plants" in render_state, "render state should expose the plant catalog"
    assert "plant_costs" in render_state, "render state should expose per-plant costs"
    assert "pending_upgrade_options" in render_state, "render state should expose pending upgrade options"
    assert "active_upgrades" in render_state, "render state should expose active upgrades"
    assert "wave_id" in render_state and "total_waves" in render_state and "wave_state" in render_state, "render state should expose top-level wave progress keys"
    assert {"pea_shooter", "sunflower", "wallnut"}.issubset(set(render_state["available_plants"])), "available_plants should list the three supported plants"
    assert render_state["plant_costs"]["pea_shooter"] == env.base_env.current_tower_cost("pea_shooter")
    assert render_state["plant_costs"]["sunflower"] == env.base_env.current_tower_cost("sunflower")
    assert render_state["plant_costs"]["wallnut"] == env.base_env.current_tower_cost("wallnut")

    valid_actions = env.valid_actions()
    assert 0 in valid_actions, "wait action must always be valid"
    assert len(valid_actions) > 1, "there should be at least one place action at reset"
    assert env.base_env.action_space_size == ACTION_SPACE_SIZE, "action space size must match expanded card space"
    assert render_state["wave_id"] == 1 and render_state["wave_state"] == "active", "env should auto-enter wave 1"

    print(f"[smoke] state_type={type(state).__name__}, state_len={len(state)}")
    print(f"[smoke] valid_actions={len(valid_actions)}")

    _, _, _, invalid_info = env.step(999)
    assert invalid_info.get("action_success") is False, "invalid action should fail"
    print(
        "[smoke] invalid_action -> "
        f"reason={invalid_info.get('action_reason')}, success={invalid_info.get('action_success')}"
    )

    env.reset(seed=SEED)
    legal_action = next((action for action in env.valid_actions() if action != 0), 0)
    assert legal_action != 0, "there should be at least one legal non-wait action at reset"

    _, _, _, legal_info = env.step(legal_action)
    assert legal_info.get("action_success") is True, "legal tower placement should succeed"
    print(
        "[smoke] valid_action -> "
        f"action={legal_action}, reason={legal_info.get('action_reason')}, success={legal_info.get('action_success')}"
    )

    env.reset(seed=SEED)
    start_time = env.game_time
    _, _, _, wait_info = env.step(0)
    assert abs(env.game_time - (start_time + STEP_DT)) < 1e-9, "step_dt should advance game time by 1 second"
    assert wait_info.get("action_success") is True, "wait action should succeed"

    print(f"[smoke] step_dt={env.step_dt}, time_after_wait={env.game_time:.2f}")


def interface_contract_test(env: FastCompatibilityEnv) -> None:
    assert action_id_to_dict(0) == {"action_type": "wait"}
    pea_action = action_id_to_dict(1)
    assert pea_action["row"] == 0 and pea_action["col"] == 0
    assert pea_action["tower_type"] == "basic" and pea_action["plant_type"] == "pea_shooter"
    assert action_id_to_dict(46)["plant_type"] == "sunflower"
    assert action_id_to_dict(91)["plant_type"] == "wallnut"
    assert action_id_to_dict(ACTION_CHOOSE_UPGRADE_OFFSET) == {"action_type": "choose_upgrade", "option_index": 0}
    assert action_dict_to_id({"action_type": "place_tower", "tower_type": "basic", "row": 4, "col": 8}) == 45
    assert action_dict_to_id({"action_type": "place_tower", "plant_type": "sunflower", "row": 0, "col": 0}) == 46
    assert action_dict_to_id({"action_type": "place_tower", "plant_type": "wallnut", "row": 0, "col": 0}) == 91
    assert action_dict_to_id({"action_type": "choose_upgrade", "option_index": 2}) == ACTION_CHOOSE_UPGRADE_OFFSET + 2

    env.reset(seed=SEED)
    agent = RuleBasedAgent(env.base_env.config)
    action = agent.choose_action(env.get_state())
    assert action in env.valid_actions(), "RuleBasedAgent should stay compatible with valid_actions()"

    base_env = TowerDefenseEnv()
    base_env.reset(seed=SEED)
    assert base_env.apply_action(1) is True, "pea_shooter placement should still work through the legacy slot"
    base_env.resources = 500
    cooldown_actions = base_env.valid_actions()
    assert 2 not in cooldown_actions, "pea_shooter card cooldown should block the next pea placement slot"
    assert 47 in cooldown_actions and 92 in cooldown_actions, "other plant cards should remain placeable while pea_shooter cools down"

    obstacle_env = TowerDefenseEnv()
    obstacle_env.reset(seed=SEED)
    obstacle_env.map_effects[(0, 1)] = MapEffectDefinition(
        id="test_obstacle",
        name="Obstacle",
        description="blocked test tile",
        is_obstacle=True,
    )
    obstacle_actions = obstacle_env.valid_actions()
    assert 2 not in obstacle_actions and 47 not in obstacle_actions and 92 not in obstacle_actions, "obstacle cells must be excluded for every plant card"
    print(f"[contract] rule_based_action={action}")


def rule_based_state_dict_test() -> None:
    agent = RuleBasedAgent(CONFIG)
    definitions = upgrade_definitions_from_config(CONFIG)

    upgrade_env = TowerDefenseEnv()
    upgrade_env.reset(seed=SEED)
    upgrade_env.wave_state = "upgrade"
    upgrade_env._set_pending_upgrade_options(
        [
            definitions["hp_up"],
            definitions["sun_up"],
            definitions["damage_up"],
        ]
    )
    upgrade_action = agent.choose_action_from_state_dict(upgrade_env.get_state_dict(), upgrade_env.valid_actions())
    assert action_id_to_dict(upgrade_action) == {"action_type": "choose_upgrade", "option_index": 2}, "upgrade state should prioritize damage_up first"

    sunflower_env = TowerDefenseEnv()
    sunflower_env.reset(seed=SEED)
    sunflower_env.wave_id = 1
    sunflower_env.wave_state = "active"
    sunflower_env.towers = []
    sunflower_env.enemies = []
    sunflower_env.map_effects = {
        (0, 0): MapEffectDefinition(
            id="fertile_land",
            name="Fertile Land",
            description="bonus sun tile",
            sun_produce_multiplier=1.2,
        )
    }
    sunflower_action = agent.choose_action_from_state_dict(sunflower_env.get_state_dict(), sunflower_env.valid_actions())
    sunflower_choice = action_id_to_dict(sunflower_action)
    assert sunflower_choice["plant_type"] == "sunflower", "early safe rows should prioritize sunflower placement"
    assert (sunflower_choice["row"], sunflower_choice["col"]) == (0, 0), "sunflower should prefer fertile_land when it is safe"

    pea_env = TowerDefenseEnv()
    pea_env.reset(seed=SEED)
    pea_env.wave_id = 3
    pea_env.wave_state = "active"
    pea_env.towers = []
    pea_env.enemies = [
        Enemy(
            uid="enemy_pressure_1",
            row=1,
            x=float(pea_env.config.grid_origin_x + pea_env.config.cell_size * 6),
            y=float(pea_env.config.grid_origin_y + pea_env.config.cell_size + 6),
            hp=10.0,
            max_hp=10.0,
            speed=0.0,
            width=pea_env.config.enemy_width,
            height=pea_env.config.enemy_height,
            reward_score=1,
            enemy_type="normal",
        ),
        Enemy(
            uid="enemy_pressure_2",
            row=1,
            x=float(pea_env.config.grid_origin_x + pea_env.config.cell_size * 7),
            y=float(pea_env.config.grid_origin_y + pea_env.config.cell_size + 6),
            hp=10.0,
            max_hp=10.0,
            speed=0.0,
            width=pea_env.config.enemy_width,
            height=pea_env.config.enemy_height,
            reward_score=1,
            enemy_type="normal",
        ),
    ]
    pea_env.map_effects = {
        (1, 2): MapEffectDefinition(
            id="attack_highland",
            name="Attack Highland",
            description="bonus damage tile",
            damage_multiplier=1.15,
        )
    }
    pea_action = agent.choose_action_from_state_dict(pea_env.get_state_dict(), pea_env.valid_actions())
    pea_choice = action_id_to_dict(pea_action)
    assert pea_choice["plant_type"] == "pea_shooter", "enemy pressure rows should prioritize pea_shooter"
    assert (pea_choice["row"], pea_choice["col"]) == (1, 2), "pea_shooter should prefer attack_highland on the pressured row"

    wallnut_env = TowerDefenseEnv()
    wallnut_env.reset(seed=SEED)
    wallnut_env.wave_id = 4
    wallnut_env.wave_state = "active"
    wallnut_env.towers = []
    wallnut_env.enemies = [
        Enemy(
            uid="enemy_tank_a",
            row=2,
            x=float(wallnut_env.config.grid_origin_x + wallnut_env.config.cell_size * 7),
            y=float(wallnut_env.config.grid_origin_y + wallnut_env.config.cell_size * 2 + 6),
            hp=30.0,
            max_hp=30.0,
            speed=0.0,
            width=wallnut_env.config.enemy_width,
            height=wallnut_env.config.enemy_height,
            reward_score=1,
            enemy_type="tank",
        ),
        Enemy(
            uid="enemy_tank_b",
            row=2,
            x=float(wallnut_env.config.grid_origin_x + wallnut_env.config.cell_size * 8),
            y=float(wallnut_env.config.grid_origin_y + wallnut_env.config.cell_size * 2 + 6),
            hp=30.0,
            max_hp=30.0,
            speed=0.0,
            width=wallnut_env.config.enemy_width,
            height=wallnut_env.config.enemy_height,
            reward_score=1,
            enemy_type="tank",
        ),
    ]
    wallnut_action = agent.choose_action_from_state_dict(wallnut_env.get_state_dict(), wallnut_env.valid_actions())
    wallnut_choice = action_id_to_dict(wallnut_action)
    assert wallnut_choice["plant_type"] == "wallnut", "tank-heavy rows should prioritize wallnut"
    assert wallnut_choice["row"] == 2, "wallnut should be placed on the tank-pressure row"
    print("[agent] rule_based_state_dict strategy passed")


def map_effect_manager_test() -> None:
    manager_a = MapEffectManager(CONFIG)
    manager_b = MapEffectManager(CONFIG)
    effects_a = manager_a.reset(SEED)
    effects_b = manager_b.reset(SEED)

    serialized_a = manager_a.serialize()
    serialized_b = manager_b.serialize()
    assert serialized_a == serialized_b, "same seed should reproduce the same map effects"
    assert len(serialized_a) == 6, "default map should place 2 obstacles, 2 attack highlands, and 2 fertile lands"

    obstacle_cells = [(item["row"], item["col"]) for item in serialized_a if item["effect"]["id"] == "obstacle"]
    assert len(obstacle_cells) == 2, "map should generate exactly 2 obstacle cells"
    assert all(0 < col < CONFIG.grid_cols - 1 for _, col in obstacle_cells), "obstacles should avoid the leftmost and rightmost columns"

    attack_cells = [item for item in serialized_a if item["effect"]["id"] == "attack_highland"]
    fertile_cells = [item for item in serialized_a if item["effect"]["id"] == "fertile_land"]
    assert len(attack_cells) == 2, "map should generate exactly 2 attack_highland cells"
    assert len(fertile_cells) == 2, "map should generate exactly 2 fertile_land cells"
    assert effects_a == effects_b, "effect dictionaries should also match directly for the same seed"
    print("[map] effect manager reproducibility passed")


def entity_profile_test() -> None:
    basic = Tower(uid="tower_basic", row=0, col=0, tower_type="basic", width=52, height=52)
    sunflower = Tower(uid="tower_sun", row=0, col=1, plant_type="sunflower", tower_type="sunflower", width=52, height=52)
    wallnut = Tower(uid="tower_wall", row=0, col=2, plant_type="wallnut", tower_type="wallnut", width=52, height=52)
    pea = Tower(uid="tower_pea", row=0, col=3, plant_type="pea_shooter", tower_type="pea_shooter", width=52, height=52)

    assert basic.plant_type == "pea_shooter", "basic tower_type must map to pea_shooter"
    assert sunflower.role == "economy", "sunflower role must be economy"
    assert wallnut.max_hp > pea.max_hp, "wallnut should be tankier than pea_shooter"
    assert basic.damage == int(PLANT_CONFIG["pea_shooter"]["damage"]), "tower should source pea_shooter damage from config"

    normal_enemy = Enemy(
        uid="enemy_normal",
        row=0,
        x=100.0,
        y=100.0,
        hp=float(ENEMY_CONFIG["normal"]["hp"]),
        max_hp=float(ENEMY_CONFIG["normal"]["hp"]),
        speed=float(ENEMY_CONFIG["normal"]["speed"]),
        width=44,
        height=44,
        reward_score=int(ENEMY_CONFIG["normal"]["reward"]),
        enemy_type="normal",
    )
    fast_enemy = Enemy(
        uid="enemy_fast",
        row=0,
        x=100.0,
        y=100.0,
        hp=float(ENEMY_CONFIG["fast"]["hp"]),
        max_hp=float(ENEMY_CONFIG["fast"]["hp"]),
        speed=float(ENEMY_CONFIG["fast"]["speed"]),
        width=44,
        height=44,
        reward_score=int(ENEMY_CONFIG["fast"]["reward"]),
        enemy_type="fast",
    )
    tank_enemy = Enemy(
        uid="enemy_tank",
        row=0,
        x=100.0,
        y=100.0,
        hp=float(ENEMY_CONFIG["tank"]["hp"]),
        max_hp=float(ENEMY_CONFIG["tank"]["hp"]),
        speed=float(ENEMY_CONFIG["tank"]["speed"]),
        width=44,
        height=44,
        reward_score=int(ENEMY_CONFIG["tank"]["reward"]),
        enemy_type="tank",
    )

    assert fast_enemy.speed > normal_enemy.speed, "fast enemy speed should exceed normal"
    assert tank_enemy.max_hp > normal_enemy.max_hp or tank_enemy.armor > normal_enemy.armor, "tank enemy should be tougher than normal"
    print("[entity] tower/enemy config alignment passed")


def sunflower_economy_test() -> None:
    custom_config = replace(
        CONFIG,
        resource_income_per_second=0,
    )
    env = TowerDefenseEnv(custom_config)
    env.reset(seed=SEED)

    sunflower = Tower(
        uid="tower_sun_test",
        row=0,
        col=0,
        plant_type="sunflower",
        tower_type="sunflower",
        width=52,
        height=52,
        produce_timer=float(PLANT_CONFIG["sunflower"]["produce_interval"]),
    )
    env.towers = [sunflower]
    env.game_modifiers["sun_produce_multiplier"] = 2.0

    start_resources = env.resources
    reward = env.advance_world(dt=0.0)

    produced_sun = int(PLANT_CONFIG["sunflower"]["sun_produce"]) * 2
    assert env.resources == start_resources + produced_sun, "sunflower should add sun directly to resources"
    assert env.last_reward_breakdown["economy"] == 0.2, "sunflower production should add the economy reward"
    assert reward >= env.config.reward_survive_per_step + 0.2, "economy reward should contribute to step reward"

    tower_state = env.get_render_state()["towers"][0]
    assert "produce_timer" in tower_state, "render state should expose sunflower produce_timer"
    assert tower_state["produce_timer"] == 0.0, "produce_timer should reset after producing sun"
    print("[economy] sunflower sun production passed")


def enemy_spawn_type_test() -> None:
    env = TowerDefenseEnv()
    env.reset(seed=SEED)
    env.enemies = []
    env.current_wave = None
    env.current_wave_modifier = None

    env._spawn_enemy()
    assert env.enemies[-1].enemy_type == "normal", "legacy no-arg _spawn_enemy() should still create a normal enemy"
    assert 0 <= env.enemies[-1].row < env.config.grid_rows, "spawned enemy row should stay in range"

    env.game_modifiers["enemy_hp_multiplier"] = 1.5
    env.game_modifiers["enemy_speed_multiplier"] = 0.5
    env._spawn_enemy(enemy_type="fast", row=2)
    fast_enemy = env.enemies[-1]
    assert fast_enemy.enemy_type == "fast", "explicit fast enemy spawn should preserve type"
    assert fast_enemy.row == 2, "explicit row should be honored"
    assert fast_enemy.max_hp == float(ENEMY_CONFIG["fast"]["hp"]) * 1.5, "fast enemy hp should come from ENEMY_CONFIG and game modifiers"
    assert fast_enemy.speed == float(ENEMY_CONFIG["fast"]["speed"]) * 0.5, "fast enemy speed should come from ENEMY_CONFIG and game modifiers"

    env._spawn_enemy(
        enemy_type="tank",
        row=1,
        modifiers={"id": "bonus_test", "enemy_hp_multiplier": 2.0, "enemy_speed_multiplier": 0.8},
    )
    tank_enemy = env.enemies[-1]
    assert tank_enemy.enemy_type == "tank", "tank spawn should preserve type"
    assert tank_enemy.max_hp == float(ENEMY_CONFIG["tank"]["hp"]) * 3.0, "tank hp should include both game and extra modifiers"
    assert tank_enemy.speed == float(ENEMY_CONFIG["tank"]["speed"]) * 0.4, "tank speed should include both game and extra modifiers"
    assert "bonus_test" in tank_enemy.modifier_ids, "explicit modifier ids should be recorded on the enemy"

    spawn = WaveSpawn(delay=0.0, row=3, enemy_type_id="fast")
    env._spawn_enemy(spawn)
    spawn_enemy = env.enemies[-1]
    assert spawn_enemy.enemy_type == "fast", "_spawn_enemy(spawn) should parse enemy_type_id from WaveSpawn"
    assert spawn_enemy.row == 3, "_spawn_enemy(spawn) should parse row from WaveSpawn"

    render_enemies = env.get_render_state()["enemies"]
    assert any(enemy["type"] == "fast" for enemy in render_enemies), "render state should expose enemy type for renderer styling"
    assert any(enemy["type"] == "tank" for enemy in render_enemies), "render state should expose tank enemy type"
    print("[enemy] typed enemy spawning passed")


def wave_manager_contract_test() -> None:
    manager = WaveManager(CONFIG)
    manager.reset(SEED)
    assert manager.is_wave_active() is False, "manager should be idle after reset before a wave is started"

    wave = manager.start_next_wave()
    assert wave is not None and wave.wave_id == 1, "manager should start from wave 1"
    assert manager.is_wave_active() is True, "manager should report an active wave after start"
    assert wave.modifier.id in {"fast_attack", "thick_armor", "number_pressure", "single_lane"}, "wave should roll one of the random pressure modifiers"

    manager.update(999.0)
    spawn_count = 0
    while manager.should_spawn():
        spawn = manager.get_next_spawn()
        assert spawn is not None
        spawn_count += 1

    assert spawn_count == wave.enemy_count, "manager should release every spawn in the active wave"
    assert manager.is_wave_cleared([]) is True, "wave should be clearable once all spawns are released and no enemies remain"
    manager.finish_current_wave()
    assert manager.is_wave_active() is False, "finish_current_wave should mark the wave inactive"
    print("[waves] manager contract passed")


def wave_modifier_reproducibility_test() -> None:
    seed = 19
    manager_a = WaveManager(CONFIG)
    manager_b = WaveManager(CONFIG)
    manager_a.reset(seed)
    manager_b.reset(seed)
    wave_a = manager_a.start_next_wave()
    wave_b = manager_b.start_next_wave()

    assert wave_a is not None and wave_b is not None
    assert wave_a.modifier.to_dict() == wave_b.modifier.to_dict(), "same seed should reproduce the same wave modifier"
    assert wave_a.enemy_count == wave_b.enemy_count, "same seed should reproduce the same wave enemy count"
    assert [spawn.to_dict() for spawn in wave_a.spawns] == [spawn.to_dict() for spawn in wave_b.spawns], "same seed should reproduce the same spawn layout"

    env_a = TowerDefenseEnv()
    env_b = TowerDefenseEnv()
    env_a.reset(seed=seed)
    env_b.reset(seed=seed)
    assert env_a.current_wave_modifier == env_b.current_wave_modifier, "env should preserve wave modifier reproducibly with a fixed seed"
    assert env_a.get_render_state()["wave_modifier"] == env_a.current_wave_modifier, "render state should expose the active wave modifier at the top level"
    assert env_a.get_state_dict()["wave_modifier"] == env_a.current_wave_modifier, "state dict should expose the active wave modifier"

    single_lane_seed = None
    number_pressure_seed = None
    fast_attack_seed = None
    thick_armor_seed = None
    for candidate_seed in range(60):
        manager = WaveManager(CONFIG)
        manager.reset(candidate_seed)
        wave = manager.start_next_wave()
        assert wave is not None
        if wave.modifier.id == "single_lane" and single_lane_seed is None:
            single_lane_seed = candidate_seed
            assert wave.modifier.target_row is not None, "single_lane should record the focused target row"
            assert len({spawn.row for spawn in wave.spawns}) == 1, "single_lane should collapse the wave into one row"
            assert wave.spawns[0].row == wave.modifier.target_row, "single_lane spawn row should match the recorded target row"
        if wave.modifier.id == "number_pressure" and number_pressure_seed is None:
            number_pressure_seed = candidate_seed
            baseline_count = int(CONFIG.wave_base_enemy_count)
            assert wave.enemy_count > baseline_count, "number_pressure should increase the wave enemy count"
        if wave.modifier.id == "fast_attack" and fast_attack_seed is None:
            fast_attack_seed = candidate_seed
            env = TowerDefenseEnv()
            env.reset(seed=candidate_seed)
            env.enemies = []
            env._spawn_enemy(enemy_type="normal", row=0)
            assert env.enemies[-1].speed == float(ENEMY_CONFIG["normal"]["speed"]) * 1.2, "fast_attack should increase spawned enemy speed by 20%"
        if wave.modifier.id == "thick_armor" and thick_armor_seed is None:
            thick_armor_seed = candidate_seed
            env = TowerDefenseEnv()
            env.reset(seed=candidate_seed)
            env.enemies = []
            env._spawn_enemy(enemy_type="normal", row=0)
            assert env.enemies[-1].max_hp == float(ENEMY_CONFIG["normal"]["hp"]) * 1.3, "thick_armor should increase spawned enemy hp by 30%"
        if (
            single_lane_seed is not None
            and number_pressure_seed is not None
            and fast_attack_seed is not None
            and thick_armor_seed is not None
        ):
            break

    assert single_lane_seed is not None, "deterministic seed scan should encounter single_lane"
    assert number_pressure_seed is not None, "deterministic seed scan should encounter number_pressure"
    assert fast_attack_seed is not None, "deterministic seed scan should encounter fast_attack"
    assert thick_armor_seed is not None, "deterministic seed scan should encounter thick_armor"
    print(
        "[waves] modifier reproducibility passed "
        f"(seed={seed}, single_lane={single_lane_seed}, number_pressure={number_pressure_seed}, "
        f"fast_attack={fast_attack_seed}, thick_armor={thick_armor_seed})"
    )


def upgrade_manager_smoke_test() -> None:
    env = TowerDefenseEnv()
    env.reset(seed=SEED)
    manager = UpgradeManager(CONFIG)
    manager.reset(SEED)

    modifiers = manager.get_modifiers()
    for key in (
        "plant_damage_multiplier",
        "plant_hp_multiplier",
        "wallnut_hp_multiplier",
        "sun_produce_multiplier",
        "plant_cost_multiplier",
        "cooldown_multiplier",
        "enemy_speed_multiplier",
        "enemy_hp_multiplier",
        "kill_sun_bonus",
    ):
        assert key in modifiers, f"{key} should exist in DEFAULT_GAME_MODIFIERS"

    options = manager.roll_options(3)
    assert 1 <= len(options) <= 3, "roll_options should return up to 3 upgrades"
    assert len({option.id for option in options}) == len(options), "roll_options should not duplicate upgrades in one offer"

    wallnut = Tower(uid="tower_upgrade_wall", row=0, col=0, plant_type="wallnut", tower_type="wallnut", width=52, height=52)
    env.towers = [wallnut]
    base_wallnut_hp = wallnut.max_hp

    manager.apply_upgrade("damage_up", env)
    manager.apply_upgrade("wallnut_hp_up", env)
    active_upgrade_ids = [item["id"] for item in manager.get_active_upgrades()]

    assert "damage_up" in active_upgrade_ids and "wallnut_hp_up" in active_upgrade_ids, "applied upgrades should be recorded"
    assert manager.get_modifiers()["plant_damage_multiplier"] == 1.2, "damage_up should raise plant_damage_multiplier by 0.2"
    assert env.game_modifiers["tower_damage_multiplier"] == 1.2, "damage_up should sync the legacy env damage modifier"
    assert manager.get_modifiers()["wallnut_hp_multiplier"] == 1.4, "wallnut_hp_up should raise wallnut hp multiplier by 0.4"
    assert wallnut.max_hp > base_wallnut_hp, "wallnut_hp_up should increase wallnut hp through env recalculation"
    print("[upgrade] manager smoke passed")


def upgrade_effect_application_test() -> None:
    definitions = upgrade_definitions_from_config(CONFIG)

    damage_env = TowerDefenseEnv()
    damage_env.reset(seed=SEED)
    damage_env.wave_state = "upgrade"
    damage_env._set_pending_upgrade_options([definitions["damage_up"]])
    damage_tower = Tower(uid="tower_damage_upgrade", row=0, col=0, plant_type="pea_shooter", tower_type="basic", width=52, height=52)
    damage_env.towers = [damage_tower]
    base_damage_multiplier = float(damage_env.game_modifiers["plant_damage_multiplier"])
    base_damage = damage_env._tower_damage(damage_tower)
    _, _, _, damage_info = damage_env.step(action_dict_to_id({"action_type": "choose_upgrade", "option_index": 0}))
    assert damage_info["action_success"] is True, "damage_up should be choosable through the upgrade action"
    assert damage_env.game_modifiers["plant_damage_multiplier"] == base_damage_multiplier + 0.2, "damage_up should raise plant_damage_multiplier"
    assert damage_env._tower_damage(damage_tower) > base_damage, "damage_up should increase actual pea_shooter attack damage"

    cost_env = TowerDefenseEnv()
    cost_env.reset(seed=SEED)
    cost_env.wave_state = "upgrade"
    cost_env._set_pending_upgrade_options([definitions["cost_down"]])
    base_cost = cost_env.current_tower_cost("pea_shooter")
    _, _, _, cost_info = cost_env.step(action_dict_to_id({"action_type": "choose_upgrade", "option_index": 0}))
    assert cost_info["action_success"] is True, "cost_down should be choosable through the upgrade action"
    reduced_cost = cost_env.current_tower_cost("pea_shooter")
    assert reduced_cost < base_cost, "cost_down should lower the actual placement cost"
    resources_before_place = cost_env.resources
    assert cost_env.apply_action(1) is True, "pea_shooter placement should still succeed after cost_down"
    assert cost_env.resources == resources_before_place - reduced_cost, "placing a plant after cost_down should spend the reduced cost"

    kill_env = TowerDefenseEnv(replace(CONFIG, resource_income_per_second=0))
    kill_env.reset(seed=SEED)
    kill_env.wave_state = "upgrade"
    kill_env._set_pending_upgrade_options([definitions["kill_sun_bonus"]])
    _, _, _, kill_upgrade_info = kill_env.step(action_dict_to_id({"action_type": "choose_upgrade", "option_index": 0}))
    assert kill_upgrade_info["action_success"] is True, "kill_sun_bonus should be choosable through the upgrade action"
    kill_env.wave_state = "waiting"
    kill_env.current_wave = None
    kill_env.pending_wave_spawns = []
    kill_env.wave_manager.finish_current_wave()
    kill_env.resources = 0
    kill_tower = Tower(uid="tower_kill_bonus", row=0, col=0, plant_type="pea_shooter", tower_type="basic", width=52, height=52)
    kill_env.towers = [kill_tower]
    kill_enemy = Enemy(
        uid="enemy_kill_bonus",
        row=0,
        x=float(kill_env.config.grid_origin_x + kill_env.config.cell_size * 2),
        y=float(kill_env.config.grid_origin_y + (kill_env.config.cell_size - kill_env.config.enemy_height) / 2),
        hp=1.0,
        max_hp=1.0,
        speed=0.0,
        width=kill_env.config.enemy_width,
        height=kill_env.config.enemy_height,
        reward_score=1,
        enemy_type="normal",
    )
    kill_env.enemies = [kill_enemy]
    kill_env.advance_world(dt=0.1)
    assert kill_env.resources == 5, "kill_sun_bonus should grant bonus sun immediately when an enemy is killed"
    assert kill_env.last_reward_breakdown["kills"] == kill_env.config.reward_kill, "kill reward should still be tracked normally alongside bonus sun"
    print("[upgrade] effect application passed")


def plant_damage_test() -> None:
    custom_config = replace(
        CONFIG,
        resource_income_per_second=0,
    )

    wallnut_env = TowerDefenseEnv(custom_config)
    wallnut_env.reset(seed=SEED)
    wallnut = Tower(
        uid="tower_wall_test",
        row=0,
        col=3,
        plant_type="wallnut",
        tower_type="wallnut",
        width=52,
        height=52,
    )
    wallnut_env.towers = [wallnut]
    wallnut_rect = wallnut.rect(wallnut_env.config)
    wallnut_enemy = Enemy(
        uid="enemy_wall_test",
        row=0,
        x=float(wallnut_rect.right - wallnut_env.config.enemy_width + 1),
        y=float(wallnut_rect.top),
        hp=50.0,
        max_hp=50.0,
        speed=20.0,
        width=wallnut_env.config.enemy_width,
        height=wallnut_env.config.enemy_height,
        reward_score=10,
        attack_damage=50.0,
        attack_cooldown=1.0,
    )
    wallnut_env.enemies = [wallnut_enemy]

    wallnut_env.advance_world(dt=1.0)
    blocked_enemy_x = wallnut_env.enemies[0].x
    wallnut_env.advance_world(dt=1.0)
    assert len(wallnut_env.towers) == 1, "wallnut should survive repeated bites thanks to high hp"
    assert wallnut_env.towers[0].hp < wallnut_env.towers[0].max_hp, "wallnut hp should decrease while blocking"
    assert wallnut_env.enemies[0].x == blocked_enemy_x, "enemy should stop moving while colliding with a plant"

    sunflower_env = TowerDefenseEnv(custom_config)
    sunflower_env.reset(seed=SEED)
    sunflower = Tower(
        uid="tower_sun_block",
        row=0,
        col=3,
        plant_type="sunflower",
        tower_type="sunflower",
        width=52,
        height=52,
    )
    sunflower_env.towers = [sunflower]
    sunflower_rect = sunflower.rect(sunflower_env.config)
    sunflower_enemy = Enemy(
        uid="enemy_sun_block",
        row=0,
        x=float(sunflower_rect.right - sunflower_env.config.enemy_width + 1),
        y=float(sunflower_rect.top),
        hp=50.0,
        max_hp=50.0,
        speed=20.0,
        width=sunflower_env.config.enemy_width,
        height=sunflower_env.config.enemy_height,
        reward_score=10,
        attack_damage=float(sunflower.max_hp / 2.0),
        attack_cooldown=1.0,
    )
    sunflower_env.enemies = [sunflower_enemy]

    sunflower_env.advance_world(dt=1.0)
    reward = sunflower_env.advance_world(dt=1.0)
    assert not sunflower_env.towers, "sunflower should be removed once hp reaches zero"
    assert sunflower_env.last_reward_breakdown["plant_lost"] == -2.0, "lost plants should record the plant_lost penalty"
    assert reward <= sunflower_env.config.reward_survive_per_step - 2.0 + 1e-9, "plant loss should reduce the step reward"

    render_tower = wallnut_env.get_render_state()["towers"][0]
    assert "hp" in render_tower and "max_hp" in render_tower, "render state should expose plant hp for future health bars"
    print("[plants] blocking and plant loss passed")


def wave_victory_test() -> None:
    env = build_fast_wave_env(total_waves=1)
    env.reset(seed=SEED)

    preview_rows = env.get_render_state()["wave"]["current"]["preview_rows"]
    target_row = int(preview_rows[0])
    action = 1 + target_row * env.base_env.config.grid_cols
    env.step(action)

    for _ in range(30):
        _, _, done, _ = env.step(0)
        if done:
            break

    assert env.done, "single-wave test env should finish"
    assert env.base_env.victory is True, "single-wave test env should end in victory"
    assert env.base_env.waves_cleared == 1, "single-wave test env should clear exactly one wave"
    print("[wave] single-wave victory path passed")


def wave_state_flow_test() -> None:
    env = build_fast_wave_env(total_waves=2)
    env.reset(seed=SEED)
    # This case checks a full clear; other cases cover overlapping waves.
    env.base_env.wave_manager.waves[1].start_requires_clear_field = True

    bonus_cells = env.get_render_state()["map"]["bonus_cells"]
    assert bonus_cells, "map should expose non-blocking bonus cells"
    assert env.get_render_state()["wave_state"] == "active", "game should begin with an active wave"
    assert env.get_render_state()["wave_id"] == 1, "wave 1 should start automatically"

    preview_rows = env.get_render_state()["wave"]["current"]["preview_rows"]
    target_row = int(preview_rows[0])
    action = 1 + target_row * env.base_env.config.grid_cols
    env.step(action)

    for _ in range(40):
        env.step(0)
        if env.base_env.wave_state == "upgrade":
            break

    assert env.base_env.wave_state == "upgrade", "clearing a wave should enter upgrade state"
    assert env.get_render_state()["wave_remaining"] == 0, "wave remaining should reach zero after a clear"
    pending_options = env.get_render_state()["pending_upgrade_options"]
    assert len(pending_options) == 3, "wave clear should roll three upgrade options"
    upgrade_valid_actions = env.valid_actions()
    assert upgrade_valid_actions == [0, ACTION_CHOOSE_UPGRADE_OFFSET, ACTION_CHOOSE_UPGRADE_OFFSET + 1, ACTION_CHOOSE_UPGRADE_OFFSET + 2], "upgrade state should only expose wait plus three choose_upgrade actions"

    paused_time = env.game_time
    _, _, _, wait_info = env.step(0)
    assert env.base_env.wave_state == "upgrade", "wait during upgrade should not advance to the next wave"
    assert env.game_time == paused_time, "upgrade wait should pause world time"
    assert wait_info["action_success"] is True and wait_info["action_reason"] == "AWAITING_UPGRADE", "upgrade wait should stay legal while prompting for a choice"

    selected_upgrade_id = pending_options[0]["id"]
    modifier_key, expected_value = {
        "damage_up": ("plant_damage_multiplier", env.base_env.game_modifiers["plant_damage_multiplier"] + 0.2),
        "attack_speed_up": ("cooldown_multiplier", env.base_env.game_modifiers["cooldown_multiplier"] * 0.85),
        "hp_up": ("plant_hp_multiplier", env.base_env.game_modifiers["plant_hp_multiplier"] + 0.2),
        "wallnut_hp_up": ("wallnut_hp_multiplier", env.base_env.game_modifiers["wallnut_hp_multiplier"] + 0.4),
        "sun_up": ("sun_produce_multiplier", env.base_env.game_modifiers["sun_produce_multiplier"] + 0.2),
        "kill_sun_bonus": ("kill_sun_bonus", env.base_env.game_modifiers["kill_sun_bonus"] + 5),
        "cost_down": ("plant_cost_multiplier", env.base_env.game_modifiers["plant_cost_multiplier"] * 0.9),
        "cooldown_down": ("cooldown_multiplier", env.base_env.game_modifiers["cooldown_multiplier"] * 0.85),
    }[selected_upgrade_id]

    choose_action = action_dict_to_id({"action_type": "choose_upgrade", "option_index": 0})
    _, _, _, choose_info = env.step(choose_action)
    assert choose_info["action_success"] is True and choose_info["action_reason"] == "UPGRADE_CHOSEN", "choose_upgrade action should apply the selected upgrade"
    assert abs(float(env.base_env.game_modifiers[modifier_key]) - float(expected_value)) < 1e-9, "selected upgrade should modify env game_modifiers"
    assert any(item["id"] == selected_upgrade_id for item in env.get_render_state()["active_upgrades"]), "render state should list the newly active upgrade"
    assert not env.get_render_state()["pending_upgrade_options"], "pending options should clear after taking an upgrade"
    assert env.base_env.wave_state == "active", "choosing an upgrade should start the next wave"
    assert env.get_render_state()["wave_id"] == 2, "wave id should advance after leaving upgrade state"
    assert env.get_render_state()["wave"]["current_wave_index"] == 2, "wave payload should expose the new wave index"
    print(f"[wave] state_flow map_bonus_cells={len(bonus_cells)}")


def logger_database_smoke_test() -> None:
    logs_dir = PROJECT_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=str(logs_dir)) as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)
        csv_dir = tmp_dir / "csv"
        db_path = tmp_dir / "game_log.sqlite3"

        env = TowerDefenseEnv()
        env.reset(seed=SEED)
        logger = GameLogger(mode="manual", session_id=1, output_dir=csv_dir)

        render_state = env.get_render_state()
        render_state["selected_plant"] = "sunflower"
        render_state["selected_plant_name"] = "Sunflower"
        render_state["selected_plant_hotkey"] = "W"
        render_state["selected_plant_cost"] = env.current_tower_cost("sunflower")
        render_state["selected_plant_cooldown"] = 0.0
        render_state["selected_plant_ready"] = True
        render_state["selected_plant_status"] = "Ready"
        render_state["valid_actions_count"] = len(env.valid_actions())

        logger.log_step(
            tick=int(render_state["tick"]),
            time=float(render_state["time"]),
            resources=int(render_state["resources"]),
            base_hp=int(render_state["base_hp"]),
            action_id=0,
            reward=0.0,
            done=False,
            valid=True,
            state=render_state,
        )

        summary = logger.build_session_summary(result="aborted", state=render_state, seed=SEED)
        logger.set_session_summary(summary)
        csv_path = logger.save_csv()
        json_path = logger.save_json()

        with csv_path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert rows, "CSV logger should still write at least one row"
        csv_row = rows[0]
        for field in (
            "wave_id",
            "wave_state",
            "wave_modifier",
            "active_upgrades",
            "pending_upgrade_options",
            "modifiers",
            "selected_plant",
            "valid_actions_count",
            "map_effect_summary",
        ):
            assert field in csv_row, f"CSV should contain the new {field} field"
        assert csv_row["selected_plant"] == "sunflower", "CSV should preserve selected_plant"

        with json_path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        assert payload["summary"]["seed"] == SEED, "JSON summary should persist the episode seed"
        assert payload["summary"]["selected_upgrades"] == render_state["active_upgrades"], "JSON summary should persist selected upgrades"

        db = GameDatabase(db_path=db_path)
        try:
            session_id = db.create_session("manual")
            db.record_session(
                session_id,
                "aborted",
                int(render_state["score"]),
                float(render_state["time"]),
                logger.to_rows(),
                session_summary=summary,
            )

            conn = sqlite3.connect(db_path)
            try:
                session_row = conn.execute(
                    """
                    SELECT victory, final_wave, total_kills, final_score, selected_upgrades, seed
                    FROM game_sessions
                    WHERE id = ?
                    """,
                    (session_id,),
                ).fetchone()
                assert session_row is not None, "game_sessions should store the final session row"
                assert session_row[1] == int(render_state["wave_id"]), "game_sessions should store final_wave"
                assert session_row[5] == SEED, "game_sessions should store the seed"

                tick_row = conn.execute(
                    """
                    SELECT wave_id, wave_state, wave_modifier, active_upgrades, pending_upgrade_options, modifiers, selected_plant, valid_actions_count, map_effect_summary
                    FROM game_ticks
                    WHERE session_id = ?
                    """,
                    (session_id,),
                ).fetchone()
                assert tick_row is not None, "game_ticks should store the expanded per-step columns"
                assert tick_row[0] == int(render_state["wave_id"]), "game_ticks should store wave_id"
                assert tick_row[1] == render_state["wave_state"], "game_ticks should store wave_state"
                assert tick_row[6] == "sunflower", "game_ticks should store selected_plant"
                assert tick_row[7] == len(env.valid_actions()), "game_ticks should store valid_actions_count"
            finally:
                conn.close()
        finally:
            db.close()

    print("[logging] logger/database expanded fields passed")


def run_external_qlearning_test(env: FastCompatibilityEnv, pvzlib_symbols: dict[str, object]) -> None:
    QLearningAgent = pvzlib_symbols["QLearningAgent"]
    QLearningConfig = pvzlib_symbols["QLearningConfig"]
    evaluate_q = pvzlib_symbols["evaluate_q"]
    tail_mean = pvzlib_symbols["tail_mean"]
    train_q_learning = pvzlib_symbols["train_q_learning"]

    agent = QLearningAgent(QLearningConfig(seed=SEED))

    print(f"Training Q-learning for {TRAIN_EPISODES} episodes...")
    train_curve = train_q_learning(env, agent, episodes=TRAIN_EPISODES)
    train_tail_avg = tail_mean(train_curve, n=TAIL_WINDOW)

    print(f"Evaluating greedy policy for {EVAL_EPISODES} episodes...")
    greedy_eval_avg = evaluate_q(env, agent, episodes=EVAL_EPISODES)

    print("\n=== Compatibility Report ===")
    print(f"Seed: {SEED}")
    print(f"Training episodes: {TRAIN_EPISODES}")
    print(f"Evaluation episodes: {EVAL_EPISODES}")
    print(f"Training tail average reward (last {min(TAIL_WINDOW, len(train_curve))} episodes): {train_tail_avg:.3f}")
    print(f"Greedy evaluation average reward: {greedy_eval_avg:.3f}")
    print(f"Final epsilon: {agent.epsilon:.4f}")
    print(f"Reward mean across all training episodes: {mean(train_curve):.3f}")


def main() -> None:
    random.seed(SEED)

    env = build_env()
    print("Running compatibility smoke suite...")
    run_compatibility_smoke_report()
    print("\nRunning compatibility regression checks...")
    smoke_test(env)
    interface_contract_test(env)
    rule_based_state_dict_test()
    map_effect_manager_test()
    entity_profile_test()
    sunflower_economy_test()
    enemy_spawn_type_test()
    wave_manager_contract_test()
    wave_modifier_reproducibility_test()
    upgrade_manager_smoke_test()
    upgrade_effect_application_test()
    plant_damage_test()
    wave_victory_test()
    wave_state_flow_test()
    logger_database_smoke_test()

    pvzlib_symbols = load_pvzlib()
    if pvzlib_symbols is None:
        print("pvzlib not found, skipped external Q-learning compatibility test.")
        return

    env.reset(seed=SEED)
    run_external_qlearning_test(env, pvzlib_symbols)


if __name__ == "__main__":
    main()
