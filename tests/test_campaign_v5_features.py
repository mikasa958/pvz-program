from __future__ import annotations

from collections import Counter

from config import build_campaign_v5_config
from enemy import Enemy
from env import TowerDefenseEnv
from tower import Tower
from waves import WaveManager


SEED = 42


def _campaign_manager(seed: int) -> WaveManager:
    manager = WaveManager(build_campaign_v5_config(seed=seed))
    manager.reset(seed)
    return manager


def _spawn_type_counts(wave) -> Counter[str]:
    return Counter(spawn.enemy_type_id for spawn in wave.spawns)


def _arm_wave_advance_ready(env: TowerDefenseEnv) -> None:
    env.wave_advance_armed = True
    env.wave_advance_countdown = 0.0
    env.wave_spawn_locked = True
    env._sync_campaign_clear_field_wait()


def _paused_campaign_env() -> TowerDefenseEnv:
    env = TowerDefenseEnv(build_campaign_v5_config(seed=SEED))
    env.wave_state = "waiting"
    env.current_wave = None
    env.pending_wave_spawns = []
    env.wave_manager.finish_current_wave()
    return env


def test_campaign_v5_opening_grace_is_fifteen_seconds() -> None:
    env = TowerDefenseEnv(build_campaign_v5_config(seed=SEED))
    assert env.config.opening_grace_seconds == 15.0

    env.advance_world(14.9)
    assert len(env.enemies) == 0
    assert env.get_render_state()["opening_grace_remaining"] == 0.1

    env.advance_world(0.1)
    assert env.get_render_state()["opening_grace_remaining"] == 0.0
    assert len(env.enemies) >= 1


def test_campaign_v5_wallnut_rolls_right_on_death_and_deals_100_damage() -> None:
    env = _paused_campaign_env()
    row = 2
    cell_size = env.config.cell_size
    origin_x = env.config.grid_origin_x
    origin_y = env.config.grid_origin_y + row * cell_size + (cell_size - env.config.enemy_height) / 2

    nut = Tower(
        uid="nut_roll",
        row=row,
        col=2,
        plant_type="wallnut",
        tower_type="wallnut",
        width=env.config.tower_width,
        height=env.config.tower_height,
        hp=1.0,
        max_hp=1.0,
    )
    env.towers = [nut]
    nut_rect = nut.rect(env.config)
    env.enemies = [
        Enemy(
            uid="z_ahead",
            row=row,
            x=float(origin_x + cell_size * 5),
            y=float(origin_y),
            hp=200.0,
            max_hp=200.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=10,
            enemy_type="normal",
        ),
        Enemy(
            uid="z_far",
            row=row,
            x=float(origin_x + cell_size * 6),
            y=float(origin_y),
            hp=200.0,
            max_hp=200.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=10,
            enemy_type="normal",
        ),
        Enemy(
            uid="z_eater",
            row=row,
            x=float(nut_rect.right - env.config.enemy_width),
            y=float(origin_y),
            hp=500.0,
            max_hp=500.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=10,
            enemy_type="normal",
            attack_damage=50.0,
            attack_cooldown_left=0.0,
        ),
    ]

    for _ in range(120):
        env.advance_world(1.0 / 60.0)
        if not any(tower.uid == "nut_roll" for tower in env.towers):
            break

    assert not any(tower.uid == "nut_roll" for tower in env.towers)
    assert len(env.rolling_wallnuts) == 1
    assert env.rolling_wallnuts[0].damage == 100

    for _ in range(300):
        env.advance_world(1.0 / 60.0)
        if not env.rolling_wallnuts:
            break

    z_ahead = next(enemy for enemy in env.enemies if enemy.uid == "z_ahead")
    z_far = next(enemy for enemy in env.enemies if enemy.uid == "z_far")
    assert z_ahead.hp == 100.0
    assert z_far.hp == 100.0
    assert not env.rolling_wallnuts


