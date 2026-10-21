from __future__ import annotations

from config import build_campaign_v5_config
from enemy import Enemy
from env import Projectile, TowerDefenseEnv
from tower import Tower


SEED = 42


class _FixedRandom:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def random(self) -> float:
        return self.value


def _paused_campaign_env() -> TowerDefenseEnv:
    env = TowerDefenseEnv(build_campaign_v5_config(seed=SEED))
    env.wave_state = "waiting"
    env.current_wave = None
    env.pending_wave_spawns = []
    env.wave_manager.finish_current_wave()
    return env


def _pea_tower(env: TowerDefenseEnv) -> Tower:
    tower = Tower(
        uid="pea_test",
        row=0,
        col=0,
        plant_type="pea_shooter",
        tower_type="pea_shooter",
        width=env.config.tower_width,
        height=env.config.tower_height,
    )
    env._sync_tower_stats(tower, preserve_ratio=False)
    return tower


def _enemy(env: TowerDefenseEnv, *, hp: float = 270.0, row: int = 0) -> Enemy:
    return Enemy(
        uid="enemy_test",
        row=row,
        x=float(env.config.grid_origin_x + env.config.cell_size * 4),
        y=float(env.config.grid_origin_y + (env.config.cell_size - env.config.enemy_height) / 2),
        hp=hp,
        max_hp=max(hp, 270.0),
        speed=16.0,
        width=env.config.enemy_width,
        height=env.config.enemy_height,
        reward_score=10,
        enemy_type="normal",
    )


def test_pea_shooter_base_damage_is_twenty() -> None:
    env = _paused_campaign_env()
    tower = _pea_tower(env)
    assert env._tower_damage(tower) == 20


def test_roll_pea_type_ice_at_fifteen_percent_threshold() -> None:
    env = _paused_campaign_env()
    tower = _pea_tower(env)
    env.random = _FixedRandom(0.0)
    assert env._roll_pea_type(tower) == "ice"
    env.random = _FixedRandom(0.14)
    assert env._roll_pea_type(tower) == "ice"
    env.random = _FixedRandom(0.15)
    assert env._roll_pea_type(tower) == "normal"


def test_ice_projectile_applies_slow_and_halves_move_speed() -> None:
    env = _paused_campaign_env()
    enemy = _enemy(env)
    projectile = Projectile(
        uid="proj_ice",
        row=0,
        x=0.0,
        y=0.0,
        speed=360.0,
        damage=20,
        source_tower_id="pea_test",
        pea_type="ice",
    )

    env._apply_projectile_hit(enemy, projectile)

    assert enemy.slow_timer == 8.0
    assert enemy._slow_ratio == 0.5
    assert enemy.get_current_speed() == 8.0


def test_ice_projectile_still_applies_slow_on_lethal_hit() -> None:
    env = _paused_campaign_env()
    enemy = _enemy(env, hp=10.0)
    projectile = Projectile(
        uid="proj_ice_kill",
        row=0,
        x=0.0,
        y=0.0,
        speed=360.0,
        damage=20,
        source_tower_id="pea_test",
        pea_type="ice",
    )

    dead = env._apply_projectile_hit(enemy, projectile)

    assert dead is True
    assert enemy.slow_timer == 8.0
    assert enemy._slow_ratio == 0.5


def test_slow_halves_attack_cooldown_recovery() -> None:
    enemy = Enemy(
        uid="slow_attack",
        row=0,
        x=100.0,
        y=100.0,
        hp=100.0,
        max_hp=100.0,
        speed=16.0,
        width=28,
        height=36,
        reward_score=10,
        attack_cooldown_left=1.0,
    )
    enemy.apply_slow(10.0, 0.5)
    enemy.tick(1.0)
    assert enemy.attack_cooldown_left == 0.5


def test_campaign_spawns_ice_projectile_with_forced_roll() -> None:
    env = _paused_campaign_env()
    env.towers = [_pea_tower(env)]
    env.enemies = [_enemy(env)]
    env.random = _FixedRandom(0.0)

    env._resolve_tower_attacks()

    assert len(env.projectiles) == 1
    assert env.projectiles[0].pea_type == "ice"
    assert env.projectiles[0].damage == 20


if __name__ == "__main__":
    tests = [
        test_pea_shooter_base_damage_is_twenty,
        test_roll_pea_type_ice_at_fifteen_percent_threshold,
        test_ice_projectile_applies_slow_and_halves_move_speed,
        test_ice_projectile_still_applies_slow_on_lethal_hit,
        test_slow_halves_attack_cooldown_recovery,
        test_campaign_spawns_ice_projectile_with_forced_roll,
    ]
    for test in tests:
        test()
        print(f"[PASS] {test.__name__}")
