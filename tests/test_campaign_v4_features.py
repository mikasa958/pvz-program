from __future__ import annotations

from collections import Counter

from config import build_campaign_v4_config
from enemy import Enemy
from env import Projectile, TowerDefenseEnv, action_dict_to_id
from tower import Tower
from waves import WaveManager


SEED = 42


def _arm_wave_advance_ready(env: TowerDefenseEnv) -> None:
    env.wave_advance_armed = True
    env.wave_advance_countdown = 0.0
    env.wave_spawn_locked = True


def _paused_campaign_env() -> TowerDefenseEnv:
    env = TowerDefenseEnv(build_campaign_v4_config(seed=SEED))
    env.wave_state = "waiting"
    env.current_wave = None
    env.pending_wave_spawns = []
    env.wave_manager.finish_current_wave()
    return env


def test_campaign_v4_manual_mode_keeps_bonus_sun_clickable() -> None:
    env = TowerDefenseEnv(build_campaign_v4_config(seed=SEED))
    env.manual_upgrade_selection = True

    env.advance_world(5.1)
    state = env.get_render_state()

    assert state["resources"] == 150
    assert len(state["sun_drops"]) == 1
    assert len(env.enemies) == 0


def test_campaign_v4_ai_mode_auto_collects_bonus_sun() -> None:
    env = _paused_campaign_env()
    env.manual_upgrade_selection = False
    start_resources = int(env.resources)
    env._spawn_sun_drop(amount=25, source="sky")

    env.advance_world(11.1)
    state = env.get_render_state()

    assert state["resources"] >= start_resources + 25
    assert len(state["sun_drops"]) == 0
    assert len(env.enemies) == 0


def test_campaign_v4_first_enemy_waits_for_opening_grace() -> None:
    env = TowerDefenseEnv(build_campaign_v4_config(seed=SEED))

    env.advance_world(14.9)
    assert len(env.enemies) == 0
    assert env.get_render_state()["opening_grace_remaining"] == 0.1

    env.advance_world(0.1)
    state = env.get_render_state()
    assert len(env.enemies) == 1
    assert state["opening_grace_remaining"] == 0.0
    assert int(state["wave_id"]) >= 1


def test_campaign_v4_pea_shooter_fires_projectile_before_damage() -> None:
    env = _paused_campaign_env()
    env.enemies = [
        Enemy(
            uid="enemy_test",
            row=0,
            x=float(env.config.grid_origin_x + env.config.cell_size * 3),
            y=float(env.config.grid_origin_y + (env.config.cell_size - env.config.enemy_height) / 2),
            hp=90.0,
            max_hp=90.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=1,
            enemy_type="normal",
        )
    ]
    env.towers = [Tower(uid="pea", row=0, col=0, plant_type="pea_shooter", tower_type="pea_shooter", width=52, height=52)]

    before_hp = env.enemies[0].hp
    env.advance_world(0.1)
    assert env.enemies[0].hp == before_hp
    assert len(env.projectiles) == 1

    env.advance_world(1.0)
    assert len(env.projectiles) == 0
    assert env.enemies[0].hp < before_hp


def test_campaign_v4_non_checkpoint_wave_skips_upgrade() -> None:
    env = TowerDefenseEnv(build_campaign_v4_config(seed=SEED))
    env.current_wave = env.wave_manager.waves[0]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 0
    env.wave_manager.pending_spawns = []
    env.wave_state = "active"
    env.enemies = []
    _arm_wave_advance_ready(env)

    env._resolve_wave_progression()

    assert env.wave_state == "active"
    assert env.wave_id == 2
    assert env.pending_upgrade_options == []