def test_campaign_v5_pole_vaulter_jumps_first_of_two_adjacent_plants() -> None:
    env = _paused_campaign_env()
    row = 2
    cell_size = env.config.cell_size
    origin_x = env.config.grid_origin_x
    origin_y = env.config.grid_origin_y + row * cell_size + (cell_size - env.config.enemy_height) / 2

    env.towers = [
        Tower(uid="nut_0", row=row, col=0, plant_type="wallnut", tower_type="wallnut", width=52, height=52),
        Tower(uid="nut_1", row=row, col=1, plant_type="wallnut", tower_type="wallnut", width=52, height=52),
    ]
    pole_x = float(origin_x + cell_size * 2)
    env.enemies = [
        Enemy(
            uid="pole_test",
            row=row,
            x=pole_x,
            y=float(origin_y),
            hp=290.0,
            max_hp=290.0,
            speed=32.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=25,
            enemy_type="pole_vaulting",
        )
    ]

    for _ in range(120):
        env.advance_world(1.0 / 60.0)
        if env.enemies[0].has_used_jump:
            break

    pole = env.enemies[0]
    assert pole.has_used_jump is True
    assert pole.x < float(origin_x + cell_size) - 4.0
    assert any(tower.col == 0 and tower.is_alive() for tower in env.towers)


def test_campaign_v5_base_hp_is_six() -> None:
    env = TowerDefenseEnv(build_campaign_v5_config(seed=SEED))
    assert env.base_hp == 6
    assert env.base_max_hp == 6


def test_campaign_v5_sun_auto_collects_after_two_seconds() -> None:
    env = TowerDefenseEnv(build_campaign_v5_config(seed=SEED))
    env.manual_upgrade_selection = True
    assert env.config.sun_drop_auto_collect_delay == 2.0

    env._spawn_sun_drop(amount=25, source="sky")
    assert len(env.sun_drops) == 1
    assert env.resources == 150

    env.advance_world(1.9)
    assert len(env.sun_drops) == 1
    assert env.resources == 150

    env.advance_world(0.2)
    assert len(env.sun_drops) <= 1
    assert env.resources == 150

    env.advance_world(0.6)
    assert env.resources == 175
    assert len(env.sun_drops) == 0


def test_campaign_v5_has_fifteen_waves_and_four_checkpoints() -> None:
    manager = _campaign_manager(SEED)
    assert len(manager.waves) == 15
    checkpoint_ids = {wave.wave_id for wave in manager.waves if wave.checkpoint_upgrade}
    assert checkpoint_ids == {4, 7, 10, 13}
    clear_before_start = {wave.wave_id for wave in manager.waves if wave.start_requires_clear_field}
    assert clear_before_start == {8, 14}


def test_campaign_v5_wave_totals_match_spec_ranges() -> None:
    manager = _campaign_manager(SEED)
    expected_ranges = {
        1: (2, 2),
        2: (2, 2),
        3: (4, 4),
        4: (3, 5),
        5: (4, 6),
        6: (7, 9),
        7: (9, 11),
        8: (14, 16),
        9: (18, 20),
        10: (14, 16),
        11: (14, 16),
        12: (15, 18),
        13: (15, 18),
        14: (18, 20),
        15: (35, 35),
    }
    for wave in manager.waves:
        low, high = expected_ranges[wave.wave_id]
        assert low <= wave.enemy_count <= high, f"wave {wave.wave_id} total {wave.enemy_count} out of range"


def test_campaign_v5_w2_includes_pole_and_normal() -> None:
    manager = _campaign_manager(SEED)
    counts = _spawn_type_counts(manager.waves[1])
    assert counts["normal"] == 1
    assert counts["pole_vaulting"] == 1


def test_campaign_v5_w9_includes_fixed_pole_and_normal() -> None:
    manager = _campaign_manager(SEED)
    wave = manager.waves[8]
    counts = _spawn_type_counts(wave)
    assert counts["normal"] >= 8
    assert counts["pole_vaulting"] >= 4
    assert 18 <= wave.enemy_count <= 20


def test_campaign_v5_w15_fixed_recipe() -> None:
    manager = _campaign_manager(SEED)
    wave = manager.waves[14]
    counts = _spawn_type_counts(wave)
    assert counts["normal"] == 8
    assert counts["pole_vaulting"] == 12
    assert counts["buckethead"] == 15
    assert wave.enemy_count == 35
    assert wave.random_slots == 0


