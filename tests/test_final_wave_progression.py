from dataclasses import replace

import pytest

from config import build_training_stage_0_config
from enemy import Enemy
from env import TowerDefenseEnv


@pytest.mark.parametrize("auto_select_upgrades", [False, True])
def test_final_training_wave_waits_for_remaining_enemies(auto_select_upgrades):
    config = replace(
        build_training_stage_0_config(seed=42),
        auto_select_upgrades=auto_select_upgrades,
    )
    env = TowerDefenseEnv(config)
    env.reset(seed=42)
    env.wave_manager.finish_current_wave()
    env.waves_cleared = 1
    env._start_next_wave()
    env.wave_manager.pending_spawns = []
    env.enemies = [
        Enemy(
            uid="last-enemy",
            row=0,
            x=float(config.grid_origin_x + config.cell_size * 4),
            y=float(config.grid_origin_y),
            hp=50.0,
            max_hp=50.0,
            speed=0.0,
            width=config.enemy_width,
            height=config.enemy_height,
            reward_score=1,
            enemy_type="normal",
        )
    ]

    assert env._resolve_wave_progression() == 0.0
    assert env.wave_state == "active"
    assert env.wave_manager.is_wave_active()
    assert env.waves_cleared == 1
    assert not env.pending_upgrade_options
    assert not env.victory

    env.enemies.clear()
    assert env._resolve_wave_progression() == config.reward_wave_clear
    assert env.wave_state == "finished"
    assert env.waves_cleared == 2
    assert env.victory
