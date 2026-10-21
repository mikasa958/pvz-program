from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import random
import subprocess
import sys


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config import (
    _scale_enemy_hp,
    build_campaign_v5_config,
    build_training_easy_config,
    build_training_stage_0_config,
)
from env import (
    ACTION_CHOOSE_UPGRADE_OFFSET,
    ACTION_WAIT,
    TRAINING_CARD_COOLDOWN_START,
    TRAINING_PENDING_UPGRADE_START,
    TRAINING_STATE_VECTOR_SIZE,
    TRAINING_STATE_VERSION,
    TowerDefenseEnv,
    action_dict_to_id,
)
from rl_training import (
    MACRO_ACTION_SIZE,
    MACRO_ACTION_WAIT,
    MACRO_PLACE_PEA_ROW_OFFSET,
    TRAINING_COMPACT_STATE_SIZE,
    encode_training_state_compact,
    macro_to_legacy_action_id,
    macro_valid_actions,
)
from tower import Tower
from training_adapter import FastCompatibilityEnv
from upgrades import upgrade_definitions_from_config


SEED = 42


def _build_fast_clear_env(*, auto_select_upgrades: bool) -> FastCompatibilityEnv:
    stage_config = build_training_stage_0_config(seed=SEED)
    enemy_scale = 5.0 / 270.0 if auto_select_upgrades else 1.0
    config = replace(
        stage_config,
        auto_select_upgrades=auto_select_upgrades,
        total_waves=2,
        wave_base_enemy_count=1 if auto_select_upgrades else 2,
        wave_enemy_count_step=0,
        enemy_spawn_interval=0.35 if auto_select_upgrades else 1.0,
        tower_range_cells=9,
        tower_cooldown=0.25,
        resource_income_per_second=0,
        game_duration=60.0,
        training_action_mode="full",
        enemy_config=_scale_enemy_hp(stage_config, enemy_scale),
    )
    return FastCompatibilityEnv(TowerDefenseEnv(config), seed=SEED, step_dt=0.5, state_mode="training")


def _clear_first_wave(env: FastCompatibilityEnv, *, expect_upgrade: bool) -> list[dict[str, object]]:
    env.reset(seed=SEED)
    preview_rows = env.get_render_state()["wave"]["current"]["preview_rows"]
    target_row = int(preview_rows[0])
    place_action = action_dict_to_id(
        {
            "action_type": "place_tower",
            "plant_type": "pea_shooter",
            "row": target_row,
            "col": 0,
        }
    )
    env.step(place_action)

    pending_options: list[dict[str, object]] = []
    for _ in range(80):
        _, _, done, info = env.step(ACTION_WAIT)
        pending_options = env.get_render_state().get("pending_upgrade_options", [])
        if expect_upgrade and env.base_env.wave_state == "upgrade":
            break
        if not expect_upgrade and (done or env.get_render_state()["wave_id"] >= 2):
            break
        if info.get("auto_selected_upgrade") is not None:
            break
    return pending_options


def test_auto_select_upgrades_skips_upgrade_state() -> None:
    env = _build_fast_clear_env(auto_select_upgrades=True)
    env.reset(seed=SEED)

    preview_rows = env.get_render_state()["wave"]["current"]["preview_rows"]
    place_action = action_dict_to_id(
        {
            "action_type": "place_tower",
            "plant_type": "pea_shooter",
            "row": int(preview_rows[0]),
            "col": 0,
        }
    )
    env.step(place_action)

    auto_selected_upgrade = None
    for _ in range(80):
        _, _, done, info = env.step(ACTION_WAIT)
        if info.get("auto_selected_upgrade") is not None:
            auto_selected_upgrade = str(info["auto_selected_upgrade"])
        if done or env.get_render_state()["wave_id"] >= 2:
            break

    assert auto_selected_upgrade is not None or len(env.base_env.applied_upgrades) >= 1
    assert env.base_env.wave_state != "upgrade"
    assert env.base_env.pending_upgrade_options == []


def test_manual_upgrade_flow_with_auto_select_disabled() -> None:
    env = _build_fast_clear_env(auto_select_upgrades=False)
    pending_options = _clear_first_wave(env, expect_upgrade=True)

    assert env.base_env.wave_state == "upgrade"
    assert len(pending_options) == 3
    assert env.valid_actions() == [
        ACTION_WAIT,
        ACTION_CHOOSE_UPGRADE_OFFSET,
        ACTION_CHOOSE_UPGRADE_OFFSET + 1,
        ACTION_CHOOSE_UPGRADE_OFFSET + 2,
    ]

    _, _, _, info = env.step(ACTION_CHOOSE_UPGRADE_OFFSET)
    assert info["invalid_action"] is False
    assert env.base_env.wave_state == "active"