def test_campaign_v5_overlapping_waves_without_clear_field() -> None:
    env = _paused_campaign_env()
    env.current_wave = env.wave_manager.waves[0]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 0
    env.wave_manager.pending_spawns = []
    env.wave_manager.active = True
    env.wave_state = "active"
    env.enemies = [
        Enemy(
            uid="linger",
            row=0,
            x=float(env.config.grid_origin_x + env.config.cell_size * 4),
            y=float(env.config.grid_origin_y),
            hp=50.0,
            max_hp=50.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=1,
            enemy_type="normal",
        )
    ]

    _arm_wave_advance_ready(env)
    assert env._wave_progress_ready() is True
    env._resolve_wave_progression()
    assert env.wave_manager.current_wave_index == 1
    assert any(enemy.uid == "linger" for enemy in env.enemies)


def test_campaign_v5_wave_advances_after_hp_damage_threshold() -> None:
    env = TowerDefenseEnv(build_campaign_v5_config(seed=SEED))
    env.reset(SEED)
    assert env.wave_damage_threshold > 0.0
    assert 35.0 <= env.wave_hp_threshold_ratio * 100.0 <= 50.0

    env.wave_damage_dealt = env.wave_damage_threshold
    env._arm_wave_advance()
    assert env.wave_spawn_locked is True
    assert env.wave_manager.remaining_spawns() == 0

    env.advance_world(3.0)
    assert env.wave_advance_countdown == 0.0
    assert env.wave_manager.current_wave_index == 1
    assert len(env.enemies) >= 1


def test_campaign_v5_empty_field_shortens_wave_advance_countdown() -> None:
    env = _paused_campaign_env()
    env.current_wave = env.wave_manager.waves[0]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 0
    env.wave_manager.active = True
    env.wave_state = "active"
    env.enemies = []
    env._init_campaign_wave_hp_tracking()
    env.wave_damage_dealt = env.wave_damage_threshold

    env._arm_wave_advance()
    assert env.wave_advance_countdown == env.config.wave_advance_empty_field_delay_seconds

    env.advance_world(env.config.wave_advance_empty_field_delay_seconds)
    assert env.wave_advance_countdown == 0.0
    assert env.wave_manager.current_wave_index == 1


def test_campaign_v5_field_clear_during_countdown_snaps_to_fast_delay() -> None:
    env = _paused_campaign_env()
    env.current_wave = env.wave_manager.waves[0]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 0
    env.wave_manager.active = True
    env.wave_state = "active"
    env.enemies = [
        Enemy(
            uid="linger",
            row=0,
            x=float(env.config.grid_origin_x + env.config.cell_size * 4),
            y=float(env.config.grid_origin_y),
            hp=50.0,
            max_hp=50.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=1,
            enemy_type="normal",
        )
    ]
    env._init_campaign_wave_hp_tracking()
    env.wave_damage_dealt = env.wave_damage_threshold
    env._arm_wave_advance()
    assert env.wave_advance_countdown == env.config.wave_advance_delay_seconds

    env.enemies = []
    env.advance_world(0.0)
    assert env.wave_advance_countdown == env.config.wave_advance_empty_field_delay_seconds
    assert env.wave_advance_countdown < env.config.wave_advance_delay_seconds


def test_campaign_v5_spawns_within_3s_after_hp_threshold_without_clear_gate() -> None:
    env = _paused_campaign_env()
    env.current_wave = env.wave_manager.waves[0]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 0
    env.wave_manager.active = True
    env.wave_state = "active"
    env._init_campaign_wave_hp_tracking()
    env.wave_damage_dealt = env.wave_damage_threshold
    env._arm_wave_advance()
    before = len(env.enemies)

    env.advance_world(3.0)

    assert env.wave_advance_countdown == 0.0
    assert env.campaign_waiting_clear_field is False
    assert env.wave_manager.current_wave_index == 1
    assert len(env.enemies) > before


def test_campaign_v5_clear_field_blocks_until_empty_then_spawns_immediately() -> None:
    env = _paused_campaign_env()
    env.current_wave = env.wave_manager.waves[6]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 6
    env.wave_manager.active = True
    env.wave_state = "active"
    env.enemies = [
        Enemy(
            uid="linger",
            row=0,
            x=float(env.config.grid_origin_x + env.config.cell_size * 4),
            y=float(env.config.grid_origin_y),
            hp=50.0,
            max_hp=50.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=1,
            enemy_type="normal",
            spawn_wave_id=7,
        )
    ]
    env.wave_damage_dealt = env.wave_damage_threshold
    env._arm_wave_advance()
    env.advance_world(3.0)

    assert env.campaign_waiting_clear_field is True
    assert env.wave_state == "waiting_clear"
    assert env.wave_manager.current_wave_index == 6
    assert not env._wave_progress_ready()

    env.enemies = []
    env.advance_world(0.1)

    assert env.campaign_waiting_clear_field is False
    assert env.wave_manager.current_wave_index == 7
    assert len(env.enemies) >= 1