def test_campaign_v4_checkpoint_wave_enters_upgrade() -> None:
    env = TowerDefenseEnv(build_campaign_v4_config(seed=SEED))
    env.current_wave = env.wave_manager.waves[3]
    env.wave_manager.current_wave = env.current_wave
    env.wave_manager.current_wave_index = 3
    env.wave_manager.pending_spawns = []
    env.wave_state = "active"
    env.enemies = []
    env.waves_cleared = 3
    _arm_wave_advance_ready(env)

    env._resolve_wave_progression()

    assert env.wave_state == "upgrade"
    assert len(env.pending_upgrade_options) == 3


def _campaign_manager(seed: int) -> WaveManager:
    manager = WaveManager(build_campaign_v4_config(seed=seed))
    manager.reset(seed)
    return manager


def _spawn_type_counts(wave) -> Counter[str]:
    return Counter(spawn.enemy_type_id for spawn in wave.spawns)


def test_campaign_v4_has_twenty_waves_and_five_checkpoints() -> None:
    manager = _campaign_manager(SEED)
    assert len(manager.waves) == 20
    checkpoint_ids = {wave.wave_id for wave in manager.waves if wave.checkpoint_upgrade}
    assert checkpoint_ids == {4, 8, 12, 16, 19}


def test_campaign_v4_w4_to_w6_total_counts() -> None:
    for seed in range(30):
        manager = _campaign_manager(seed)
        for wave in manager.waves[3:6]:
            total = wave.enemy_count
            assert 1 <= total <= 2, f"wave {wave.wave_id} total {total} out of range for seed {seed}"


def test_campaign_v4_w10_includes_fixed_pole_and_normal() -> None:
    manager = _campaign_manager(SEED)
    wave = manager.waves[9]
    counts = _spawn_type_counts(wave)
    assert counts["normal"] >= 5
    assert counts["pole_vaulting"] >= 2
    assert 10 <= wave.enemy_count <= 12


def test_campaign_v4_w20_fixed_recipe() -> None:
    manager = _campaign_manager(SEED)
    wave = manager.waves[19]
    counts = _spawn_type_counts(wave)
    assert counts["normal"] == 12
    assert counts["pole_vaulting"] == 7
    assert counts["buckethead"] == 6
    assert wave.enemy_count == 25
    assert wave.random_slots == 0


def test_campaign_v4_lane_balance_constraints() -> None:
    manager = _campaign_manager(SEED)
    for wave in manager.waves:
        rows = [spawn.row for spawn in wave.spawns]
        if not rows:
            continue
        row_counts = Counter(rows)
        count_gap = max(row_counts.values()) - min(row_counts.values())
        limit = 1 if wave.enemy_count <= 10 else 2
        assert count_gap <= limit, f"wave {wave.wave_id} count gap {count_gap} exceeds {limit}"

        threat_by_row = [0.0 for _ in range(manager.config.grid_rows)]
        weights = manager.config.lane_threat_weights
        for spawn in wave.spawns:
            threat_by_row[spawn.row] += float(weights.get(spawn.enemy_type_id, weights["normal"]))
        threat_gap = max(threat_by_row) - min(threat_by_row)
        threat_limit = 3.5 if wave.wave_id == 20 else 2.5
        assert threat_gap <= threat_limit + 0.01, f"wave {wave.wave_id} threat gap {threat_gap} exceeds {threat_limit}"


def test_campaign_v4_w20_spreads_bucketheads() -> None:
    manager = _campaign_manager(SEED)
    wave = manager.waves[19]
    bucket_rows = {spawn.row for spawn in wave.spawns if spawn.enemy_type_id == "buckethead"}
    assert len(bucket_rows) >= 4, "bucketheads should spread across multiple lanes"


def test_campaign_v4_shovel_removes_plant_and_projectiles() -> None:
    env = _paused_campaign_env()
    env.wave_state = "active"
    env.towers = [
        Tower(uid="pea", row=0, col=0, plant_type="pea_shooter", tower_type="pea_shooter", width=52, height=52)
    ]
    env.projectiles = [
        Projectile(
            uid="p1",
            row=0,
            x=100.0,
            y=100.0,
            speed=360.0,
            damage=20,
            source_tower_id="pea",
        )
    ]

    assert env.remove_tower_at(0, 0) is True
    assert len(env.towers) == 0
    assert len(env.projectiles) == 0
    assert env.shovel_cooldown_left > 0.0
    assert env.remove_tower_at(0, 0) is False