def test_training_state_fixed_and_distinguishes_plants() -> None:
    config = build_training_easy_config(seed=SEED)

    pea_env = TowerDefenseEnv(config)
    pea_env.reset(seed=SEED)
    pea_env.towers = [Tower(uid="pea", row=0, col=0, plant_type="pea_shooter", tower_type="basic", width=52, height=52)]

    sunflower_env = TowerDefenseEnv(config)
    sunflower_env.reset(seed=SEED)
    sunflower_env.towers = [Tower(uid="sun", row=0, col=0, plant_type="sunflower", tower_type="sunflower", width=52, height=52)]

    pea_state = pea_env.get_training_state()
    sunflower_state = sunflower_env.get_training_state()
    assert len(pea_state) == TRAINING_STATE_VECTOR_SIZE
    assert len(sunflower_state) == TRAINING_STATE_VECTOR_SIZE
    assert pea_state != sunflower_state


def test_training_state_tracks_cooldowns_and_pending_upgrades() -> None:
    config = replace(build_training_easy_config(seed=SEED), auto_select_upgrades=False)
    env = TowerDefenseEnv(config)
    env.reset(seed=SEED)

    before_state = env.get_training_state()
    assert before_state[TRAINING_CARD_COOLDOWN_START] == 0

    env.apply_action(action_dict_to_id({"action_type": "place_tower", "plant_type": "pea_shooter", "row": 0, "col": 0}))
    cooldown_state = env.get_training_state()
    assert cooldown_state[TRAINING_CARD_COOLDOWN_START] > 0

    definitions = upgrade_definitions_from_config(config)
    env.wave_state = "upgrade"
    env._set_pending_upgrade_options(
        [
            definitions["damage_up"],
            definitions["cost_down"],
            definitions["sun_up"],
        ]
    )
    upgrade_state = env.get_training_state()
    assert all(upgrade_state[index] > 0 for index in range(TRAINING_PENDING_UPGRADE_START, TRAINING_PENDING_UPGRADE_START + 3))


def test_fast_compat_env_training_mode_info() -> None:
    config = build_training_easy_config(seed=SEED)
    env = FastCompatibilityEnv(TowerDefenseEnv(config), seed=SEED, step_dt=1.0, state_mode="training")

    state = env.reset(seed=SEED)
    assert len(state) == TRAINING_STATE_VECTOR_SIZE

    next_state, _, _, info = env.step(ACTION_WAIT)
    assert len(next_state) == TRAINING_STATE_VECTOR_SIZE
    assert info["state_mode"] == "training"
    assert info["training_state_size"] == TRAINING_STATE_VECTOR_SIZE
    assert info["training_state_version"] == TRAINING_STATE_VERSION


def test_build_training_easy_config_is_usable() -> None:
    config = build_training_easy_config(seed=SEED)
    assert config.auto_select_upgrades is True
    assert config.reward_preset == "training"
    assert config.max_episode_steps == 1000

    env = FastCompatibilityEnv(TowerDefenseEnv(config), seed=SEED, step_dt=1.0, state_mode="training")
    state = env.reset(seed=SEED)
    assert len(state) == TRAINING_STATE_VECTOR_SIZE


def test_valid_action_sample_never_invalid() -> None:
    env = FastCompatibilityEnv(TowerDefenseEnv(build_training_easy_config(seed=SEED)), seed=SEED, step_dt=1.0, state_mode="training")
    env.reset(seed=SEED)

    rng = random.Random(SEED)
    for _ in range(30):
        valid_actions = env.valid_actions()
        action = rng.choice(valid_actions)
        _, _, done, info = env.step(action)
        assert info["invalid_action"] is False
        if done:
            break