def test_campaign_v5_final_wave_requires_field_clear_before_victory() -> None:
    env = _paused_campaign_env()
    final_wave = env.wave_manager.waves[-1]
    assert final_wave.wave_id == 15

    env.current_wave = final_wave
    env.wave_manager.current_wave = final_wave
    env.wave_manager.current_wave_index = len(env.wave_manager.waves) - 1
    env.wave_manager.active = True
    env.wave_state = "active"
    env.waves_cleared = env.total_waves - 1
    env.enemies = [
        Enemy(
            uid="w15_linger",
            row=2,
            x=float(env.config.grid_origin_x + env.config.cell_size * 6),
            y=float(env.config.grid_origin_y + 2 * env.config.cell_size),
            hp=200.0,
            max_hp=200.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=10,
            enemy_type="normal",
            spawn_wave_id=15,
        )
    ]
    env._init_campaign_wave_hp_tracking()
    env.wave_damage_dealt = env.wave_damage_threshold
    env._arm_wave_advance()
    env.wave_advance_countdown = 0.0

    assert env._campaign_wave_progress_ready() is False
    assert env.victory is False

    env.enemies = []
    assert env._campaign_wave_progress_ready() is True

    reward = env._resolve_wave_progression()
    assert reward > 0.0
    assert env.victory is True
    assert env.waves_cleared == env.total_waves


def test_campaign_v5_clear_field_required_before_wave_fourteen() -> None:
    env = _paused_campaign_env()
    env.current_wave = env.wave_manager.waves[12]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 12
    env.wave_manager.pending_spawns = []
    env.wave_manager.active = True
    env.wave_state = "active"
    env.enemies = [
        Enemy(
            uid="linger",
            row=0,
            x=float(env.config.grid_origin_x + env.config.cell_size * 4),
            y=float(env.config.grid_origin_y),
            hp=50.0,
            max_hp=50.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=1,
            enemy_type="normal",
        )
    ]

    _arm_wave_advance_ready(env)
    assert env.campaign_waiting_clear_field is True
    assert not env._wave_progress_ready()
    env.enemies = []
    env._sync_campaign_clear_field_wait()
    assert env.campaign_waiting_clear_field is False
    assert env._wave_progress_ready() is True


def test_campaign_v5_spawn_lanes_are_balanced_and_not_always_low_rows() -> None:
    row_sets: set[tuple[int, ...]] = set()
    for seed in range(30):
        manager = _campaign_manager(seed)
        wave_one_rows = tuple(spawn.row for spawn in manager.waves[0].spawns)
        row_sets.add(wave_one_rows)
        row_counts = [0 for _ in range(5)]
        for wave in manager.waves:
            if wave.enemy_count < 5:
                continue
            for spawn in wave.spawns:
                row_counts[spawn.row] += 1
            low = min(row_counts)
            high = max(row_counts)
            assert high - low <= 1, f"seed {seed} wave {wave.wave_id} lane gap {high - low}"
            break

    assert len(row_sets) >= 3, "wave 1 lanes should vary across seeds, not always the same rows"


def test_campaign_v5_spawn_times_are_not_perfectly_uniform() -> None:
    manager = _campaign_manager(SEED)
    varied_gaps = False
    for wave in manager.waves:
        if wave.enemy_count < 4:
            continue
        spawn_times = [float(spawn.spawn_at or 0.0) for spawn in wave.spawns]
        gaps = [spawn_times[index + 1] - spawn_times[index] for index in range(len(spawn_times) - 1)]
        if len(set(round(gap, 3) for gap in gaps)) > 1:
            varied_gaps = True
            break
    assert varied_gaps, "campaign spawns should use uneven randomized gaps"