def test_campaign_v4_can_place_plant_on_enemy_cell_but_not_on_existing_plant() -> None:
    env = _paused_campaign_env()
    row, col = 0, 3
    enemy_x = float(env.config.grid_origin_x + col * env.config.cell_size + 8)
    env.enemies = [
        Enemy(
            uid="enemy_lane",
            row=row,
            x=enemy_x,
            y=float(env.config.grid_origin_y + (env.config.cell_size - env.config.enemy_height) / 2),
            hp=90.0,
            max_hp=90.0,
            speed=0.0,
            width=env.config.enemy_width,
            height=env.config.enemy_height,
            reward_score=1,
            enemy_type="normal",
        )
    ]
    assert env.has_tower_at_cell(row, col) is False
    assert env.is_cell_occupied(row, col) is False

    env.resources = 500
    env.card_cooldowns = {plant_type: 0.0 for plant_type in ("pea_shooter", "sunflower", "wallnut")}
    place_on_zombie = env.apply_action(
        action_dict_to_id(
            {
                "action_type": "place_tower",
                "plant_type": "wallnut",
                "row": row,
                "col": col,
            }
        )
    )
    assert place_on_zombie is True
    assert env.has_tower_at_cell(row, col) is True
    assert len(env.towers) == 1
    assert len(env.enemies) == 1

    duplicate = env.apply_action(
        action_dict_to_id(
            {
                "action_type": "place_tower",
                "plant_type": "pea_shooter",
                "row": row,
                "col": col,
            }
        )
    )
    assert duplicate is False
    assert env.last_action_info.get("reason") == "CELL_OCCUPIED"
    assert len(env.towers) == 1


def test_campaign_v4_has_no_playable_time_limit() -> None:
    env = TowerDefenseEnv(build_campaign_v4_config(seed=SEED))
    assert env.config.game_duration <= 0.0

    env.advance_world(200.0)
    assert env.is_done() is False
    assert env.game_time > 180.0


def test_campaign_v4_render_state_handles_empty_entity_lists() -> None:
    env = TowerDefenseEnv(build_campaign_v4_config(seed=SEED))
    env.projectiles = []
    env.sun_drops = []
    state = env.get_render_state()
    assert state.get("projectiles") == []
    assert state.get("sun_drops") == []
    assert len(state.get("lane_pressure") or []) == env.config.grid_rows


if __name__ == "__main__":
    tests = [
        test_campaign_v4_manual_mode_keeps_bonus_sun_clickable,
        test_campaign_v4_ai_mode_auto_collects_bonus_sun,
        test_campaign_v4_first_enemy_waits_for_opening_grace,
        test_campaign_v4_pea_shooter_fires_projectile_before_damage,
        test_campaign_v4_non_checkpoint_wave_skips_upgrade,
        test_campaign_v4_checkpoint_wave_enters_upgrade,
        test_campaign_v4_has_twenty_waves_and_five_checkpoints,
        test_campaign_v4_w4_to_w6_total_counts,
        test_campaign_v4_w10_includes_fixed_pole_and_normal,
        test_campaign_v4_w20_fixed_recipe,
        test_campaign_v4_lane_balance_constraints,
        test_campaign_v4_w20_spreads_bucketheads,
        test_campaign_v4_shovel_removes_plant_and_projectiles,
        test_campaign_v4_can_place_plant_on_enemy_cell_but_not_on_existing_plant,
        test_campaign_v4_has_no_playable_time_limit,
        test_campaign_v4_render_state_handles_empty_entity_lists,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