def test_invalid_actions_are_stable() -> None:
    env = TowerDefenseEnv(build_training_easy_config(seed=SEED))
    env.reset(seed=SEED)

    _, reward, done, info = env.step(999999)
    assert done is False
    assert reward <= 0
    assert info["invalid_action"] is True
    assert info["reward_breakdown"]["invalid_action"] == env.config.reward_invalid_action

    env.reset(seed=SEED)
    env.resources = max(0, env.current_tower_cost("pea_shooter") - 1)
    _, _, _, info = env.step(action_dict_to_id({"action_type": "place_tower", "plant_type": "pea_shooter", "row": 0, "col": 0}))
    assert info["invalid_action"] is True
    assert info["action_reason"] == "RESOURCE_NOT_ENOUGH"

    env.reset(seed=SEED)
    first_action = action_dict_to_id({"action_type": "place_tower", "plant_type": "pea_shooter", "row": 0, "col": 0})
    env.step(first_action)
    env.resources = 500
    _, _, _, info = env.step(action_dict_to_id({"action_type": "place_tower", "plant_type": "pea_shooter", "row": 0, "col": 1}))
    assert info["invalid_action"] is True
    assert info["action_reason"] == "CARD_COOLDOWN"

    env.reset(seed=SEED)
    definitions = upgrade_definitions_from_config(env.config)
    env.wave_state = "upgrade"
    env._set_pending_upgrade_options([definitions["damage_up"]])
    _, _, _, info = env.step(first_action)
    assert info["invalid_action"] is True
    assert info["action_reason"] == "UPGRADE_SELECTION_PENDING"

    env.reset(seed=SEED)
    _, _, _, info = env.step(ACTION_CHOOSE_UPGRADE_OFFSET)
    assert info["invalid_action"] is True
    assert info["action_reason"] == "NO_UPGRADE_PENDING"


def test_max_episode_steps_truncates() -> None:
    config = replace(build_training_easy_config(seed=SEED), max_episode_steps=3)
    env = FastCompatibilityEnv(TowerDefenseEnv(config), seed=SEED, step_dt=0.0, state_mode="training")
    env.reset(seed=SEED)

    info: dict[str, object] = {}
    done = False
    for _ in range(5):
        _, _, done, info = env.step(ACTION_WAIT)
        if done:
            break

    assert done is True
    assert info["episode_truncated"] is True
    assert info["termination_reason"] == "max_episode_steps"


def test_reward_breakdown_has_key_items() -> None:
    env = TowerDefenseEnv(build_training_easy_config(seed=SEED))
    env.reset(seed=SEED)

    placement_action = action_dict_to_id({"action_type": "place_tower", "plant_type": "pea_shooter", "row": 0, "col": 0})
    _, _, _, info = env.step(placement_action)
    assert "valid_placement" in info["reward_breakdown"]
    assert info["reward_breakdown"]["valid_placement"] >= env.config.reward_valid_placement
    assert info["reward_breakdown"]["invalid_action"] == 0.0

    _, _, _, wait_info = env.step(ACTION_WAIT)
    assert "survive" in wait_info["reward_breakdown"]
    assert "terminal" in wait_info["reward_breakdown"]


def test_campaign_config_keeps_full_action_mode() -> None:
    config = build_campaign_v5_config(seed=SEED)
    assert config.training_action_mode == "full"
    assert config.reward_clamp_terminal_separately is False
    assert config.reward_valid_placement_front_bonus == 0.0


def test_compact_state_size_and_macro_actions() -> None:
    config = build_training_stage_0_config(seed=SEED)
    env = TowerDefenseEnv(config)
    env.reset(seed=SEED)
    compact = encode_training_state_compact(env)
    assert len(compact) == TRAINING_COMPACT_STATE_SIZE

    adapter = FastCompatibilityEnv(env, seed=SEED, step_dt=1.0, state_mode="compact")
    adapter.reset(seed=SEED)
    macro_valid = adapter.valid_actions()
    assert MACRO_ACTION_WAIT in macro_valid
    assert all(0 <= action < MACRO_ACTION_SIZE for action in macro_valid)

    pea_macro = MACRO_PLACE_PEA_ROW_OFFSET
    if pea_macro in macro_valid:
        legacy = macro_to_legacy_action_id(env, pea_macro)
        assert legacy is not None


def test_training_terminal_reward_not_clamped_with_stage_config() -> None:
    config = build_training_stage_0_config(seed=SEED)
    env = FastCompatibilityEnv(TowerDefenseEnv(config), seed=SEED, step_dt=1.0, state_mode="compact")
    env.reset(seed=SEED)
    env.base_env.victory = True
    env.base_env.done = False
    reward = env.base_env._advance_world(0.0)
    assert reward >= config.reward_win


def test_smoke_training_script_runs() -> None:
    script_path = PROJECT_DIR / "scripts" / "train_q_table_smoke.py"
    env = os.environ.copy()
    env["TD_SMOKE_EPISODES"] = "3"
    completed = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(PROJECT_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "average_reward=" in completed.stdout
    assert "episode=00" in completed.stdout