def test_campaign_v5_wave_advances_when_field_empty_without_hp_threshold() -> None:
    """Regression: breach/leak clears the field without registering wave damage."""
    env = _paused_campaign_env()
    env.current_wave = env.wave_manager.waves[0]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 0
    env.wave_manager.pending_spawns = []
    env.wave_manager.active = True
    env.wave_state = "active"
    env.enemies = []
    env.wave_advance_armed = False
    env.wave_spawn_locked = False
    env._init_campaign_wave_hp_tracking()
    assert env.wave_damage_dealt == 0.0
    assert env.wave_damage_threshold > 0.0

    assert env._wave_progress_ready() is True
    env._resolve_wave_progression()
    assert env.wave_manager.current_wave_index == 1
    assert env.wave_manager.is_wave_active() is True


def test_campaign_v5_manual_upgrade_resumes_active_wave_spawns() -> None:
    env = _paused_campaign_env()
    env.current_wave = env.wave_manager.waves[3]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 3
    env.wave_manager.pending_spawns = list(env.current_wave.spawns)
    env.wave_manager.active = True
    env.wave_state = "upgrade"
    env.waves_cleared = 4
    env.manual_upgrade_selection = True
    env._set_pending_upgrade_options(env.upgrade_manager.roll_options(3))
    assert env._placement_locked()

    assert env.select_upgrade(option_index=0) is True
    assert env.wave_state == "active"
    assert not env._placement_locked()
    assert env._should_run_wave_spawns() is True

    assert env.wave_manager.remaining_spawns() > 0
    env.advance_world(7.0)
    assert env.wave_manager.remaining_spawns() < len(env.current_wave.spawns)


def test_campaign_v5_clear_field_required_before_wave_eight() -> None:
    env = _paused_campaign_env()
    env.current_wave = env.wave_manager.waves[6]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 6
    env.wave_manager.pending_spawns = []
    env.wave_manager.active = True
    env.wave_state = "active"
    env.enemies = [
        Enemy(
            uid="linger",
            row=0,
            x=float(env.config.grid_origin_x + env.config.cell_size * 4),
            y=float(env.config.grid_origin_y),
            hp=50.0,
            max_hp=50.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=1,
            enemy_type="normal",
        )
    ]

    _arm_wave_advance_ready(env)
    assert env.campaign_waiting_clear_field is True
    assert not env._wave_progress_ready()
    env.enemies = []
    env._sync_campaign_clear_field_wait()
    assert env.campaign_waiting_clear_field is False
    assert env._wave_progress_ready() is True


if __name__ == "__main__":
    tests = [
        test_campaign_v5_opening_grace_is_fifteen_seconds,
        test_campaign_v5_wallnut_rolls_right_on_death_and_deals_100_damage,
        test_campaign_v5_pole_vaulter_jumps_first_of_two_adjacent_plants,
        test_campaign_v5_base_hp_is_six,
        test_campaign_v5_sun_auto_collects_after_two_seconds,
        test_campaign_v5_has_fifteen_waves_and_four_checkpoints,
        test_campaign_v5_wave_totals_match_spec_ranges,
        test_campaign_v5_w2_includes_pole_and_normal,
        test_campaign_v5_w9_includes_fixed_pole_and_normal,
        test_campaign_v5_w15_fixed_recipe,
        test_campaign_v5_overlapping_waves_without_clear_field,
        test_campaign_v5_wave_advances_after_hp_damage_threshold,
        test_campaign_v5_empty_field_shortens_wave_advance_countdown,
        test_campaign_v5_field_clear_during_countdown_snaps_to_fast_delay,
        test_campaign_v5_spawns_within_3s_after_hp_threshold_without_clear_gate,
        test_campaign_v5_clear_field_blocks_until_empty_then_spawns_immediately,
        test_campaign_v5_spawn_lanes_are_balanced_and_not_always_low_rows,
        test_campaign_v5_spawn_times_are_not_perfectly_uniform,
        test_campaign_v5_wave_advances_when_field_empty_without_hp_threshold,
        test_campaign_v5_manual_upgrade_resumes_active_wave_spawns,
        test_campaign_v5_clear_field_required_before_wave_eight,
        test_campaign_v5_final_wave_requires_field_clear_before_victory,
        test_campaign_v5_clear_field_required_before_wave_fourteen,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
